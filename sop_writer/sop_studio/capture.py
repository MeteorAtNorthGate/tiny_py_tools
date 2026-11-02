"""Windows global hotkey and multi-screen region capture using Qt logical pixels."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget


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


def grab_desktop() -> tuple[QImage, QRect, float]:
    screens = QApplication.screens()
    virtual = QRect()
    for screen in screens:
        virtual = virtual.united(screen.geometry())
    ratio = max(screen.devicePixelRatio() for screen in screens)
    image = QImage(round(virtual.width() * ratio), round(virtual.height() * ratio), QImage.Format.Format_RGB32)
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    for screen in screens:
        position = screen.geometry().topLeft() - virtual.topLeft()
        pixmap = screen.grabWindow(0)
        painter.drawPixmap(QRect(position, screen.geometry().size()), pixmap, pixmap.rect())
    painter.end()
    return image, virtual, ratio


class CaptureOverlay(QWidget):
    captured = Signal(QImage)
    cancelled = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.image, self.virtual, self.ratio = grab_desktop()
        self.setGeometry(self.virtual)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.start = None
        self.end = None
        self.done = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(QPoint(0, 0), self.image)
        painter.fillRect(self.rect(), QColor(12, 20, 36, 115))
        if self.start is not None and self.end is not None:
            rect = QRect(self.start, self.end).normalized().intersected(self.rect())
            painter.save()
            painter.setClipRect(rect)
            painter.drawImage(QPoint(0, 0), self.image)
            painter.restore()
            painter.setPen(QPen(QColor("#76a5ff"), 2))
            painter.drawRect(rect)
            text = f"{round(rect.width() * self.ratio)} × {round(rect.height() * self.ratio)} px"
            label = QRect(rect.left(), max(0, rect.top() - 30), 230, 26)
            painter.fillRect(label, QColor("#182338"))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(label.adjusted(8, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)
        else:
            painter.setFont(QFont("Microsoft YaHei UI", 14))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "拖动选择截图区域   ·   Esc / 右键取消")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.close()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()
            self.end = self.start
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.start is not None:
            self.end = event.position().toPoint()
            rect = QRect(self.start, self.end).normalized().intersected(self.rect())
            if rect.width() < 4 or rect.height() < 4:
                self.start = self.end = None
                self.update()
                return
            pixels = QRect(round(rect.x() * self.ratio), round(rect.y() * self.ratio),
                           round(rect.width() * self.ratio), round(rect.height() * self.ratio))
            result = self.image.copy(pixels)
            result.setDevicePixelRatio(1)
            self.done = True
            self.captured.emit(result)
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event):
        if not self.done:
            self.cancelled.emit()
        event.accept()
