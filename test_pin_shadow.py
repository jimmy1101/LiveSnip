# -*- coding: utf-8 -*-
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QSettings
from PySide6.QtGui import QPixmap, QColor, QImage

from ui.pin_window import PinWindow
from main import SnipasteApp

def test_pin_shadow():
    app = QApplication.instance() or QApplication(sys.argv)
    print("=== Testing Pin Window Drop Shadow Feature ===")

    # 1. Test initial PinWindow creation with shadow (default True)
    base_pix = QPixmap(300, 200)
    base_pix.fill(QColor(240, 240, 240))

    initial_pos = QPoint(200, 200)
    pin = PinWindow(base_pix, initial_pos=initial_pos, enable_shadow=True)
    pin.show()
    app.processEvents()

    assert pin.has_shadow is True, "Default shadow state must be True"
    assert pin.shadow_margin == 16, f"Shadow margin must be 16, got {pin.shadow_margin}"
    assert pin.content_w == 300
    assert pin.content_h == 200
    assert pin.width() == 300 + 2 * 16, f"Window width must include margins: {pin.width()}"
    assert pin.height() == 200 + 2 * 16, f"Window height must include margins: {pin.height()}"

    # Content rect in local coordinates
    c_rect = pin.content_rect()
    assert c_rect.x() == 16 and c_rect.y() == 16
    assert c_rect.width() == 300 and c_rect.height() == 200
    print("Pass 1: PinWindow creates with default shadow=True and proper 16px outer margin!")

    # 2. Test dynamic toggling of shadow
    # Turn shadow OFF
    pin.set_shadow_enabled(False)
    app.processEvents()
    assert pin.has_shadow is False
    assert pin.shadow_margin == 0
    assert pin.width() == 300 and pin.height() == 200
    assert pin.content_rect().x() == 0 and pin.content_rect().y() == 0
    print("Pass 2: Dynamic shadow toggle OFF -> margins collapse smoothly to 0, size matches image!")

    # Turn shadow back ON
    pin.set_shadow_enabled(True)
    app.processEvents()
    assert pin.has_shadow is True
    assert pin.shadow_margin == 16
    assert pin.width() == 300 + 32 and pin.height() == 200 + 32
    print("Pass 3: Dynamic shadow toggle ON -> margins and dimensions restore perfectly!")

    # 3. Test PaintEvent rendering
    # Grab window to confirm shadow renders without crash
    grabbed = pin.grab()
    assert not grabbed.isNull()
    assert grabbed.width() == 300 + 32
    assert grabbed.height() == 200 + 32
    print("Pass 4: PinWindow paintEvent renders drop shadow smoothly into image buffer!")

    # 4. Test SnipasteApp Tray Menu and Setting Synchronization
    snip_app = SnipasteApp()
    assert hasattr(snip_app, "act_shadow"), "SnipasteApp must have act_shadow tray menu item"
    assert snip_app.act_shadow.isCheckable() is True, "act_shadow must be checkable"
    assert snip_app.act_shadow.text() == "开启贴图阴影", f"Unexpected text: {snip_app.act_shadow.text()}"

    # Test toggling via SnipasteApp
    snip_app.create_pin(base_pix, QPoint(100, 100))
    active_pin = snip_app.active_pins[-1]
    assert active_pin.has_shadow == snip_app.enable_shadow

    # Toggle to False
    snip_app.set_shadow_enabled(False)
    assert snip_app.enable_shadow is False
    assert snip_app.act_shadow.isChecked() is False
    assert active_pin.has_shadow is False

    # Toggle to True
    snip_app.set_shadow_enabled(True)
    assert snip_app.enable_shadow is True
    assert snip_app.act_shadow.isChecked() is True
    assert active_pin.has_shadow is True
    print("Pass 5: Tray menu '开启贴图阴影' checkable action and active pins stay 100% in sync!")

    # Cleanup
    snip_app.close_all_pins()
    pin.close()
    print(">>> 贴图阴影全部功能与右键设置测试 100% 成功！ <<<")

if __name__ == "__main__":
    test_pin_shadow()
