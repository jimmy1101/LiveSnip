import sys
import os
import ctypes
import threading
from typing import List

# Instantly hide any attached console window (SW_HIDE = 0, no command prompt popup)
try:
    _console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if _console_hwnd:
        ctypes.windll.user32.ShowWindow(_console_hwnd, 0)
except Exception:
    pass

from PySide6.QtCore import Qt, QPoint, QRect, QTimer, QSettings
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont, QPen,
    QGuiApplication
)
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox
)

from core.hotkey import GlobalHotkeyManager
from core.ocr_engine import get_ocr_engine
from ui.snipper import SnipperWidget
from ui.pin_window import PinWindow

def create_app_icon() -> QIcon:
    """Dynamically draw a modern Snipaste-style icon."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Blue-cyan rounded background
    p.setBrush(QColor(0, 122, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)

    # White crop border
    p.setPen(QPen(QColor(255, 255, 255), 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(16, 16, 32, 32, 6, 6)

    # Pin point dot
    p.setBrush(QColor(0, 255, 180))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(36, 12, 12, 12)

    p.end()
    return QIcon(pix)

def render_text_to_pixmap(text: str) -> QPixmap:
    """Convert plain text from clipboard into a stylish card image to pin."""
    font = QFont("Consolas", 11)
    dummy_pix = QPixmap(1, 1)
    p = QPainter(dummy_pix)
    p.setFont(font)
    fm = p.fontMetrics()
    p.end()

    all_lines = text.splitlines()
    lines = all_lines[:50]
    if len(all_lines) > 50:
        lines.append(f"... [已截断显示前 50 行，共 {len(all_lines)} 行]")
    max_line_w = max([fm.horizontalAdvance(line) for line in lines] or [100])
    total_h = len(lines) * fm.lineSpacing()

    padding = 20
    w = max(200, max_line_w + padding * 2)
    h = max(80, total_h + padding * 2)

    card_pix = QPixmap(w, h)
    card_pix.fill(Qt.GlobalColor.transparent)

    cp = QPainter(card_pix)
    cp.setRenderHint(QPainter.RenderHint.Antialiasing)

    cp.setBrush(QColor(32, 33, 36))
    cp.setPen(QPen(QColor(60, 64, 67), 1))
    cp.drawRoundedRect(QRect(1, 1, w - 2, h - 2), 8, 8)

    cp.setFont(font)
    cp.setPen(QColor(230, 230, 230))
    y = padding + fm.ascent()
    for line in lines:
        cp.drawText(padding, y, line)
        y += fm.lineSpacing()

    cp.end()
    return card_pix

class LiveSnipApp:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.app_icon = create_app_icon()
        self.app.setWindowIcon(self.app_icon)

        # 1. Pre-instantiate Snipper overlay in memory (Persistent Singleton like Snipaste)
        self.snipper = SnipperWidget()
        self.snipper.snip_done.connect(self.create_pin)
        self.snipper.hide()

        self.active_pins: List[PinWindow] = []

        # Settings persistence (Default: enable_shadow is True)
        self.settings = QSettings("LiveSnip", "Settings")
        val = self.settings.value("enable_shadow", True)
        self.enable_shadow = (str(val).lower() != "false") if isinstance(val, str) else bool(val)

        # 2. Global hotkeys
        self.hotkey_mgr = GlobalHotkeyManager()
        self.hotkey_mgr.snip_requested.connect(self.start_snip)
        self.hotkey_mgr.pin_requested.connect(self.handle_f3_pin)
        self.hotkey_mgr.start()

        # 3. System tray setup
        self.tray = QSystemTrayIcon(self.app_icon, self.app)
        self.tray.setToolTip(f"LiveSnip (截图: {self.hotkey_mgr.snip_key_desc} / 贴图: {self.hotkey_mgr.pin_key_desc})\n中键托盘可直接贴图")
        self._setup_tray_menu()
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        # 4. Asynchronously warm up OCR after UI event loop is fully idle (avoids GIL contention)
        QTimer.singleShot(1500, self._async_warmup_ocr)

        # Initial balloon tip
        snip_k = self.hotkey_mgr.snip_key_desc
        pin_k = self.hotkey_mgr.pin_key_desc
        self.tray.showMessage(
            "LiveSnip 已就绪",
            f"已绑定快捷键：\n【{snip_k}】屏幕截图 (截图时点鼠标中键也可贴图)\n【{pin_k}】贴图悬浮 (鼠标中键点托盘也可贴图)\n贴图后鼠标直接左键划选文字复制！",
            QSystemTrayIcon.MessageIcon.Information,
            3500
        )

    def _async_warmup_ocr(self):
        threading.Thread(target=get_ocr_engine, daemon=True).start()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            # Middle click on tray icon -> pin from clipboard
            self.handle_f3_pin()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Left click on tray icon -> start snip
            self.start_snip()

    def _setup_tray_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #444;
                padding: 4px;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 22px 6px 26px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
            }
        """)

        snip_k = self.hotkey_mgr.snip_key_desc
        pin_k = self.hotkey_mgr.pin_key_desc

        act_snip = menu.addAction(f"📸 截图 ({snip_k})")
        act_snip.triggered.connect(self.start_snip)

        act_pin = menu.addAction(f"📌 贴图 ({pin_k} / 托盘中键)")
        act_pin.triggered.connect(self.handle_f3_pin)

        menu.addSeparator()

        self.act_shadow = menu.addAction("开启贴图阴影")
        self.act_shadow.setCheckable(True)
        self.act_shadow.setChecked(self.enable_shadow)
        self.act_shadow.toggled.connect(self.set_shadow_enabled)

        act_toggle_through = menu.addAction("👻 切换贴图穿透 (F4)")
        act_toggle_through.triggered.connect(self.toggle_all_click_through)

        act_close_all_pins = menu.addAction("🗑️ 关闭所有贴图")
        act_close_all_pins.triggered.connect(self.close_all_pins)

        act_about = menu.addAction("ℹ️ 关于与操作指南")
        act_about.triggered.connect(self.show_about)

        menu.addSeparator()

        act_quit = menu.addAction("🚪 退出程序")
        act_quit.triggered.connect(self.quit_app)

        self.tray.setContextMenu(menu)

    def start_snip(self):
        # Directly wake up pre-instantiated overlay with zero creation latency
        self.snipper.prepare_and_show()

    def set_shadow_enabled(self, enabled: bool):
        self.enable_shadow = enabled
        self.settings.setValue("enable_shadow", enabled)
        if hasattr(self, "act_shadow") and self.act_shadow.isChecked() != enabled:
            self.act_shadow.blockSignals(True)
            self.act_shadow.setChecked(enabled)
            self.act_shadow.blockSignals(False)
        for pin in self.active_pins:
            pin.set_shadow_enabled(enabled)

    def create_pin(self, pixmap: QPixmap, pos: QPoint):
        if pixmap.isNull():
            return
        pin = PinWindow(pixmap, pos, enable_shadow=self.enable_shadow)
        pin.shadow_toggled.connect(self.set_shadow_enabled)
        self.active_pins.append(pin)
        pin.destroyed.connect(lambda: self._on_pin_destroyed(pin))
        pin.show()

    def _on_pin_destroyed(self, pin):
        if pin in self.active_pins:
            self.active_pins.remove(pin)

    def handle_f3_pin(self):
        clipboard = QApplication.clipboard()
        pixmap = clipboard.pixmap()

        if not pixmap.isNull():
            screen_geo = QGuiApplication.primaryScreen().geometry()
            pos = QPoint(
                screen_geo.center().x() - pixmap.width() // 2,
                screen_geo.center().y() - pixmap.height() // 2
            )
            self.create_pin(pixmap, pos)
            return

        text = clipboard.text().strip()
        if text:
            card_pixmap = render_text_to_pixmap(text)
            screen_geo = QGuiApplication.primaryScreen().geometry()
            pos = QPoint(
                screen_geo.center().x() - card_pixmap.width() // 2,
                screen_geo.center().y() - card_pixmap.height() // 2
            )
            self.create_pin(card_pixmap, pos)
            return

        self.tray.showMessage("贴图提示", "剪贴板中既没有图片也没有文本，请先复制或截图。", QSystemTrayIcon.MessageIcon.Warning, 2000)

    def toggle_all_click_through(self):
        for pin in self.active_pins:
            pin.toggle_click_through()

    def close_all_pins(self):
        for pin in list(self.active_pins):
            pin.close()
        self.active_pins.clear()

    def show_about(self):
        snip_k = self.hotkey_mgr.snip_key_desc
        pin_k = self.hotkey_mgr.pin_key_desc
        msg = (
            "<h3>LiveSnip 全功能桌面截图与贴图工具</h3>"
            f"<p><b>快捷键一览：</b></p>"
            f"<ul>"
            f"<li><b>【{snip_k}】</b>：截图（移动自动吸附窗口，单击一键选窗，点鼠标中键秒贴图）</li>"
            f"<li><b>【{pin_k}】</b>：贴图悬浮（鼠标中键点击任务栏托盘也可贴图）</li>"
            f"<li><b>【C】键</b>：截图未框选时，直接复制放大镜准星下的颜色（HEX/RGB）</li>"
            f"<li><b>【Shift】键</b>：切换放大镜取色格式（HEX / RGB）</li>"
            f"<li><b>【F4】键</b>：切换贴图鼠标穿透（开启后可描摹底层内容）</li>"
            f"<li><b>【1 / 2】键</b>：对准贴图逆时针/顺时针旋转 90 度</li>"
            f"<li><b>【3 / 4】键</b>：对准贴图水平/垂直镜像翻转</li>"
            f"<li><b>【空格键】</b>：贴图开启/关闭矢量画板标注</li>"
            f"<li><b>微信同款原地划选文字</b>：直接鼠标左键拖拽选词复制！</li>"
            f"</ul>"
        )
        QMessageBox.information(None, "LiveSnip 操作指南", msg)

    def quit_app(self):
        global _single_instance_mutex
        if _single_instance_mutex:
            try:
                ctypes.windll.kernel32.CloseHandle(_single_instance_mutex)
                _single_instance_mutex = None
            except Exception:
                pass
        lock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_instance.pid")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
        self.hotkey_mgr.stop()
        self.snipper.close()
        self.close_all_pins()
        self.app.quit()

    def run(self):
        return self.app.exec()

# Backward-compatibility alias for tests and external scripts
SnipasteApp = LiveSnipApp

_single_instance_mutex = None

def check_and_clean_single_instance():
    """Ensure safe single instance execution:
    Uses Windows Named Mutex (Local\\LiveSnip_SingleInstance_Mutex) and
    safely verifies process image name before terminating older duplicate instances,
    preventing PID-reuse collateral damage.
    """
    global _single_instance_mutex
    lock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_instance.pid")
    my_pid = os.getpid()

    if sys.platform == "win32":
        try:
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            ERROR_ALREADY_EXISTS = 183
            mutex_name = "Local\\LiveSnip_SingleInstance_Mutex"

            _single_instance_mutex = kernel32.CreateMutexW(None, False, mutex_name)
            last_err = kernel32.GetLastError()

            if last_err == ERROR_ALREADY_EXISTS:
                # Existing instance detected. If user explicitly re-launched the app,
                # safely terminate previous duplicate instance only after verifying its image name.
                if os.path.exists(lock_file):
                    try:
                        with open(lock_file, "r", encoding="utf-8") as f:
                            old_pid_str = f.read().strip()
                        if old_pid_str.isdigit():
                            old_pid = int(old_pid_str)
                            if old_pid != my_pid:
                                # PROCESS_QUERY_LIMITED_INFORMATION (0x1000) | PROCESS_TERMINATE (0x0001)
                                h_proc = kernel32.OpenProcess(0x1001, False, old_pid)
                                if h_proc:
                                    try:
                                        buf = ctypes.create_unicode_buffer(1024)
                                        size = wintypes.DWORD(1024)
                                        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                                            img_name = buf.value.lower()
                                            # Strict validation: must be python/pythonw or LiveSnip/Snipaste executable
                                            if any(token in img_name for token in ("python", "livesnip", "snipaste")):
                                                kernel32.TerminateProcess(h_proc, 1)
                                                import time
                                                time.sleep(0.2)
                                    finally:
                                        kernel32.CloseHandle(h_proc)
                    except Exception:
                        pass

                # Recreate or take ownership of mutex
                if _single_instance_mutex:
                    kernel32.CloseHandle(_single_instance_mutex)
                _single_instance_mutex = kernel32.CreateMutexW(None, False, mutex_name)
        except Exception:
            pass

    try:
        with open(lock_file, "w", encoding="utf-8") as f:
            f.write(str(my_pid))
    except Exception:
        pass

if __name__ == "__main__":
    check_and_clean_single_instance()
    app = LiveSnipApp()
    sys.exit(app.run())
