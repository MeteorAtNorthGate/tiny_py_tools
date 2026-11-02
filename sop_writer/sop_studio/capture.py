"""Windows Snipping Tool integration; no screen geometry or pixel scaling here."""
from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QKeySequence
from PySide6.QtWidgets import QApplication


class GlobalHotkey(QObject, QAbstractNativeEventFilter):
    triggered = Signal()
    HOTKEY_ID = 0x5A31

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self.registered = False
        self.sequence = ""
        QApplication.instance().installNativeEventFilter(self)

    @staticmethod
    def parse(sequence: str):
        key = QKeySequence(sequence)
        if key.count() != 1 or key.isEmpty():
            raise ValueError("请设置单个快捷键，例如 Ctrl+1 或 Ctrl+Shift+S。")
        combination = key[0]
        qt_modifiers = combination.keyboardModifiers()
        modifiers = 0x4000  # MOD_NOREPEAT
        for flag, native in [(Qt.KeyboardModifier.ControlModifier, 0x2), (Qt.KeyboardModifier.AltModifier, 0x1),
                             (Qt.KeyboardModifier.ShiftModifier, 0x4), (Qt.KeyboardModifier.MetaModifier, 0x8)]:
            if qt_modifiers & flag:
                modifiers |= native
        value = combination.key()
        if Qt.Key.Key_A <= value <= Qt.Key.Key_Z or Qt.Key.Key_0 <= value <= Qt.Key.Key_9:
            native_key = int(value)
        elif Qt.Key.Key_F1 <= value <= Qt.Key.Key_F24:
            native_key = 0x70 + int(value) - int(Qt.Key.Key_F1)
        else:
            raise ValueError("截图快捷键请使用字母、数字或 F1～F24。")
        if modifiers == 0x4000:
            raise ValueError("请至少添加 Ctrl、Alt、Shift 或 Win 中的一个修饰键。")
        if modifiers == 0x400C and native_key == 0x53:
            raise ValueError("Win+Shift+S 已自动监听，请选择其他额外的截图快捷键。")
        return modifiers, native_key

    def register(self, sequence: str) -> bool:
        modifiers, key = self.parse(sequence)
        old_sequence = self.sequence
        self.unregister()
        if sys.platform == "win32":
            self.registered = bool(ctypes.windll.user32.RegisterHotKey(None, self.HOTKEY_ID, modifiers, key))
        if self.registered:
            self.sequence = sequence
        elif old_sequence:
            old_modifiers, old_key = self.parse(old_sequence)
            self.registered = bool(ctypes.windll.user32.RegisterHotKey(None, self.HOTKEY_ID, old_modifiers, old_key))
            self.sequence = old_sequence if self.registered else ""
            return False
        return self.registered

    def unregister(self):
        if self.registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
        self.registered = False

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32" and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.HOTKEY_ID:
                self.triggered.emit()
                return True, 0
        return False, 0


class SnipShortcutState:
    """Track just the modifier keys, S and Escape; never store typed content."""
    MODIFIERS = {0x5B, 0x5C, 0x10, 0xA0, 0xA1, 0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5}

    def __init__(self):
        self.pressed = set()

    def feed(self, key: int, down: bool) -> str | None:
        repeated = key in self.pressed
        if down and (key in self.MODIFIERS or key == 0x53):
            self.pressed.add(key)
        elif not down:
            self.pressed.discard(key)
        if not down:
            return None
        if key == 0x1B:
            return "cancel"
        if key != 0x53 or repeated:
            return None
        win = bool(self.pressed & {0x5B, 0x5C})
        shift = bool(self.pressed & {0x10, 0xA0, 0xA1})
        other = bool(self.pressed & {0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5})
        return "snip" if win and shift and not other else None


def clipboard_sequence() -> int:
    return int(ctypes.windll.user32.GetClipboardSequenceNumber()) if sys.platform == "win32" else 0


class SnipShortcutListener(QObject):
    """A pass-through hook on its own message-pump thread, independent of Qt I/O."""
    shortcut_pressed = Signal(object)
    escape_pressed = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.thread_id = 0
        self._stop = threading.Event()
        self.ready = threading.Event()
        self.installed = False

    def start(self):
        if sys.platform != "win32" or self.thread is not None:
            return
        self.thread = threading.Thread(target=self._run, name="WindowsSnipShortcut", daemon=True)
        self.thread.start()

    def _run(self):
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KeyboardData(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        user.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HANDLE
        user.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = ctypes.c_ssize_t
        user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user.UnhookWindowsHookEx.restype = wintypes.BOOL
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user.GetMessageW.restype = wintypes.BOOL
        user.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        state = SnipShortcutState()
        hook = None

        @callback_type
        def callback(code, message, data):
            if code == 0:
                try:
                    key = ctypes.cast(data, ctypes.POINTER(KeyboardData)).contents.vkCode
                    action = state.feed(key, message in (0x100, 0x104))
                    if action == "snip":
                        self.shortcut_pressed.emit(clipboard_sequence())
                    elif action == "cancel":
                        self.escape_pressed.emit()
                except Exception:
                    logging.exception("Snipping shortcut listener callback failed")
            # In particular, never consume Win+Shift+S: Windows must receive it.
            return user.CallNextHookEx(hook, code, message, data)

        try:
            msg = wintypes.MSG()
            self.thread_id = kernel.GetCurrentThreadId()
            user.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # Create the queue before stop().
            hook = user.SetWindowsHookExW(13, callback, kernel.GetModuleHandleW(None), 0)
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            self.installed = True
            self.ready.set()
            while not self._stop.is_set():
                result = user.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:
                    break
        except Exception as error:
            logging.exception("Cannot listen for the Windows screenshot shortcut")
            self.failed.emit(str(error))
        finally:
            self.ready.set()
            if hook:
                user.UnhookWindowsHookEx(hook)
            self.installed = False

    def stop(self):
        self._stop.set()
        if self.thread_id and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)  # WM_QUIT
        if self.thread:
            self.thread.join(timeout=1)


def modifiers_held() -> bool:
    if sys.platform != "win32":
        return False
    return any(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000
               for key in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0x53))


def launch_windows_snipping():
    """Send the real Windows shortcut, avoiding version-specific Snipping Tool URIs."""
    if sys.platform != "win32":
        raise OSError("系统截图仅支持 Windows。")

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

    class KeyboardInput(ctypes.Structure):
        _fields_ = [("key", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

    class HardwareInput(ctypes.Structure):
        _fields_ = [("message", wintypes.DWORD), ("low", wintypes.WORD), ("high", wintypes.WORD)]

    class InputUnion(ctypes.Union):
        _fields_ = [("mouse", MouseInput), ("keyboard", KeyboardInput), ("hardware", HardwareInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]

    events = (Input * 6)()
    for event, (key, up) in zip(events, [(0x5B, False), (0xA0, False), (0x53, False),
                                        (0x53, True), (0xA0, True), (0x5B, True)]):
        event.type = 1  # INPUT_KEYBOARD
        event.data.keyboard = KeyboardInput(key, 0, 2 if up else 0, 0, 0)
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user.SendInput.restype = wintypes.UINT
    if user.SendInput(len(events), events, ctypes.sizeof(Input)) != len(events):
        # Release any modifiers inserted before a partial failure.
        releases = (Input * 3)()
        for event, key in zip(releases, (0x53, 0xA0, 0x5B)):
            event.type = 1
            event.data.keyboard = KeyboardInput(key, 0, 2, 0, 0)
        user.SendInput(len(releases), releases, ctypes.sizeof(Input))
        raise OSError("无法打开系统截图，请直接按 Win+Shift+S。")


class SystemCapture(QObject):
    """Read one *new* clipboard image per screenshot request; never clear clipboard."""
    shortcut_detected = Signal(object)
    image_ready = Signal(QImage)
    cancelled = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None, native=True, clipboard=None, sequence_getter=None):
        super().__init__(parent)
        self.clipboard = clipboard if clipboard is not None else QApplication.clipboard()
        self.native = native
        self._revision = 0
        self.sequence_getter = sequence_getter or (clipboard_sequence if native else lambda: self._revision)
        self.pending = False
        self.baseline = None
        self.clipboard.dataChanged.connect(self._clipboard_changed)
        self.listener = SnipShortcutListener(self)
        self.listener.shortcut_pressed.connect(self.shortcut_detected, Qt.ConnectionType.QueuedConnection)
        self.listener.escape_pressed.connect(self.cancel_from_keyboard, Qt.ConnectionType.QueuedConnection)
        self.listener.failed.connect(self.failed, Qt.ConnectionType.QueuedConnection)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(120)
        self.poll_timer.timeout.connect(self.check_clipboard)
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.setInterval(60000)
        self.timeout_timer.timeout.connect(lambda: self.cancel("timeout"))
        self.launch_timer = QTimer(self)
        self.launch_timer.setInterval(40)
        self.launch_timer.timeout.connect(self._launch_when_released)
        self.launch_deadline = 0

    def start(self):
        if self.native:
            self.listener.start()

    def arm(self, baseline=None):
        if self.pending:
            return
        self.baseline = self.sequence_getter() if baseline is None else baseline
        self.pending = True
        self.poll_timer.start()
        self.timeout_timer.start()
        # A queued shortcut notification may arrive after the clipboard notification.
        self.check_clipboard()

    def request(self):
        self.arm()
        self.launch_deadline = time.monotonic() + 3
        self.launch_timer.start()

    def _launch_when_released(self):
        if not self.pending:
            self.launch_timer.stop()
            return
        if modifiers_held():
            if time.monotonic() >= self.launch_deadline:
                self.cancel("cancelled")
                self.failed.emit("截图快捷键仍被按住，请松开按键后重试。")
            return
        self.launch_timer.stop()
        try:
            launch_windows_snipping()
        except OSError as error:
            self.cancel("cancelled")
            self.failed.emit(str(error))

    @Slot()
    def _clipboard_changed(self):
        self._revision += 1
        self.check_clipboard()

    @Slot()
    def check_clipboard(self):
        if not self.pending:
            return
        sequence = self.sequence_getter()
        if sequence == self.baseline:
            return
        try:
            mime = self.clipboard.mimeData()
            if mime is None or mime.hasFormat("application/x-sop-studio-element") or self.clipboard.ownsClipboard():
                return
            image = self.clipboard.image()
            # Windows may advertise PNG before exposing the standard bitmap formats.
            if image.isNull() and mime.hasFormat("PNG"):
                image = QImage.fromData(mime.data("PNG"), "PNG")
            if image.isNull() or sequence != self.sequence_getter():
                return  # Clipboard can be locked, incomplete, or changed while reading.
            result = image.copy()
            result.setDevicePixelRatio(1)
        except (RuntimeError, OSError):
            return  # Retry from the timer without consuming this request.
        self._disarm()
        self.image_ready.emit(result)

    def _disarm(self):
        self.pending = False
        self.poll_timer.stop()
        self.timeout_timer.stop()
        self.launch_timer.stop()

    @Slot()
    def cancel_from_keyboard(self):
        self.cancel("cancelled")

    def cancel(self, reason="cancelled"):
        if self.pending:
            self._disarm()
            self.cancelled.emit(reason)

    def stop(self):
        self._disarm()
        self.listener.stop()
        try:
            self.clipboard.dataChanged.disconnect(self._clipboard_changed)
        except RuntimeError:
            pass
