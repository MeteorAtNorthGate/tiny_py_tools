"""Deterministic Windows shortcut / clipboard tests without real screen capture."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ctypes
import unittest
from ctypes import wintypes
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QObject, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from sop_studio.app import MainWindow
from sop_studio.capture import GlobalHotkey, SnipShortcutState, SystemCapture, launch_windows_snipping
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
        self.ui_state = self.enterContext(patch("sop_studio.capture.snipping_window_state", return_value=(False, False)))
        self.repair = self.enterContext(patch("sop_studio.capture.repair_windows_snipping", return_value=0))
        self.wake = self.enterContext(patch("sop_studio.capture.wake_windows_snipping"))
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
            self.assertTrue(self.capture.pending)
            self.capture.launch_phase_deadline = 0
            self.capture._verify_launch()
        self.assertFalse(self.capture.pending)
        self.assertEqual(len(errors), 1)
        self.assertIn("not available", errors[0])
        self.repair.assert_called_once()
        self.wake.assert_called_once()
        self.assertFalse(self.capture.launch_verify_timer.isActive())

    def test_successful_launch_is_verified_without_retry_or_repair(self):
        self.ui_state.return_value = (True, False)
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.request()
            self.capture._launch_when_released()
            self.capture._verify_launch()
        launch.assert_called_once()
        self.repair.assert_not_called()
        self.wake.assert_not_called()
        self.assertTrue(self.capture.pending)
        self.assertFalse(self.capture.launch_verify_timer.isActive())

    def test_silent_launch_failure_wakes_repairs_and_retries_then_accepts_image(self):
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.request()
            self.capture._launch_when_released()
            self.capture.launch_phase_deadline = 0
            self.capture._verify_launch()
            self.assertEqual(self.capture.launch_phase, "warming")
            self.capture.launch_phase_deadline = 0
            self.capture._verify_launch()
            self.ui_state.return_value = (True, False)
            self.capture._verify_launch()
        self.assertEqual(launch.call_count, 2)
        self.repair.assert_called_once()
        self.wake.assert_called_once()
        self.assertFalse(self.capture.launch_verify_timer.isActive())
        self.clipboard.publish(image())
        self.assertEqual(len(self.received), 1)

    def test_silent_failures_stop_after_one_recovery_and_disarm_every_timer(self):
        errors = []
        self.capture.failed.connect(errors.append)
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.request()
            self.capture._launch_when_released()
            for _ in range(3):
                self.capture.launch_phase_deadline = 0
                self.capture._verify_launch()
        self.assertEqual(launch.call_count, 2)
        self.repair.assert_called_once()
        self.assertFalse(self.capture.pending)
        self.assertFalse(self.capture.launch_verify_timer.isActive())
        self.assertFalse(self.capture.poll_timer.isActive())
        self.assertFalse(self.capture.timeout_timer.isActive())
        self.assertEqual(len(errors), 1)

    def test_escape_during_warmup_prevents_delayed_retry(self):
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.request()
            self.capture._launch_when_released()
            self.capture.launch_phase_deadline = 0
            self.capture._verify_launch()
            self.capture.cancel_from_keyboard()
            self.capture.launch_phase_deadline = 0
            self.capture._verify_launch()
        launch.assert_called_once()
        self.assertFalse(self.capture.launch_verify_timer.isActive())

    def test_external_shortcut_is_monitored_without_a_duplicate_launch(self):
        with patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.arm(watch_launch=True)
            self.capture._verify_launch()
        launch.assert_not_called()
        self.assertTrue(self.capture.launch_verify_timer.isActive())

    def test_external_shortcut_silent_failure_recovers_with_one_launch(self):
        with patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.arm(watch_launch=True)
            for _ in range(2):
                self.capture.launch_phase_deadline = 0
                self.capture._verify_launch()
            self.ui_state.return_value = (True, False)
            self.capture._verify_launch()
        launch.assert_called_once()
        self.repair.assert_called_once()
        self.wake.assert_called_once()
        self.assertTrue(self.capture.pending)
        self.assertFalse(self.capture.launch_verify_timer.isActive())

    def test_repair_or_wakeup_error_does_not_prevent_successful_retry(self):
        self.repair.side_effect = OSError("access denied")
        self.wake.side_effect = OSError("tool unavailable")
        with patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.arm(watch_launch=True)
            for _ in range(2):
                self.capture.launch_phase_deadline = 0
                self.capture._verify_launch()
            self.ui_state.return_value = (True, False)
            self.capture._verify_launch()
        launch.assert_called_once()
        self.assertTrue(self.capture.pending)
        self.assertFalse(self.capture.launch_verify_timer.isActive())

    def test_late_overlay_prevents_cleanup_and_tool_wakeup(self):
        self.capture.arm(watch_launch=True)
        self.ui_state.return_value = (True, False)
        self.capture._recover_launcher()
        self.repair.assert_not_called()
        self.wake.assert_not_called()
        self.assertFalse(self.capture.launch_verify_timer.isActive())

    def test_visible_standalone_tool_is_kept_as_manual_fallback(self):
        self.capture.arm()
        self.capture.launch_phase = "retry"
        self.capture.launch_phase_deadline = 0
        self.ui_state.return_value = (False, True)
        messages = []
        self.capture.progress.connect(messages.append)
        self.capture._verify_launch()
        self.assertTrue(self.capture.pending)
        self.assertFalse(self.capture.launch_verify_timer.isActive())
        self.assertIn("新建", messages[-1])

    def test_image_arriving_during_recovery_stops_all_later_launches(self):
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.request()
            self.capture._launch_when_released()
            self.capture.launch_phase_deadline = 0
            self.capture._verify_launch()
            self.clipboard.publish(image())
            self.capture._verify_launch()
        launch.assert_called_once()
        self.assertEqual(len(self.received), 1)
        self.assertFalse(self.capture.launch_verify_timer.isActive())

    def test_held_modifiers_time_out_without_launching_or_leaving_timers_running(self):
        errors = []
        self.capture.failed.connect(errors.append)
        with patch("sop_studio.capture.time.monotonic", return_value=100):
            self.capture.request()
        with patch("sop_studio.capture.time.monotonic", return_value=104), \
                patch("sop_studio.capture.modifiers_held", return_value=True), \
                patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture._launch_when_released()
        launch.assert_not_called()
        self.assertFalse(self.capture.pending)
        self.assertFalse(self.capture.launch_timer.isActive())
        self.assertFalse(self.capture.poll_timer.isActive())
        self.assertFalse(self.capture.timeout_timer.isActive())
        self.assertEqual(self.cancelled, ["cancelled"])
        self.assertEqual(len(errors), 1)

    def test_cancel_before_launch_does_not_open_snipping_tool_later(self):
        with patch("sop_studio.capture.launch_windows_snipping") as launch:
            self.capture.request()
            self.capture.cancel_from_keyboard()
            self.capture._launch_when_released()
        launch.assert_not_called()
        self.assertFalse(self.capture.launch_timer.isActive())


class WindowsLauncherTests(unittest.TestCase):
    def test_launch_opens_system_capture_uri_without_injecting_keys(self):
        with patch("sop_studio.capture.sys.platform", "win32"), \
                patch("sop_studio.capture.os.startfile", create=True) as startfile:
            launch_windows_snipping()
        startfile.assert_called_once_with("ms-screenclip://?source=HotKey")

    def test_missing_protocol_handler_reports_actionable_error(self):
        with patch("sop_studio.capture.sys.platform", "win32"), \
                patch("sop_studio.capture.os.startfile", create=True,
                      side_effect=OSError("protocol handler missing")):
            with self.assertRaisesRegex(OSError, "Win\\+Shift\\+S") as error:
                launch_windows_snipping()
        self.assertIn("protocol handler missing", str(error.exception))

    def test_other_platforms_do_not_attempt_to_open_a_uri(self):
        with patch("sop_studio.capture.sys.platform", "linux"), \
                patch("sop_studio.capture.os.startfile", create=True) as startfile:
            with self.assertRaisesRegex(OSError, "Windows"):
                launch_windows_snipping()
        startfile.assert_not_called()


class GlobalHotkeyTests(unittest.TestCase):
    def setUp(self):
        self.hotkey = GlobalHotkey()

    def tearDown(self):
        self.hotkey.unregister()
        APP.removeNativeEventFilter(self.hotkey)

    def test_ctrl_1_native_message_triggers_capture_once(self):
        triggered = []
        self.hotkey.triggered.connect(lambda: triggered.append(True))
        message = wintypes.MSG()
        message.message = 0x0312  # WM_HOTKEY
        message.wParam = self.hotkey.HOTKEY_ID
        with patch("sop_studio.capture.sys.platform", "win32"):
            result = self.hotkey.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message))
        self.assertEqual(result, (True, 0))
        self.assertEqual(triggered, [True])

    def test_system_snipping_shortcut_cannot_be_registered_as_extra_hotkey(self):
        with self.assertRaises(ValueError):
            self.hotkey.register("Meta+Shift+S")


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
        self.enterContext(patch("sop_studio.capture.snipping_window_state", return_value=(False, False)))
        self.enterContext(patch("sop_studio.capture.repair_windows_snipping", return_value=0))
        self.enterContext(patch("sop_studio.capture.wake_windows_snipping"))
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
        capture.failed.connect(self.window.capture_failed)

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

    def test_ctrl_1_launches_then_clipboard_annotation_insert_end_to_end(self):
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.os.startfile", create=True) as startfile:
            self.window.hotkey.triggered.emit()
            self.assertFalse(self.window.isVisible())
            self.window.system_capture._launch_when_released()
        startfile.assert_called_once_with("ms-screenclip://?source=HotKey")
        self.clipboard.publish(image())
        flush()
        self.assertIsNotNone(self.window.annotation)
        self.window.annotation.insert()
        flush()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.capture_busy)
        self.assertEqual(self.window.current_page().elements[0].kind, "image")

    def test_launcher_failure_restores_window_and_allows_another_capture(self):
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.os.startfile", create=True,
                      side_effect=OSError("protocol handler missing")), \
                self.assertLogs(level="WARNING"):
            self.window.hotkey.triggered.emit()
            self.window.system_capture._launch_when_released()
            self.window.system_capture.launch_phase_deadline = 0
            self.window.system_capture._verify_launch()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.capture_busy)
        self.assertFalse(self.window.capture_restore_owned)
        self.assertFalse(self.window.system_capture.pending)
        self.assertIn("protocol handler missing", self.window.statusBar().currentMessage())
        with patch.object(self.window.system_capture, "request", side_effect=self.window.system_capture.arm):
            self.window.hotkey.triggered.emit()
        self.assertTrue(self.window.system_capture.pending)

    def test_ctrl_1_still_receives_capture_with_system_shortcut_auto_receive_disabled(self):
        self.window.set_auto_receive_snips(False)
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.os.startfile", create=True):
            self.window.hotkey.triggered.emit()
            self.window.system_capture._launch_when_released()
        self.clipboard.publish(image())
        flush()
        self.assertIsNotNone(self.window.annotation)

    def test_silent_launch_failure_restores_hidden_window_after_bounded_recovery(self):
        with patch("sop_studio.capture.modifiers_held", return_value=False), \
                patch("sop_studio.capture.launch_windows_snipping") as launch, \
                self.assertLogs(level="WARNING"):
            self.window.hotkey.triggered.emit()
            self.window.system_capture._launch_when_released()
            for _ in range(3):
                self.window.system_capture.launch_phase_deadline = 0
                self.window.system_capture._verify_launch()
        self.assertEqual(launch.call_count, 2)
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.capture_busy)
        self.assertFalse(self.window.system_capture.pending)
        self.assertIn("重试", self.window.statusBar().currentMessage())


if __name__ == "__main__":
    unittest.main()
