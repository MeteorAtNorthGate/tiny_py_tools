"""Shared text, preview and PDF rendering, in document pixels at 96 DPI."""
from __future__ import annotations

import os
import tempfile
import math
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QAbstractTextDocumentLayout, QColor, QFont, QImage, QPageSize, QPainter,
    QPainterPath, QPainterPathStroker, QPalette, QPdfWriter, QTextBlockFormat,
    QTextCursor, QTextDocument, QTextOption,
)

from .document import Document, Element, Page

LINE_HEIGHT_FACTOR = 1.2


def apply_line_spacing(document: QTextDocument, factor: float = LINE_HEIGHT_FACTOR):
    """Apply a proportional line height to every block, including new ones."""
    block_format = QTextBlockFormat()
    block_format.setLineHeight(factor * 100, QTextBlockFormat.LineHeightTypes.ProportionalHeight)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeBlockFormat(block_format)
    cursor.clearSelection()


def image_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("无法编码图片。")
    return bytes(data)


def make_text_document(element: Element) -> QTextDocument:
    text = QTextDocument()
    extra = 0
    if QColor(element.text_stroke_color).alpha() and element.text_stroke_width:
        extra = element.text_stroke_width * {"outside": 1, "center": .5, "inside": 0}[element.text_stroke_alignment]
    text.setDocumentMargin(5 + extra)
    font = QFont(element.font_family)
    font.setPixelSize(element.font_size)
    font.setBold(element.bold)
    text.setDefaultFont(font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    text.setDefaultTextOption(option)
    text.setPlainText(element.text)
    apply_line_spacing(text)
    text.setTextWidth(element.width)
    return text


def text_glyph_path(document: QTextDocument) -> QPainterPath:
    """Use Qt's shaped glyph runs, preserving wrapping and fallback fonts."""
    document.size()  # Lay out every block before requesting glyph positions.
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    block = document.begin()
    while block.isValid():
        layout = block.layout()
        # An explicit range also works with Qt builds that return no runs for -1.
        for run in layout.glyphRuns(0, block.length() - 1 + len(layout.preeditAreaText())):
            font = run.rawFont()
            for glyph, position in zip(run.glyphIndexes(), run.positions()):
                path.addPath(font.pathForGlyph(glyph).translated(layout.position() + position))
        block = block.next()
    return path


def text_stroke_paths(glyphs: QPainterPath, width: float, alignment: str):
    """Split fill and outline into disjoint regions for uniform opacity."""
    stroker = QPainterPathStroker()
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    stroker.setWidth(width if alignment == "center" else width * 2)
    ring = stroker.createStroke(glyphs)
    if alignment == "outside":
        return glyphs, ring.subtracted(glyphs)
    if alignment == "inside":
        ring = ring.intersected(glyphs)
    return glyphs.subtracted(ring), ring


def paint_text(painter: QPainter, element: Element, document: QTextDocument | None = None,
               glyphs: QPainterPath | None = None, cache: dict | None = None):
    """The same text effects serve the canvas, inline editor, thumbnails and PDF."""
    if element.text_opacity <= 0:
        return
    text = document if document is not None else make_text_document(element)
    painter.save()
    painter.setClipRect(QRectF(0, 0, element.width, element.height), Qt.ClipOperation.IntersectClip)
    painter.setOpacity(painter.opacity() * element.text_opacity)
    context = QAbstractTextDocumentLayout.PaintContext()
    context.palette.setColor(QPalette.ColorRole.Text, QColor(element.color))
    stroke_color = QColor(element.text_stroke_color)
    if element.text_stroke_width > 0 and stroke_color.alpha():
        glyphs = text_glyph_path(text) if glyphs is None else glyphs
        fill, stroke = text_stroke_paths(glyphs, element.text_stroke_width, element.text_stroke_alignment)
        if element.text_opacity == 1:
            painter.fillPath(fill, QColor(element.color))
            painter.fillPath(stroke, stroke_color)
        else:
            # Composite the two colors once, including antialiased shared edges.
            # A supersampled layer keeps PDF output sharp and alpha uniform.
            layer = cache.get("text_layer") if cache is not None else None
            if layer is None:
                bounds = glyphs.boundingRect().united(stroke.boundingRect()).adjusted(-1, -1, 1, 1)
                bounds = bounds.intersected(QRectF(0, 0, element.width, element.height))
                if bounds.isEmpty():
                    painter.restore()
                    return
                scale = min(4, 8192 / max(bounds.width(), bounds.height()),
                            math.sqrt(16_000_000 / max(1, bounds.width() * bounds.height())))
                image = QImage(max(1, math.ceil(bounds.width() * scale)), max(1, math.ceil(bounds.height() * scale)),
                               QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(Qt.GlobalColor.transparent)
                ink = QPainter(image)
                ink.setRenderHint(QPainter.RenderHint.Antialiasing)
                ink.scale(image.width() / bounds.width(), image.height() / bounds.height())
                ink.translate(-bounds.x(), -bounds.y())
                ink.fillPath(fill, QColor(element.color))
                ink.fillPath(stroke, stroke_color)
                ink.end()
                layer = bounds, image
                if cache is not None:
                    cache["text_layer"] = layer
            painter.drawImage(*layer)
    else:
        text.documentLayout().draw(painter, context)
    painter.restore()


def paint_text_box(painter: QPainter, element: Element):
    """Frame fill and inside border share opacity without darkening their overlap."""
    if element.box_opacity <= 0:
        return
    painter.save()
    painter.setOpacity(painter.opacity() * element.box_opacity)
    bounds = QRectF(0, 0, element.width, element.height)
    width = min(element.box_stroke_width, element.width / 2, element.height / 2)
    border = QColor(element.box_stroke_color)
    background = QColor(element.background)
    if width > 0 and border.alpha():
        inside = bounds.adjusted(width, width, -width, -width)
        frame = QPainterPath()
        frame.addRect(bounds)
        frame.addRect(inside)
        painter.fillPath(frame, border)
        painter.fillRect(inside, background)
    else:
        painter.fillRect(bounds, background)
    painter.restore()


def paint_element(painter: QPainter, element: Element, assets: dict[str, bytes], images: dict | None = None):
    painter.save()
    painter.translate(element.x, element.y)
    bounds = QRectF(0, 0, element.width, element.height)
    painter.setClipRect(bounds, Qt.ClipOperation.IntersectClip)
    if element.kind == "image":
        if element.background != "transparent":
            painter.fillRect(bounds, QColor(element.background))
        if images is not None and element.asset in images:
            image = images[element.asset]
        else:
            image = QImage.fromData(assets.get(element.asset, b""))
            if images is not None:
                images[element.asset] = image
        painter.drawImage(bounds, image)
    else:
        paint_text_box(painter, element)
        paint_text(painter, element)
    painter.restore()


def paint_page(painter: QPainter, page: Page, assets: dict[str, bytes], images: dict | None = None):
    painter.save()
    painter.setClipRect(QRectF(0, 0, page.width, page.height))
    painter.fillRect(QRectF(0, 0, page.width, page.height), Qt.GlobalColor.white)
    for element in page.elements:
        paint_element(painter, element, assets, images)
    painter.restore()


def thumbnail(page: Page, assets: dict[str, bytes], width=152) -> QImage:
    image = QImage(width, max(1, round(width * page.height / page.width)), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    painter.scale(width / page.width, width / page.width)
    paint_page(painter, page, assets)
    painter.end()
    return image


def export_pdf(document: Document, filename: str | Path):
    destination = Path(filename)
    handle, temporary = tempfile.mkstemp(prefix=".sop-export-", suffix=".pdf", dir=destination.parent)
    os.close(handle)
    try:
        writer = QPdfWriter(temporary)
        writer.setResolution(96)
        writer.setCreator("SOP Studio")
        writer.setTitle(document.title)
        writer.setPageMargins(QMarginsF(0, 0, 0, 0))

        def size(page):
            return QPageSize(QSizeF(page.width * 25.4 / 96, page.height * 25.4 / 96),
                             QPageSize.Unit.Millimeter, "SOP", QPageSize.SizeMatchPolicy.ExactMatch)

        writer.setPageSize(size(document.pages[0]))
        painter = QPainter()
        if not painter.begin(writer):
            raise OSError("无法创建 PDF 文件。")
        try:
            painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
            images = {}
            for index, page in enumerate(document.pages):
                if index:
                    writer.setPageSize(size(page))
                    if not writer.newPage():
                        raise OSError("无法写入 PDF 页面。")
                paint_page(painter, page, document.assets, images)
        finally:
            painter.end()
        del writer
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
