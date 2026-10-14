import numpy as np
from dataclasses import dataclass
from typing import List, Optional
from PySide6.QtCore import QThread, Signal, QRectF
from PySide6.QtGui import QImage, QPixmap

@dataclass
class CharInfo:
    char: str
    rect: QRectF

@dataclass
class TextBlock:
    text: str
    box: List[List[float]]  # 4 points: [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
    rect: QRectF
    confidence: float
    chars: List[CharInfo] = None

def split_text_into_chars(text: str, line_rect: QRectF) -> List[CharInfo]:
    """Calculate character-level bounding rects using font weight interpolation."""
    if not text:
        return []

    def char_weight(ch: str) -> float:
        code = ord(ch)
        # CJK ideographs and fullwidth characters
        if (0x4E00 <= code <= 0x9FFF or
            0x3400 <= code <= 0x4DBF or
            0x3000 <= code <= 0x303F or
            0xFF00 <= code <= 0xFFEF or
            0x20000 <= code <= 0x2A6DF):
            return 1.0
        elif ch == ' ':
            return 0.35
        elif ch in 'ijlI1.,:;!\'|`':
            return 0.28
        elif ch in 'mwMW@%#':
            return 0.8
        elif ch in 'frt-()[]{}':
            return 0.4
        else:
            return 0.55

    weights = [char_weight(c) for c in text]
    total_w = sum(weights)
    if total_w <= 0:
        total_w = 1.0

    rx, ry, rw, rh = line_rect.x(), line_rect.y(), line_rect.width(), line_rect.height()
    chars = []
    curr_x = rx
    for i, c in enumerate(text):
        cw = (weights[i] / total_w) * rw
        chars.append(CharInfo(char=c, rect=QRectF(curr_x, ry, cw, rh)))
        curr_x += cw
    return chars

_engine_instance = None

def get_ocr_engine():
    global _engine_instance
    if _engine_instance is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine_instance = RapidOCR()
        except Exception as e:
            print(f"[OCR] Failed to initialize RapidOCR: {e}")
            return None
    return _engine_instance

def qpixmap_to_numpy(pixmap: QPixmap) -> Optional[np.ndarray]:
    """Convert QPixmap to RGB numpy array for RapidOCR."""
    qimage = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width = qimage.width()
    height = qimage.height()
    
    ptr = qimage.constBits()
    # Pointers in PySide6 are memoryview/buffer
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, width, 4))
    # Return RGB (discard alpha for OCR)
    return arr[:, :, :3].copy()

class OcrWorker(QThread):
    finished_ocr = Signal(list)  # Emits List[TextBlock]

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap

    def run(self):
        engine = get_ocr_engine()
        if engine is None or self.isInterruptionRequested():
            self.finished_ocr.emit([])
            return

        try:
            import cv2
            img_np = qpixmap_to_numpy(self.pixmap)
            if img_np is None or img_np.size == 0 or self.isInterruptionRequested():
                self.finished_ocr.emit([])
                return

            orig_h, orig_w = img_np.shape[:2]
            result = None
            pad_x, pad_y = 0, 0
            scale = 1.0

            # 1. If image is narrow/short (e.g. single line banner, small height < 120),
            # small font and tight borders suppress DBNet detection. Pre-scale and pad directly:
            if orig_h < 120 or orig_w < 150:
                scale = 1.5
                scaled = cv2.resize(img_np, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                pad_val = 32
                padded = cv2.copyMakeBorder(scaled, pad_val, pad_val, pad_val, pad_val, cv2.BORDER_CONSTANT, value=[30, 30, 30])
                result, _ = engine(padded)
                if result:
                    pad_x, pad_y = pad_val, pad_val

            # 2. For standard images (or if small-image upscale didn't detect):
            if not result and not self.isInterruptionRequested():
                result, _ = engine(img_np)
                scale = 1.0
                pad_x, pad_y = 0, 0

            # 3. Fallback: if standard image still returned nothing, try with 1.5x scale and padding
            if not result and not self.isInterruptionRequested():
                scale = 1.5
                scaled = cv2.resize(img_np, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                pad_val = 32
                padded = cv2.copyMakeBorder(scaled, pad_val, pad_val, pad_val, pad_val, cv2.BORDER_CONSTANT, value=[30, 30, 30])
                result, _ = engine(padded)
                if result:
                    pad_x, pad_y = pad_val, pad_val

            if not result or self.isInterruptionRequested():
                self.finished_ocr.emit([])
                return

            blocks = []
            for item in result:
                if self.isInterruptionRequested():
                    return
                # item: [box, text, score]
                raw_box = item[0]
                text = item[1]
                score = float(item[2])

                # Map coordinates back to original image coordinate space
                box = []
                for p in raw_box:
                    ox = max(0.0, min(float(orig_w), (p[0] - pad_x) / scale))
                    oy = max(0.0, min(float(orig_h), (p[1] - pad_y) / scale))
                    box.append([ox, oy])

                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                rect = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
                chars = split_text_into_chars(text, rect)
                blocks.append(TextBlock(text=text, box=box, rect=rect, confidence=score, chars=chars))

            if self.isInterruptionRequested():
                return

            # Sort blocks top-to-bottom, left-to-right
            blocks.sort(key=lambda b: (round(b.rect.y() / 15) * 15, b.rect.x()))
            self.finished_ocr.emit(blocks)
        except Exception as e:
            if not self.isInterruptionRequested():
                print(f"[OCR] Error during recognition: {e}")
            self.finished_ocr.emit([])
