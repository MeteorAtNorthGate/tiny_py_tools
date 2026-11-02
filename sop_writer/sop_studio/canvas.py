"""Continuous pages and interactive image/text objects."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAbstractTextDocumentLayout, QColor, QImage, QKeyEvent, QPainter, QPalette, QPen, QTextCursor
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsTextItem, QGraphicsView

from .document import Element
from .rendering import make_text_document, paint_text, paint_text_box, text_glyph_path


class EditableText(QGraphicsTextItem):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setDocument(make_text_document(owner.element))
        self.setDefaultTextColor(QColor(owner.element.color))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.glyphs = None
        self.paint_cache = {}
        self.composing = False
        self.preedit_cursor = 0
        self.cursor_visible = True
        self.blink = QTimer(self)
        self.blink.timeout.connect(self.blink_cursor)
        self.document().contentsChanged.connect(self.invalidate_glyphs)

    def invalidate_glyphs(self):
        self.glyphs = None
        self.paint_cache.clear()
        if self.owner.editing:
            height = max(self.owner.height, self.document().size().height())
            if height != self.owner.height:
                self.owner.prepareGeometryChange()
                self.owner.height = height
                self.owner.update()
        self.update()

    def blink_cursor(self):
        self.cursor_visible = not self.cursor_visible
        self.update()

    def paint(self, painter, option, widget=None):
        element = replace(self.owner.element, width=self.owner.width, height=self.owner.height)
        if self.glyphs is None and element.text_stroke_width and QColor(element.text_stroke_color).alpha():
            self.glyphs = text_glyph_path(self.document())
        paint_text(painter, element, self.document(), self.glyphs, self.paint_cache)
        if not self.owner.editing:
            return
        painter.save()
        painter.setClipRect(QRectF(0, 0, element.width, element.height), Qt.ClipOperation.IntersectClip)
        cursor = self.textCursor()
        if cursor.hasSelection():
            context = QAbstractTextDocumentLayout.PaintContext()
            context.palette.setColor(QPalette.ColorRole.Text, QColor("transparent"))
            selection = QAbstractTextDocumentLayout.Selection()
            selection.cursor = cursor
            selection.format.setBackground(QColor("#416fe8"))
            selection.format.setForeground(QColor("white"))
            context.selections = [selection]
            self.document().documentLayout().draw(painter, context)
        if self.hasFocus() and self.cursor_visible:
            layout = cursor.block().layout()
            offset = cursor.positionInBlock()
            if self.composing:
                offset = max(0, layout.preeditAreaPosition()) + self.preedit_cursor
            line = layout.lineForTextPosition(offset)
            if line.isValid():
                x = line.cursorToX(offset)
                x = x[0] if isinstance(x, tuple) else x
                point = layout.position() + QPointF(x, line.y())
                pen = QPen(QColor("#416fe8"), 1)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawLine(point, point + QPointF(0, line.height()))
        painter.restore()

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        self.preedit_cursor = len(event.preeditString())
        for attribute in event.attributes():
            if attribute.type == event.AttributeType.Cursor:
                self.preedit_cursor = attribute.start
        super().inputMethodEvent(event)
        self.cursor_visible = True
        self.invalidate_glyphs()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.owner.finish_text_edit()

    def keyPressEvent(self, event):
        self.cursor_visible = True
        self.update()
        if not self.composing and (event.key() == Qt.Key.Key_Escape or (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ControlModifier)):
            self.clearFocus()
            event.accept()
        else:
            super().keyPressEvent(event)


class ElementItem(QGraphicsObject):
    def __init__(self, element: Element, page_id: str, origin: QPointF, canvas):
        super().__init__()
        self.element, self.page_id, self.origin, self.canvas = element, page_id, origin, canvas
        self.width, self.height = element.width, element.height
        self.setPos(origin + QPointF(element.x, element.y))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setAcceptHoverEvents(True)
        self.resizing = False
        self.editing = False
        self.text_item = EditableText(self) if element.kind == "text" else None
        self.image = canvas.image_cache.get(element.asset, QImage()) if element.kind == "image" else None

    def boundingRect(self):
        return QRectF(-3, -3, self.width + 11, self.height + 11)

    def handle(self):
        return QRectF(self.width - 12, self.height - 12, 22, 22)

    def paint(self, painter, option, widget=None):
        bounds = QRectF(0, 0, self.width, self.height)
        if self.image is not None:
            if self.element.background != "transparent":
                painter.fillRect(bounds, QColor(self.element.background))
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(bounds, self.image)
        else:
            paint_text_box(painter, replace(self.element, width=self.width, height=self.height))
        if self.isSelected():
            pen = QPen(QColor("#4778ed"), 1.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(bounds)
            painter.setBrush(QColor("#ffffff"))
            painter.drawRoundedRect(QRectF(self.width - 5, self.height - 5, 10, 10), 2, 2)

    def hoverMoveEvent(self, event):
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if self.isSelected() and self.handle().contains(event.pos()) else Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # One active object keeps the inspector and drag transaction unambiguous.
            if not self.isSelected():
                self.scene().clearSelection()
                self.setSelected(True)
            event.setModifiers(Qt.KeyboardModifier.NoModifier)
            self.canvas.page_activated.emit(self.page_id)
            self.resizing = self.isSelected() and self.handle().contains(event.pos())
            self.start_point = event.scenePos()
            self.start_size = (self.width, self.height)
            if self.resizing:
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resizing:
            delta = event.scenePos() - self.start_point
            width = max(24, self.start_size[0] + delta.x())
            height = max(24, self.start_size[1] + delta.y())
            if self.element.kind == "image" and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                height = width * self.start_size[1] / self.start_size[0]
            self.prepareGeometryChange()
            self.width, self.height = min(width, 24000), min(height, 24000)
            if self.text_item:
                self.text_item.setTextWidth(self.width)
                self.text_item.invalidate_glyphs()
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.resizing = False
            self.canvas.commit_geometry(self)

    def mouseDoubleClickEvent(self, event):
        if self.text_item:
            self.start_text_edit()
            event.accept()
        else:
            self.canvas.annotate_requested.emit(self.element.id)
            event.accept()

    def start_text_edit(self):
        self.editing = True
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.text_item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.text_item.setFocus(Qt.FocusReason.MouseFocusReason)
        self.text_item.cursor_visible = True
        if QApplication.cursorFlashTime() > 0:
            self.text_item.blink.start(max(100, QApplication.cursorFlashTime() // 2))
        cursor = self.text_item.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_item.setTextCursor(cursor)

    def finish_text_edit(self):
        if not self.editing:
            return
        self.editing = False
        self.text_item.blink.stop()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        text = self.text_item.toPlainText()
        height = max(self.height, self.text_item.document().size().height())
        element_id = self.element.id

        def update(document):
            found = document.find(element_id)
            if found:
                found[1].text = text
                found[1].height = height

        self.canvas.controller.perform("编辑文字", update)


class CanvasView(QGraphicsView):
    selected = Signal(str)
    interaction_started = Signal()
    page_activated = Signal(str)
    annotate_requested = Signal(str)
    zoom_changed = Signal(int)
    image_dropped = Signal(str)
    delete_requested = Signal()
    nudge_requested = Signal(int, int)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor("#e9edf3"))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setAcceptDrops(True)
        self.scene().selectionChanged.connect(self._selection_changed)
        self.origins = {}
        self.page_rects = {}
        self.items_by_id = {}
        self.image_cache = {}
        self.rebuilding = False
        self.zoom_percent = 65
        self.set_zoom(65)
        self.panning = False
        self.space_down = False

    def selected_id(self):
        for item in self.scene().selectedItems():
            if isinstance(item, ElementItem):
                return item.element.id
        return ""

    def editing_item(self):
        return next((item for item in self.items_by_id.values() if item.editing), None)

    def finish_edit(self):
        item = self.editing_item()
        if item:
            item.text_item.clearFocus()

    def rebuild(self, select_id=None):
        old_id = self.selected_id() if select_id is None else select_id
        self.rebuilding = True
        self.scene().clear()
        self.origins.clear()
        self.page_rects.clear()
        self.items_by_id.clear()
        document = self.controller.document
        used = document.used_assets()
        self.image_cache = {key: value for key, value in self.image_cache.items() if key in used}
        for key in used:
            if key not in self.image_cache:
                self.image_cache[key] = QImage.fromData(document.assets[key])
        max_width = max(page.width for page in document.pages)
        y = 42
        for index, page in enumerate(document.pages):
            x = 48 + (max_width - page.width) / 2
            rect = QRectF(x, y, page.width, page.height)
            self.origins[page.id] = QPointF(x, y)
            self.page_rects[page.id] = rect
            shadow = self.scene().addRect(rect.translated(3, 5), QPen(Qt.PenStyle.NoPen), QColor("#d5dce6"))
            shadow.setZValue(-3)
            sheet = self.scene().addRect(rect, QPen(QColor("#dce2eb")), QColor("white"))
            sheet.setZValue(-2)
            label = self.scene().addSimpleText(f"{index + 1:02d}  /  {page.width} × {page.height} px")
            label.setBrush(QColor("#8792a4"))
            label.setPos(x, y - 26)
            label.setZValue(-1)
            # The parent clips content exactly as the PDF renderer does.
            clip = self.scene().addRect(rect, QPen(Qt.PenStyle.NoPen), Qt.BrushStyle.NoBrush)
            clip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
            clip.setZValue(0)
            for z, element in enumerate(page.elements):
                item = ElementItem(element, page.id, QPointF(x, y), self)
                item.setParentItem(clip)
                item.setZValue(z + 1)
                self.items_by_id[element.id] = item
                if element.id == old_id:
                    item.setSelected(True)
            y += page.height + 60
        self.scene().setSceneRect(0, 0, max_width + 96, y)
        self.rebuilding = False
        self._selection_changed()

    def _selection_changed(self):
        if not self.rebuilding:
            self.selected.emit(self.selected_id())

    def select_element(self, element_id):
        self.scene().clearSelection()
        item = self.items_by_id.get(element_id)
        if item:
            item.setSelected(True)

    def commit_geometry(self, item):
        element_id = item.element.id
        position = item.pos()
        center = item.sceneBoundingRect().center()
        destination = item.page_id
        # Release over another page to move the object to that page.
        for page_id, rect in self.page_rects.items():
            if rect.contains(center):
                destination = page_id
                break
        origin = self.origins[destination]
        x, y = position.x() - origin.x(), position.y() - origin.y()
        width, height = item.width, item.height

        def update(document):
            found = document.find(element_id)
            if not found:
                return
            page, element = found
            if destination != page.id:
                page.elements.remove(element)
                page = next(p for p in document.pages if p.id == destination)
                page.elements.append(element)
            element.x = round(max(0, min(x, page.width - 24)), 1)
            element.y = round(max(0, min(y, page.height - 24)), 1)
            element.width, element.height = round(width, 1), round(height, 1)

        self.controller.perform("调整位置与尺寸", update)
        found = self.controller.document.find(element_id)
        if found:
            # A clamped drag can leave the model unchanged; restore the view as well.
            self_pos = self.origins[found[0].id] + QPointF(found[1].x, found[1].y)
            item.setPos(self_pos)
        self.page_activated.emit(destination)

    def set_zoom(self, percent):
        self.zoom_percent = max(15, min(250, int(percent)))
        self.resetTransform()
        self.scale(self.zoom_percent / 100, self.zoom_percent / 100)
        self.zoom_changed.emit(self.zoom_percent)

    def fit_width(self, page_id):
        rect = self.page_rects.get(page_id)
        if rect:
            self.set_zoom((self.viewport().width() - 76) / rect.width() * 100)

    def go_to_page(self, page_id):
        rect = self.page_rects.get(page_id)
        if rect:
            self.centerOn(rect.center().x(), rect.top() + self.viewport().height() / (2 * self.transform().m11()) - 24)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.zoom_percent + (5 if event.angleDelta().y() > 0 else -5))
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        self.interaction_started.emit()
        if event.button() == Qt.MouseButton.MiddleButton or (self.space_down and event.button() == Qt.MouseButton.LeftButton):
            self.panning = True
            self.pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            position = self.mapToScene(event.position().toPoint())
            for page_id, rect in self.page_rects.items():
                if rect.contains(position):
                    self.page_activated.emit(page_id)
                    break
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.panning:
            delta = event.position() - self.pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(delta.y()))
            self.pan_start = event.position()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.panning:
            self.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if self.editing_item():
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Space:
            self.space_down = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_requested.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2):
            item = self.items_by_id.get(self.selected_id())
            if item and item.text_item:
                item.start_text_edit()
            event.accept()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx = step * ((event.key() == Qt.Key.Key_Right) - (event.key() == Qt.Key.Key_Left))
            dy = step * ((event.key() == Qt.Key.Key_Down) - (event.key() == Qt.Key.Key_Up))
            self.nudge_requested.emit(dx, dy)
        elif event.key() == Qt.Key.Key_Escape:
            self.scene().clearSelection()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.space_down = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            position = self.mapToScene(event.position().toPoint())
            for page_id, rect in self.page_rects.items():
                if rect.contains(position):
                    self.page_activated.emit(page_id)
                    break
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    self.image_dropped.emit(url.toLocalFile())
            event.acceptProposedAction()
