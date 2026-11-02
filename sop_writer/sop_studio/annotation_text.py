"""In-place annotation text with the same document layout for editing and export."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextDocument, QTextOption
from PySide6.QtWidgets import QGraphicsObject, QGraphicsTextItem


def make_annotation_text(operation):
    rect = QRectF(QPointF(*operation["points"][0]), QPointF(*operation["points"][-1])).normalized()
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(operation.get("font_size", 24))
    document = QTextDocument()
    document.setDefaultFont(font)
    document.setDocumentMargin(10)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.NoWrap if operation.get("auto_width")
                       else QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    document.setDefaultTextOption(option)
    document.setPlainText(operation.get("text", ""))
    document.setTextWidth(max(32, rect.width()))
    return document


def annotation_text_box(operation, document):
    rect = QRectF(QPointF(*operation["points"][0]), QPointF(*operation["points"][-1])).normalized()
    size = document.size()
    width = max(32, rect.width(), size.width()) if operation.get("auto_width") else document.textWidth()
    return QRectF(rect.x(), rect.y(), width, max(rect.height(), size.height()))


class InlineTextFrame(QGraphicsObject):
    def __init__(self, canvas, operation):
        super().__init__()
        self.canvas = canvas
        self.operation = operation
        self.document = make_annotation_text(operation)
        self._updating_box = False
        self.box = annotation_text_box(operation, self.document)
        self.setPos(self.box.topLeft())
        self.setZValue(100)
        self.text_item = InlineTextItem(canvas, self)
        self.text_item.setDocument(self.document)
        self.text_item.setDefaultTextColor(QColor(operation["color"]))
        self.document.setParent(self.text_item)
        self.document.contentsChanged.connect(self.update_box)
        self.document.documentLayout().documentSizeChanged.connect(lambda _: self.update_box())
        self.document.undoAvailable.connect(lambda _: canvas.history_changed.emit())
        self.document.redoAvailable.connect(lambda _: canvas.history_changed.emit())

    def boundingRect(self):
        margin = max(1, self.operation["width"] / 2) + 1
        return QRectF(0, 0, self.box.width(), self.box.height()).adjusted(-margin, -margin, margin, margin)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(self.operation["color"]), max(1, self.operation["width"] / 2)))
        painter.setBrush(QColor("white"))
        painter.drawRoundedRect(QRectF(0, 0, self.box.width(), self.box.height()), 5, 5)

    def update_box(self):
        if self._updating_box:
            return
        self._updating_box = True
        try:
            self.prepareGeometryChange()
            self.box = annotation_text_box(self.operation, self.document)
            self.update()
            self.canvas.history_changed.emit()
        finally:
            self._updating_box = False

    def update_style(self, color, font_size, width):
        self.prepareGeometryChange()
        self.operation.update(color=color, font_size=font_size, width=width)
        font = self.document.defaultFont()
        font.setPixelSize(font_size)
        self.document.setDefaultFont(font)
        self.text_item.setDefaultTextColor(QColor(color))
        self.update_box()


class InlineTextItem(QGraphicsTextItem):
    def __init__(self, canvas, parent):
        super().__init__(parent)
        self.canvas = canvas
        self.composing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.canvas.finish_text_edit(cancel=True)
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if not self.composing:
                self.canvas.finish_text_edit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)
