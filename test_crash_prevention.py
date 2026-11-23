import sys
import gc
import time
import faulthandler
faulthandler.enable()

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtCore import QPoint

def test_pin_and_card_lifecycle():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from ui.pin_window import PinWindow
    from ui.translation_card import TranslationCard
    from core.hotkey import GlobalHotkeyManager

    print("--- 1. Testing PinWindow Lifecycle & GC Safety ---", flush=True)
    active_pins = []

    def on_pin_closed(p):
        print(f"on_pin_closed called for {p}", flush=True)
        if p in active_pins:
            active_pins.remove(p)

    for i in range(10):
        pix = QPixmap(100, 100)
        pix.fill(QColor(255, 0, 0))
        pin = PinWindow(pix, QPoint(100 + i * 10, 100 + i * 10))
        pin.closed.connect(on_pin_closed)
        active_pins.append(pin)
        pin.show()

    assert len(active_pins) == 10
    app.processEvents()
    gc.collect()

    # Close half immediately while OCR may still be starting/running
    for p in list(active_pins[:5]):
        p.close()
    
    app.processEvents()
    gc.collect()
    assert len(active_pins) == 5

    # Close remaining
    for pin in list(active_pins):
        pin.close()

    app.processEvents()
    gc.collect()
    assert len(active_pins) == 0
    print("PinWindow GC lifecycle test PASSED.")

    print("--- 2. Testing TranslationCard Lifecycle & GC Safety ---")
    active_cards = []

    def on_card_closed(c):
        if c in active_cards:
            active_cards.remove(c)

    for i in range(5):
        card = TranslationCard()
        card.closed.connect(on_card_closed)
        active_cards.append(card)
        card.show()

    assert len(active_cards) == 5
    app.processEvents()
    gc.collect()

    for card in list(active_cards):
        card.close()

    app.processEvents()
    gc.collect()
    assert len(active_cards) == 0
    print("TranslationCard GC lifecycle test PASSED.")

    print("--- 3. Testing Hotkey nativeEvent robust handling ---")
    mgr = GlobalHotkeyManager()
    if hasattr(mgr, "listener") and mgr.listener:
        # Verify unregister_all and closeEvent safety
        mgr.listener.unregister_all()
        mgr.listener.close()
        print("Hotkey listener lifecycle test PASSED.")

    print(">>> ALL CRASH PREVENTION TESTS PASSED! <<<")
    time.sleep(0.5)
    sys.exit(0)

if __name__ == "__main__":
    try:
        test_pin_and_card_lifecycle()
    except SystemExit:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
