"""An exponential mouse scale with integer-pixel keyboard steps."""
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider


class StrokeSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(1, 50)
        self.setValue(4)
        self.setSingleStep(1)
        self.setPageStep(5)
        self.setFixedHeight(28)
        self.setMinimumWidth(128)
        self.setMaximumWidth(208)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("线条粗细")
        self.setAccessibleDescription("1～50 像素，指数刻度；左右箭头每次调整 1 像素。")
        self.setToolTip("线宽 1～50 px · 指数刻度\n拖动调整；点击选中后按 ← / → 微调 1 px")

    def sizeHint(self):
        return QSize(174, 28)

    def track(self):
        return 10.0, max(11.0, self.width() - 49.0)

    def position_for_value(self, value):
        left, right = self.track()
        value = max(self.minimum(), min(self.maximum(), value))
        return left + math.log(value) / math.log(self.maximum()) * (right - left)

    def value_for_position(self, position):
        left, right = self.track()
        fraction = max(0.0, min(1.0, (position - left) / (right - left)))
        return max(self.minimum(), min(self.maximum(), round(self.maximum() ** fraction)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.hasFocus() or self.underMouse():
            painter.setPen(QPen(QColor("#bfd1f6"), 1) if self.hasFocus() else QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QColor("#eef4ff" if self.hasFocus() else "#f1f4f9"))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 5, 5)
        left, right = self.track()
        x = self.position_for_value(self.value())
        painter.setPen(QPen(QColor("#dce4ef"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(left, 10), QPointF(right, 10))
        painter.setPen(QPen(QColor("#6c91e8"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(left, 10), QPointF(x, 10))
        painter.setPen(QPen(QColor("#c8d2e2"), 1))
        for value in (2, 5, 10, 20):
            tick = self.position_for_value(value)
            painter.drawLine(QPointF(tick, 14), QPointF(tick, 16))
        painter.setPen(QPen(QColor("#5985e3"), 1.6))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(x, 10), 4.2, 4.2)
        font = painter.font()
        font.setPixelSize(8)
        painter.setFont(font)
        painter.setPen(QColor("#8d99ab"))
        painter.drawText(QRectF(left - 2, 17, 18, 9), Qt.AlignmentFlag.AlignLeft, "1")
        painter.drawText(QRectF(right - 15, 17, 18, 9), Qt.AlignmentFlag.AlignRight, "50")
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor("#446086" if self.hasFocus() else "#69788d"))
        painter.drawText(QRectF(self.width() - 43, 0, 40, 28), Qt.AlignmentFlag.AlignCenter, f"{self.value()} px")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            if event.position().x() <= self.track()[1] + 8:
                self.setSliderDown(True)
                self.setValue(self.value_for_position(event.position().x()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self.setValue(self.value_for_position(event.position().x()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.isSliderDown():
                self.setValue(self.value_for_position(event.position().x()))
                self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.setValue(self.value() + (1 if event.key() == Qt.Key.Key_Right else -1))
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
