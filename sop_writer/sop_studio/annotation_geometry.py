"""Shared vector geometry for annotation previews, exported images and icons."""
import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath


def tapered_arrow_path(start: QPointF, end: QPointF, width: float) -> QPainterPath:
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = math.hypot(dx, dy)
    path = QPainterPath()
    if length < 1:
        path.addEllipse(start, max(1, width / 2), max(1, width / 2))
        return path
    direction = QPointF(dx / length, dy / length)
    normal = QPointF(-direction.y(), direction.x())
    head_length = min(length * .42, max(18, width * 7))
    head_half = head_length * .62
    shaft_half = head_half * .26
    wings = end - direction * head_length
    neck = end - direction * (head_length * .56)
    path.moveTo(start)
    for point in (neck + normal * shaft_half, wings + normal * head_half, end,
                  wings - normal * head_half, neck - normal * shaft_half):
        path.lineTo(point)
    path.closeSubpath()
    return path
