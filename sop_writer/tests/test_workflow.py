"""Exercise real Qt widgets and renderers without touching the user's desktop."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sop_studio.annotations import AnnotationWindow, render_annotation
from sop_studio.app import MainWindow
from sop_studio.capture import GlobalHotkey
from sop_studio.document import Document, Element, Page, load_document, save_document
from sop_studio.rendering import export_pdf, image_bytes, thumbnail
from sop_studio.style import apply_style


APP = QApplication.instance() or QApplication([])
apply_style(APP)


def flush():
    for _ in range(4):
        APP.processEvents()


def sample_image(width=600, height=320):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#eff4ff"))
    painter = QPainter(image)
    painter.fillRect(20, 20, 200, 80, QColor("#356fe8"))
    painter.end()
    return image


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow(test_mode=True)
        self.window.show()
        flush()
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        # Qt's Windows offscreen clipboard must release Python-owned QMimeData
        # before QApplication is destroyed (the native Windows backend differs).
        APP.clipboard().clear()
        self.window.close()
        flush()
        self.directory.cleanup()

    def test_image_and_text_save_reload_undo_redo(self):
        window = self.window
        window.add_text("步骤 01：打开控制台")
        flush()
        window.insert_image(sample_image())
        flush()
        self.assertEqual(len(window.current_page().elements), 2)
        selected_id = window.canvas.selected_id()
        window.nudge(10, 20)
        flush()
        after = window.controller.document.find(selected_id)[1].x
        window.undo()
        flush()
        self.assertEqual(window.controller.document.find(selected_id)[1].x, after - 10)
        window.redo()
        flush()
        self.assertEqual(window.controller.document.find(selected_id)[1].x, after)
        path = Path(self.directory.name) / "完整流程.sopx"
        self.assertTrue(window.write_path(path))
        self.assertTrue(window.controller.undo_stack.isClean())
        self.assertTrue(window.load_path(path))
        flush()
        self.assertEqual(window.current_page().elements[0].text, "步骤 01：打开控制台")
        self.assertEqual(len(window.controller.document.assets), 1)

    def test_inline_text_commits_with_control_enter_without_adding_page(self):
        window = self.window
        window.add_text()
        flush()
        editing = window.canvas.editing_item()
        self.assertIsNotNone(editing)
        cursor = editing.text_item.textCursor()
        cursor.insertText("检查电源\n启动设备")
        editing.text_item.setTextCursor(cursor)
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        flush()
        self.assertIsNone(window.canvas.editing_item())
        self.assertEqual(len(window.controller.document.pages), 1)
        self.assertEqual(window.current_page().elements[0].text, "检查电源\n启动设备")

    def test_resize_handle_preserves_image_ratio_and_persists(self):
        window = self.window
        window.insert_image(sample_image())
        flush()
        item = window.canvas.items_by_id[window.canvas.selected_id()]
        start = window.canvas.mapFromScene(item.mapToScene(QPointF(item.width - 2, item.height - 2)))
        end = start + QPoint(60, 20)
        QTest.mousePress(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window.canvas.viewport(), end, 20)
        QTest.mouseRelease(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        flush()
        element = window.current_page().elements[0]
        self.assertGreater(element.width, 600)
        self.assertAlmostEqual(element.width / element.height, 600 / 320, places=3)

    def test_next_screenshot_flows_to_new_page_and_undo_restores(self):
        window = self.window
        window.current_page().height = 400
        window.insert_image(sample_image())
        flush()
        window.insert_image(sample_image())
        flush()
        self.assertEqual(len(window.controller.document.pages), 2)
        self.assertEqual([len(p.elements) for p in window.controller.document.pages], [1, 1])
        window.undo()
        flush()
        self.assertEqual(len(window.controller.document.pages), 1)

    def test_clipboard_copy_is_portable_between_document_replacements(self):
        window = self.window
        window.insert_image(sample_image())
        flush()
        window.copy_selected()
        window.controller.replace(Document())
        flush()
        window.paste()
        flush()
        element = window.current_page().elements[0]
        self.assertEqual(element.kind, "image")
        self.assertFalse(QImage.fromData(window.controller.document.assets[element.asset]).isNull())

    def test_page_copy_reorders_and_gives_unique_element_ids(self):
        window = self.window
        window.add_text("第一步")
        flush()
        window.duplicate_page()
        flush()
        pages = window.controller.document.pages
        self.assertNotEqual(pages[0].elements[0].id, pages[1].elements[0].id)
        copied_id = pages[1].id
        window.move_page(-1)
        flush()
        self.assertEqual(window.controller.document.pages[0].id, copied_id)

    def test_floating_annotation_insert_updates_existing_image(self):
        window = self.window
        window.insert_image(sample_image())
        flush()
        element_id = window.canvas.selected_id()
        original = window.controller.document.find(element_id)[1].asset
        window.annotate_element(element_id)
        flush()
        editor = window.annotation
        self.assertTrue(editor.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        editor.canvas.operations.append({"kind": "arrow", "points": [[250, 160], [80, 60]], "color": "#ef4444", "width": 5})
        editor.insert()
        flush()
        self.assertIsNone(window.annotation)
        self.assertNotEqual(window.controller.document.find(element_id)[1].asset, original)
        self.assertEqual(len(window.current_page().elements), 1)
        window.undo()
        flush()
        self.assertEqual(window.controller.document.find(element_id)[1].asset, original)


class RenderingTests(unittest.TestCase):
    def test_mosaic_changes_pixels_without_mutating_original(self):
        base = QImage(120, 120, QImage.Format.Format_RGB32)
        for y in range(120):
            for x in range(120):
                base.setPixelColor(x, y, QColor("white") if (x + y) % 2 else QColor("black"))
        original = base.copy()
        result = render_annotation(base, [{"kind": "mosaic", "points": [[10, 10], [110, 110]], "color": "#ef4444", "width": 6}])
        self.assertEqual(base, original)
        self.assertNotEqual(result, original.convertToFormat(result.format()))
        self.assertEqual(result.pixelColor(0, 0), original.pixelColor(0, 0))
        self.assertEqual(result.pixelColor(40, 40), result.pixelColor(41, 40))

    def test_all_annotation_tools_produce_visible_content(self):
        base = sample_image()
        for kind in ["arrow", "text", "pen", "rectangle"]:
            with self.subTest(tool=kind):
                operation = {"kind": kind, "points": [[240, 130], [450, 250]], "color": "#ef4444", "width": 4, "text": "点击确认", "font_size": 24}
                result = render_annotation(base, [operation])
                self.assertNotEqual(image_bytes(result), image_bytes(base))

    def test_pdf_has_mixed_sizes_and_thumbnail_clips_off_page_content(self):
        document = Document(title="导出验证", pages=[Page(width=960, height=1360), Page(width=1200, height=600)])
        document.pages[0].elements = [Element(text="第一步：确认参数", bold=True), Element(text="第二步：提交", y=150)]
        key = document.add_asset(image_bytes(sample_image()))
        document.pages[1].elements = [Element(kind="image", asset=key, x=100, y=100, width=600, height=320)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "中文导出.pdf"
            export_pdf(document, path)
            content = path.read_bytes()
            self.assertTrue(content.startswith(b"%PDF-"))
            self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", content)), 2)
            boxes = re.findall(rb"/MediaBox\s*\[([^\]]+)\]", content)
            self.assertEqual(len(boxes), 2)
            sizes = [[float(value) for value in box.split()] for box in boxes]
            self.assertAlmostEqual(sizes[0][2], 720, delta=1)
            self.assertAlmostEqual(sizes[0][3], 1020, delta=1)
            self.assertAlmostEqual(sizes[1][2], 900, delta=1)
            self.assertAlmostEqual(sizes[1][3], 450, delta=1)
        self.assertFalse(thumbnail(document.pages[1], document.assets).isNull())

    def test_hotkey_validation(self):
        self.assertEqual(GlobalHotkey.parse("Ctrl+1"), (0x4002, ord("1")))
        self.assertEqual(GlobalHotkey.parse("Alt+Shift+F2"), (0x4005, 0x71))
        for sequence in ["1", "Ctrl+Left", "Ctrl+K, Ctrl+C", "", "Meta+Shift+S"]:
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                GlobalHotkey.parse(sequence)


if __name__ == "__main__":
    unittest.main()
