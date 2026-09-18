import ctypes
from ctypes import wintypes
import time
from typing import List, Set
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000

# Global system hotkeys: F1 for Snipping, F3 for Pinning
VK_F1 = 0x70
VK_F3 = 0x72

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]

user32 = ctypes.windll.user32

class HotkeyListenerWidget(QWidget):
    hotkey_triggered = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered_ids: Set[int] = set()

    def register_hotkey(self, hotkey_id: int, modifiers: int, vk: int) -> bool:
        hwnd = int(self.winId())
        res = user32.RegisterHotKey(hwnd, hotkey_id, modifiers | MOD_NOREPEAT, vk)
        if res:
            self.registered_ids.add(hotkey_id)
            return True
        return False

    def unregister_all(self):
        hwnd = int(self.winId())
        for hid in list(self.registered_ids):
            user32.UnregisterHotKey(hwnd, hid)
        self.registered_ids.clear()

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self.hotkey_triggered.emit(int(msg.wParam))
                return True, 0
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        self.unregister_all()
        super().closeEvent(event)

class GlobalHotkeyManager(QObject):
    snip_requested = Signal()
    pin_requested = Signal()

    HOTKEY_SNIP_F1 = 1001
    HOTKEY_PIN_F3 = 2001

    def __init__(self, parent=None):
        super().__init__(parent)
        self.listener = HotkeyListenerWidget()
        self.listener.hotkey_triggered.connect(self._on_hotkey)
        self.snip_key_desc = "未绑定"
        self.pin_key_desc = "未绑定"
        self._last_trigger_time = 0.0

    def _debounce_trigger(self, signal: Signal):
        now = time.time()
        if now - self._last_trigger_time > 0.35:
            self._last_trigger_time = now
            signal.emit()

    def start(self):
        if self.listener.register_hotkey(self.HOTKEY_SNIP_F1, 0, VK_F1):
            self.snip_key_desc = "F1"
        else:
            self.snip_key_desc = "未绑定"

        if self.listener.register_hotkey(self.HOTKEY_PIN_F3, 0, VK_F3):
            self.pin_key_desc = "F3"
        else:
            self.pin_key_desc = "未绑定"

        print(f"[Hotkey Engine] Active. Snip: {self.snip_key_desc} | Pin: {self.pin_key_desc}")

    def stop(self):
        self.listener.unregister_all()

    def _on_hotkey(self, hotkey_id: int):
        if hotkey_id == self.HOTKEY_SNIP_F1:
            self._debounce_trigger(self.snip_requested)
        elif hotkey_id == self.HOTKEY_PIN_F3:
            self._debounce_trigger(self.pin_requested)
