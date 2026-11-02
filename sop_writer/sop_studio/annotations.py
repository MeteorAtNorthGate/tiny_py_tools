"""Floating screenshot markup editor. Markup is baked into the inserted PNG."""
from __future__ import annotations

import math
from copy import deepcopy

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QDialog, QGraphicsItem, QGraphicsScene, QGraphicsView,
    QLayout, QMenu, QVBoxLayout,
)

from .annotation_geometry import tapered_arrow_path
from .annotation_text import InlineTextFrame, annotation_text_box, make_annotation_text
from .annotation_toolbar import AnnotationToolbar
from .style import ANNOTATION_STYLE


def brush_path(points, width):
    path = QPainterPath(points[0])
    previous = points[0]
    for point in points[1:]:
        if point != previous:
            path.lineTo(point)
            previous = point
    if path.elementCount() == 1:
        path.addEllipse(points[0], width / 2, width / 2)
        return path
    stroker = QPainterPathStroker()
    stroker.setWidth(width)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(path)


def draw_operations(painter: QPainter, base: QImage, operations: list[dict], mosaic_cache=None):
    if mosaic_cache is None:
        mosaic_cache = {}
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
        elif kind == "tapered_arrow":
            painter.setPen(QPen(color, min(2, stroke * .15), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(color)
            painter.drawPath(tapered_arrow_path(start, end, stroke))
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
            if "pixelated" not in mosaic_cache:
                # One stable pixel grid for all strokes, also reused during live drawing.
                small = base.scaled(max(1, math.ceil(base.width() / 10)), max(1, math.ceil(base.height() / 10)),
                                    Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                mosaic_cache["pixelated"] = small.scaled(base.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                                          Qt.TransformationMode.FastTransformation)
            painter.setClipPath(brush_path(points, stroke), Qt.ClipOperation.IntersectClip)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(QPointF(0, 0), mosaic_cache["pixelated"])
        elif kind == "text" and not operation.get("text"):
            # Keep the screenshot visible while the user chooses the text box bounds.
            painter.setPen(QPen(color, max(1, stroke / 2)))
            painter.drawRoundedRect(rect, 5, 5)
        elif kind == "text":
            text = make_annotation_text(operation)
            box = annotation_text_box(operation, text)
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


class AnnotationLayer(QGraphicsItem):
    """Markup sits above the screenshot and below the active text editor."""
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.setZValue(1)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape)

    def boundingRect(self):
        return QRectF(self.canvas.base.rect())

    def paint(self, painter, option, widget=None):
        operations = self.canvas.operations + ([self.canvas.current] if self.canvas.current else [])
        draw_operations(painter, self.canvas.base, operations, self.canvas.mosaic_cache)


class AnnotationCanvas(QGraphicsView):
    history_changed = Signal()
    zoom_requested = Signal(float)
    editing_changed = Signal(bool)

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        self.base = image.copy()
        self.operations = []
        self.redo_operations = []
        self.mosaic_cache = {}
        self.current = None
        self.inline_frame = None
        self.tool = "arrow"
        self.color = "#ef4444"
        self.stroke = 4
        self.font_size = 24
        scene = QGraphicsScene(self)
        scene.addPixmap(QPixmap.fromImage(image))
        self.markup_layer = AnnotationLayer(self)
        scene.addItem(self.markup_layer)
        scene.setSceneRect(0, 0, image.width(), image.height())
        self.setScene(scene)
        self.setBackgroundBrush(QColor("#ffffff"))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setStyleSheet("border: none; padding: 0;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.fitted = True
        self.space_down = False
        self.window_drag = None

    def fit_image(self):
        # fitInView reserves an internal gutter; an explicit transform is edge to edge.
        scroll = self.verticalScrollBar().value()
        self.resetTransform()
        scale = self.viewport().width() / max(1, self.base.width())
        self.scale(scale, scale)
        self.horizontalScrollBar().setValue(0)
        self.verticalScrollBar().setValue(scroll)
        self.fitted = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fitted:
            self.fit_image()

    def refresh_markup(self):
        self.markup_layer.update()
        self.viewport().update()

    def point(self, event):
        point = self.mapToScene(event.position().toPoint())
        return [max(0, min(self.base.width(), point.x())), max(0, min(self.base.height(), point.y()))]

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (self.space_down and event.button() == Qt.MouseButton.LeftButton):
            self.window_drag = event.globalPosition().toPoint() - self.window().pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            if self.inline_frame is not None:
                position = self.mapToScene(event.position().toPoint())
                if self.inline_frame.box.contains(position):
                    super().mousePressEvent(event)
                    return
                self.finish_text_edit()
            point = self.point(event)
            self.current = {"kind": self.tool, "points": [point] if self.tool in ("pen", "mosaic") else [point, point], "color": self.color,
                            "width": self.stroke, "font_size": self.font_size}
            self.refresh_markup()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.window_drag is not None:
            self.window().move(event.globalPosition().toPoint() - self.window_drag)
            event.accept()
        elif self.current:
            self.extend_current(self.point(event))
            self.refresh_markup()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.window_drag is not None:
            self.window_drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.space_down else Qt.CursorShape.CrossCursor)
            event.accept()
        elif self.current and event.button() == Qt.MouseButton.LeftButton:
            self.extend_current(self.point(event))
            operation = self.current
            self.current = None
            if operation["kind"] == "text":
                self.begin_text_edit(operation)
                return
            self.operations.append(operation)
            self.redo_operations.clear()
            self.history_changed.emit()
            self.refresh_markup()
        else:
            super().mouseReleaseEvent(event)

    def extend_current(self, point):
        if self.current["kind"] in ("pen", "mosaic"):
            if point != self.current["points"][-1]:
                self.current["points"].append(point)
        else:
            self.current["points"][-1] = point

    def begin_text_edit(self, operation):
        rect = QRectF(QPointF(*operation["points"][0]), QPointF(*operation["points"][-1])).normalized()
        if rect.width() < 8:
            rect.setWidth(min(260, max(32, self.base.width() - rect.x())))
        if rect.height() < 8:
            rect.setHeight(operation.get("font_size", 24) + 24)
        operation["points"] = [[rect.left(), rect.top()], [rect.right(), rect.bottom()]]
        operation["text"] = ""
        self.inline_frame = InlineTextFrame(self, operation)
        self.scene().addItem(self.inline_frame)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.inline_frame.text_item.setFocus(Qt.FocusReason.OtherFocusReason)
        self.editing_changed.emit(True)
        self.history_changed.emit()
        self.refresh_markup()

    def update_inline_style(self):
        if self.inline_frame is not None:
            self.inline_frame.update_style(self.color, self.font_size, self.stroke)

    def finish_text_edit(self, cancel=False):
        frame = self.inline_frame
        if frame is None:
            return
        if not cancel:
            QApplication.inputMethod().commit()
        operation = frame.operation
        text = frame.text_item.toPlainText().replace("\u2028", "\n")
        self.inline_frame = None
        self.scene().removeItem(frame)
        frame.deleteLater()
        if not cancel and text.strip():
            operation["text"] = text
            self.operations.append(operation)
            self.redo_operations.clear()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.editing_changed.emit(False)
        self.history_changed.emit()
        self.refresh_markup()

    def undo(self):
        if self.inline_frame is not None:
            self.inline_frame.document.undo()
            return
        if self.operations:
            self.redo_operations.append(self.operations.pop())
            self.refresh_markup()
            self.history_changed.emit()

    def redo(self):
        if self.inline_frame is not None:
            self.inline_frame.document.redo()
            return
        if self.redo_operations:
            self.operations.append(self.redo_operations.pop())
            self.refresh_markup()
            self.history_changed.emit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.zoom_requested.emit(factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if self.inline_frame is not None:
            super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Space:
            self.space_down = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.space_down = False
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self.space_down = False
        self.window_drag = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        super().focusOutEvent(event)


class AnnotationWindow(QDialog):
    image_ready = Signal(QImage)

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("annotationWindow")
        self.setWindowTitle("截图标注 · SOP Studio")
        self.setStyleSheet(ANNOTATION_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(360)
        self._syncing_geometry = False
        self.canvas = AnnotationCanvas(image)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.canvas)
        self.toolbar = AnnotationToolbar(self)
        self.toolbar.tool_selected.connect(self.set_tool)
        self.toolbar.color_selected.connect(self.set_color)
        layout.addWidget(self.toolbar)
        # Preserve the public history controls used by the document workflow.
        self.undo_button = self.toolbar.undo_button
        self.redo_button = self.toolbar.redo_button
        self.group = self.toolbar.group
        self.tool_shortcuts = []
        for name, key in [("arrow", "A"), ("tapered_arrow", "B"), ("text", "T"), ("mosaic", "M"), ("pen", "P"), ("rectangle", "R")]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(self.toolbar.tool_buttons[name].click)
            self.tool_shortcuts.append(shortcut)
        for key, callback in [("Ctrl+Z", self.canvas.undo), ("Ctrl+Y", self.canvas.redo), ("Ctrl+Shift+Z", self.canvas.redo), ("Ctrl+Return", self.insert)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
        self.canvas.history_changed.connect(self.update_history)
        self.canvas.editing_changed.connect(self.text_editing_changed)
        self.canvas.zoom_requested.connect(self.zoom_window)
        self.update_history()
        self.fit_to_screen()

    def set_tool(self, tool):
        self.canvas.finish_text_edit()
        self.canvas.tool = tool
        self.toolbar.select_tool(tool)
        self.sync_geometry()

    def set_color(self, color):
        self.canvas.color = color
        self.canvas.update_inline_style()
        self.toolbar.select_color(color)

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.canvas.color), self, "标注颜色")
        if color.isValid():
            self.set_color(color.name())

    def screen_area(self):
        screen = self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry().adjusted(16, 16, -16, -16)

    def fit_to_screen(self):
        area = self.screen_area()
        native_width = round(self.canvas.base.width() / max(1, self.devicePixelRatioF()))
        width = max(360, min(native_width, area.width(), 1440))
        self.resize(width, self.height())
        self.sync_geometry()
        if not self.isVisible():
            self.move(area.center() - self.rect().center())
        else:
            self.keep_on_screen()

    def sync_geometry(self):
        if self._syncing_geometry:
            return
        self._syncing_geometry = True
        try:
            self.toolbar.adapt_to_width(self.width())
            toolbar_height = self.toolbar.sizeHint().height()
            image_height = max(1, round(self.width() * self.canvas.base.height() / self.canvas.base.width()))
            available_height = max(60, self.screen_area().height() - toolbar_height)
            # Very tall images scroll vertically instead of adding side gutters.
            self.canvas.setFixedHeight(min(image_height, available_height))
            self.toolbar.setFixedHeight(toolbar_height)
            self.resize(self.width(), self.canvas.height() + toolbar_height)
            self.layout().activate()
            self.canvas.fit_image()
            zoom = self.canvas.transform().m11() * self.devicePixelRatioF() * 100
            self.toolbar.fit_button.setToolTip(f"恢复适合屏幕的预览窗口大小\n当前显示比例 {round(zoom)}%，不改变原图像素尺寸\nCtrl+滚轮可缩放窗口")
        finally:
            self._syncing_geometry = False

    def keep_on_screen(self):
        area = self.screen_area()
        self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))

    def zoom_window(self, factor):
        area = self.screen_area()
        self.resize(max(360, min(round(self.width() * factor), area.width())), self.height())
        self.sync_geometry()
        self.keep_on_screen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toolbar"):
            self.sync_geometry()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_geometry()
        self.canvas.setFocus()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for tool, text in [("arrow", "箭头  A"), ("tapered_arrow", "渐尖箭头  B"), ("pen", "涂鸦  P"), ("rectangle", "矩形  R"), ("text", "文本框  T"), ("mosaic", "马赛克  M")]:
            menu.addAction(text, lambda name=tool: self.set_tool(name))
        menu.addSeparator()
        menu.addAction("适应屏幕", self.fit_to_screen)
        menu.addAction("插入画布    Ctrl+Enter", self.insert)
        menu.addAction("取消标注    Esc", self.reject)
        menu.exec(event.globalPos())

    def update_history(self):
        if self.canvas.inline_frame is not None:
            document = self.canvas.inline_frame.document
            self.undo_button.setEnabled(document.isUndoAvailable())
            self.redo_button.setEnabled(document.isRedoAvailable())
        else:
            self.undo_button.setEnabled(bool(self.canvas.operations))
            self.redo_button.setEnabled(bool(self.canvas.redo_operations))

    def text_editing_changed(self, editing):
        for shortcut in self.tool_shortcuts:
            shortcut.setEnabled(not editing)

    def insert(self):
        self.canvas.finish_text_edit()
        self.image_ready.emit(render_annotation(self.canvas.base, deepcopy(self.canvas.operations)))
        self.accept()
