"""Custom widgets used by Pandoc Studio."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDragLeaveEvent, QDropEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QVBoxLayout


class DropZone(QFrame):
    """A painted, keyboard-friendly single-file drop target."""

    file_dropped = Signal(object)
    browse_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(190)
        self.setProperty("dragActive", False)

        # Content is added by MainWindow; keeping the layout here makes the
        # entire painted surface behave as one coherent drop target.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 34, 32, 30)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.browse_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if any(url.isLocalFile() and Path(url.toLocalFile()).is_file() for url in urls):
            event.acceptProposedAction()
            self._set_drag_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_drag_active(False)
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if url.isLocalFile() and path.is_file():
                self.file_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        active = bool(self.property("dragActive"))
        border = QColor("#7357f6" if active else "#c9c4e5")
        fill = QColor("#f0edff" if active else "#fbfaff")
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)

        painter.setBrush(fill)
        painter.setPen(QPen(border, 1.6, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(rect, 18, 18)

        # Simple document + upward arrow icon, drawn rather than loaded from
        # an asset so it stays crisp at every Windows display scale.
        center_x = self.width() / 2
        top = 42.0
        icon = QPainterPath()
        icon.moveTo(center_x - 19, top)
        icon.lineTo(center_x + 9, top)
        icon.lineTo(center_x + 19, top + 10)
        icon.lineTo(center_x + 19, top + 44)
        icon.quadTo(center_x + 19, top + 48, center_x + 15, top + 48)
        icon.lineTo(center_x - 19, top + 48)
        icon.quadTo(center_x - 23, top + 48, center_x - 23, top + 44)
        icon.lineTo(center_x - 23, top + 4)
        icon.quadTo(center_x - 23, top, center_x - 19, top)
        painter.setPen(QPen(QColor("#7357f6"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(QColor("#ffffff"))
        painter.drawPath(icon)

        painter.drawLine(QPointF(center_x - 1.5, top + 38), QPointF(center_x - 1.5, top + 19))
        painter.drawLine(QPointF(center_x - 9, top + 26), QPointF(center_x - 1.5, top + 18.5))
        painter.drawLine(QPointF(center_x + 6, top + 26), QPointF(center_x - 1.5, top + 18.5))
