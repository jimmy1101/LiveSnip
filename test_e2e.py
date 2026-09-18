# -*- coding: utf-8 -*-
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF
from ui.pin_window import PinWindow
from core.ocr_engine import TextBlock, split_text_into_chars

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)
    
    # 1. Create a test image
    pix = QPixmap(500, 250)
    pix.fill(QColor(255, 255, 255))
    p = QPainter(pix)
    p.setFont(QFont("Arial", 16))
    p.setPen(QColor(0, 0, 0))
    p.drawText(50, 60, "Hello World")
    p.drawText(50, 120, "微信同款原地划选测试")
    p.end()

    # 2. Create PinWindow
    pin = PinWindow(pix, QPoint(100, 100))
    pin.show()

    # 3. Simulate OCR finished with 2 blocks
    t1 = "Hello World"
    r1 = QRectF(50, 40, 200, 30)
    b1 = TextBlock(
        text=t1,
        box=[[50, 40], [250, 40], [250, 70], [50, 70]],
        rect=r1,
        confidence=0.98,
        chars=split_text_into_chars(t1, r1)
    )

    t2 = "微信同款原地划选测试"
    r2 = QRectF(50, 100, 300, 30)
    b2 = TextBlock(
        text=t2,
        box=[[50, 100], [350, 100], [350, 130], [50, 130]],
        rect=r2,
        confidence=0.99,
        chars=split_text_into_chars(t2, r2)
    )
    pin._on_ocr_finished([b1, b2])

    assert len(pin.text_blocks) == 2, "Text blocks should be 2"
    assert len(pin.text_blocks[0].chars) == len(t1), "Chars in block 0 should match text length"
    assert len(pin.text_blocks[1].chars) == len(t2), "Chars in block 1 should match text length"
    print("Pass 1: Text blocks and character-level structures loaded successfully")

    # 4. Test Single-Character Selection
    # Select just the first letter 'H' (line 0, char 0)
    pin.sel_anchor = (0, 0)
    pin.sel_active = (0, 0)
    text, rects = pin.get_selected_text_and_rects()
    assert text == "H", f"Expected 'H', got '{text}'"
    assert len(rects) == 1, f"Expected 1 highlight rect, got {len(rects)}"
    print(f"Pass 2: Single English character selected: '{text}' (width={rects[0].width():.1f}px)")

    # Select just a single Chinese character: '划' (line 1, char 6: "微信同款原地划选测试" -> index 6 is '划')
    # 0:微, 1:信, 2:同, 3:款, 4:原, 5:地, 6:划, 7:选, 8:测, 9:试
    pin.sel_anchor = (1, 6)
    pin.sel_active = (1, 6)
    text_cn, rects_cn = pin.get_selected_text_and_rects()
    assert text_cn == "划", f"Expected '划', got '{text_cn}'"
    print(f"Pass 3: Single Chinese character selected: '{text_cn}' (width={rects_cn[0].width():.1f}px)")

    # 5. Test Sub-Line / Partial Word Selection
    # Select "World" from "Hello World" (indices 6 to 10)
    pin.sel_anchor = (0, 6)
    pin.sel_active = (0, 10)
    text_word, _ = pin.get_selected_text_and_rects()
    assert text_word == "World", f"Expected 'World', got '{text_word}'"
    print(f"Pass 4: Sub-line word selected: '{text_word}'")

    # Select "原地划选" from "微信同款原地划选测试" (indices 4 to 7)
    pin.sel_anchor = (1, 4)
    pin.sel_active = (1, 7)
    text_sub_cn, _ = pin.get_selected_text_and_rects()
    assert text_sub_cn == "原地划选", f"Expected '原地划选', got '{text_sub_cn}'"
    print(f"Pass 5: Sub-phrase Chinese characters selected: '{text_sub_cn}'")

    # Test copying to clipboard
    pin.copy_selected_text()
    app.processEvents()
    copied = QApplication.clipboard().text()
    assert copied == "原地划选", f"Expected '原地划选' in clipboard, got '{copied}'"
    print(f"Pass 6: Clipboard text accurately matches sub-phrase: '{copied}'")

    # 6. Test Multi-Line Character Range Selection
    # From 'World' (line 0, char 6) to '微信同款' (line 1, char 3)
    pin.sel_anchor = (0, 6)
    pin.sel_active = (1, 3)
    text_multi, rects_multi = pin.get_selected_text_and_rects()
    expected_multi = "World\n微信同款"
    assert text_multi == expected_multi, f"Expected '{expected_multi}', got '{text_multi}'"
    assert len(rects_multi) == 2, f"Expected 2 highlight rects across 2 lines, got {len(rects_multi)}"
    print(f"Pass 7: Multi-line partial character range selected successfully:\n{text_multi}")

    # Wait for any worker thread
    if hasattr(pin, "ocr_worker") and pin.ocr_worker.isRunning():
        pin.ocr_worker.wait()
    pin.close()
    print("\nALL CHARACTER-LEVEL TESTS PASSED WITH 100% ACCURACY!")

if __name__ == "__main__":
    run_test()
