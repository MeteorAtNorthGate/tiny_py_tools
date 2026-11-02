"""Inspector interactions and shared text effects, including independent alpha."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from types import SimpleNamespace
import unittest

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QInputMethodEvent, QPainter, QPainterPath, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QFontComboBox, QGraphicsScene, QLineEdit, QPushButton

from sop_studio.app import MainWindow
from sop_studio.canvas import ElementItem
from sop_studio.document import Element
from sop_studio.rendering import make_text_document, paint_element, text_glyph_path, text_stroke_paths
from sop_studio.style import apply_style


APP = QApplication.instance() or QApplication([])
apply_style(APP)


def flush():
    for _ in range(4):
        APP.processEvents()


def render(element):
    image = QImage(round(element.width), round(element.height), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing |
                           QPainter.RenderHint.SmoothPixmapTransform)
    paint_element(painter, element, {})
    painter.end()
    return image


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow(test_mode=True)
        self.window.show()
        self.window.activateWindow()
        flush()
        self.window.add_text("步骤 01：确认设备")
        flush()
        self.element_id = self.window.canvas.selected_id()

    def tearDown(self):
        APP.clipboard().clear()
        self.window.close()
        flush()

    def element(self):
        return self.window.controller.document.find(self.element_id)[1]

    def enter(self, widget, text):
        widget.setFocus()
        widget.selectAll()
        QTest.keyClick(widget, Qt.Key.Key_Backspace)
        QTest.keyClicks(widget, text)
        QTest.keyClick(widget, Qt.Key.Key_Return)
        flush()

    def test_direct_entries_replace_step_controls_and_obsolete_buttons(self):
        window = self.window
        self.assertEqual(window.element_panel.findChildren(QAbstractSpinBox), [])
        for control in [*window.geometry_inputs.values(), window.font_size, *window.text_effect_inputs.values()]:
            self.assertIsInstance(control, QLineEdit)
            self.assertGreater(control.width(), 60)
        self.assertIsInstance(window.font_family, QFontComboBox)
        for button in window.element_panel.findChildren(QPushButton):
            self.assertFalse(any(label in button.text() for label in ("编辑文字", "复制元素", "删除元素")))
        self.enter(window.geometry_inputs["x"], "123.4")
        self.assertEqual(self.element().x, 123.4)
        self.enter(window.font_size, "37")
        self.assertEqual(self.element().font_size, 37)

    def test_scrolling_a_number_does_not_change_the_value(self):
        control = self.window.font_size
        before = control.value()
        event = QWheelEvent(QPointF(20, 10), QPointF(control.mapToGlobal(control.rect().center())),
                            QPoint(), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        APP.sendEvent(control, event)
        self.assertEqual(control.value(), before)
        self.assertEqual(self.element().font_size, before)

    def test_color_stroke_position_and_opacity_commit_and_undo(self):
        window = self.window
        for field, value in [("color", "#123456"), ("text_stroke_color", "#3478ef"),
                             ("background", "#eef2fa"), ("box_stroke_color", "#345678")]:
            self.enter(window.text_color_inputs[field].entry, value)
            self.assertEqual(getattr(self.element(), field), value)
        for field, value in [("text_stroke_width", "2.5"), ("box_stroke_width", "4.0"), ("text_opacity", "65")]:
            self.enter(window.text_effect_inputs[field], value)
        window.text_stroke_alignment.setCurrentIndex(2)
        flush()
        self.assertEqual(self.element().text_stroke_alignment, "inside")
        self.assertEqual(self.element().text_stroke_width, 2.5)
        self.assertEqual(self.element().box_stroke_width, 4)
        self.assertEqual(self.element().text_opacity, .65)
        self.enter(window.text_effect_inputs["box_opacity"], "35")
        self.assertEqual(self.element().box_opacity, .35)
        window.undo()
        flush()
        self.assertEqual(self.element().box_opacity, 1)
        self.assertEqual(self.element().text_opacity, .65)
        window.redo()
        flush()
        self.assertEqual(window.text_effect_inputs["box_opacity"].value(), 35)
        self.enter(window.text_color_inputs["background"].entry, "")
        self.assertEqual(self.element().background, "transparent")
        self.enter(window.text_color_inputs["color"].entry, "invalid-color")
        self.assertEqual(self.element().color, "#123456")

    def test_ctrl_j_duplicates_all_styles_and_delete_can_be_undone(self):
        window = self.window
        for field, value in {"text_stroke_color": "#3366ee", "text_stroke_width": 2.5,
                             "text_stroke_alignment": "center", "text_opacity": .7,
                             "background": "#ddeecc", "box_stroke_color": "#aabbcc",
                             "box_stroke_width": 3, "box_opacity": .4}.items():
            window.apply_text_effect(field, value)
        flush()
        original = replace(self.element())
        window.canvas.setFocus()
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_J, Qt.KeyboardModifier.ControlModifier)
        flush()
        self.assertEqual(len(window.current_page().elements), 2)
        copied = window.selected()[1]
        self.assertEqual(copied, replace(original, id=copied.id, x=original.x + 24, y=original.y + 24))
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
        flush()
        self.assertEqual(len(window.current_page().elements), 2)
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Delete)
        flush()
        self.assertEqual(len(window.current_page().elements), 1)
        window.undo()
        flush()
        self.assertEqual(window.current_page().elements[-1], copied)

    def test_enter_edits_styled_text_in_place_and_ime_preserves_styles(self):
        window = self.window
        window.apply_text_effect("text_stroke_color", "#3268df")
        window.apply_text_effect("text_opacity", .7)
        flush()
        window.canvas.setFocus()
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Return)
        item = window.canvas.editing_item()
        self.assertIsNotNone(item)
        event = QInputMethodEvent("新增", [])
        window.canvas.scene().sendEvent(item.text_item, event)
        self.assertTrue(item.text_item.composing)
        event = QInputMethodEvent()
        event.setCommitString("新增文字")
        window.canvas.scene().sendEvent(item.text_item, event)
        self.assertFalse(item.text_item.composing)
        # Painting the active editor exercises the same effects with its caret.
        window.grab()
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        flush()
        self.assertIsNone(window.canvas.editing_item())
        self.assertTrue(self.element().text.endswith("新增文字"))
        self.assertEqual(self.element().text_stroke_color, "#3268df")
        self.assertEqual(self.element().text_opacity, .7)

    def test_styled_text_grows_while_typing_so_new_lines_remain_visible(self):
        window = self.window
        window.apply_text_effect("text_stroke_color", "#3268df")
        flush()
        window.canvas.setFocus()
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_F2)
        item = window.canvas.editing_item()
        original_height = item.height
        cursor = item.text_item.textCursor()
        cursor.insertText("\n第二步\n第三步\n第四步\n第五步")
        item.text_item.setTextCursor(cursor)
        flush()
        self.assertGreater(item.height, original_height)
        self.assertGreaterEqual(item.height, item.text_item.document().size().height())
        self.assertEqual(self.element().height, original_height)
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        flush()
        self.assertGreater(self.element().height, original_height)


class TextEffectRenderingTests(unittest.TestCase):
    def test_outline_regions_have_the_requested_inner_and_outer_width(self):
        glyph = QPainterPath()
        glyph.addRect(QRectF(20, 20, 40, 40))
        outer_fill, outer = text_stroke_paths(glyph, 4, "outside")
        center_fill, center = text_stroke_paths(glyph, 4, "center")
        inner_fill, inner = text_stroke_paths(glyph, 4, "inside")
        self.assertTrue(outer.contains(QPointF(17, 40)))
        self.assertFalse(outer.contains(QPointF(22, 40)))
        self.assertTrue(center.contains(QPointF(19, 40)))
        self.assertTrue(center.contains(QPointF(21, 40)))
        self.assertFalse(center.contains(QPointF(17, 40)))
        self.assertTrue(inner.contains(QPointF(23, 40)))
        self.assertFalse(inner.contains(QPointF(19, 40)))
        self.assertTrue(outer_fill.contains(QPointF(21, 40)))
        self.assertFalse(center_fill.contains(QPointF(21, 40)))
        self.assertFalse(inner_fill.contains(QPointF(23, 40)))
        self.assertTrue(inner_fill.contains(QPointF(26, 40)))

    def test_shaped_glyphs_include_wrapped_chinese_and_new_paragraphs(self):
        element = Element(text="ABC 中文步骤\n确认设备与参数", width=120, font_size=32, font_family="Segoe UI")
        document = make_text_document(element)
        glyphs = text_glyph_path(document)
        self.assertFalse(glyphs.isEmpty())
        self.assertGreater(glyphs.boundingRect().height(), 80)
        self.assertLessEqual(glyphs.boundingRect().right(), element.width)
        self.assertGreater(glyphs.elementCount(), 100)

    def test_partial_text_opacity_composites_fill_and_outline_once(self):
        element = Element(x=0, y=0, width=260, height=100, text="Aa 描边", font_size=40,
                          color="#ff0000", text_stroke_color="#0000ff", text_stroke_width=3,
                          text_opacity=.5)
        for alignment in ("outside", "center", "inside"):
            with self.subTest(alignment=alignment):
                image = render(replace(element, text_stroke_alignment=alignment))
                pixels = [image.pixelColor(x, y) for y in range(image.height()) for x in range(image.width())]
                self.assertLessEqual(max(color.alpha() for color in pixels), 128)
                self.assertGreaterEqual(max(color.alpha() for color in pixels), 125)
                self.assertTrue(any(color.blue() > 200 and color.alpha() > 100 for color in pixels))
                if alignment != "inside":
                    self.assertTrue(any(color.red() > 200 and color.alpha() > 100 for color in pixels))

    def test_text_and_box_opacity_are_independent_and_border_does_not_stack(self):
        element = Element(x=0, y=0, width=200, height=100, text="Test", font_size=36, color="#00ff00",
                          text_opacity=0, background="#ff0000", box_stroke_color="#0000ff",
                          box_stroke_width=6, box_opacity=.5)
        image = render(element)
        self.assertEqual(image.pixelColor(2, 2).blue(), 255)
        self.assertEqual(image.pixelColor(80, 50).red(), 255)
        self.assertAlmostEqual(image.pixelColor(2, 2).alpha(), 128, delta=1)
        self.assertEqual(image.pixelColor(2, 2).alpha(), image.pixelColor(80, 50).alpha())
        text_only = render(replace(element, text_opacity=1, box_opacity=0))
        self.assertEqual(text_only.pixelColor(2, 2).alpha(), 0)
        self.assertTrue(any(text_only.pixelColor(x, y).green() == 255 and text_only.pixelColor(x, y).alpha() > 200
                            for y in range(60) for x in range(100)))

    def test_canvas_uses_the_same_text_and_frame_painting_as_export(self):
        element = Element(x=0, y=0, width=260, height=130, text="文字 Test\n第二行", font_size=32,
                          text_stroke_color="#3366ee", text_stroke_width=2, text_opacity=.65,
                          background="#f0ddcc", box_stroke_color="#cc5533", box_stroke_width=3, box_opacity=.45)
        expected = render(element)
        scene = QGraphicsScene()
        item = ElementItem(element, "page", QPointF(), SimpleNamespace(image_cache={}))
        scene.addItem(item)
        image = QImage(expected.size(), expected.format())
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing |
                               QPainter.RenderHint.SmoothPixmapTransform)
        bounds = QRectF(0, 0, element.width, element.height)
        scene.render(painter, bounds, bounds)
        painter.end()
        self.assertEqual(image, expected)


if __name__ == "__main__":
    unittest.main()
