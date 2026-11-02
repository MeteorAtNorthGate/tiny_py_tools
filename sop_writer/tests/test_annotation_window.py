"""Verify frameless controls remain usable and image coordinates stay intact."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sop_studio.annotations import AnnotationWindow
from sop_studio.style import apply_style


APP = QApplication.instance() or QApplication([])
apply_style(APP)


def flush():
    for _ in range(4):
        APP.processEvents()


class AnnotationWindowTests(unittest.TestCase):
    def setUp(self):
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            try:
                window.close()
            except RuntimeError:  # WA_DeleteOnClose may already have disposed it.
                pass
        flush()

    def editor(self, width=800, height=400):
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        window = AnnotationWindow(image)
        self.windows.append(window)
        window.show()
        flush()
        return window

    def test_image_meets_window_edges_and_close_button_replaces_title_bar(self):
        window = self.editor()
        self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertEqual(window.canvas.geometry().topLeft(), QPoint(0, 0))
        self.assertEqual(window.canvas.width(), window.width())
        self.assertEqual(window.canvas.mapFromScene(0, 0), QPoint(0, 0))
        self.assertEqual(window.toolbar.y(), window.canvas.height())
        self.assertEqual(window.toolbar.geometry().bottom(), window.height() - 1)
        rejected = []
        window.rejected.connect(lambda: rejected.append(True))
        QTest.mouseClick(window.toolbar.close_button, Qt.MouseButton.LeftButton)
        flush()
        self.assertEqual(rejected, [True])

    def test_zoomed_drawing_and_insert_keep_original_image_coordinates_and_size(self):
        window = self.editor()
        window.zoom_window(.8)
        flush()
        start = window.canvas.mapFromScene(100, 100)
        end = window.canvas.mapFromScene(400, 200)
        QTest.mousePress(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window.canvas.viewport(), end, 10)
        QTest.mouseRelease(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertTrue(window.undo_button.isEnabled())
        QTest.mouseClick(window.undo_button, Qt.MouseButton.LeftButton)
        self.assertEqual(window.canvas.operations, [])
        QTest.mouseClick(window.redo_button, Qt.MouseButton.LeftButton)
        operation = window.canvas.operations[0]
        self.assertAlmostEqual(operation["points"][0][0], 100, delta=2)
        self.assertAlmostEqual(operation["points"][-1][1], 200, delta=2)
        received = []
        window.image_ready.connect(received.append)
        QTest.mouseClick(window.toolbar.insert_button, Qt.MouseButton.LeftButton)
        flush()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].size(), QImage(800, 400, QImage.Format.Format_RGB32).size())
        self.assertEqual(received[0].pixelColor(10, 10), QColor("white"))
        self.assertLess(received[0].pixelColor(250, 150).green(), 120)

    def test_small_image_wraps_controls_and_insert_is_accessible(self):
        window = self.editor(120, 75)
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_T)
        flush()
        self.assertEqual(window.canvas.tool, "text")
        self.assertTrue(window.toolbar.font_button.isVisible())
        for button in [window.toolbar.close_button, window.toolbar.insert_button,
                       window.toolbar.font_button, window.toolbar.fit_button, window.toolbar.stroke_slider]:
            bottom_right = button.mapTo(window, button.rect().bottomRight())
            self.assertTrue(window.rect().contains(bottom_right), button.toolTip())
        received = []
        window.image_ready.connect(received.append)
        QTest.mouseClick(window.toolbar.insert_button, Qt.MouseButton.LeftButton)
        flush()
        self.assertEqual(received[0].width(), 120)
        self.assertEqual(received[0].height(), 75)

    def test_window_can_be_moved_from_image_without_drawing(self):
        window = self.editor()
        before = window.pos()
        QTest.mousePress(window.canvas.viewport(), Qt.MouseButton.MiddleButton, pos=QPoint(100, 100))
        QTest.mouseMove(window.canvas.viewport(), QPoint(125, 115), 10)
        QTest.mouseRelease(window.canvas.viewport(), Qt.MouseButton.MiddleButton, pos=QPoint(125, 115))
        self.assertNotEqual(window.pos(), before)
        self.assertEqual(window.canvas.operations, [])

    def test_tall_image_scrolls_and_keeps_finish_controls_on_screen(self):
        window = self.editor(150, 3000)
        self.assertLessEqual(window.height(), window.screen_area().height())
        self.assertGreater(window.canvas.verticalScrollBar().maximum(), 0)
        window.canvas.verticalScrollBar().setValue(window.canvas.verticalScrollBar().maximum())
        flush()
        self.assertTrue(window.toolbar.insert_button.isVisible())
        self.assertEqual(window.canvas.mapFromScene(0, 3000).x(), 0)
        self.assertTrue(window.rect().contains(window.toolbar.insert_button.mapTo(window, QPoint(0, 0))))
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Escape)
        flush()


if __name__ == "__main__":
    unittest.main()
