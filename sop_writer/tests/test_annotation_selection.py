"""Auto-width click text and selection-only deletion in the screenshot editor."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sop_studio.annotation_text import annotation_text_box, make_annotation_text
from sop_studio.annotations import AnnotationWindow, render_annotation
from sop_studio.style import apply_style


APP = QApplication.instance() or QApplication([])
apply_style(APP)


def flush():
    for _ in range(4):
        APP.processEvents()


def mark(kind="rectangle", points=None, **extra):
    return {"kind": kind, "points": points or [[80, 80], [300, 180]],
            "color": "#ef4444", "width": 4, "font_size": 24, **extra}


def visual_lines(document):
    document.size()
    count = 0
    block = document.begin()
    while block.isValid():
        count += block.layout().lineCount()
        block = block.next()
    return count


class AnnotationSelectionTests(unittest.TestCase):
    def setUp(self):
        self.base = QImage(800, 440, QImage.Format.Format_RGB32)
        self.base.fill(QColor("#e2e8f0"))
        self.window = AnnotationWindow(self.base)
        self.window.show()
        self.window.activateWindow()
        flush()

    def tearDown(self):
        try:
            self.window.close()
        except RuntimeError:
            pass
        flush()

    def click(self, x, y):
        canvas = self.window.canvas
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(x, y))
        flush()

    def drag(self, start, end):
        canvas = self.window.canvas
        first, last = canvas.mapFromScene(*start), canvas.mapFromScene(*end)
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=first)
        QTest.mouseMove(canvas.viewport(), last, 10)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=last)
        flush()

    def key(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        QTest.keyClick(self.window.canvas.viewport(), key, modifiers)
        flush()

    def click_text(self):
        self.window.set_tool("text")
        self.click(80, 70)
        return self.window.canvas.inline_frame

    def test_click_text_keeps_its_initial_size_then_grows_without_wrapping(self):
        canvas = self.window.canvas
        frame = self.click_text()
        initial_width, initial_height = frame.box.width(), frame.box.height()
        self.assertEqual(initial_width, 260)
        for actual, expected in zip(frame.operation["points"], [[80, 70], [340, 126]]):
            self.assertAlmostEqual(actual[0], expected[0], delta=1)
            self.assertAlmostEqual(actual[1], expected[1], delta=1)
        initial_position = frame.box.topLeft()
        self.assertTrue(frame.operation["auto_width"])
        QTest.keyClicks(canvas.viewport(), "Auto width text with spaces, longer than the original box")
        flush()
        self.assertGreater(frame.box.width(), initial_width)
        self.assertEqual(frame.box.height(), initial_height)
        self.assertEqual(visual_lines(frame.document), 1)
        self.assertEqual(frame.box.topLeft(), initial_position)
        expected_box = frame.box
        self.key(Qt.Key.Key_Return)
        operation = canvas.operations[0]
        self.assertEqual(annotation_text_box(operation, make_annotation_text(operation)), expected_box)

    def test_click_text_wraps_only_at_shift_enter_and_shrinks_back_to_initial_width(self):
        frame = self.click_text()
        viewport = self.window.canvas.viewport()
        initial_height = frame.box.height()
        QTest.keyClicks(viewport, "A long line that expands the original text box to the right")
        self.key(Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClicks(viewport, "second line V")
        flush()
        self.assertEqual(visual_lines(frame.document), 2)
        self.assertGreater(frame.box.height(), initial_height)
        self.assertEqual(self.window.canvas.tool, "text")
        self.key(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_Backspace)
        self.assertEqual(frame.box.width(), 260)
        self.assertEqual(frame.box.height(), initial_height)
        QTest.keyClicks(viewport, "First")
        self.key(Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClicks(viewport, "Second")
        self.key(Qt.Key.Key_Return)
        self.assertEqual(self.window.canvas.operations[0]["text"], "First\nSecond")

    def test_dragged_text_still_wraps_at_the_selected_width(self):
        canvas = self.window.canvas
        self.window.set_tool("text")
        self.drag((80, 70), (240, 120))
        frame = canvas.inline_frame
        self.assertFalse(frame.operation["auto_width"])
        QTest.keyClicks(canvas.viewport(), "This long text still wraps inside the dragged text box")
        flush()
        self.assertAlmostEqual(frame.box.width(), 160, delta=1)
        self.assertGreater(visual_lines(frame.document), 1)
        expected_box = frame.box
        self.key(Qt.Key.Key_Return)
        self.assertEqual(annotation_text_box(canvas.operations[0], make_annotation_text(canvas.operations[0])), expected_box)

    def test_selection_tool_and_both_delete_keys_work_for_every_annotation_kind(self):
        canvas = self.window.canvas
        for kind, point in [("rectangle", (80, 130)), ("arrow", (300, 180)),
                            ("tapered_arrow", (300, 180)), ("pen", (190, 80)),
                            ("mosaic", (190, 80)), ("text", (190, 130))]:
            with self.subTest(kind=kind):
                operation = mark(kind, text="Annotation")
                if kind in ("pen", "mosaic"):
                    operation["points"] = [[80, 80], [300, 80], [300, 180]]
                canvas.operations = [operation]
                self.window.set_tool("select")
                self.click(*point)
                self.assertEqual(canvas.selected_index, 0)
                self.assertIsNone(canvas.current)
                self.assertTrue(all(shortcut.isEnabled() for shortcut in self.window.delete_shortcuts))
                self.key(Qt.Key.Key_Delete)
                self.assertEqual(canvas.operations, [])
                self.assertTrue(self.window.undo_button.isEnabled())
                canvas.undo()
                self.assertEqual(canvas.operations, [operation])
                self.click(*point)
                self.key(Qt.Key.Key_Backspace)
                self.assertEqual(canvas.operations, [])

    def test_freehand_and_hollow_rectangle_hit_tests_do_not_select_empty_interiors(self):
        canvas = self.window.canvas
        for operation in [mark("rectangle"), mark("pen", [[80, 80], [300, 80], [300, 180]]),
                          mark("mosaic", [[80, 80], [300, 80], [300, 180]])]:
            with self.subTest(kind=operation["kind"]):
                canvas.operations = [operation]
                self.window.set_tool("select")
                self.click(180, 130)
                self.assertIsNone(canvas.selected_index)
                self.key(Qt.Key.Key_Delete)
                self.assertEqual(canvas.operations, [operation])

    def test_overlap_selects_the_topmost_annotation_and_empty_click_clears_selection(self):
        canvas = self.window.canvas
        bottom = mark("pen", [[80, 110], [350, 110]], width=20)
        top = mark("text", text="On top")
        canvas.operations = [bottom, top]
        self.key(Qt.Key.Key_V)
        self.assertEqual(canvas.tool, "select")
        self.click(190, 110)
        self.assertEqual(canvas.selected_index, 1)
        self.key(Qt.Key.Key_Delete)
        self.assertEqual(canvas.operations, [bottom])
        canvas.undo()
        self.assertEqual(canvas.operations, [bottom, top])
        self.click(190, 110)
        self.click(600, 300)
        self.assertIsNone(canvas.selected_index)
        self.assertTrue(all(not shortcut.isEnabled() for shortcut in self.window.delete_shortcuts))

    def test_delete_only_operates_in_selection_mode_and_never_removes_text_while_typing(self):
        canvas = self.window.canvas
        operation = mark("rectangle")
        canvas.operations = [operation]
        self.key(Qt.Key.Key_Delete)
        self.key(Qt.Key.Key_Backspace)
        self.assertEqual(canvas.operations, [operation])
        self.window.set_tool("select")
        self.click(80, 130)
        self.window.set_tool("pen")
        self.assertIsNone(canvas.selected_index)
        self.key(Qt.Key.Key_Delete)
        self.assertEqual(canvas.operations, [operation])
        frame = self.click_text()
        QTest.keyClicks(canvas.viewport(), "ABC")
        self.key(Qt.Key.Key_Backspace)
        self.assertEqual(frame.text_item.toPlainText(), "AB")
        self.key(Qt.Key.Key_Home)
        self.key(Qt.Key.Key_Delete)
        self.assertEqual(frame.text_item.toPlainText(), "B")
        self.assertEqual(canvas.operations, [operation])
        self.assertIs(canvas.inline_frame, frame)

    def test_deleting_a_middle_element_and_undo_redo_preserve_stack_order(self):
        canvas = self.window.canvas
        operations = [mark("rectangle", [[30, 30], [180, 90]]),
                      mark("text", [[240, 100], [430, 170]], text="Middle"),
                      mark("arrow", [[500, 200], [700, 260]])]
        for operation in operations:
            canvas.change_operations(canvas.operations + [operation])
        self.window.set_tool("select")
        self.click(300, 130)
        self.key(Qt.Key.Key_Delete)
        self.assertEqual(canvas.operations, [operations[0], operations[2]])
        for expected in [operations, operations[:2], operations[:1], []]:
            self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(canvas.operations, expected)
        for expected in [operations[:1], operations[:2], operations, [operations[0], operations[2]]]:
            self.key(Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(canvas.operations, expected)
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.window.set_tool("pen")
        self.drag((500, 350), (700, 350))
        self.assertEqual(canvas.redo_states, [])
        self.assertFalse(self.window.redo_button.isEnabled())

    def test_selected_text_is_not_reopened_or_moved_by_clicking_and_dragging(self):
        canvas = self.window.canvas
        operation = mark("text", text="Completed text")
        canvas.operations = [operation]
        original = deepcopy(operation)
        self.window.set_tool("select")
        self.click(150, 130)
        QTest.mouseDClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(150, 130))
        self.drag((150, 130), (200, 150))
        self.assertIsNone(canvas.inline_frame)
        self.assertIsNone(canvas.current)
        self.assertEqual(canvas.operations, [original])
        self.assertEqual(canvas.selected_index, 0)

    def test_selection_follows_zoom_and_is_excluded_from_the_inserted_image(self):
        canvas = self.window.canvas
        operation = mark("text", [[80, 70], [340, 118]], text="This text extends beyond the initial width", auto_width=True)
        canvas.operations = [operation]
        self.window.set_tool("select")
        self.window.zoom_window(.7)
        flush()
        box = annotation_text_box(operation, make_annotation_text(operation))
        self.assertGreater(box.width(), 260)
        self.click(min(750, box.right() - 10), 90)
        self.assertEqual(canvas.selected_index, 0)
        expected = render_annotation(self.base, [operation])
        received = []
        self.window.image_ready.connect(received.append)
        QTest.mouseClick(self.window.toolbar.insert_button, Qt.MouseButton.LeftButton)
        flush()
        self.assertEqual(received, [expected])

    def test_delete_shortcuts_remain_available_when_toolbar_has_focus(self):
        canvas = self.window.canvas
        canvas.operations = [mark("rectangle")]
        self.window.set_tool("select")
        self.click(80, 130)
        self.window.toolbar.stroke_slider.setFocus()
        QTest.keyClick(self.window.toolbar.stroke_slider, Qt.Key.Key_Backspace)
        flush()
        self.assertEqual(canvas.operations, [])

    def test_selection_tool_fits_in_the_toolbar_of_a_small_screenshot(self):
        self.window.resize(360, self.window.height())
        flush()
        button = self.window.toolbar.tool_buttons["select"]
        self.assertTrue(self.window.rect().contains(button.mapTo(self.window, QPoint())))
        for control in [*self.window.toolbar.tool_buttons.values(), self.window.undo_button,
                        self.window.redo_button, self.window.toolbar.insert_button]:
            self.assertTrue(self.window.rect().contains(control.mapTo(self.window, control.rect().bottomRight())))


if __name__ == "__main__":
    unittest.main()
