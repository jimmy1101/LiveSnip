import sys
import ctypes
from typing import Optional
from PySide6.QtCore import QRect, QPoint

HAS_WIN32GUI = False
dwmapi = None
DWMWA_EXTENDED_FRAME_BOUNDS = 9

if sys.platform == "win32":
    try:
        import win32gui
        import win32con
        HAS_WIN32GUI = True
    except ImportError:
        HAS_WIN32GUI = False

    try:
        dwmapi = ctypes.windll.dwmapi
    except Exception:
        dwmapi = None

class RECT(ctypes.Structure):
    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long)
    ]

def get_window_rect_at_point(pt: QPoint) -> Optional[QRect]:
    """Detect visible window or control rectangle at the given global point."""
    if not HAS_WIN32GUI:
        return None

    try:
        hwnd = win32gui.WindowFromPoint((pt.x(), pt.y()))
        if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return None

        # Prefer DWM extended frame bounds (excludes invisible window drop shadow)
        if dwmapi is not None:
            r = RECT()
            res = dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(r),
                ctypes.sizeof(r)
            )
            if res == 0 and r.right > r.left and r.bottom > r.top:
                return QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)

        # Fallback to standard GetWindowRect
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right > left and bottom > top:
            return QRect(left, top, right - left, bottom - top)
    except Exception:
        pass
    return None
