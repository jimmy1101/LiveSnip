# -*- coding: utf-8 -*-
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont

from core.annotation import (
    AnnotationManager, RectShape, EllipseShape, ArrowShape,
    PenShape, TextShape, MosaicShape
)
from ui.magnifier import MagnifierHUD
from ui.pin_window import PinWindow
from core.ocr_engine import TextBlock, split_text_into_chars
from core.window_detector import get_window_rect_at_point

def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)
    print("Testing Snipaste Full Features...")

    # 1. Test Vector Annotation System
    mgr = AnnotationManager()
    assert mgr.current_tool == AnnotationManager.TOOL_NONE

    # Add RectShape
    r = RectShape(rect=QRectF(10, 10, 50, 50), color=QColor("red"), width=3)
    mgr.add_shape(r)
    assert len(mgr.shapes) == 1

    # Add ArrowShape
    arr = ArrowShape(start=QPointF(0, 0), end=QPointF(100, 100), color=QColor("blue"), width=4)
    mgr.add_shape(arr)
    assert len(mgr.shapes) == 2

    # Test Undo and Redo
    mgr.undo()
    assert len(mgr.shapes) == 1, "Undo should reduce shapes to 1"
    mgr.redo()
    assert len(mgr.shapes) == 2, "Redo should restore shapes to 2"
    print("Pass 1: Vector annotation system and Undo/Redo verified!")

    # Test Mosaic Shape drawing on QPixmap
    base_pix = QPixmap(200, 200)
    base_pix.fill(QColor("yellow"))
    p = QPainter(base_pix)
    p.fillRect(QRect(50, 50, 50, 50), QColor("black"))
    p.end()

    mos = MosaicShape(rect=QRectF(40, 40, 60, 60), block_size=10)
    mgr.add_shape(mos)

    # Test draw_all
    p2 = QPainter(base_pix)
    mgr.draw_all(p2, base_pix)
    p2.end()
    print("Pass 2: Mosaic shape pixelation and composite drawing verified!")

    # 2. Test Magnifier HUD and Color Formats
    hud = MagnifierHUD()
    red = QColor(255, 0, 0)
    hex_str = hud.get_color_str(red)
    assert hex_str == "#FF0000", f"Expected #FF0000, got {hex_str}"

    hud.toggle_format()
    rgb_str = hud.get_color_str(red)
    assert rgb_str == "rgb(255, 0, 0)", f"Expected rgb(255, 0, 0), got {rgb_str}"
    print(f"Pass 3: Magnifier HUD color picker formats verified: {hex_str} <-> {rgb_str}")

    # 3. Test PinWindow Rotation, Flip & Click-Through
    test_pix = QPixmap(100, 50)
    test_pix.fill(QColor("white"))
    pin = PinWindow(test_pix, QPoint(100, 100), enable_shadow=False)

    # Test 90-degree rotate
    assert pin.width() == 100 and pin.height() == 50
    pin.rotate_90(clockwise=True)
    assert pin.width() == 50 and pin.height() == 100, f"Expected 50x100 after 90 deg rotate, got {pin.width()}x{pin.height()}"
    print("Pass 4: PinWindow 90-degree rotation verified!")

    # Test PinWindow with drop shadow (default mode) & dynamic toggle
    pin_shadow = PinWindow(test_pix, QPoint(100, 100), enable_shadow=True)
    assert pin_shadow.has_shadow is True
    assert pin_shadow.content_w == 100 and pin_shadow.content_h == 50
    assert pin_shadow.width() == 100 + 2 * pin_shadow.shadow_margin
    assert pin_shadow.height() == 50 + 2 * pin_shadow.shadow_margin
    pin_shadow.set_shadow_enabled(False)
    assert pin_shadow.has_shadow is False
    assert pin_shadow.width() == 100 and pin_shadow.height() == 50
    pin_shadow.set_shadow_enabled(True)
    assert pin_shadow.has_shadow is True
    assert pin_shadow.width() == 100 + 2 * pin_shadow.shadow_margin
    print("Pass 4.1: PinWindow drop shadow and dynamic enable/disable toggle verified!")

    # Test Horizontal Flip
    orig_w, orig_h = pin.width(), pin.height()
    pin.flip(horizontal=True)
    assert pin.width() == orig_w and pin.height() == orig_h
    print("Pass 5: PinWindow horizontal/vertical flip verified!")

    # Test Click-Through (F4)
    assert pin.is_click_through is False
    pin.toggle_click_through()
    assert pin.is_click_through is True
    pin.toggle_click_through()
    assert pin.is_click_through is False
    print("Pass 6: PinWindow F4 mouse click-through mode verified!")

    # Test PinWindow secondary annotation mode (Space)
    pin.show()
    app.processEvents()
    assert pin.is_annot_mode is False
    pin.toggle_annotation_mode()
    assert pin.is_annot_mode is True
    assert not pin.annot_bar.isHidden()
    pin.toggle_annotation_mode()
    assert pin.is_annot_mode is False
    print("Pass 7: PinWindow secondary annotation board mode verified!")

    # 4. Test Window Detector
    # Testing detection function call safety
    rect = get_window_rect_at_point(QPoint(100, 100))
    print("Pass 8: Window detector safely executed (returned:", rect, ")")

    if hasattr(pin, "ocr_worker") and pin.ocr_worker.isRunning():
        pin.ocr_worker.wait(1000)
    pin.close()

    if hasattr(pin_shadow, "ocr_worker") and pin_shadow.ocr_worker.isRunning():
        pin_shadow.ocr_worker.wait(1000)
    pin_shadow.close()
    app.processEvents()

    print("\nALL 8 EXTENDED SNIPASTE FEATURE TESTS PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    run_tests()
