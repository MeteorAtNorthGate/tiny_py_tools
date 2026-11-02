"""Document data and portable, atomic .sopx persistence. No Qt dependency."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Element:
    kind: str = "text"
    id: str = field(default_factory=new_id)
    x: float = 56
    y: float = 56
    width: float = 640
    height: float = 100
    text: str = ""
    asset: str = ""
    font_family: str = "Microsoft YaHei UI"
    font_size: int = 24
    color: str = "#243247"
    bold: bool = False
    background: str = "transparent"
    text_stroke_color: str = "transparent"
    text_stroke_width: float = 1
    text_stroke_alignment: str = "outside"
    text_opacity: float = 1
    box_stroke_color: str = "transparent"
    box_stroke_width: float = 1
    box_opacity: float = 1


@dataclass
class Page:
    id: str = field(default_factory=new_id)
    width: int = 960
    height: int = 1360
    elements: list[Element] = field(default_factory=list)


@dataclass
class Document:
    title: str = "未命名 SOP"
    pages: list[Page] = field(default_factory=lambda: [Page()])
    assets: dict[str, bytes] = field(default_factory=dict)

    def add_asset(self, png: bytes) -> str:
        key = hashlib.sha256(png).hexdigest()
        self.assets[key] = png
        return key

    def find(self, element_id: str) -> tuple[Page, Element] | None:
        for page in self.pages:
            for element in page.elements:
                if element.id == element_id:
                    return page, element
        return None

    def used_assets(self) -> set[str]:
        return {e.asset for p in self.pages for e in p.elements if e.kind == "image"}


def _number(value, minimum: float, maximum: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and minimum <= value <= maximum


def validate(document: Document) -> None:
    if not isinstance(document.title, str) or len(document.title) > 1000:
        raise ValueError("文档名称不正确。")
    if not 1 <= len(document.pages) <= 200:
        raise ValueError("文档应包含 1～200 页。")
    seen = set()
    for page in document.pages:
        if not isinstance(page.id, str) or page.id in seen:
            raise ValueError("页面标识重复或无效。")
        seen.add(page.id)
        if not isinstance(page.width, int) or not isinstance(page.height, int) or not _number(page.width, 160, 12000) or not _number(page.height, 160, 12000):
            raise ValueError("页面尺寸应在 160～12000 像素之间。")
        if len(page.elements) > 2000:
            raise ValueError("单页元素数量过多。")
        for element in page.elements:
            if not isinstance(element.id, str) or element.id in seen or element.kind not in {"text", "image"}:
                raise ValueError("元素标识或类型无效。")
            seen.add(element.id)
            for value in (element.x, element.y):
                if not _number(value, -12000, 24000):
                    raise ValueError("元素坐标无效。")
            for value in (element.width, element.height):
                if not _number(value, 8, 24000):
                    raise ValueError("元素尺寸无效。")
            if not isinstance(element.font_size, int) or not _number(element.font_size, 6, 256):
                raise ValueError("字号无效。")
            if not isinstance(element.text, str) or len(element.text) > 400000:
                raise ValueError("文本内容无效或过长。")
            if not all(isinstance(v, str) for v in (element.font_family, element.color, element.background,
                                                    element.text_stroke_color, element.box_stroke_color)):
                raise ValueError("文字样式无效。")
            if element.text_stroke_alignment not in ("outside", "center", "inside"):
                raise ValueError("文字描边位置无效。")
            if any(not _number(value, 0, 1) for value in (element.text_opacity, element.box_opacity)):
                raise ValueError("不透明度应在 0～100% 之间。")
            if any(not _number(value, 0, 50) for value in (element.text_stroke_width, element.box_stroke_width)):
                raise ValueError("描边宽度应在 0～50 像素之间。")
            if element.kind == "image" and element.asset not in document.assets:
                raise ValueError("文档中的图片缺失。")


def save_document(document: Document, filename: str | Path) -> None:
    validate(document)
    destination = Path(filename)
    manifest = {"format": "sop-studio", "version": 1, "title": document.title,
                "pages": [asdict(page) for page in document.pages]}
    handle, temporary = tempfile.mkstemp(prefix=".sop-save-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(handle, "wb") as output:
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("document.json", json.dumps(manifest, ensure_ascii=False), compress_type=zipfile.ZIP_DEFLATED)
                for key in sorted(document.used_assets()):
                    archive.writestr(f"assets/{key}.png", document.assets[key])
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_document(filename: str | Path) -> Document:
    try:
        with zipfile.ZipFile(filename) as archive:
            entries = archive.infolist()
            if len(entries) > 5000 or sum(info.file_size for info in entries) > 512 * 1024 * 1024:
                raise ValueError("文档过大，无法打开。")
            if archive.getinfo("document.json").file_size > 16 * 1024 * 1024:
                raise ValueError("文档描述文件过大。")
            data = json.loads(archive.read("document.json"))
            if data.get("format") != "sop-studio" or data.get("version") != 1:
                raise ValueError("不支持此文档格式或版本。")
            pages = []
            for raw in data["pages"]:
                pages.append(Page(id=raw["id"], width=raw["width"], height=raw["height"],
                                  elements=[Element(**element) for element in raw["elements"]]))
            document = Document(title=data["title"], pages=pages)
            for key in document.used_assets():
                if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                    raise ValueError("图片资源名称无效。")
                content = archive.read(f"assets/{key}.png")
                if hashlib.sha256(content).hexdigest() != key or not content.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("图片资源校验失败。")
                document.assets[key] = content
        validate(document)
        return document
    except (KeyError, TypeError, AttributeError, zipfile.BadZipFile, json.JSONDecodeError, RuntimeError) as error:
        raise ValueError(f"文件损坏或不是有效的 SOP Studio 文档：{error}") from error
