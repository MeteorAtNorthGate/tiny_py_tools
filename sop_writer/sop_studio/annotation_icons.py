"""Small vector-drawn toolbar icons, independent of symbol fonts and SVG plugins."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from .annotation_geometry import tapered_arrow_path


def _paint(painter, name, color):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if name == "arrow":
        painter.drawLine(QPointF(5, 19), QPointF(19, 5))
        painter.drawPolyline([QPointF(10, 5), QPointF(19, 5), QPointF(19, 14)])
    elif name == "tapered_arrow":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(tapered_arrow_path(QPointF(4, 20), QPointF(20, 4), 2))
    elif name == "rectangle":
        painter.drawRoundedRect(QRectF(4, 5, 16, 14), 2, 2)
    elif name == "text":
        for x1, y1, x2, y2 in [(5, 5, 19, 5), (12, 5, 12, 19), (8, 19, 16, 19), (5, 5, 5, 8), (19, 5, 19, 8)]:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif name == "pen":
        path = QPainterPath(QPointF(4, 18))
        path.cubicTo(3, 10, 11, 4, 12, 8)
        path.cubicTo(14, 13, 5, 20, 12, 18)
        path.cubicTo(15, 17, 15, 10, 19, 10)
        path.cubicTo(21, 10, 18, 17, 21, 17)
        painter.drawPath(path)
    elif name == "mosaic":
        painter.setPen(Qt.PenStyle.NoPen)
        for row in range(3):
            for column in range(3):
                tint = QColor(color)
                tint.setAlpha(255 if (row + column) % 2 == 0 else 90)
                painter.setBrush(tint)
                painter.drawRoundedRect(QRectF(4 + column * 5.5, 4 + row * 5.5, 4.5, 4.5), .6, .6)
    elif name in ("undo", "redo"):
        if name == "redo":
            painter.translate(24, 0)
            painter.scale(-1, 1)
        path = QPainterPath(QPointF(5, 9))
        path.cubicTo(20, 3, 24, 21, 12, 19)
        painter.drawPath(path)
        painter.drawPolyline([QPointF(5, 4), QPointF(5, 10), QPointF(11, 10)])
    elif name == "close":
        painter.drawLine(QPointF(6, 6), QPointF(18, 18))
        painter.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "check":
        painter.drawPolyline([QPointF(5, 12), QPointF(10, 17), QPointF(20, 7)])
    elif name == "grip":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for x in (9, 15):
            for y in (6, 12, 18):
                painter.drawEllipse(QPointF(x, y), 1.25, 1.25)
    elif name == "stroke":
        for y, width in [(6, 1), (12, 2.4), (18, 4)]:
            painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(5, y), QPointF(19, y))
    elif name == "color":
        painter.setPen(Qt.PenStyle.NoPen)
        for start, tint in [(0, "#4e7ef3"), (90, "#33b995"), (180, "#ffbc56"), (270, "#ed6474")]:
            painter.setBrush(QColor(tint))
            painter.drawPie(QRectF(3, 3, 18, 18), start * 16, 90 * 16)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QPointF(12, 12), 4, 4)


def toolbar_icon(name: str, tint=None) -> QIcon:
    icon = QIcon()
    for mode, color in [(QIcon.Mode.Normal, tint or "#485466"), (QIcon.Mode.Active, tint or "#3168df"),
                        (QIcon.Mode.Selected, tint or "#3168df"), (QIcon.Mode.Disabled, "#bec6d1")]:
        for state in (QIcon.State.Off, QIcon.State.On):
            pixmap = QPixmap(48, 48)
            pixmap.setDevicePixelRatio(2)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            _paint(painter, name, QColor("#3168df" if state == QIcon.State.On and not tint else color))
            painter.end()
            icon.addPixmap(pixmap, mode, state)
    return icon
