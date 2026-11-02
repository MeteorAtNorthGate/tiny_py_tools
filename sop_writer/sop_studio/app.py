"""Main desktop workflow: capture, compose, persist, export."""
from __future__ import annotations

import logging
import sys
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QImageReader, QKeySequence, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QInputDialog, QKeySequenceEdit, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QToolBar, QVBoxLayout, QWidget,
)

from .annotations import AnnotationWindow
from .canvas import CanvasView
from .capture import GlobalHotkey, SystemCapture
from .controller import DocumentController
from .document import Document, Element, Page, load_document, new_id, save_document
from .inspector_controls import ChoiceInput, ColorInput, FontPicker, IntegerInput, NumberInput
from .rendering import export_pdf, image_bytes, thumbnail
from .style import apply_style


class PageSizeDialog(QDialog):
    def __init__(self, width=960, height=1360, parent=None, title="页面尺寸"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)
        hint = QLabel("以像素定义页面。导出 PDF 时按 96 DPI 换算。")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)
        form = QFormLayout()
        preset = QComboBox()
        preset.addItems(["自定义", "SOP 标准 · 960 × 1360", "A4 比例 · 794 × 1123", "高清 · 1440 × 2040", "横向 · 1360 × 960"])
        form.addRow("预设", preset)
        self.width_input = QSpinBox()
        self.height_input = QSpinBox()
        for spin, value in [(self.width_input, width), (self.height_input, height)]:
            spin.setRange(160, 12000)
            spin.setSuffix(" px")
            spin.setValue(value)
        form.addRow("宽度", self.width_input)
        form.addRow("高度", self.height_input)
        sizes = [(width, height), (960, 1360), (794, 1123), (1440, 2040), (1360, 960)]
        preset.currentIndexChanged.connect(lambda i: (self.width_input.setValue(sizes[i][0]), self.height_input.setValue(sizes[i][1])))
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def dimensions(self):
        return self.width_input.value(), self.height_input.value()


class MainWindow(QMainWindow):
    def __init__(self, test_mode=False):
        super().__init__()
        self.test_mode = test_mode
        self.settings = QSettings("LocalTools", "SOPStudio")
        self.controller = DocumentController(self)
        self.filename = None
        self.active_page_id = self.controller.document.pages[0].id
        self.next_selected = None
        self.refresh_pending = False
        self.updating_inspector = False
        self.annotation = None
        self.capture_busy = False
        self.capture_restore_owned = False
        self.capture_restore_visible = True
        self.capture_restore_minimized = False
        self.pending_snips = []
        self.closing = False
        self.auto_receive_snips = self.settings.value("receive_system_snips", True, type=bool)
        self.element_clipboard = None
        self.resize(1480, 940)
        self.setMinimumSize(1120, 720)
        self.setWindowTitle("SOP Studio")
        self.setWindowIcon(self.make_icon())
        self.build_ui()
        self.build_menus()
        self.controller.changed.connect(self.schedule_refresh)
        self.controller.undo_stack.cleanChanged.connect(self.update_title)
        self.refresh()
        self.hotkey = GlobalHotkey(self)
        self.hotkey.triggered.connect(self.start_capture)
        self.system_capture = SystemCapture(self, native=not test_mode)
        self.system_capture.shortcut_detected.connect(self.external_capture)
        self.system_capture.image_ready.connect(self.captured)
        self.system_capture.cancelled.connect(self.cancel_capture)
        self.system_capture.failed.connect(self.capture_failed)
        if not test_mode:
            sequence = self.settings.value("capture_hotkey", "Ctrl+1")
            try:
                registered = self.hotkey.register(sequence)
            except ValueError:
                sequence = "Ctrl+1"
                registered = self.hotkey.register(sequence)
            self.capture_shortcut = sequence
            self.capture_button.setText(f"系统截图  {sequence}")
            if not registered:
                self.statusBar().showMessage(f"{sequence} 被占用，点击“截图”仍可使用；在“设置”中更换快捷键。", 18000)
            saved_geometry = self.settings.value("window_geometry")
            if saved_geometry:
                self.restoreGeometry(saved_geometry)
        else:
            self.capture_shortcut = "Ctrl+1"
        self.system_capture.start()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30000)
        self.autosave_timer.timeout.connect(self.autosave)
        if not test_mode:
            self.autosave_timer.start()
            QTimer.singleShot(100, self.offer_recovery)
        QTimer.singleShot(0, lambda: self.canvas.fit_width(self.active_page_id))

    @staticmethod
    def make_icon():
        image = QImage(64, 64, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor("#416fe8"))
        from PySide6.QtGui import QPainter
        painter = QPainter(image)
        painter.setPen(QColor("white"))
        font = QFont("Segoe UI", 28, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "S")
        painter.end()
        return QIcon(QPixmap.fromImage(image))

    def button(self, text, callback, primary=False):
        button = QPushButton(text)
        button.clicked.connect(lambda checked=False: callback())
        if primary:
            button.setObjectName("primary")
        return button

    def build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget()
        header.setObjectName("header")
        top = QHBoxLayout(header)
        top.setContentsMargins(20, 14, 20, 14)
        top.setSpacing(12)
        brand = QLabel("SOP STUDIO")
        brand.setObjectName("brand")
        top.addWidget(brand)
        divider = QLabel(" / ")
        divider.setObjectName("muted")
        top.addWidget(divider)
        self.title_input = QLineEdit("未命名 SOP")
        self.title_input.setObjectName("documentTitle")
        self.title_input.setMinimumWidth(140)
        self.title_input.setMaximumWidth(310)
        self.title_input.editingFinished.connect(self.rename_document)
        top.addWidget(self.title_input)
        self.save_status = QLabel("尚未保存")
        self.save_status.setObjectName("saved")
        top.addWidget(self.save_status)
        top.addStretch()
        top.addWidget(self.button("保存", self.save))
        self.capture_button = self.button("系统截图  Ctrl+1", self.start_capture, True)
        self.capture_button.setToolTip("打开 Windows 截图；也可直接按 Win+Shift+S，完成后自动进入标注。")
        top.addWidget(self.capture_button)
        top.addWidget(self.button("导出 PDF", self.export))
        root.addWidget(header)
        toolbar = QToolBar()
        toolbar.setMovable(False)
        for label, callback in [("＋ 图片", self.import_images), ("T  文本框", self.add_text), ("＋ 页面", self.add_page), ("页面尺寸", self.resize_page)]:
            action = toolbar.addAction(label)
            action.triggered.connect(lambda checked=False, cb=callback: cb())
        toolbar.addSeparator()
        toolbar.addAction("撤销", self.undo)
        toolbar.addAction("重做", self.redo)
        toolbar.addSeparator()
        toolbar.addAction("适合宽度", lambda: self.canvas.fit_width(self.active_page_id))
        toolbar.addAction("−", lambda: self.canvas.set_zoom(self.canvas.zoom_percent - 10))
        self.zoom_label = QLabel("65%")
        self.zoom_label.setMinimumWidth(40)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.zoom_label)
        toolbar.addAction("＋", lambda: self.canvas.set_zoom(self.canvas.zoom_percent + 10))
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Policy.Expanding, spacer.sizePolicy().Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addWidget(QLabel("拖入图片 · 双击编辑 · Ctrl + 滚轮缩放"))
        root.addWidget(toolbar)
        splitter = QSplitter()
        splitter.setHandleWidth(1)
        left = QWidget()
        left.setObjectName("sidebar")
        left.setMinimumWidth(160)
        left.setMaximumWidth(230)
        sidebar = QVBoxLayout(left)
        sidebar.setContentsMargins(10, 4, 10, 12)
        label = QLabel("文档页面")
        label.setObjectName("section")
        sidebar.addWidget(label)
        self.page_list = QListWidget()
        self.page_list.setIconSize(QSize(120, 170))
        self.page_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.page_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.page_list.setMovement(QListWidget.Movement.Static)
        self.page_list.setWordWrap(True)
        self.page_list.setSpacing(2)
        self.page_list.currentRowChanged.connect(self.page_selected)
        sidebar.addWidget(self.page_list, 1)
        sidebar.addWidget(self.button("＋ 添加页面", self.add_page))
        splitter.addWidget(left)
        self.canvas = CanvasView(self.controller)
        self.canvas.selected.connect(self.inspect_element)
        self.canvas.page_activated.connect(self.activate_page)
        self.canvas.annotate_requested.connect(self.annotate_element)
        self.canvas.zoom_changed.connect(lambda percent: self.zoom_label.setText(f"{percent}%"))
        self.canvas.image_dropped.connect(self.import_image_path)
        self.canvas.delete_requested.connect(self.delete_selected)
        self.canvas.nudge_requested.connect(self.nudge)
        splitter.addWidget(self.canvas)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setMinimumWidth(270)
        inspector_scroll.setMaximumWidth(320)
        inspector = QWidget()
        inspector.setObjectName("inspector")
        self.inspector_layout = QVBoxLayout(inspector)
        self.inspector_layout.setContentsMargins(18, 4, 18, 18)
        self.inspector_layout.setSpacing(10)
        self.section("当前页面")
        self.page_info = QLabel()
        self.inspector_layout.addWidget(self.page_info)
        self.inspector_layout.addWidget(self.button("修改页面尺寸", self.resize_page))
        page_tools = QHBoxLayout()
        page_tools.addWidget(self.button("复制页", self.duplicate_page))
        page_tools.addWidget(self.button("删除页", self.delete_page))
        self.inspector_layout.addLayout(page_tools)
        page_order = QHBoxLayout()
        page_order.addWidget(self.button("上移页", lambda: self.move_page(-1)))
        page_order.addWidget(self.button("下移页", lambda: self.move_page(1)))
        self.inspector_layout.addLayout(page_order)
        self.section("所选元素")
        self.selection_hint = QLabel("选择图片或文本框来调整属性。")
        self.selection_hint.setWordWrap(True)
        self.selection_hint.setObjectName("muted")
        self.inspector_layout.addWidget(self.selection_hint)
        self.element_panel = QWidget()
        panel = QVBoxLayout(self.element_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)
        self.geometry_inputs = {}
        for index, (name, label) in enumerate([("x", "X"), ("y", "Y"), ("width", "宽度"), ("height", "高度")]):
            spin = NumberInput()
            spin.setRange(0 if name in ("x", "y") else 8, 24000)
            spin.setDecimals(1)
            spin.setSuffix(" px")
            spin.editingFinished.connect(lambda field=name: self.apply_geometry(field))
            spin.setAccessibleName(label)
            self.geometry_inputs[name] = spin
            row, column = (index // 2) * 2, index % 2
            form.addWidget(QLabel(label), row, column)
            form.addWidget(spin, row + 1, column)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        panel.addLayout(form)
        self.lock_ratio = QCheckBox("缩放时锁定图片比例")
        self.lock_ratio.setChecked(True)
        panel.addWidget(self.lock_ratio)
        alignment = QHBoxLayout()
        alignment.addWidget(self.button("水平居中", self.center_selected))
        alignment.addWidget(self.button("铺满页宽", self.fit_selected))
        panel.addLayout(alignment)
        layers = QHBoxLayout()
        layers.addWidget(self.button("移到顶层", lambda: self.reorder_selected(True)))
        layers.addWidget(self.button("移到底层", lambda: self.reorder_selected(False)))
        panel.addLayout(layers)
        self.text_style = QWidget()
        text_form = QFormLayout(self.text_style)
        text_form.setContentsMargins(0, 8, 0, 0)
        text_form.setVerticalSpacing(8)
        text_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.font_family = FontPicker()
        self.font_family.currentFontChanged.connect(self.apply_font)
        text_form.addRow("字体", self.font_family)
        self.font_size = IntegerInput()
        self.font_size.setRange(6, 256)
        self.font_size.editingFinished.connect(self.apply_font)
        text_form.addRow("字号", self.font_size)
        self.bold = QCheckBox("加粗")
        self.bold.clicked.connect(self.apply_font)
        text_form.addRow("", self.bold)
        self.text_color_inputs = {}
        self.text_effect_inputs = {}

        def group(title):
            label = QLabel(title)
            label.setObjectName("propertyGroup")
            text_form.addRow(label)

        def color_field(field, label, title):
            control = ColorInput(title)
            control.valueChanged.connect(lambda value, key=field: self.apply_text_effect(key, value))
            self.text_color_inputs[field] = control
            text_form.addRow(label, control)

        def numeric_field(field, label, maximum, suffix, integer=False):
            control = IntegerInput() if integer else NumberInput()
            control.setRange(0, maximum)
            control.setSuffix(suffix)
            control.setAccessibleName(label)
            control.editingFinished.connect(lambda key=field, widget=control:
                                           self.apply_text_effect(key, widget.value() / 100 if key.endswith("opacity") else widget.value()))
            self.text_effect_inputs[field] = control
            text_form.addRow(label, control)

        group("文字")
        color_field("color", "颜色", "文本颜色")
        color_field("text_stroke_color", "描边", "文本描边颜色")
        numeric_field("text_stroke_width", "描边宽度", 50, " px")
        self.text_stroke_alignment = ChoiceInput()
        for title, value in [("向外", "outside"), ("居中", "center"), ("向内", "inside")]:
            self.text_stroke_alignment.addItem(title, value)
        self.text_stroke_alignment.currentIndexChanged.connect(lambda:
            self.apply_text_effect("text_stroke_alignment", self.text_stroke_alignment.currentData()))
        text_form.addRow("描边位置", self.text_stroke_alignment)
        numeric_field("text_opacity", "不透明度", 100, " %", integer=True)

        group("文本框")
        color_field("background", "填充", "文本框填充色")
        color_field("box_stroke_color", "描边", "文本框描边颜色")
        numeric_field("box_stroke_width", "描边宽度", 50, " px")
        numeric_field("box_opacity", "不透明度", 100, " %", integer=True)
        panel.addWidget(self.text_style)
        self.annotate_button = self.button("标注图片", lambda: self.annotate_element(self.canvas.selected_id()))
        panel.addWidget(self.annotate_button)
        self.inspector_layout.addWidget(self.element_panel)
        self.inspector_layout.addStretch()
        self.section("快速上手")
        help_text = QLabel("① Win+Shift+S 使用系统截图\n② 截图完成后自动打开标注窗\n③ Ctrl+Enter 插入文档\n\nCtrl+1 也可打开系统截图\nCtrl+Shift+V 标注剪贴板图片\n拖动元素移动位置\n拖右下角缩放，Shift 自由比例\nEnter / 双击文字编辑\nCtrl+Enter 完成文字编辑\nCtrl+J 复制元素，Delete 删除\n双击图片继续标注\n空格拖动或中键平移画布")
        help_text.setObjectName("muted")
        help_text.setWordWrap(True)
        self.inspector_layout.addWidget(help_text)
        inspector_scroll.setWidget(inspector)
        splitter.addWidget(inspector_scroll)
        splitter.setSizes([184, 1000, 296])
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("就绪 · 从截图、图片或一段说明开始。")
        self.page_count_label = QLabel()
        self.statusBar().addPermanentWidget(self.page_count_label)

    def section(self, text):
        label = QLabel(text)
        label.setObjectName("section")
        self.inspector_layout.addWidget(label)

    def action(self, menu, text, callback, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda checked=False: callback())
        menu.addAction(action)
        return action

    def build_menus(self):
        file_menu = self.menuBar().addMenu("文件")
        self.action(file_menu, "新建文档", self.new_document, "Ctrl+N")
        self.action(file_menu, "打开文档…", self.open_document, "Ctrl+O")
        file_menu.addSeparator()
        self.action(file_menu, "保存", self.save, "Ctrl+S")
        self.action(file_menu, "另存为…", self.save_as, "Ctrl+Shift+S")
        self.action(file_menu, "导出 PDF…", self.export, "Ctrl+E")
        file_menu.addSeparator()
        self.action(file_menu, "退出", self.close, "Alt+F4")
        edit = self.menuBar().addMenu("编辑")
        self.action(edit, "撤销", self.undo, "Ctrl+Z")
        redo = self.action(edit, "重做", self.redo)
        redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        edit.addSeparator()
        self.action(edit, "复制", self.copy_selected, "Ctrl+C")
        self.action(edit, "粘贴", self.paste, "Ctrl+V")
        self.action(edit, "复制元素", self.duplicate_selected, "Ctrl+J")
        insert = self.menuBar().addMenu("插入")
        self.action(insert, "Windows 系统截图", self.start_capture)
        self.action(insert, "标注剪贴板图片", self.annotate_clipboard, "Ctrl+Shift+V")
        self.action(insert, "图片…", self.import_images, "Ctrl+Shift+I")
        self.action(insert, "文本框", self.add_text, "Ctrl+Alt+T")
        self.action(insert, "新页面", self.add_page, "Ctrl+Shift+Return")
        settings = self.menuBar().addMenu("设置")
        self.action(settings, "截图快捷键…", self.change_hotkey)
        receive = QAction("自动接收 Win+Shift+S 截图", self)
        receive.setCheckable(True)
        receive.setChecked(self.auto_receive_snips)
        receive.toggled.connect(self.set_auto_receive_snips)
        settings.addAction(receive)
        help_menu = self.menuBar().addMenu("帮助")
        self.action(help_menu, "使用说明", self.show_help)

    def schedule_refresh(self):
        if not self.refresh_pending:
            self.refresh_pending = True
            QTimer.singleShot(0, self.refresh)

    def refresh(self):
        self.refresh_pending = False
        document = self.controller.document
        if not any(page.id == self.active_page_id for page in document.pages):
            self.active_page_id = document.pages[0].id
        self.canvas.rebuild(self.next_selected)
        self.next_selected = None
        self.page_list.blockSignals(True)
        self.page_list.clear()
        for index, page in enumerate(document.pages):
            image = thumbnail(page, document.assets, 120)
            pixmap = QPixmap.fromImage(image)
            icon = QIcon(pixmap)
            icon.addPixmap(pixmap, QIcon.Mode.Selected)
            icon.addPixmap(pixmap, QIcon.Mode.Active)
            item = QListWidgetItem(icon, f"{index + 1:02d}   ·   {page.width} × {page.height}")
            item.setData(Qt.ItemDataRole.UserRole, page.id)
            item.setSizeHint(QSize(146, 207))
            self.page_list.addItem(item)
            if page.id == self.active_page_id:
                self.page_list.setCurrentItem(item)
        self.page_list.blockSignals(False)
        self.title_input.setText(document.title)
        self.page_count_label.setText(f"{len(document.pages)} 页    ·    {sum(len(p.elements) for p in document.pages)} 个元素    ")
        self.update_page_info()
        self.inspect_element(self.canvas.selected_id())
        self.update_title()

    def current_page(self):
        return next((p for p in self.controller.document.pages if p.id == self.active_page_id), self.controller.document.pages[0])

    def activate_page(self, page_id):
        self.active_page_id = page_id
        self.page_list.blockSignals(True)
        for index in range(self.page_list.count()):
            if self.page_list.item(index).data(Qt.ItemDataRole.UserRole) == page_id:
                self.page_list.setCurrentRow(index)
                break
        self.page_list.blockSignals(False)
        self.update_page_info()

    def page_selected(self, index):
        if index < 0:
            return
        self.active_page_id = self.page_list.item(index).data(Qt.ItemDataRole.UserRole)
        self.canvas.go_to_page(self.active_page_id)
        self.update_page_info()

    def update_page_info(self):
        page = self.current_page()
        index = self.controller.document.pages.index(page) + 1
        self.page_info.setText(f"第 {index} 页\n{page.width} × {page.height} px")

    def inspect_element(self, element_id):
        found = self.controller.document.find(element_id)
        self.element_panel.setVisible(bool(found))
        self.selection_hint.setVisible(not bool(found))
        if not found:
            return
        page, element = found
        self.activate_page(page.id)
        self.updating_inspector = True
        for key, spin in self.geometry_inputs.items():
            spin.setValue(getattr(element, key))
        self.lock_ratio.setVisible(element.kind == "image")
        self.text_style.setVisible(element.kind == "text")
        self.annotate_button.setVisible(element.kind == "image")
        self.font_family.setCurrentFont(QFont(element.font_family))
        self.font_size.setValue(element.font_size)
        self.bold.setChecked(element.bold)
        for field, control in self.text_color_inputs.items():
            control.setValue(getattr(element, field))
        for field, control in self.text_effect_inputs.items():
            value = getattr(element, field)
            control.setValue(round(value * 100) if field.endswith("opacity") else value)
        self.text_stroke_alignment.setCurrentIndex(self.text_stroke_alignment.findData(element.text_stroke_alignment))
        self.updating_inspector = False

    def selected(self):
        return self.controller.document.find(self.canvas.selected_id())

    def undo(self):
        editing = self.canvas.editing_item()
        if editing:
            editing.text_item.document().undo()
        else:
            self.controller.undo_stack.undo()

    def redo(self):
        editing = self.canvas.editing_item()
        if editing:
            editing.text_item.document().redo()
        else:
            self.controller.undo_stack.redo()

    def mutate_selected(self, label, mutation):
        element_id = self.canvas.selected_id()
        self.canvas.finish_edit()
        if not self.controller.document.find(element_id):
            return

        def apply(document):
            found = document.find(element_id)
            if found:
                mutation(*found)

        self.controller.perform(label, apply)

    def apply_geometry(self, field):
        if self.updating_inspector:
            return
        value = self.geometry_inputs[field].value()

        def change(page, element):
            if element.kind == "image" and self.lock_ratio.isChecked():
                if field == "width":
                    element.height = max(8, min(24000, element.height * value / element.width))
                elif field == "height":
                    element.width = max(8, min(24000, element.width * value / element.height))
            setattr(element, field, value)

        self.mutate_selected("调整元素属性", change)

    def apply_font(self, *args):
        if self.updating_inspector:
            return
        family, size, bold = self.font_family.currentFont().family(), self.font_size.value(), self.bold.isChecked()

        def change(page, element):
            element.font_family, element.font_size, element.bold = family, size, bold
            from .rendering import make_text_document
            element.height = max(element.height, make_text_document(element).size().height())

        self.mutate_selected("调整文字样式", change)

    def apply_text_effect(self, field, value):
        if self.updating_inspector:
            return

        def change(page, element):
            if element.kind != "text":
                return
            setattr(element, field, value)
            from .rendering import make_text_document
            element.height = max(element.height, make_text_document(element).size().height())

        self.mutate_selected("调整文字外观", change)

    def center_selected(self):
        self.mutate_selected("水平居中", lambda p, e: setattr(e, "x", max(0, (p.width - e.width) / 2)))

    def fit_selected(self):
        def change(page, element):
            width = page.width - 96
            if element.kind == "image":
                element.height = max(8, element.height * width / element.width)
            element.x, element.width = 48, width
        self.mutate_selected("适合页宽", change)

    def reorder_selected(self, top):
        def change(page, element):
            page.elements.remove(element)
            page.elements.insert(len(page.elements) if top else 0, element)
        self.mutate_selected("调整图层", change)

    def nudge(self, dx, dy):
        def change(page, element):
            element.x = max(0, min(page.width - 24, element.x + dx))
            element.y = max(0, min(page.height - 24, element.y + dy))
        self.mutate_selected("微调位置", change)

    def delete_selected(self):
        if self.canvas.editing_item():
            return
        self.mutate_selected("删除元素", lambda page, element: page.elements.remove(element))

    def duplicate_selected(self):
        self.canvas.finish_edit()
        found = self.selected()
        if not found:
            return
        page_id = found[0].id
        element = deepcopy(found[1])
        element.id = new_id()
        element.x += 24
        element.y += 24
        self.next_selected = element.id
        self.controller.perform("复制元素", lambda d: next(p for p in d.pages if p.id == page_id).elements.append(element))

    def copy_selected(self):
        editing = self.canvas.editing_item()
        if editing:
            QApplication.clipboard().setText(editing.text_item.textCursor().selectedText().replace("\u2029", "\n"))
            return
        found = self.selected()
        if found:
            element = deepcopy(found[1])
            asset = self.controller.document.assets.get(element.asset)
            self.element_clipboard = (element, asset)
            from PySide6.QtCore import QMimeData
            mime = QMimeData()
            mime.setData("application/x-sop-studio-element", element.id.encode())
            if element.kind == "image" and asset:
                mime.setImageData(QImage.fromData(asset))
            else:
                mime.setText(element.text)
            QApplication.clipboard().setMimeData(mime)
            self.statusBar().showMessage("已复制元素。", 2500)

    def paste(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        editing = self.canvas.editing_item()
        if editing:
            cursor = editing.text_item.textCursor()
            cursor.insertText(clipboard.text())
            return
        self.canvas.finish_edit()
        if mime.hasFormat("application/x-sop-studio-element") and self.element_clipboard:
            element, asset = deepcopy(self.element_clipboard)
            element.id = new_id()
            element.x += 24
            element.y += 24
            page_id = self.active_page_id
            self.next_selected = element.id

            def apply(document):
                if asset:
                    element.asset = document.add_asset(asset)
                next(p for p in document.pages if p.id == page_id).elements.append(element)

            self.controller.perform("粘贴元素", apply)
        elif mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                self.insert_image(image)
        elif mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self.import_image_path(url.toLocalFile())
        elif mime.hasText() and clipboard.text().strip():
            self.add_text(clipboard.text())

    def add_text(self, text=None):
        self.canvas.finish_edit()
        page = self.current_page()
        y = self.insertion_y(page, 100)
        element = Element(text=text or "在这里输入步骤说明…", x=48, y=y, width=page.width - 96, height=90)
        page_id = page.id
        self.next_selected = element.id
        self.controller.perform("添加文本框", lambda d: next(p for p in d.pages if p.id == page_id).elements.append(element))
        if text is None:
            QTimer.singleShot(0, lambda: self.begin_new_text(element.id))

    def begin_new_text(self, element_id):
        item = self.canvas.items_by_id.get(element_id)
        if item:
            self.canvas.setFocus()
            item.start_text_edit()
            cursor = item.text_item.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            item.text_item.setTextCursor(cursor)

    @staticmethod
    def insertion_y(page, height):
        bottom = max((e.y + e.height for e in page.elements), default=24)
        return max(24, min(bottom + 24, page.height - min(height, page.height - 48) - 24))

    def import_images(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "插入图片", self.settings.value("image_directory", ""),
                                               "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tif *.tiff);;所有文件 (*)")
        for path in paths:
            self.import_image_path(path)

    def import_image_path(self, path):
        self.canvas.finish_edit()
        try:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            if reader.size().width() * reader.size().height() > 100_000_000:
                raise ValueError("图片超过 1 亿像素，请缩小后再导入。")
            image = reader.read()
            if image.isNull():
                raise ValueError(f"无法读取图片：{reader.errorString()}")
            self.insert_image(image)
            if not self.test_mode:
                self.settings.setValue("image_directory", str(Path(path).parent))
        except (OSError, ValueError) as error:
            self.error("导入失败", error)

    def insert_image(self, image: QImage):
        if image.isNull():
            return
        self.canvas.finish_edit()
        page = self.current_page()
        width = min(image.width(), page.width - 96)
        height = image.height() * width / image.width()
        if height > page.height - 96:
            width *= (page.height - 96) / height
            height = page.height - 96
        next_y = max((e.y + e.height for e in page.elements), default=24) + 24
        # Long capture sessions flow into new pages instead of covering previous steps.
        needs_page = bool(page.elements) and next_y + height > page.height - 32
        page_id = page.id
        new_page = Page(width=page.width, height=page.height) if needs_page else None
        if new_page:
            page_id = new_page.id
        y = 48 if new_page else self.insertion_y(page, height)
        element = Element(kind="image", x=(page.width - width) / 2, y=y, width=width, height=height)
        png = image_bytes(image)
        self.next_selected = element.id
        self.active_page_id = page_id

        def insert(document):
            if new_page:
                index = next(i for i, p in enumerate(document.pages) if p.id == page.id)
                document.pages.insert(index + 1, new_page)
            element.asset = document.add_asset(png)
            next(p for p in document.pages if p.id == page_id).elements.append(element)

        self.controller.perform("插入图片", insert)
        QTimer.singleShot(0, lambda: self.canvas.go_to_page(page_id))

    def add_page(self):
        self.canvas.finish_edit()
        page = self.current_page()
        if len(self.controller.document.pages) >= 200:
            self.error("无法添加", "最多支持 200 页。")
            return
        new_page = Page(width=page.width, height=page.height)
        self.active_page_id = new_page.id

        def insert(document):
            index = next(i for i, p in enumerate(document.pages) if p.id == page.id)
            document.pages.insert(index + 1, new_page)

        self.next_selected = ""
        self.controller.perform("添加页面", insert)
        QTimer.singleShot(0, lambda: self.canvas.go_to_page(new_page.id))

    def resize_page(self):
        self.canvas.finish_edit()
        page = self.current_page()
        dialog = PageSizeDialog(page.width, page.height, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            width, height = dialog.dimensions()
            page_id = page.id

            def apply(document):
                target = next(p for p in document.pages if p.id == page_id)
                target.width, target.height = width, height

            self.controller.perform("修改页面尺寸", apply)
            QTimer.singleShot(0, lambda: self.canvas.fit_width(page_id))

    def duplicate_page(self):
        self.canvas.finish_edit()
        if len(self.controller.document.pages) >= 200:
            return
        current = self.current_page()
        page = deepcopy(current)
        page.id = new_id()
        for element in page.elements:
            element.id = new_id()
        self.active_page_id = page.id

        def insert(document):
            index = next(i for i, p in enumerate(document.pages) if p.id == current.id)
            document.pages.insert(index + 1, page)

        self.next_selected = ""
        self.controller.perform("复制页面", insert)
        QTimer.singleShot(0, lambda: self.canvas.go_to_page(page.id))

    def delete_page(self):
        self.canvas.finish_edit()
        page = self.current_page()
        if page.elements and QMessageBox.question(self, "删除页面", "删除当前页面及其中的所有元素？此操作可以撤销。") != QMessageBox.StandardButton.Yes:
            return

        def remove(document):
            if len(document.pages) == 1:
                document.pages[0].elements.clear()
            else:
                document.pages = [p for p in document.pages if p.id != page.id]

        self.next_selected = ""
        self.controller.perform("删除页面", remove)

    def move_page(self, direction):
        self.canvas.finish_edit()
        page_id = self.active_page_id

        def move(document):
            index = next(i for i, p in enumerate(document.pages) if p.id == page_id)
            destination = index + direction
            if 0 <= destination < len(document.pages):
                document.pages[index], document.pages[destination] = document.pages[destination], document.pages[index]

        self.controller.perform("调整页序", move)
        QTimer.singleShot(0, lambda: self.canvas.go_to_page(page_id))

    def start_capture(self):
        if self.capture_busy or QApplication.activeModalWidget():
            return
        if self.annotation is not None:
            self.annotation.raise_()
            self.annotation.activateWindow()
            return
        self.canvas.finish_edit()
        self.capture_busy = True
        self.capture_restore_visible = self.isVisible()
        self.capture_restore_minimized = self.isMinimized()
        self.capture_restore_owned = True
        self.hide()
        self.statusBar().showMessage("等待 Windows 截图完成；Esc 取消。", 60000)
        self.system_capture.request()

    def external_capture(self, baseline):
        if self.closing or not self.auto_receive_snips or self.system_capture.pending:
            return
        self.canvas.finish_edit()
        self.capture_busy = True
        self.statusBar().showMessage("已检测到 Win+Shift+S，等待截图写入剪贴板…", 60000)
        self.system_capture.arm(baseline)

    def set_auto_receive_snips(self, enabled):
        self.auto_receive_snips = enabled
        if not self.test_mode:
            self.settings.setValue("receive_system_snips", enabled)
        if not enabled and not self.capture_restore_owned:
            self.system_capture.cancel()

    def capture_failed(self, message):
        logging.warning("Windows screenshot integration: %s", message)
        self.statusBar().showMessage(f"{message}  可用 Ctrl+Shift+V 手动标注剪贴板图片。", 20000)

    def restore_after_capture(self):
        if not self.capture_restore_owned:
            return
        if self.capture_restore_minimized:
            self.showMinimized()
        elif self.capture_restore_visible:
            self.show()

    def cancel_capture(self, reason="cancelled"):
        self.capture_busy = False
        self.restore_after_capture()
        self.capture_restore_owned = False
        self.statusBar().showMessage("截图等待超时，可重新按 Win+Shift+S。" if reason == "timeout" else "已取消截图。", 5000)

    def captured(self, image):
        self.capture_busy = False
        self.pending_snips.append(image.copy())
        self.statusBar().showMessage("已接收系统截图。", 5000)
        self.open_next_snip()

    def open_next_snip(self):
        if self.closing or self.annotation is not None or not self.pending_snips:
            return
        if QApplication.activeModalWidget():
            QTimer.singleShot(200, self.open_next_snip)
            return
        self.open_annotation(self.pending_snips.pop(0))

    def annotate_clipboard(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            self.statusBar().showMessage("剪贴板中没有图片。请先用 Win+Shift+S 截图。", 7000)
            return
        self.system_capture.cancel()
        self.captured(image)

    def open_annotation(self, image, element_id=None):
        # An independent window remains visible even when the document is minimized.
        self.annotation = AnnotationWindow(image)
        self.annotation.image_ready.connect(lambda result: self.annotation_result(result, element_id))
        self.annotation.finished.connect(self.annotation_closed)
        self.annotation.show()
        self.annotation.raise_()
        self.annotation.activateWindow()

    def annotation_result(self, image, element_id=None):
        if element_id and self.controller.document.find(element_id):
            png = image_bytes(image)

            def replace(document):
                found = document.find(element_id)
                found[1].asset = document.add_asset(png)

            self.next_selected = element_id
            self.controller.perform("更新图片标注", replace)
        else:
            self.insert_image(image)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def annotation_closed(self, result):
        self.annotation = None
        if not self.isVisible():
            self.restore_after_capture()
        self.capture_restore_owned = False
        if self.pending_snips and not self.closing:
            QTimer.singleShot(0, self.open_next_snip)

    def annotate_element(self, element_id):
        if self.annotation is not None:
            self.annotation.raise_()
            return
        found = self.controller.document.find(element_id)
        if found and found[1].kind == "image":
            self.open_annotation(QImage.fromData(self.controller.document.assets[found[1].asset]), element_id)

    def change_hotkey(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("截图快捷键")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("点击下方并按下新的组合键："))
        editor = QKeySequenceEdit(QKeySequence(self.capture_shortcut))
        if hasattr(editor, "setMaximumSequenceLength"):
            editor.setMaximumSequenceLength(1)
        layout.addWidget(editor)
        label = QLabel("例如 Ctrl+1、Ctrl+Shift+2、Alt+F2。\n用于打开 Windows 系统截图。\nWin+Shift+S 由系统处理，无需在此设置。")
        label.setObjectName("muted")
        layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        sequence = editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        try:
            if not self.hotkey.register(sequence):
                raise ValueError("该快捷键被其他程序占用，请选择其他组合。")
        except ValueError as error:
            self.error("快捷键设置失败", error)
            return
        self.capture_shortcut = sequence
        self.settings.setValue("capture_hotkey", sequence)
        self.capture_button.setText(f"系统截图  {sequence}")
        self.statusBar().showMessage(f"截图快捷键已改为 {sequence}", 5000)

    def rename_document(self):
        title = self.title_input.text().strip()[:1000] or "未命名 SOP"
        self.controller.perform("修改文档名称", lambda d: setattr(d, "title", title))

    def update_title(self, *args):
        dirty = not self.controller.undo_stack.isClean()
        name = self.controller.document.title
        self.setWindowTitle(f"{'* ' if dirty else ''}{name} · SOP Studio")
        self.save_status.setText("有未保存更改" if dirty else ("已保存" if self.filename else "尚未保存"))

    def may_discard(self):
        self.canvas.finish_edit()
        if self.controller.undo_stack.isClean():
            return True
        result = QMessageBox.warning(self, "保存文档", "当前文档有未保存的更改。", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Save)
        if result == QMessageBox.StandardButton.Save:
            return self.save()
        return result == QMessageBox.StandardButton.Discard

    def new_document(self):
        if not self.may_discard():
            return
        dialog = PageSizeDialog(parent=self, title="新建 SOP 文档")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        width, height = dialog.dimensions()
        document = Document(pages=[Page(width=width, height=height)])
        self.filename = None
        self.active_page_id = document.pages[0].id
        self.controller.replace(document)
        self.clear_recovery()

    def open_document(self):
        if not self.may_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开 SOP 文档", self.settings.value("document_directory", ""), "SOP Studio 文档 (*.sopx)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            document = load_document(path)
            for asset in document.assets.values():
                if QImage.fromData(asset).isNull():
                    raise ValueError("文档包含无法读取的图片。")
            self.filename = str(path)
            self.active_page_id = document.pages[0].id
            self.next_selected = ""
            self.controller.replace(document)
            if not self.test_mode:
                self.settings.setValue("document_directory", str(Path(path).parent))
                self.clear_recovery()
            self.statusBar().showMessage(f"已打开 {path}", 6000)
            return True
        except (OSError, ValueError) as error:
            self.error("打开失败", error)
            return False

    def save(self):
        self.canvas.finish_edit()
        self.rename_document()
        if not self.filename:
            return self.save_as()
        return self.write_path(self.filename)

    def save_as(self):
        self.canvas.finish_edit()
        self.rename_document()
        default = self.filename or str(Path(self.settings.value("document_directory", "")) / self.safe_filename(self.controller.document.title))
        path, _ = QFileDialog.getSaveFileName(self, "保存 SOP 文档", default, "SOP Studio 文档 (*.sopx)")
        if not path:
            return False
        if not path.lower().endswith(".sopx"):
            path += ".sopx"
        return self.write_path(path)

    def write_path(self, path):
        try:
            save_document(self.controller.document, path)
            self.filename = str(path)
            self.controller.undo_stack.setClean()
            self.update_title()
            if not self.test_mode:
                self.settings.setValue("document_directory", str(Path(path).parent))
                self.clear_recovery()
            self.statusBar().showMessage(f"已保存 {path}", 6000)
            return True
        except (OSError, ValueError) as error:
            self.error("保存失败", error)
            return False

    @staticmethod
    def safe_filename(title):
        return "".join("_" if char in '<>:"/\\|?*' else char for char in title).strip(" .")[:100] or "未命名 SOP"

    def export(self):
        self.canvas.finish_edit()
        default = str(Path(self.filename).with_suffix(".pdf")) if self.filename else self.safe_filename(self.controller.document.title) + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", default, "PDF 文档 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            export_pdf(self.controller.document, path)
            self.statusBar().showMessage(f"已导出 {len(self.controller.document.pages)} 页 PDF：{path}", 12000)
        except (OSError, ValueError) as error:
            self.error("导出失败", error)

    def recovery_path(self):
        return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "recovery.sopx"

    def autosave(self):
        if self.controller.undo_stack.isClean() or self.capture_busy or self.canvas.editing_item():
            return
        try:
            self.canvas.finish_edit()
            path = self.recovery_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            save_document(self.controller.document, path)
        except (OSError, ValueError):
            logging.exception("Autosave failed")
            self.statusBar().showMessage("自动恢复副本保存失败，请手动保存文档。", 8000)

    def clear_recovery(self):
        if not self.test_mode:
            try:
                self.recovery_path().unlink(missing_ok=True)
            except OSError:
                logging.exception("Could not remove recovery copy")

    def offer_recovery(self):
        path = self.recovery_path()
        if not path.exists():
            return
        if QMessageBox.question(self, "恢复文档", "发现上次未正常退出时的恢复副本，是否恢复？") == QMessageBox.StandardButton.Yes:
            try:
                document = load_document(path)
                self.controller.replace(Document())
                self.controller.perform("恢复未保存文档", lambda d: (setattr(d, "title", document.title), setattr(d, "pages", document.pages), setattr(d, "assets", document.assets)))
                self.filename = None
                self.active_page_id = document.pages[0].id
            except (OSError, ValueError) as error:
                self.error("恢复失败", error)
        else:
            self.clear_recovery()

    def show_help(self):
        QMessageBox.information(self, "SOP Studio · 使用说明", "1. 直接按 Win+Shift+S，用 Windows 自带工具截图。\n2. 截图写入剪贴板后，自动打开本工具的悬浮标注窗。\n3. 选择箭头、文本框、马赛克或涂鸦，Ctrl+Enter 插入文档。\n4. 拖动元素，拖右下角缩放；双击文字或选中后按 Enter 编辑。\n5. 右栏直接输入精确数值，分别调整文字与文本框的颜色、描边和不透明度。\n6. 保存为 .sopx 可继续编辑，Ctrl+E 导出多页 PDF。\n\nCtrl+1 或截图按钮也会打开 Windows 截图。\nCtrl+Shift+V 可手动标注剪贴板图片。\n设置菜单可关闭自动接收、修改额外截图快捷键。\n\nCtrl+V 粘贴图片或文字；Ctrl+J 复制元素，Delete 删除。\n马赛克和标注插入后合并为图片；文档编辑仍可撤销。")

    def error(self, title, error):
        logging.error("%s: %s", title, error)
        if self.test_mode:
            raise RuntimeError(f"{title}: {error}")
        QMessageBox.warning(self, title, str(error))

    def closeEvent(self, event):
        if not self.test_mode and not self.may_discard():
            event.ignore()
            return
        self.autosave_timer.stop()
        self.closing = True
        self.system_capture.stop()
        self.hotkey.unregister()
        QApplication.instance().removeNativeEventFilter(self.hotkey)
        if self.annotation is not None:
            self.annotation.close()
        self.pending_snips.clear()
        if not self.test_mode:
            self.settings.setValue("window_geometry", self.saveGeometry())
            self.clear_recovery()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SOP Studio")
    app.setOrganizationName("LocalTools")
    apply_style(app)
    log_directory = Path(__file__).resolve().parent.parent / "logs"
    log_directory.mkdir(exist_ok=True)
    logging.basicConfig(filename=log_directory / "sop-studio.log", level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")

    def handle_exception(error_type, error, traceback):
        logging.critical("Unhandled error", exc_info=(error_type, error, traceback))
        QMessageBox.critical(None, "运行错误", f"{error}\n\n详细信息已记录在 logs/sop-studio.log。")

    sys.excepthook = handle_exception
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        QTimer.singleShot(200, lambda: window.load_path(sys.argv[1]))
    return app.exec()
