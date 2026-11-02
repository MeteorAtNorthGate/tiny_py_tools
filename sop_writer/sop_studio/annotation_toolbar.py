"""Compact annotation controls and the drag surface replacing a native title bar."""
from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QActionGroup, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QBoxLayout, QButtonGroup, QHBoxLayout, QLabel,
    QMenu, QPushButton, QSpinBox, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

from .annotation_icons import toolbar_icon
from .stroke_slider import StrokeSlider


class DragSurface(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if QApplication.platformName() not in ("offscreen", "minimal") and handle and handle.startSystemMove():
                event.accept()
                return
            self.drag_offset = event.globalPosition().toPoint() - self.window().pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "drag_offset"):
            self.window().move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, "drag_offset"):
            del self.drag_offset
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().fit_to_screen()
            event.accept()


class ColorSwatch(QAbstractButton):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(20, 28)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(color.upper())
        self.setAccessibleName(f"标注颜色 {color}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        if self.isChecked():
            painter.setPen(QPen(QColor("#6e7d94"), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, 8.9, 8.9)
        painter.setPen(QPen(QColor("#d5dde8"), .8) if self.color.lightness() > 230 else QPen(Qt.PenStyle.NoPen))
        painter.setBrush(self.color)
        painter.drawEllipse(center, 6, 6)


class AnnotationToolbar(DragSurface):
    tool_selected = Signal(str)
    color_selected = Signal(str)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setObjectName("annotationToolbar")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)
        self.main_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.main_layout.setSpacing(6)
        self.tools_group = QWidget()
        tools = QHBoxLayout(self.tools_group)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(2)
        grip = QLabel()
        grip.setPixmap(toolbar_icon("grip", "#a6afbf").pixmap(16, 24))
        grip.setFixedSize(18, 34)
        grip.setToolTip("拖动移动窗口；双击工具栏适应屏幕")
        grip.setCursor(Qt.CursorShape.SizeAllCursor)
        grip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        tools.addWidget(grip)
        self.group = QButtonGroup(self)
        self.tool_buttons = {}
        for label, name, key in [("选择", "select", "V"), ("矩形", "rectangle", "R"), ("箭头", "arrow", "A"), ("渐尖箭头", "tapered_arrow", "B"),
                                  ("涂鸦", "pen", "P"), ("文本框", "text", "T"), ("马赛克", "mosaic", "M")]:
            button = self.icon_button(name, f"{label}  ·  {key}")
            button.setAccessibleName(label)
            if name == "select":
                button.setToolTip("选择标记  ·  V\n单击标记选中，Delete / Backspace 删除")
            button.setCheckable(True)
            self.group.addButton(button)
            button.clicked.connect(lambda checked=False, tool=name: self.tool_selected.emit(tool))
            self.tool_buttons[name] = button
            tools.addWidget(button)
        tools.addSpacing(5)
        separator = QWidget()
        separator.setObjectName("annotationSeparator")
        separator.setFixedSize(1, 20)
        tools.addWidget(separator)
        tools.addSpacing(5)
        self.undo_button = self.icon_button("undo", "撤销  ·  Ctrl+Z")
        self.redo_button = self.icon_button("redo", "重做  ·  Ctrl+Y")
        self.undo_button.clicked.connect(owner.canvas.undo)
        self.redo_button.clicked.connect(owner.canvas.redo)
        tools.addWidget(self.undo_button)
        tools.addWidget(self.redo_button)
        self.main_layout.addWidget(self.tools_group, 0, Qt.AlignmentFlag.AlignLeft)
        self.main_layout.addStretch(1)
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)
        self.close_button = self.icon_button("close", "取消标注  ·  Esc")
        self.close_button.setAccessibleName("取消标注")
        self.close_button.clicked.connect(owner.reject)
        actions_layout.addWidget(self.close_button)
        self.insert_button = QPushButton("插入画布")
        self.insert_button.setObjectName("annotationInsert")
        self.insert_button.setIcon(toolbar_icon("check", "#ffffff"))
        self.insert_button.setIconSize(QSize(18, 18))
        self.insert_button.setFixedSize(106, 34)
        self.insert_button.setAutoDefault(False)
        self.insert_button.setToolTip("插入画布  ·  Ctrl+Enter")
        self.insert_button.clicked.connect(owner.insert)
        actions_layout.addWidget(self.insert_button)
        self.main_layout.addWidget(actions, 0, Qt.AlignmentFlag.AlignRight)
        root.addLayout(self.main_layout)

        self.properties_row = QWidget()
        self.properties_row.setFixedHeight(28)
        self.properties_layout = QHBoxLayout(self.properties_row)
        self.properties_layout.setContentsMargins(0, 0, 0, 0)
        self.properties_layout.setSpacing(4)
        self.stroke_row = QWidget()
        self.stroke_row.setFixedHeight(28)
        self.stroke_layout = QHBoxLayout(self.stroke_row)
        self.stroke_layout.setContentsMargins(0, 0, 0, 0)
        self.stroke_layout.setSpacing(4)
        self._properties_compact = None
        self.palette = QWidget()
        palette_layout = QHBoxLayout(self.palette)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(2)
        self.colors = QButtonGroup(self)
        self.color_buttons = {}
        for color in ("#ef4444", "#f59e0b", "#22b785", "#3b82f6", "#ffffff", "#263244"):
            button = ColorSwatch(color)
            button.clicked.connect(lambda checked=False, value=color: self.color_selected.emit(value))
            self.colors.addButton(button)
            self.color_buttons[color] = button
            palette_layout.addWidget(button)
        custom_color = self.icon_button("color", "自定义颜色")
        custom_color.setFixedSize(24, 28)
        custom_color.clicked.connect(owner.choose_color)
        palette_layout.addWidget(custom_color)
        self.stroke_slider = StrokeSlider()
        self.stroke_slider.setValue(owner.canvas.stroke)
        self.stroke_slider.valueChanged.connect(self.set_stroke)
        self.font_button = self.setting_button("24 px", "文本字号")
        self.font_button.setFixedWidth(48)
        self.font_button.setMenu(self.number_menu("字号", [12, 16, 20, 24, 32, 48, 64], 10, 120, 24, self.set_font_size))
        self.dimensions = QLabel(f"{owner.canvas.base.width()} × {owner.canvas.base.height()}")
        self.dimensions.setObjectName("annotationMeta")
        self.dimensions.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.fit_button = self.setting_button("适应屏幕", "恢复适合屏幕的预览窗口大小；Ctrl+滚轮缩放")
        self.fit_button.setFixedWidth(76)
        self.fit_button.clicked.connect(owner.fit_to_screen)
        root.addWidget(self.properties_row)
        root.addWidget(self.stroke_row)
        self.select_tool("arrow")
        self.select_color(owner.canvas.color)
        self.adapt_to_width(owner.width())

    def icon_button(self, icon, tooltip):
        button = QToolButton()
        button.setObjectName("annotationTool")
        button.setIcon(toolbar_icon(icon))
        button.setIconSize(QSize(22, 22))
        button.setFixedSize(32, 34)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def setting_button(self, text, tooltip):
        button = QToolButton()
        button.setObjectName("annotationSetting")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setFixedHeight(28)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        return button

    def number_menu(self, label, presets, minimum, maximum, initial, callback):
        menu = QMenu(self)
        group = QActionGroup(menu)
        for number in presets:
            action = menu.addAction(f"{number} px")
            action.setCheckable(True)
            action.setChecked(number == initial)
            group.addAction(action)
            action.triggered.connect(lambda checked=False, value=number: callback(value))
        menu.addSeparator()
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.addWidget(QLabel(label))
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(initial)
        spin.setSuffix(" px")
        spin.setFixedWidth(82)
        spin.valueChanged.connect(callback)
        menu.aboutToShow.connect(lambda: spin.setValue(self.owner.canvas.font_size))
        layout.addWidget(spin)
        custom = QWidgetAction(menu)
        custom.setDefaultWidget(row)
        menu.addAction(custom)
        menu.aboutToShow.connect(lambda: self._check_number_actions(group, spin.value()))
        return menu

    @staticmethod
    def _check_number_actions(group, value):
        for action in group.actions():
            action.setChecked(action.text() == f"{value} px")

    def set_stroke(self, value):
        value = max(1, min(50, int(value)))
        self.owner.canvas.stroke = value
        self.owner.canvas.update_inline_style()
        if self.stroke_slider.value() != value:
            self.stroke_slider.setValue(value)

    def set_font_size(self, value):
        self.owner.canvas.font_size = value
        self.font_button.setText(f"{value} px")
        self.owner.canvas.update_inline_style()

    def select_tool(self, tool):
        self.tool_buttons[tool].setChecked(True)
        self.font_button.setVisible(tool == "text")

    def select_color(self, color):
        self.colors.setExclusive(False)
        for name, button in self.color_buttons.items():
            button.setChecked(name == color)
        self.colors.setExclusive(True)

    def adapt_to_width(self, width):
        compact = width < 540
        self.main_layout.setDirection(QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight)
        if compact != self._properties_compact:
            for layout in (self.properties_layout, self.stroke_layout):
                while layout.count():
                    layout.takeAt(0)
            self.properties_layout.addWidget(self.palette)
            if not compact:
                self.properties_layout.addSpacing(4)
                self.properties_layout.addWidget(self.stroke_slider, 1)
                self.properties_layout.addWidget(self.font_button)
            else:
                self.stroke_layout.addWidget(self.stroke_slider, 1)
                self.stroke_layout.addWidget(self.font_button)
                self.stroke_layout.addStretch(1)
            self.properties_layout.addStretch(1)
            self.properties_layout.addWidget(self.dimensions)
            self.properties_layout.addWidget(self.fit_button)
            self.stroke_row.setVisible(compact)
            self._properties_compact = compact
        self.dimensions.setVisible(width >= 760)
        self.layout().invalidate()
