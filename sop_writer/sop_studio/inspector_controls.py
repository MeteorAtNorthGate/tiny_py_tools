"""Direct numeric entry, light chevrons and editable color swatches."""
from PySide6.QtCore import QLocale, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QIntValidator, QPainter, QPen
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFontComboBox, QHBoxLayout, QLabel, QLineEdit,
    QSizePolicy, QToolButton, QWidget,
)


class NumberInput(QLineEdit):
    """A validated value with a separate unit label; no stepping controls."""
    integer = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.minimum, self.maximum = 0, 24000
        self.decimals = 1
        self.committed = 0
        self.unit = QLabel(self)
        self.unit.setObjectName("inputUnit")
        self.unit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.unit.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.number_validator = QIntValidator(self) if self.integer else QDoubleValidator(self)
        if not self.integer:
            self.number_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.number_validator.setLocale(QLocale.c())
        self.setValidator(self.number_validator)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setRange(self.minimum, self.maximum)
        self.editingFinished.connect(self.normalize)
        self.setValue(0)

    def setRange(self, minimum, maximum):
        self.minimum, self.maximum = minimum, maximum
        if self.integer:
            self.number_validator.setRange(int(minimum), int(maximum))
        else:
            self.number_validator.setRange(minimum, maximum, self.decimals)

    def setDecimals(self, decimals):
        self.decimals = decimals
        self.setRange(self.minimum, self.maximum)
        self.setValue(self.committed)

    def setSuffix(self, suffix):
        self.unit.setText(suffix.strip())
        self.layout_unit()

    def layout_unit(self):
        width = self.unit.sizeHint().width() if self.unit.text() else 0
        self.unit.setGeometry(self.width() - width - 8, 0, width, self.height())
        self.setTextMargins(0, 0, width + 6 if width else 0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_unit()

    def setValue(self, value):
        self.committed = max(self.minimum, min(self.maximum, value))
        self.setText(str(round(self.committed)) if self.integer else f"{self.committed:.{self.decimals}f}")

    def value(self):
        try:
            value = int(self.text()) if self.integer else float(self.text())
            return max(self.minimum, min(self.maximum, value))
        except ValueError:
            return self.committed

    def normalize(self):
        self.setValue(self.value())

    def focusOutEvent(self, event):
        # Recover an empty or unfinished entry before Qt emits editingFinished.
        if not self.hasAcceptableInput():
            self.normalize()
        super().focusOutEvent(event)

    def wheelEvent(self, event):
        # The inspector scrolls without silently changing a selected property.
        event.ignore()


class IntegerInput(NumberInput):
    integer = True


class _Chevron:
    def configure_combo(self):
        self.setObjectName("inspectorCombo")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(6)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#758299" if self.isEnabled() else "#b9c2cf")
        painter.setPen(QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        x, y = self.width() - 15, self.height() / 2
        painter.drawPolyline([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)])

    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


class FontPicker(_Chevron, QFontComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.configure_combo()


class ChoiceInput(_Chevron, QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.configure_combo()


class ColorSwatch(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = QColor(Qt.GlobalColor.transparent)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("选择颜色")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(3, 3, 24, 24)
        painter.fillRect(box, QColor("white"))
        if not self.color.alpha():
            for row in range(4):
                for col in range(4):
                    if (row + col) % 2 == 0:
                        painter.fillRect(QRectF(3 + col * 6, 3 + row * 6, 6, 6), QColor("#e5eaf2"))
            painter.setPen(QPen(QColor("#e0787e"), 1.5))
            painter.drawLine(QPointF(6, 24), QPointF(24, 6))
        else:
            painter.fillRect(box, self.color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#9bb6f2" if self.underMouse() or self.hasFocus() else "#cdd6e3"), 1))
        painter.drawRoundedRect(box, 4, 4)


class ColorInput(QWidget):
    valueChanged = Signal(str)

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.value = "transparent"
        self.swatch = ColorSwatch(self)
        self.swatch.setAccessibleName(title)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("无")
        self.entry.setClearButtonEnabled(True)
        self.entry.setAccessibleName(title + "色值")
        self.entry.setToolTip("输入 #RRGGBB；清空或输入“无”表示透明。")
        self.entry.setMinimumWidth(0)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.swatch)
        layout.addWidget(self.entry, 1)
        self.swatch.clicked.connect(self.choose)
        self.entry.editingFinished.connect(self.commit)

    def setValue(self, value):
        self.value = value
        color = QColor(value)
        self.swatch.color = color
        self.swatch.update()
        self.entry.setText(color.name().upper() if color.alpha() else "")

    def commit(self):
        value = self.entry.text().strip()
        color = QColor("transparent" if value.lower() in ("", "无", "透明", "none", "transparent") else value)
        if not color.isValid():
            self.setValue(self.value)
            return
        value = color.name() if color.alpha() else "transparent"
        changed = value != self.value
        self.setValue(value)
        if changed:
            self.valueChanged.emit(value)

    def choose(self):
        initial = QColor(self.value) if self.value != "transparent" else QColor("#243247")
        color = QColorDialog.getColor(initial, self.window(), self.title)
        if color.isValid():
            self.entry.setText(color.name())
            self.commit()
