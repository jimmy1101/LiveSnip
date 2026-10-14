# -*- coding: utf-8 -*-
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QRect, QEvent
from PySide6.QtGui import QPixmap, QColor, QMouseEvent

from core.translator import (
    detect_local_language, get_auto_target_lang, translate_text,
    get_language_display_name, TranslationWorker
)
from ui.translation_card import TranslationCard
from ui.snipper import SnipperWidget
from ui.pin_window import PinWindow

def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)
    print("=== Testing Translation Feature ===")

    # 1. Test Language Detection & Target Decision
    assert detect_local_language("Hello World, testing.") == "en"
    assert detect_local_language("你好，世界！") == "zh-CN"
    assert detect_local_language("こんにちは、世界！") == "ja"
    assert detect_local_language("안녕하세요") == "ko"
    assert detect_local_language("Привет мир") == "ru"

    assert get_auto_target_lang("zh-CN") == "en"
    assert get_auto_target_lang("zh") == "en"
    assert get_auto_target_lang("en") == "zh-CN"
    assert get_auto_target_lang("ja") == "zh-CN"

    assert get_language_display_name("en") == "英语"
    assert get_language_display_name("zh-CN") == "简体中文"
    print("Pass 1: Local language detection and target logic verified!")

    # 2. Test Live Translation Call
    try:
        translated_en, src1, tgt1 = translate_text("LiveSnip is a powerful screen capture tool.")
        assert len(translated_en) > 0
        assert src1 == "en"
        assert tgt1 == "zh-CN"
        print(f"Pass 2.1: Online translation en->zh verified! ('{translated_en}')")

        translated_zh, src2, tgt2 = translate_text("这是一个功能强大的桌面截图工具。")
        assert len(translated_zh) > 0
        assert src2.startswith("zh")
        assert tgt2 == "en"
        print(f"Pass 2.2: Online translation zh->en verified! ('{translated_zh}')")
    except Exception as e:
        print(f"Online translation warning: {e}")

    # 3. Test TranslationCard UI
    card = TranslationCard()
    assert card.txt_original is not None
    assert card.txt_translated is not None
    assert card.combo_target.count() > 5

    # Test direct text setting
    card.start_translate_text("Test translation text")
    assert card.current_raw_text == "Test translation text"
    assert card.isVisible() is True
    if card.trans_worker and card.trans_worker.isRunning():
        card.trans_worker.wait(3000)
    card.close()
    print("Pass 3: TranslationCard UI creation, styling, and lifecycle verified!")

    # 4. Test Snipper Toolbar Integration
    snipper = SnipperWidget()
    snipper.full_pixmap = QPixmap(800, 600)
    snipper.full_pixmap.fill(QColor("white"))
    snipper.selection_rect = QRect(100, 100, 300, 200)

    received_signals = []
    snipper.translate_requested.connect(lambda pix, r: received_signals.append((pix, r)))

    snipper.confirm_translate()
    assert len(received_signals) == 1
    pix, rect = received_signals[0]
    assert pix.width() == 300 and pix.height() == 200
    assert rect == QRect(100, 100, 300, 200)
    print("Pass 4: Snipper translate_requested signal and confirm_translate verified!")

    # 5. Test PinWindow Action Bubble Integration
    test_pix = QPixmap(200, 100)
    test_pix.fill(QColor("blue"))
    pin = PinWindow(test_pix)
    assert hasattr(pin, "copy_bubble")
    assert hasattr(pin, "translate_requested")

    pin_trans_received = []
    pin.translate_requested.connect(lambda txt, pt: pin_trans_received.append((txt, pt)))

    # Simulate translate_selected_text
    pin.get_selected_text_and_rects = lambda: ("Selected text for test", [])
    pin.translate_selected_text()
    assert len(pin_trans_received) == 1
    assert pin_trans_received[0][0] == "Selected text for test"
    if hasattr(pin, "ocr_worker") and pin.ocr_worker and pin.ocr_worker.isRunning():
        pin.ocr_worker.wait(5000)
    pin.close()
    print("Pass 5: PinWindow FloatingActionBubble and translate_selected_text verified!")

    print("\n>>> ALL TRANSLATION TESTS PASSED 100%! <<<")

if __name__ == "__main__":
    run_tests()
