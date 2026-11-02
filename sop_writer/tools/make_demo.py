"""Generate a portable sample SOP and offscreen UI previews from synthetic content."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

from sop_studio.annotations import AnnotationWindow, render_annotation
from sop_studio.app import MainWindow
from sop_studio.document import Document, Element, Page, save_document
from sop_studio.rendering import export_pdf, image_bytes
from sop_studio.style import apply_style


def console_image():
    image = QImage(1120, 500, QImage.Format.Format_RGB32)
    image.fill(QColor("#f4f7fc"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(0, 0, 1120, 60, QColor("#20304a"))

    def text(x, y, value, size=20, color="#24354f", bold=False):
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(size)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(x, y, value)

    text(28, 38, "WORKSPACE    /    操作控制台", 22, "#ffffff", True)
    text(30, 113, "新建操作任务", 28, bold=True)
    text(30, 148, "按顺序填写以下参数，确认后提交。", 17, "#7b8ba3")
    for y, label, value in [(185, "任务名称", "月度设备巡检"), (280, "负责人", "操作人员 / 示例")]:
        text(32, y + 25, label, 18)
        painter.setPen(QPen(QColor("#dbe3ef")))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(160, y, 860, 55), 6, 6)
        text(180, y + 34, value, 19)
    painter.setBrush(QColor("#416fe8"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(840, 405, 180, 56), 7, 7)
    text(884, 441, "创建任务", 21, "#ffffff", True)
    painter.end()
    return image


def sample_document():
    original = console_image()
    annotated = render_annotation(original, [
        {"kind": "mosaic", "points": [[172, 286], [418, 327]], "width": 5, "color": "#ef4444"},
        {"kind": "rectangle", "points": [[155, 180], [1027, 246]], "width": 4, "color": "#ef4444"},
        {"kind": "arrow", "points": [[700, 360], [855, 423]], "width": 6, "color": "#ef4444"},
        {"kind": "text", "points": [[480, 300], [740, 352]], "width": 3, "color": "#e94b4b", "font_size": 23, "text": "确认信息后，点击这里"},
    ])
    document = Document(title="快速上手 · 创建操作任务", pages=[Page(), Page()])
    asset = document.add_asset(image_bytes(annotated))

    def text(value, y, size=24, bold=False, color="#26354d", height=64):
        return Element(text=value, x=64, y=y, width=832, height=height, font_size=size, bold=bold, color=color)

    document.pages[0].elements = [
        text("SOP  /  QUICK START                                      操作手册  001", 43, 16, True, "#5479c9", 40),
        text("创建操作任务", 103, 44, True, height=80),
        text("把操作过程写清楚，从一张截图开始。\n本示例可直接编辑，也可以新建一份自己的 SOP。", 205, 21, color="#78869b", height=100),
        text("01   填写任务信息", 337, 28, True, height=65),
        text("打开控制台，输入任务名称，并选择负责人。", 410, 21, height=50),
        Element(kind="image", asset=asset, x=64, y=492, width=832, height=832 * 500 / 1120),
        text("02   检查并提交", 918, 28, True, height=64),
        text("确认名称与负责人无误，点击右下角「创建任务」。\n截图中的箭头、文本框与马赛克都可以在标注窗口里快速完成。", 1004, 21, height=110),
        text("提示：双击文字直接修改；双击图片继续标注。", 1198, 18, color="#5479c9", height=50),
    ]
    document.pages[1].elements = [
        text("SOP  /  QUICK START                                             02", 43, 16, True, "#5479c9", 40),
        text("让每一步都清晰", 103, 40, True, height=80),
        text("你的快捷工作流", 238, 28, True),
        text("1.  Ctrl+1：框选需要说明的屏幕区域。\n\n2.  A / T / M / P：箭头、文字、马赛克、涂鸦。\n\n3.  Ctrl+Enter：插入当前文档。\n\n4.  拖动位置，拖右下角缩放。\n\n5.  Ctrl+S 保存；Ctrl+E 导出 PDF。", 338, 24, height=540),
        text("完成前检查", 944, 28, True),
        text("□  步骤是否按顺序排列？\n□  关键按钮是否清楚标记？\n□  隐私信息是否完成遮挡？\n□  是否保存了可继续编辑的 .sopx 文件？", 1034, 22, height=230),
    ]
    return document, original


def main():
    app = QApplication([])
    apply_style(app)
    examples = ROOT / "examples"
    examples.mkdir(exist_ok=True)
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    document, original = sample_document()
    path = examples / "快速上手.sopx"
    save_document(document, path)
    export_pdf(document, build / "快速上手.pdf")
    window = MainWindow(test_mode=True)
    window.load_path(path)
    window.show()
    for _ in range(5):
        app.processEvents()
    window.canvas.fit_width(window.active_page_id)
    window.canvas.go_to_page(window.active_page_id)
    app.processEvents()
    window.grab().save(str(build / "preview.png"))
    editor = AnnotationWindow(original)
    editor.canvas.operations = [
        {"kind": "arrow", "points": [[700, 360], [855, 423]], "width": 6, "color": "#ef4444"},
        {"kind": "rectangle", "points": [[155, 180], [1027, 246]], "width": 4, "color": "#ef4444"},
    ]
    editor.show()
    for _ in range(5):
        app.processEvents()
    editor.grab().save(str(build / "annotation-preview.png"))
    editor.close()
    window.close()
    print(f"Example: {path}")
    print(f"Previews: {build}")


if __name__ == "__main__":
    main()
