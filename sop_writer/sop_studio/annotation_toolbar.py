"""Compact annotation controls and the drag surface replacing a native title bar."""
from PySide6.QtCore import QPointF, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QBoxLayout, QButtonGroup, QHBoxLayout, QLabel,
    QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from .annotation_icons import toolbar_icon
from .stroke_slider import ValueSlider


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
        self.stroke_slider = ValueSlider(
            minimum=1, maximum=50, value=owner.canvas.stroke, ticks=(2, 5, 10, 20),
            suffix="px", accessible_name="线条粗细",
            tooltip="线宽 1～50 px · 指数刻度\n拖动调整；点击选中后按 ← / → 微调 1 px")
        self.stroke_slider.valueChanged.connect(self.set_stroke)
        self.stroke_slider.sliderPressed.connect(owner.canvas.begin_style_edit)
        self.stroke_slider.sliderReleased.connect(owner.canvas.end_style_edit)
        self.font_slider = ValueSlider(
            minimum=6, maximum=80, value=owner.canvas.font_size, ticks=(8, 12, 24, 48),
            suffix="px", accessible_name="字体大小",
            tooltip="字号 6～80 px · 指数刻度\n拖动调整；点击选中后按 ← / → 微调 1 px")
        self.font_slider.valueChanged.connect(self.set_font_size)
        self.font_slider.sliderPressed.connect(owner.canvas.begin_style_edit)
        self.font_slider.sliderReleased.connect(owner.canvas.end_style_edit)
        self.dimensions = QLabel(f"{owner.canvas.base.width()} × {owner.canvas.base.height()}")
        self.dimensions.setObjectName("annotationMeta")
        self.dimensions.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.fit_button = self.setting_button("适应屏幕", "恢复适合屏幕的预览窗口大小；Ctrl+滚轮缩放")
        self.fit_button.setFixedWidth(76)
        self.fit_button.clicked.connect(owner.fit_to_screen)
        root.addWidget(self.properties_row)
        root.addWidget(self.stroke_row)
        self.adapt_to_width(owner.width())
        self.select_tool("arrow")
        self.select_color(owner.canvas.color)

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

    def set_stroke(self, value):
        value = max(1, min(50, int(value)))
        canvas = self.owner.canvas
        canvas.stroke = value
        if not canvas.update_selected_style(width=value):
            canvas.update_inline_style()
        self._sync_slider(self.stroke_slider, value)

    def set_font_size(self, value):
        value = max(6, min(80, int(value)))
        canvas = self.owner.canvas
        canvas.font_size = value
        if not canvas.update_selected_style(font_size=value):
            canvas.update_inline_style()
        self._sync_slider(self.font_slider, value)

    @staticmethod
    def _sync_slider(slider, value):
        if slider.value() != value:
            with QSignalBlocker(slider):
                slider.setValue(value)

    def sync_sliders(self, tool=None):
        """Show the selected annotation's width and font size in the sliders."""
        canvas = self.owner.canvas
        tool = canvas.tool if tool is None else tool
        selected = canvas.selected_operation()
        is_text = selected is not None and selected.get("kind") == "text"
        self.font_slider.setVisible(tool == "text" or (tool == "select" and is_text))
        self._sync_slider(self.stroke_slider, selected["width"] if selected is not None else canvas.stroke)
        value = selected.get("font_size", canvas.font_size) if is_text else canvas.font_size
        self._sync_slider(self.font_slider, value)
        self.layout().invalidate()

    def select_tool(self, tool):
        self.tool_buttons[tool].setChecked(True)
        self.sync_sliders(tool)

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
                self.properties_layout.addWidget(self.font_slider, 1)
            else:
                self.stroke_layout.addWidget(self.stroke_slider, 1)
                self.stroke_layout.addWidget(self.font_slider, 1)
                self.stroke_layout.addStretch(1)
            self.properties_layout.addStretch(1)
            self.properties_layout.addWidget(self.dimensions)
            self.properties_layout.addWidget(self.fit_button)
            self.stroke_row.setVisible(compact)
            self._properties_compact = compact
        self.dimensions.setVisible(width >= 760)
        self.layout().invalidate()
