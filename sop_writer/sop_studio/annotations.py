"""Floating screenshot markup editor. Markup is baked into the inserted PNG."""
from __future__ import annotations

import math
from copy import deepcopy

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QShortcut, QTextDocument
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QDialog, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QInputDialog, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


def draw_operations(painter: QPainter, base: QImage, operations: list[dict]):
    for operation in operations:
        points = [QPointF(*point) for point in operation["points"]]
        color = QColor(operation["color"])
        stroke = operation["width"]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        start, end = points[0], points[-1]
        rect = QRectF(start, end).normalized()
        kind = operation["kind"]
        if kind == "arrow":
            angle = math.atan2(end.y() - start.y(), end.x() - start.x())
            length = max(15, stroke * 4)
            neck = end - QPointF(math.cos(angle) * length * .65, math.sin(angle) * length * .65)
            painter.drawLine(start, neck)
            left = end - QPointF(math.cos(angle - .48) * length, math.sin(angle - .48) * length)
            right = end - QPointF(math.cos(angle + .48) * length, math.sin(angle + .48) * length)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([end, left, right]))
        elif kind == "rectangle":
            painter.drawRoundedRect(rect, 3, 3)
        elif kind == "pen":
            path = QPainterPath(start)
            for point in points[1:]:
                path.lineTo(point)
            if len(points) == 1:
                painter.drawPoint(start)
            else:
                painter.drawPath(path)
        elif kind == "mosaic":
            area = rect.toAlignedRect().intersected(base.rect())
            if not area.isEmpty():
                block = max(8, stroke * 4)
                small = base.copy(area).scaled(max(1, area.width() // block), max(1, area.height() // block),
                                               Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                painter.drawImage(QRectF(area), small)
        elif kind == "text" and operation.get("text"):
            width = max(80, rect.width())
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(operation.get("font_size", 24))
            text = QTextDocument()
            text.setDefaultFont(font)
            text.setDocumentMargin(10)
            text.setPlainText(operation["text"])
            text.setTextWidth(width)
            box = QRectF(rect.topLeft(), text.size())
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(color, max(1, stroke / 2)))
            painter.drawRoundedRect(box, 5, 5)
            painter.translate(box.topLeft())
            from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette
            context = QAbstractTextDocumentLayout.PaintContext()
            context.palette.setColor(QPalette.ColorRole.Text, color)
            text.documentLayout().draw(painter, context)
        painter.restore()


def render_annotation(base: QImage, operations: list[dict]) -> QImage:
    result = base.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(result)
    draw_operations(painter, base, operations)
    painter.end()
    return result


class AnnotationCanvas(QGraphicsView):
    history_changed = Signal()

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        self.base = image.copy()
        self.operations = []
        self.redo_operations = []
        self.current = None
        self.tool = "arrow"
        self.color = "#ef4444"
        self.stroke = 4
        self.font_size = 24
        scene = QGraphicsScene(self)
        scene.addPixmap(QPixmap.fromImage(image))
        scene.setSceneRect(0, 0, image.width(), image.height())
        self.setScene(scene)
        self.setBackgroundBrush(QColor("#1d2533"))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.fitted = True

    def fit_image(self):
        self.fitInView(self.sceneRect().adjusted(-16, -16, 16, 16), Qt.AspectRatioMode.KeepAspectRatio)
        self.fitted = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fitted:
            self.fit_image()

    def drawForeground(self, painter, rect):
        operations = self.operations + ([self.current] if self.current else [])
        draw_operations(painter, self.base, operations)

    def point(self, event):
        point = self.mapToScene(event.position().toPoint())
        return [max(0, min(self.base.width(), point.x())), max(0, min(self.base.height(), point.y()))]

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = self.point(event)
            self.current = {"kind": self.tool, "points": [point, point], "color": self.color,
                            "width": self.stroke, "font_size": self.font_size}
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current:
            if self.tool == "pen":
                self.current["points"].append(self.point(event))
            else:
                self.current["points"][-1] = self.point(event)
            self.viewport().update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.current and event.button() == Qt.MouseButton.LeftButton:
            operation = self.current
            self.current = None
            if operation["kind"] == "text":
                value, accepted = QInputDialog.getMultiLineText(self, "添加标注文本框", "输入说明文字（可以换行）：")
                if not accepted or not value.strip():
                    self.viewport().update()
                    return
                operation["text"] = value
                a, b = operation["points"]
                if abs(b[0] - a[0]) < 30:
                    b[0] = min(self.base.width(), a[0] + 260)
                if abs(b[1] - a[1]) < 10:
                    b[1] = min(self.base.height(), a[1] + 50)
            self.operations.append(operation)
            self.redo_operations.clear()
            self.history_changed.emit()
            self.viewport().update()
        else:
            super().mouseReleaseEvent(event)

    def undo(self):
        if self.operations:
            self.redo_operations.append(self.operations.pop())
            self.viewport().update()
            self.history_changed.emit()

    def redo(self):
        if self.redo_operations:
            self.operations.append(self.redo_operations.pop())
            self.viewport().update()
            self.history_changed.emit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.fitted = False
            scale = self.transform().m11()
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            if .05 <= scale * factor <= 8:
                self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)


class AnnotationWindow(QDialog):
    image_ready = Signal(QImage)

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("截图标注 · SOP Studio")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(760, 440)
        self.resize(min(1200, max(820, image.width() + 40)), min(850, max(520, image.height() + 150)))
        self.canvas = AnnotationCanvas(image)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.canvas, 1)
        toolbar = QWidget()
        toolbar.setObjectName("annotationBar")
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(14, 12, 14, 12)
        tools.setSpacing(6)
        self.group = QButtonGroup(self)
        for label, name, key in [("箭头", "arrow", "A"), ("文本框", "text", "T"), ("马赛克", "mosaic", "M"), ("涂鸦", "pen", "P"), ("矩形", "rectangle", "R")]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(f"{label}  ({key})")
            self.group.addButton(button)
            tools.addWidget(button)
            button.clicked.connect(lambda checked=False, tool=name: self.set_tool(tool))
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(button.click)
            if name == "arrow":
                button.setChecked(True)
        color = QPushButton("颜色")
        color.clicked.connect(self.choose_color)
        tools.addWidget(color)
        tools.addWidget(QLabel("粗细"))
        stroke = QSpinBox()
        stroke.setRange(1, 24)
        stroke.setValue(4)
        stroke.setFixedWidth(58)
        stroke.valueChanged.connect(lambda value: setattr(self.canvas, "stroke", value))
        tools.addWidget(stroke)
        tools.addWidget(QLabel("字号"))
        font_size = QSpinBox()
        font_size.setRange(10, 120)
        font_size.setValue(24)
        font_size.setFixedWidth(60)
        font_size.valueChanged.connect(lambda value: setattr(self.canvas, "font_size", value))
        tools.addWidget(font_size)
        self.undo_button = QPushButton("撤销")
        self.redo_button = QPushButton("重做")
        self.undo_button.clicked.connect(self.canvas.undo)
        self.redo_button.clicked.connect(self.canvas.redo)
        tools.addWidget(self.undo_button)
        tools.addWidget(self.redo_button)
        tools.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        tools.addWidget(cancel)
        insert = QPushButton("插入画布")
        insert.setObjectName("primary")
        insert.clicked.connect(self.insert)
        tools.addWidget(insert)
        layout.addWidget(toolbar)
        hint = QLabel("  A 箭头 · T 文本 · M 马赛克 · P 涂鸦 · R 矩形    |    Ctrl + 滚轮缩放    |    Ctrl + Enter 插入")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        for key, callback in [("Ctrl+Z", self.canvas.undo), ("Ctrl+Y", self.canvas.redo), ("Ctrl+Shift+Z", self.canvas.redo), ("Ctrl+Return", self.insert)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
        self.canvas.history_changed.connect(self.update_history)
        self.update_history()

    def set_tool(self, tool):
        self.canvas.tool = tool

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.canvas.color), self, "标注颜色")
        if color.isValid():
            self.canvas.color = color.name()

    def update_history(self):
        self.undo_button.setEnabled(bool(self.canvas.operations))
        self.redo_button.setEnabled(bool(self.canvas.redo_operations))

    def insert(self):
        self.image_ready.emit(render_annotation(self.canvas.base, deepcopy(self.canvas.operations)))
        self.accept()
