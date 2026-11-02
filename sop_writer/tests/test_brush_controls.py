"""Brush footprint, true freehand input, and exponential pointer / pixel keyboard control."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sop_studio.annotations import AnnotationWindow, render_annotation
from sop_studio.style import apply_style


APP = QApplication.instance() or QApplication([])
apply_style(APP)


def flush():
    for _ in range(4):
        APP.processEvents()


def checkerboard(width=200, height=200):
    base = QImage(width, height, QImage.Format.Format_RGB32)
    for y in range(height):
        for x in range(width):
            base.setPixelColor(x, y, QColor("white") if (x + y) % 2 else QColor("black"))
    return base


class MosaicBrushTests(unittest.TestCase):
    def test_mosaic_follows_bent_path_without_filling_its_rectangle(self):
        base = checkerboard()
        original = base.copy()
        operation = {"kind": "mosaic", "points": [[30, 30], [150, 30], [150, 150]], "color": "#ef4444", "width": 20}
        result = render_annotation(base, [operation])
        self.assertNotEqual(result.pixelColor(80, 30), base.pixelColor(80, 30))
        self.assertNotEqual(result.pixelColor(150, 90), base.pixelColor(150, 90))
        for point in [(80, 80), (30, 100), (100, 100), (180, 180)]:
            self.assertEqual(result.pixelColor(*point), base.pixelColor(*point))
        self.assertEqual(base, original)

    def test_single_click_is_round_and_has_brush_diameter(self):
        base = checkerboard()
        operation = {"kind": "mosaic", "points": [[80, 80]], "color": "#ef4444", "width": 20}
        result = render_annotation(base, [operation])
        self.assertNotEqual(result.pixelColor(80, 80), base.pixelColor(80, 80))
        self.assertNotEqual(result.pixelColor(88, 80), base.pixelColor(88, 80))
        self.assertEqual(result.pixelColor(92, 80), base.pixelColor(92, 80))
        self.assertEqual(result.pixelColor(89, 89), base.pixelColor(89, 89))

    def test_overlapping_strokes_use_the_same_pixel_grid(self):
        base = checkerboard()
        first = {"kind": "mosaic", "points": [[20, 50], [120, 50]], "color": "#ef4444", "width": 20}
        second = {"kind": "mosaic", "points": [[50, 20], [50, 120]], "color": "#3b82f6", "width": 10}
        one = render_annotation(base, [first])
        two = render_annotation(base, [first, second])
        self.assertEqual(one.pixelColor(50, 50), two.pixelColor(50, 50))
        self.assertEqual(one.pixelColor(80, 50), two.pixelColor(80, 50))


class BrushInteractionTests(unittest.TestCase):
    def setUp(self):
        self.window = AnnotationWindow(checkerboard())
        self.window.show()
        flush()

    def tearDown(self):
        self.window.close()
        flush()

    def test_mosaic_records_intermediate_points_and_supports_undo_redo(self):
        window = self.window
        window.set_tool("mosaic")
        window.toolbar.set_stroke(20)
        points = [(30, 30), (150, 30), (150, 150)]
        locations = [window.canvas.mapFromScene(*point) for point in points]
        QTest.mousePress(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=locations[0])
        QTest.mouseMove(window.canvas.viewport(), locations[1], 10)
        QTest.mouseRelease(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=locations[2])
        operation = window.canvas.operations[0]
        self.assertEqual(len(operation["points"]), 3)
        self.assertEqual(operation["width"], 20)
        result = render_annotation(window.canvas.base, window.canvas.operations)
        self.assertEqual(result.pixelColor(80, 80), window.canvas.base.pixelColor(80, 80))
        self.assertNotEqual(result.pixelColor(150, 100), window.canvas.base.pixelColor(150, 100))
        QTest.mouseClick(window.undo_button, Qt.MouseButton.LeftButton)
        self.assertEqual(window.canvas.operations, [])
        QTest.mouseClick(window.redo_button, Qt.MouseButton.LeftButton)
        self.assertEqual(window.canvas.operations, [operation])

    def test_slider_pointer_uses_exponential_scale_and_keeps_low_values_spaced(self):
        slider = self.window.toolbar.stroke_slider
        left, right = slider.track()
        y = 10
        for fraction, expected in [(0, 1), (.25, 3), (.5, 7), (.75, 19), (1, 50)]:
            QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=QPoint(round(left + (right - left) * fraction), y))
            self.assertEqual(slider.value(), expected)
            self.assertEqual(self.window.canvas.stroke, expected)
        low_span = slider.position_for_value(5) - slider.position_for_value(1)
        high_span = slider.position_for_value(50) - slider.position_for_value(46)
        self.assertGreater(low_span, high_span * 10)

    def test_keyboard_steps_are_one_pixel_and_clamp_to_endpoints(self):
        slider = self.window.toolbar.stroke_slider
        QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=QPoint(slider.width() - 15, 14))
        self.assertTrue(slider.hasFocus())
        for initial in (1, 4, 25, 49):
            slider.setValue(initial)
            QTest.keyClick(slider, Qt.Key.Key_Right)
            self.assertEqual(slider.value(), initial + 1)
            self.assertEqual(self.window.canvas.stroke, initial + 1)
            QTest.keyClick(slider, Qt.Key.Key_Left)
            self.assertEqual(slider.value(), initial)
        slider.setValue(1)
        QTest.keyClick(slider, Qt.Key.Key_Left)
        self.assertEqual(slider.value(), 1)
        slider.setValue(50)
        QTest.keyClick(slider, Qt.Key.Key_Right)
        self.assertEqual(slider.value(), 50)

    def test_slider_drag_does_not_move_the_frameless_window(self):
        slider = self.window.toolbar.stroke_slider
        before = self.window.pos()
        left, right = slider.track()
        QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=QPoint(round(left), 10))
        QTest.mouseMove(slider, QPoint(round(right), 10), 10)
        QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=QPoint(round(right), 10))
        self.assertEqual(slider.value(), 50)
        self.assertEqual(self.window.pos(), before)

    def test_fit_action_has_a_clear_label_and_restores_window_size(self):
        initial_width = self.window.width()
        self.window.zoom_window(1.4)
        flush()
        self.assertEqual(self.window.toolbar.fit_button.text(), "适应屏幕")
        QTest.mouseClick(self.window.toolbar.fit_button, Qt.MouseButton.LeftButton)
        flush()
        self.assertEqual(self.window.width(), initial_width)


if __name__ == "__main__":
    unittest.main()
