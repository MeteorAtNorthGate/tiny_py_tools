"""Shared text, preview and PDF rendering, in document pixels at 96 DPI."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageSize, QPainter, QPdfWriter, QTextDocument, QTextOption

from .document import Document, Element, Page


def image_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("无法编码图片。")
    return bytes(data)


def make_text_document(element: Element) -> QTextDocument:
    text = QTextDocument()
    text.setDocumentMargin(5)
    font = QFont(element.font_family)
    font.setPixelSize(element.font_size)
    font.setBold(element.bold)
    text.setDefaultFont(font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    text.setDefaultTextOption(option)
    text.setPlainText(element.text)
    text.setTextWidth(element.width)
    return text


def paint_element(painter: QPainter, element: Element, assets: dict[str, bytes], images: dict | None = None):
    painter.save()
    painter.translate(element.x, element.y)
    bounds = QRectF(0, 0, element.width, element.height)
    painter.setClipRect(bounds)
    if element.background != "transparent":
        painter.fillRect(bounds, QColor(element.background))
    if element.kind == "image":
        if images is not None and element.asset in images:
            image = images[element.asset]
        else:
            image = QImage.fromData(assets.get(element.asset, b""))
            if images is not None:
                images[element.asset] = image
        painter.drawImage(bounds, image)
    else:
        text = make_text_document(element)
        from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.ColorRole.Text, QColor(element.color))
        text.documentLayout().draw(painter, context)
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
