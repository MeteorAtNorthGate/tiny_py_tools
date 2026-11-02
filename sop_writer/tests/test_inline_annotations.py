"""Tapered arrows and real in-place text input, including IME and confirmation paths."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from copy import deepcopy

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sop_studio.annotations import AnnotationWindow, render_annotation
from sop_studio.style import apply_style


APP = QApplication.instance() or QApplication([])
apply_style(APP)


def flush():
    for _ in range(4):
        APP.processEvents()


class InlineAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.base = QImage(800, 440, QImage.Format.Format_RGB32)
        self.base.fill(QColor("#e2e8f0"))
        self.window = AnnotationWindow(self.base)
        self.window.show()
        flush()

    def tearDown(self):
        try:
            self.window.close()
        except RuntimeError:
            pass
        flush()

    def begin_text(self):
        window = self.window
        window.set_tool("text")
        start = window.canvas.mapFromScene(100, 80)
        end = window.canvas.mapFromScene(420, 160)
        QTest.mousePress(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window.canvas.viewport(), end, 10)
        flush()
        self.assertIsNone(window.canvas.inline_frame)
        self.assertEqual(window.canvas.current["kind"], "text")
        # The drag preview is only an outline, preserving the screenshot inside.
        inside = window.canvas.mapFromScene(240, 120)
        preview = window.canvas.viewport().grab().toImage()
        self.assertEqual(preview.pixelColor(inside), QColor("#e2e8f0"))
        QTest.mouseRelease(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        flush()
        self.assertIsNone(QApplication.activeModalWidget())
        self.assertIsNotNone(window.canvas.inline_frame)
        return window.canvas.inline_frame

    def test_new_arrow_is_between_arrow_and_pen_and_draws_a_tapered_solid_shape(self):
        window = self.window
        buttons = window.toolbar.tool_buttons
        self.assertLess(buttons["arrow"].x(), buttons["tapered_arrow"].x())
        self.assertLess(buttons["tapered_arrow"].x(), buttons["pen"].x())
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_B)
        self.assertEqual(window.canvas.tool, "tapered_arrow")
        window.toolbar.set_stroke(8)
        start = window.canvas.mapFromScene(40, 160)
        end = window.canvas.mapFromScene(300, 160)
        QTest.mousePress(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window.canvas.viewport(), end, 10)
        QTest.mouseRelease(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        operation = window.canvas.operations[0]
        self.assertEqual(operation["kind"], "tapered_arrow")
        rendered = render_annotation(self.base, [operation])
        self.assertEqual(rendered.pixelColor(80, 164), self.base.pixelColor(80, 164))
        self.assertNotEqual(rendered.pixelColor(200, 164), self.base.pixelColor(200, 164))
        self.assertNotEqual(rendered.pixelColor(260, 180), self.base.pixelColor(260, 180))
        window.canvas.undo()
        self.assertEqual(window.canvas.operations, [])
        window.canvas.redo()
        self.assertEqual(window.canvas.operations, [operation])

    def test_text_is_entered_in_place_without_triggering_letter_shortcuts(self):
        frame = self.begin_text()
        expected = "A B P M T R text with spaces"
        QTest.keyClicks(self.window.canvas.viewport(), expected)
        self.assertEqual(frame.text_item.toPlainText(), expected)
        self.assertEqual(self.window.canvas.tool, "text")
        self.assertEqual(self.window.canvas.operations, [])
        QTest.keyClick(self.window.canvas.viewport(), Qt.Key.Key_Return)
        flush()
        self.assertIsNone(self.window.canvas.inline_frame)
        self.assertTrue(self.window.isVisible())
        self.assertEqual(self.window.canvas.operations[0]["text"], expected)
        self.assertTrue(all(shortcut.isEnabled() for shortcut in self.window.tool_shortcuts))

    def test_chinese_ime_enter_does_not_confirm_an_unfinished_composition(self):
        frame = self.begin_text()
        frame.text_item.inputMethodEvent(QInputMethodEvent("zhongwen", []))
        self.assertTrue(frame.text_item.composing)
        QTest.keyClick(self.window.canvas.viewport(), Qt.Key.Key_Return)
        self.assertIs(self.window.canvas.inline_frame, frame)
        self.assertEqual(self.window.canvas.operations, [])
        event = QInputMethodEvent()
        event.setCommitString("中文操作步骤")
        frame.text_item.inputMethodEvent(event)
        self.assertFalse(frame.text_item.composing)
        QTest.keyClick(self.window.canvas.viewport(), Qt.Key.Key_Return)
        flush()
        self.assertEqual(self.window.canvas.operations[0]["text"], "中文操作步骤")

    def test_shift_enter_inserts_a_line_break_and_undo_stays_in_the_text_editor(self):
        frame = self.begin_text()
        viewport = self.window.canvas.viewport()
        QTest.keyClicks(viewport, "First line")
        QTest.keyClick(viewport, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClicks(viewport, "Second line")
        expected = frame.text_item.toPlainText()
        QTest.keyClick(viewport, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertIsNotNone(self.window.canvas.inline_frame)
        self.assertNotEqual(frame.text_item.toPlainText(), expected)
        QTest.keyClick(viewport, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(frame.text_item.toPlainText(), expected)
        QTest.keyClick(viewport, Qt.Key.Key_Return)
        flush()
        self.assertEqual(self.window.canvas.operations[0]["text"], "First line\nSecond line")

    def test_escape_discards_only_the_current_text_and_empty_enter_adds_nothing(self):
        self.begin_text()
        QTest.keyClicks(self.window.canvas.viewport(), "discard this")
        QTest.keyClick(self.window.canvas.viewport(), Qt.Key.Key_Escape)
        flush()
        self.assertTrue(self.window.isVisible())
        self.assertIsNone(self.window.canvas.inline_frame)
        self.assertEqual(self.window.canvas.operations, [])
        self.begin_text()
        QTest.keyClick(self.window.canvas.viewport(), Qt.Key.Key_Return)
        flush()
        self.assertEqual(self.window.canvas.operations, [])

    def test_styles_change_while_editing_and_the_dragged_box_bounds_are_preserved(self):
        frame = self.begin_text()
        bounds = deepcopy(frame.operation["points"])
        QTest.keyClicks(self.window.canvas.viewport(), "live styling")
        self.window.toolbar.set_font_size(32)
        self.window.set_color("#3b82f6")
        self.window.toolbar.set_stroke(6)
        self.assertEqual(frame.text_item.defaultTextColor(), QColor("#3b82f6"))
        self.assertEqual(frame.document.defaultFont().pixelSize(), 32)
        QTest.keyClick(self.window.canvas.viewport(), Qt.Key.Key_Return)
        operation = self.window.canvas.operations[0]
        self.assertEqual(operation["points"], bounds)
        self.assertEqual(operation["font_size"], 32)
        self.assertEqual(operation["color"], "#3b82f6")
        self.assertEqual(operation["width"], 6)

    def test_insert_commits_current_text_before_emitting_the_image(self):
        self.begin_text()
        QTest.keyClicks(self.window.canvas.viewport(), "Include this text")
        received = []
        operations = []
        self.window.image_ready.connect(received.append)
        self.window.image_ready.connect(lambda _: operations.extend(deepcopy(self.window.canvas.operations)))
        QTest.mouseClick(self.window.toolbar.insert_button, Qt.MouseButton.LeftButton)
        flush()
        self.assertEqual(operations[0]["text"], "Include this text")
        self.assertEqual(received[0], render_annotation(self.base, operations))

    def test_switching_tools_commits_text_before_drawing_the_next_annotation(self):
        self.begin_text()
        QTest.keyClicks(self.window.canvas.viewport(), "Keep this")
        QTest.mouseClick(self.window.toolbar.tool_buttons["tapered_arrow"], Qt.MouseButton.LeftButton)
        self.assertIsNone(self.window.canvas.inline_frame)
        self.assertEqual(self.window.canvas.operations[0]["text"], "Keep this")
        self.assertEqual(self.window.canvas.tool, "tapered_arrow")


if __name__ == "__main__":
    unittest.main()
