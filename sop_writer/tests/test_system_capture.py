"""Deterministic Windows shortcut / clipboard tests without real screen capture."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QObject, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from sop_studio.app import MainWindow
from sop_studio.capture import SnipShortcutState, SystemCapture
from sop_studio.rendering import image_bytes
from sop_studio.style import apply_style


APP = QApplication.instance() or QApplication([])
apply_style(APP)


def flush():
    for _ in range(4):
        APP.processEvents()


def image():
    result = QImage(800, 500, QImage.Format.Format_RGB32)
    result.fill(QColor("#3355aa"))
    return result


class FakeClipboard(QObject):
    dataChanged = Signal()

    def __init__(self):
        super().__init__()
        self.revision = 10
        self.picture = QImage()
        self.mime = QMimeData()
        self.owned = False
        self.locked = False

    def mimeData(self):
        return self.mime

    def image(self):
        if self.locked:
            raise OSError("clipboard temporarily locked")
        return self.picture

    def ownsClipboard(self):
        return self.owned

    def publish(self, picture=None, *, text=None, owned=False, png=False):
        self.revision += 1
        self.owned = owned
        self.picture = picture.copy() if picture is not None and not png else QImage()
        self.mime = QMimeData()
        if png:
            self.mime.setData("PNG", image_bytes(picture))
        elif picture is not None:
            self.mime.setImageData(picture)
        if text is not None:
            self.mime.setText(text)
        self.dataChanged.emit()


class SystemCaptureTests(unittest.TestCase):
    def setUp(self):
        self.clipboard = FakeClipboard()
        self.capture = SystemCapture(native=False, clipboard=self.clipboard,
                                     sequence_getter=lambda: self.clipboard.revision)
        self.received = []
        self.cancelled = []
        self.capture.image_ready.connect(self.received.append)
        self.capture.cancelled.connect(self.cancelled.append)

    def tearDown(self):
        self.capture.stop()

    def test_ordinary_copy_and_existing_image_do_not_open_annotation(self):
        self.clipboard.publish(image())
        self.assertEqual(self.received, [])
        self.capture.arm()
        self.capture.check_clipboard()
        self.assertEqual(self.received, [])
        self.assertTrue(self.capture.pending)

    def test_new_capture_delivered_once_at_original_pixel_size(self):
        self.capture.arm()
        picture = image()
        picture.setDevicePixelRatio(2)
        self.clipboard.publish(picture)
        self.clipboard.dataChanged.emit()
        self.capture.check_clipboard()
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].size(), picture.size())
        self.assertEqual(self.received[0].devicePixelRatio(), 1)
        self.assertFalse(self.capture.pending)
        self.assertFalse(self.capture.timeout_timer.isActive())

    def test_text_and_empty_updates_wait_for_actual_image(self):
        self.capture.arm()
        self.clipboard.publish()
        self.clipboard.publish(text="普通复制")
        self.assertTrue(self.capture.pending)
        self.assertEqual(self.received, [])
        self.clipboard.publish(image())
        self.assertEqual(len(self.received), 1)

    def test_escape_and_timeout_do_not_later_read_stale_capture(self):
        self.capture.arm()
        self.capture.cancel_from_keyboard()
        self.clipboard.publish(image())
        self.assertEqual(self.received, [])
        self.assertEqual(self.cancelled, ["cancelled"])
        self.capture.arm()
        self.capture.timeout_timer.timeout.emit()
        self.clipboard.publish(image())
        self.assertEqual(self.received, [])
        self.assertEqual(self.cancelled, ["cancelled", "timeout"])

    def test_shortcut_signal_may_arrive_after_the_clipboard_change(self):
        baseline = self.clipboard.revision
        self.clipboard.publish(image())
        self.assertEqual(self.received, [])
        self.capture.arm(baseline)
        self.assertEqual(len(self.received), 1)

    def test_clipboard_lock_and_delayed_formats_are_retried(self):
        self.capture.arm()
        self.clipboard.locked = True
        self.clipboard.publish(image())
        self.assertTrue(self.capture.pending)
        self.clipboard.locked = False
        self.capture.check_clipboard()
        self.assertEqual(len(self.received), 1)
        self.capture.arm()
        self.clipboard.publish()  # Formats not rendered yet.
        self.clipboard.picture = image()
        self.capture.check_clipboard()
        self.assertEqual(len(self.received), 2)

    def test_png_only_clipboard_supported_and_own_copy_ignored(self):
        self.capture.arm()
        self.clipboard.publish(image(), owned=True)
        self.assertEqual(self.received, [])
        self.clipboard.publish(image(), png=True)
        self.assertEqual(len(self.received), 1)

    def test_identical_pixels_from_a_new_screenshot_still_delivered(self):
        picture = image()
        for _ in range(2):
            self.capture.arm()
            self.clipboard.publish(picture)
        self.assertEqual(len(self.received), 2)

    def test_launcher_waits_for_original_modifiers_to_be_released(self):
        with patch("sop_studio.capture.modifiers_held", return_value=True), patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.request()
            self.capture._launch_when_released()
            launch.assert_not_called()
            self.assertTrue(self.capture.pending)
        with patch("sop_studio.capture.modifiers_held", return_value=False), patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture._launch_when_released()
            launch.assert_called_once()
            self.assertFalse(self.capture.launch_timer.isActive())

    def test_launcher_failure_disarms_and_reports_error(self):
        errors = []
        self.capture.failed.connect(errors.append)
        with patch("sop_studio.capture.modifiers_held", return_value=False), patch("sop_studio.capture.launch_windows_snipping", side_effect=OSError("not available")):
            self.capture.request()
            self.capture._launch_when_released()
        self.assertFalse(self.capture.pending)
        self.assertEqual(errors, ["not available"])


class ShortcutStateTests(unittest.TestCase):
    def test_left_and_right_modifiers_repeats_and_escape(self):
        for win, shift in [(0x5B, 0xA0), (0x5C, 0xA1)]:
            state = SnipShortcutState()
            state.feed(win, True)
            state.feed(shift, True)
            self.assertEqual(state.feed(0x53, True), "snip")
            self.assertIsNone(state.feed(0x53, True))
            state.feed(0x53, False)
            self.assertEqual(state.feed(0x53, True), "snip")
            self.assertEqual(state.feed(0x1B, True), "cancel")

    def test_normal_typing_and_other_shortcuts_do_not_trigger(self):
        state = SnipShortcutState()
        for key in range(0x41, 0x5B):
            self.assertIsNone(state.feed(key, True))
            state.feed(key, False)
        self.assertEqual(state.pressed, set())
        for key in (0x5B, 0xA0, 0xA2):
            state.feed(key, True)
        self.assertIsNone(state.feed(0x53, True))


class CaptureWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow(test_mode=True)
        self.window.show()
        flush()
        self.window.auto_receive_snips = True
        self.window.system_capture.stop()
        self.clipboard = FakeClipboard()
        capture = SystemCapture(self.window, native=False, clipboard=self.clipboard,
                                sequence_getter=lambda: self.clipboard.revision)
        self.window.system_capture = capture
        capture.image_ready.connect(self.window.captured)
        capture.cancelled.connect(self.window.cancel_capture)

    def tearDown(self):
        APP.clipboard().clear()
        self.window.close()
        flush()

    def test_system_shortcut_clipboard_annotation_insert_end_to_end(self):
        self.window.showMinimized()
        flush()
        self.window.external_capture(self.clipboard.revision)
        self.clipboard.publish(image())
        flush()
        editor = self.window.annotation
        self.assertIsNotNone(editor)
        self.assertTrue(editor.isVisible())
        self.assertIsNone(editor.parentWidget())
        self.assertEqual(editor.canvas.base.width(), 800)
        editor.insert()
        flush()
        self.assertEqual(self.window.current_page().elements[0].kind, "image")
        self.assertFalse(self.window.isMinimized())

    def test_cancel_restores_window_only_when_our_button_hid_it(self):
        with patch.object(self.window.system_capture, "request", side_effect=self.window.system_capture.arm):
            self.window.start_capture()
        self.assertFalse(self.window.isVisible())
        self.window.system_capture.cancel_from_keyboard()
        self.assertTrue(self.window.isVisible())
        self.assertIsNone(self.window.annotation)
        self.window.showMinimized()
        self.window.external_capture(self.clipboard.revision)
        self.window.system_capture.cancel_from_keyboard()
        self.assertTrue(self.window.isMinimized())

    def test_repeated_screenshots_queue_without_overwriting_unsaved_markup(self):
        for _ in range(2):
            self.window.external_capture(self.clipboard.revision)
            self.clipboard.publish(image())
            flush()
        first = self.window.annotation
        self.assertEqual(len(self.window.pending_snips), 1)
        first.insert()
        flush()
        self.assertIsNotNone(self.window.annotation)
        self.assertIsNot(self.window.annotation, first)
        self.window.annotation.insert()
        flush()
        self.assertEqual(sum(len(page.elements) for page in self.window.controller.document.pages), 2)

    def test_auto_receive_can_be_disabled(self):
        self.window.set_auto_receive_snips(False)
        self.window.external_capture(self.clipboard.revision)
        self.clipboard.publish(image())
        self.assertIsNone(self.window.annotation)
        self.assertFalse(self.window.system_capture.pending)


if __name__ == "__main__":
    unittest.main()
