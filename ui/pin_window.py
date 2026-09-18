import math
import ctypes
from typing import List, Set, Optional, Tuple
from PySide6.QtCore import (
    Qt, QRect, QRectF, QPointF, QPoint, Signal, QTimer
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QCursor,
    QFont, QAction, QKeySequence, QTransform,
    QLinearGradient, QRadialGradient
)
from PySide6.QtWidgets import (
    QWidget, QApplication, QMenu, QFileDialog, QPushButton,
    QToolTip, QInputDialog
)

from core.ocr_engine import TextBlock, CharInfo, OcrWorker, split_text_into_chars
from core.annotation import (
    AnnotationManager, RectShape, EllipseShape, ArrowShape,
    PenShape, TextShape, MosaicShape
)
from ui.annotation_bar import AnnotationToolbar

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

class FloatingCopyBubble(QPushButton):
    """Mini floating button that pops up after text is selected."""
    def __init__(self, parent=None):
        super().__init__("📋 复制文本", parent)
        self.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide()

class PinWindow(QWidget):
    close_requested = Signal(object)
    shadow_toggled = Signal(bool)

    MODE_NONE = 0
    MODE_DRAG_WINDOW = 1
    MODE_SELECT_TEXT = 2
    MODE_ANNOTATING = 3

    def __init__(self, pixmap: QPixmap, initial_pos: Optional[QPoint] = None, enable_shadow: bool = True, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self.current_zoom = 1.0
        self.opacity_val = 1.0
        self.is_click_through = False
        self.has_shadow = enable_shadow
        self.SHADOW_MARGIN = 16

        self.content_w = self.original_pixmap.width()
        self.content_h = self.original_pixmap.height()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        m = self.shadow_margin
        self.resize(self.content_w + 2 * m, self.content_h + 2 * m)
        if initial_pos:
            self.move(initial_pos - QPoint(m, m))

        self.setMouseTracking(True)

        # 1. OCR state
        self.is_ocr_running = True
        self.text_blocks: List[TextBlock] = []

        # 2. Character-level selection state: (line_index, char_index)
        self.sel_anchor: Optional[Tuple[int, int]] = None
        self.sel_active: Optional[Tuple[int, int]] = None

        # 3. Vector Annotation System
        self.annot_mgr = AnnotationManager()
        self.is_annot_mode = False
        self.drawing_start_pt: Optional[QPointF] = None
        self.drawing_pen_points: List[QPointF] = []
        self.current_drawing_shape = None

        self.annot_bar = AnnotationToolbar(self)
        self.annot_bar.tool_changed.connect(self._on_annot_tool_changed)
        self.annot_bar.color_changed.connect(lambda c: setattr(self.annot_mgr, "current_color", c))
        self.annot_bar.width_changed.connect(lambda w: setattr(self.annot_mgr, "current_width", w))
        self.annot_bar.undo_clicked.connect(self._undo_annot)
        self.annot_bar.redo_clicked.connect(self._redo_annot)
        self.annot_bar.hide()

        # Interaction state
        self.current_mode = self.MODE_NONE
        self.drag_window_offset = QPoint()

        # Mini floating copy bubble
        self.copy_bubble = FloatingCopyBubble(self)
        self.copy_bubble.clicked.connect(self.copy_selected_text)

        # Active worker threads registry to prevent QThread GC while running
        self._active_workers = set()

        # Launch OCR in background
        self._start_ocr()

    def _start_ocr(self):
        self.is_ocr_running = True
        if hasattr(self, "_active_workers"):
            self._active_workers = {w for w in self._active_workers if w.isRunning()}
        else:
            self._active_workers = set()

        if hasattr(self, "ocr_worker") and self.ocr_worker is not None:
            if self.ocr_worker.isRunning():
                self.ocr_worker.requestInterruption()
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    try:
                        self.ocr_worker.finished_ocr.disconnect()
                    except Exception:
                        pass
                self._active_workers.add(self.ocr_worker)

        self.ocr_worker = OcrWorker(self.original_pixmap, parent=None)
        self.ocr_worker.finished_ocr.connect(self._on_ocr_finished)
        self.ocr_worker.finished.connect(self.ocr_worker.deleteLater)
        self._active_workers.add(self.ocr_worker)
        self.ocr_worker.start()

    def _on_ocr_finished(self, blocks: List[TextBlock]):
        self.is_ocr_running = False
        self.text_blocks = blocks
        self.update()

    # --- Shadow & Content Geometry Helpers ---

    @property
    def shadow_margin(self) -> int:
        return self.SHADOW_MARGIN if self.has_shadow else 0

    @property
    def image_width(self) -> int:
        return self.content_w

    @property
    def image_height(self) -> int:
        return self.content_h

    def content_rect(self) -> QRect:
        m = self.shadow_margin
        return QRect(m, m, self.content_w, self.content_h)

    def content_rect_f(self) -> QRectF:
        m = float(self.shadow_margin)
        return QRectF(m, m, float(self.content_w), float(self.content_h))

    def set_shadow_enabled(self, enabled: bool):
        if self.has_shadow == enabled:
            return
        old_m = self.shadow_margin
        self.has_shadow = enabled
        new_m = self.shadow_margin

        delta = old_m - new_m
        new_pos = self.pos() + QPoint(delta, delta)
        new_w = self.content_w + 2 * new_m
        new_h = self.content_h + 2 * new_m

        self.setGeometry(new_pos.x(), new_pos.y(), new_w, new_h)
        if self.is_annot_mode:
            self._position_annot_bar()
        self.update()

    # --- Click-Through & Transformation Features ---

    def toggle_click_through(self):
        """Toggles mouse click-through (drawing/tracing aid). Press F4 to toggle."""
        self.is_click_through = not self.is_click_through
        hwnd = int(self.winId())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if self.is_click_through:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT)
            QToolTip.showText(QCursor.pos(), "已开启鼠标穿透 (描图模式)\n按 F4 恢复正常交互", self, msecShowTime=2500)
        else:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
            QToolTip.showText(QCursor.pos(), "已恢复正常鼠标交互", self, msecShowTime=1500)

    def rotate_90(self, clockwise: bool = True):
        """Rotate pinned image 90 degrees."""
        transform = QTransform().rotate(90 if clockwise else -90)
        self.original_pixmap = self.original_pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        self.content_w, self.content_h = self.content_h, self.content_w
        m = self.shadow_margin
        self.resize(self.content_w + 2 * m, self.content_h + 2 * m)
        self.sel_anchor = None
        self.sel_active = None
        self.annot_mgr.clear()
        self._start_ocr()
        self.update()

    def flip(self, horizontal: bool = True):
        """Flip pinned image horizontally or vertically."""
        transform = QTransform().scale(-1 if horizontal else 1, 1 if horizontal else -1)
        self.original_pixmap = self.original_pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        self.sel_anchor = None
        self.sel_active = None
        self.annot_mgr.clear()
        self._start_ocr()
        self.update()

    def toggle_annotation_mode(self):
        """Toggle secondary markup drawing board on this pinned window."""
        self.is_annot_mode = not self.is_annot_mode
        if self.is_annot_mode:
            self.annot_bar.show()
            self._position_annot_bar()
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.annot_bar.hide()
            self.annot_mgr.current_tool = AnnotationManager.TOOL_NONE
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.update()

    def _position_annot_bar(self):
        m = self.shadow_margin
        ab_size = self.annot_bar.sizeHint()
        x = m + max(5, (self.content_w - ab_size.width()) // 2)
        y = m + max(5, self.content_h - ab_size.height() - 8)
        self.annot_bar.move(x, y)

    def _on_annot_tool_changed(self, tool_id: str):
        self.annot_mgr.current_tool = tool_id

    def _undo_annot(self):
        if self.annot_mgr.undo():
            self.update()

    def _redo_annot(self):
        if self.annot_mgr.redo():
            self.update()

    # --- Geometry & Coordinate Mapping ---

    def _scale_x(self) -> float:
        return self.content_w / max(1, self.original_pixmap.width())

    def _scale_y(self) -> float:
        return self.content_h / max(1, self.original_pixmap.height())

    def get_block_display_rect(self, block: TextBlock) -> QRectF:
        sx = self._scale_x()
        sy = self._scale_y()
        r = block.rect
        return QRectF(r.x() * sx, r.y() * sy, r.width() * sx, r.height() * sy)

    def get_char_display_rect(self, block: TextBlock, char_info: CharInfo) -> QRectF:
        sx = self._scale_x()
        sy = self._scale_y()
        r = char_info.rect
        return QRectF(r.x() * sx, r.y() * sy, r.width() * sx, r.height() * sy)

    def find_char_at_pos(self, pt: QPointF) -> Optional[Tuple[int, int]]:
        if not self.text_blocks:
            return None

        best_line_idx = None
        min_dist_y = 9999.0

        for idx, block in enumerate(self.text_blocks):
            if not block.chars:
                continue
            d_rect = self.get_block_display_rect(block)
            if d_rect.top() - 4 <= pt.y() <= d_rect.bottom() + 4:
                if d_rect.left() - 20 <= pt.x() <= d_rect.right() + 20:
                    best_line_idx = idx
                    break

            cy = d_rect.center().y()
            dy = abs(pt.y() - cy)
            if dy < min_dist_y and dy < d_rect.height() * 0.9:
                if d_rect.left() - 30 <= pt.x() <= d_rect.right() + 30:
                    min_dist_y = dy
                    best_line_idx = idx

        if best_line_idx is None:
            return None

        block = self.text_blocks[best_line_idx]
        chars = block.chars
        if not chars:
            return None

        first_rect = self.get_char_display_rect(block, chars[0])
        last_rect = self.get_char_display_rect(block, chars[-1])

        if pt.x() <= first_rect.left():
            return (best_line_idx, 0)
        if pt.x() >= last_rect.right():
            return (best_line_idx, len(chars) - 1)

        for c_idx, c_info in enumerate(chars):
            c_rect = self.get_char_display_rect(block, c_info)
            if c_rect.left() <= pt.x() <= c_rect.right():
                return (best_line_idx, c_idx)

        closest_c = 0
        min_dx = 9999.0
        for c_idx, c_info in enumerate(chars):
            c_rect = self.get_char_display_rect(block, c_info)
            dx = abs(pt.x() - c_rect.center().x())
            if dx < min_dx:
                min_dx = dx
                closest_c = c_idx

        return (best_line_idx, closest_c)

    def get_selection_span(self) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        if self.sel_anchor is None or self.sel_active is None:
            return None
        l1, c1 = self.sel_anchor
        l2, c2 = self.sel_active
        if l1 < l2 or (l1 == l2 and c1 <= c2):
            return (l1, c1), (l2, c2)
        else:
            return (l2, c2), (l1, c1)

    def get_selected_text_and_rects(self) -> Tuple[str, List[QRectF]]:
        span = self.get_selection_span()
        if not span:
            return "", []

        (s_line, s_char), (e_line, e_char) = span
        selected_text_lines = []
        highlight_rects = []

        for l_idx in range(s_line, e_line + 1):
            if l_idx >= len(self.text_blocks):
                break
            block = self.text_blocks[l_idx]
            if not block.chars:
                continue

            num_chars = len(block.chars)
            if l_idx == s_line and l_idx == e_line:
                c_start = max(0, min(s_char, num_chars - 1))
                c_end = max(0, min(e_char, num_chars - 1))
            elif l_idx == s_line:
                c_start = max(0, min(s_char, num_chars - 1))
                c_end = num_chars - 1
            elif l_idx == e_line:
                c_start = 0
                c_end = max(0, min(e_char, num_chars - 1))
            else:
                c_start = 0
                c_end = num_chars - 1

            if c_start <= c_end:
                line_sub = "".join(block.chars[i].char for i in range(c_start, c_end + 1))
                selected_text_lines.append(line_sub)

                first_r = self.get_char_display_rect(block, block.chars[c_start])
                last_r = self.get_char_display_rect(block, block.chars[c_end])
                block_r = self.get_block_display_rect(block)

                x = first_r.left()
                w = max(2.0, last_r.right() - x)
                y = block_r.top()
                h = block_r.height()
                highlight_rects.append(QRectF(x, y, w, h))

        full_text = "\n".join(selected_text_lines)
        return full_text, highlight_rects

    def has_selection(self) -> bool:
        text, _ = self.get_selected_text_and_rects()
        return len(text) > 0

    # --- Mouse & Keyboard Events ---

    def mousePressEvent(self, event):
        pos = event.position()
        m = self.shadow_margin
        content_pt = pos - QPointF(m, m)

        # If click falls on the outer shadow margin
        if not self.content_rect().contains(pos.toPoint()):
            if event.button() == Qt.MouseButton.LeftButton:
                self.current_mode = self.MODE_DRAG_WINDOW
                self.drag_window_offset = event.globalPosition().toPoint() - self.pos()
                if self.sel_anchor is not None:
                    self.sel_anchor = None
                    self.sel_active = None
                    self.copy_bubble.hide()
                self.update()
            return

        # If in annotation mode and active tool selected
        if self.is_annot_mode and self.annot_mgr.current_tool != AnnotationManager.TOOL_NONE:
            tool = self.annot_mgr.current_tool
            pt = content_pt

            if tool == AnnotationManager.TOOL_TEXT:
                text, ok = QInputDialog.getText(self, "添加标注文字", "输入文字:")
                if ok and text.strip():
                    font = QFont("Segoe UI", max(10, self.annot_mgr.current_width * 3), QFont.Weight.Bold)
                    shape = TextShape(pos=pt, text=text.strip(), color=self.annot_mgr.current_color, font=font)
                    self.annot_mgr.add_shape(shape)
                    self.update()
                return

            self.drawing_start_pt = pt
            if tool in (AnnotationManager.TOOL_PEN, AnnotationManager.TOOL_HIGHLIGHTER):
                self.drawing_pen_points = [pt]
            self.current_mode = self.MODE_ANNOTATING
            self.update()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            char_loc = self.find_char_at_pos(content_pt)

            if char_loc is not None:
                self.current_mode = self.MODE_SELECT_TEXT
                self.sel_anchor = char_loc
                self.sel_active = char_loc
                self.copy_bubble.hide()
            else:
                self.current_mode = self.MODE_DRAG_WINDOW
                self.drag_window_offset = event.globalPosition().toPoint() - self.pos()
                if self.sel_anchor is not None:
                    self.sel_anchor = None
                    self.sel_active = None
                    self.copy_bubble.hide()

            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        m = self.shadow_margin
        content_pt = pos - QPointF(m, m)

        if self.current_mode == self.MODE_ANNOTATING and self.drawing_start_pt is not None:
            tool = self.annot_mgr.current_tool
            pt = content_pt

            if tool == AnnotationManager.TOOL_RECT:
                r = QRectF(self.drawing_start_pt, pt).normalized()
                self.current_drawing_shape = RectShape(rect=r, color=self.annot_mgr.current_color, width=self.annot_mgr.current_width)
            elif tool == AnnotationManager.TOOL_ELLIPSE:
                r = QRectF(self.drawing_start_pt, pt).normalized()
                self.current_drawing_shape = EllipseShape(rect=r, color=self.annot_mgr.current_color, width=self.annot_mgr.current_width)
            elif tool == AnnotationManager.TOOL_ARROW:
                self.current_drawing_shape = ArrowShape(start=self.drawing_start_pt, end=pt, color=self.annot_mgr.current_color, width=self.annot_mgr.current_width)
            elif tool in (AnnotationManager.TOOL_PEN, AnnotationManager.TOOL_HIGHLIGHTER):
                self.drawing_pen_points.append(pt)
                is_high = (tool == AnnotationManager.TOOL_HIGHLIGHTER)
                self.current_drawing_shape = PenShape(points=list(self.drawing_pen_points), color=self.annot_mgr.current_color, width=self.annot_mgr.current_width, is_highlighter=is_high)
            elif tool == AnnotationManager.TOOL_MOSAIC:
                r = QRectF(self.drawing_start_pt, pt).normalized()
                self.current_drawing_shape = MosaicShape(rect=r, block_size=12)

            self.update()
            return

        if self.current_mode == self.MODE_SELECT_TEXT:
            char_loc = self.find_char_at_pos(content_pt)
            if char_loc is not None:
                self.sel_active = char_loc
                self.update()

        elif self.current_mode == self.MODE_DRAG_WINDOW:
            self.move(event.globalPosition().toPoint() - self.drag_window_offset)

        else:
            if not self.is_annot_mode:
                if self.content_rect().contains(pos.toPoint()):
                    char_loc = self.find_char_at_pos(content_pt)
                    if char_loc is not None:
                        self.setCursor(Qt.CursorShape.IBeamCursor)
                    else:
                        self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, event):
        if self.current_mode == self.MODE_ANNOTATING:
            if self.current_drawing_shape is not None:
                self.annot_mgr.add_shape(self.current_drawing_shape)
                self.current_drawing_shape = None
            self.drawing_start_pt = None
            self.drawing_pen_points = []
            self.current_mode = self.MODE_NONE
            self.update()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.current_mode == self.MODE_SELECT_TEXT:
                text, _ = self.get_selected_text_and_rects()
                if text:
                    m = self.shadow_margin
                    bx = int(event.position().x() + 10)
                    by = int(event.position().y() - 32)
                    bx = max(m + 5, min(bx, m + self.content_w - self.copy_bubble.width() - 5))
                    by = max(m + 5, min(by, m + self.content_h - self.copy_bubble.height() - 5))
                    self.copy_bubble.move(bx, by)
                    self.copy_bubble.show()
                else:
                    self.copy_bubble.hide()

            self.current_mode = self.MODE_NONE
            self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            m = self.shadow_margin
            content_pt = event.position() - QPointF(m, m)
            if not self.is_annot_mode and self.content_rect().contains(event.position().toPoint()):
                char_loc = self.find_char_at_pos(content_pt)
                if char_loc is not None:
                    line_idx, _ = char_loc
                    line_len = len(self.text_blocks[line_idx].chars)
                    self.sel_anchor = (line_idx, 0)
                    self.sel_active = (line_idx, max(0, line_len - 1))
                    self.copy_bubble.hide()
                    self.update()
                    return

            # Double click empty area or shadow margin to close
            self.close()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()

        # Ctrl + Wheel: Adjust Opacity
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if delta > 0:
                self.opacity_val = min(1.0, self.opacity_val + 0.08)
            else:
                self.opacity_val = max(0.2, self.opacity_val - 0.08)
            self.setWindowOpacity(self.opacity_val)
            QToolTip.showText(QCursor.pos(), f"不透明度: {int(self.opacity_val * 100)}%", self)
            return

        # Normal Wheel: Zoom in / Zoom out
        factor = 1.1 if delta > 0 else 0.9
        new_cw = int(self.content_w * factor)
        new_ch = int(self.content_h * factor)

        if 40 < new_cw < 8000 and 40 < new_ch < 8000:
            cursor_pos = event.position()
            m = self.shadow_margin
            content_cursor_x = cursor_pos.x() - m
            content_cursor_y = cursor_pos.y() - m
            rx = max(0.0, min(1.0, content_cursor_x / max(1, self.content_w)))
            ry = max(0.0, min(1.0, content_cursor_y / max(1, self.content_h)))

            old_img_x = self.x() + m
            old_img_y = self.y() + m

            new_img_x = old_img_x - int((new_cw - self.content_w) * rx)
            new_img_y = old_img_y - int((new_ch - self.content_h) * ry)

            self.content_w = new_cw
            self.content_h = new_ch

            new_win_x = new_img_x - m
            new_win_y = new_img_y - m
            new_win_w = new_cw + 2 * m
            new_win_h = new_ch + 2 * m

            self.setGeometry(new_win_x, new_win_y, new_win_w, new_win_h)
            self.copy_bubble.hide()
            if self.is_annot_mode:
                self._position_annot_bar()
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.is_annot_mode:
                self.toggle_annotation_mode()
            else:
                self.close()
        elif event.key() == Qt.Key.Key_F4:
            self.toggle_click_through()
        elif event.key() == Qt.Key.Key_1:
            self.rotate_90(clockwise=False)
        elif event.key() == Qt.Key.Key_2:
            self.rotate_90(clockwise=True)
        elif event.key() == Qt.Key.Key_3:
            self.flip(horizontal=True)
        elif event.key() == Qt.Key.Key_4:
            self.flip(horizontal=False)
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_annotation_mode()
        elif event.matches(QKeySequence.StandardKey.Undo):
            self._undo_annot()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self._redo_annot()
        elif event.matches(QKeySequence.StandardKey.Copy):
            if self.has_selection():
                self.copy_selected_text()
            else:
                self.copy_full_image()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2e2e2e;
                color: #ffffff;
                border: 1px solid #454545;
                padding: 4px;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
            }
        """)

        if self.has_selection():
            act_copy_sel = menu.addAction("📋 复制划选文字 (Ctrl+C)")
            act_copy_sel.triggered.connect(self.copy_selected_text)

        act_copy_all_text = menu.addAction("📑 提取整图全部文字")
        act_copy_all_text.triggered.connect(self.copy_all_text)

        menu.addSeparator()

        annot_text = "✏️ 关闭画板标注 (空格)" if self.is_annot_mode else "✏️ 开启画板标注 (空格)"
        act_annot = menu.addAction(annot_text)
        act_annot.triggered.connect(self.toggle_annotation_mode)

        pass_through_text = "👻 取消鼠标穿透 (F4)" if self.is_click_through else "👻 开启鼠标穿透描摹 (F4)"
        act_pass = menu.addAction(pass_through_text)
        act_pass.triggered.connect(self.toggle_click_through)

        menu.addSeparator()

        sub_rotate = menu.addMenu("🔄 旋转与翻转")
        sub_rotate.setStyleSheet(menu.styleSheet())
        act_r90 = sub_rotate.addAction("顺时针旋转 90° (按 2)")
        act_r90.triggered.connect(lambda: self.rotate_90(True))
        act_l90 = sub_rotate.addAction("逆时针旋转 90° (按 1)")
        act_l90.triggered.connect(lambda: self.rotate_90(False))
        act_fh = sub_rotate.addAction("水平镜像翻转 (按 3)")
        act_fh.triggered.connect(lambda: self.flip(True))
        act_fv = sub_rotate.addAction("垂直镜像翻转 (按 4)")
        act_fv.triggered.connect(lambda: self.flip(False))

        menu.addSeparator()

        act_copy_img = menu.addAction("🖼️ 复制图片到剪贴板")
        act_copy_img.triggered.connect(self.copy_full_image)

        act_save = menu.addAction("💾 另存为图片...")
        act_save.triggered.connect(self.save_image)

        menu.addSeparator()

        act_shadow = menu.addAction("开启贴图阴影")
        act_shadow.setCheckable(True)
        act_shadow.setChecked(self.has_shadow)
        act_shadow.toggled.connect(lambda chk: self.shadow_toggled.emit(chk))

        menu.addSeparator()

        act_close = menu.addAction("❌ 关闭贴图 (Esc / 双击)")
        act_close.triggered.connect(self.close)

        menu.exec(event.globalPos())

    def closeEvent(self, event):
        workers = []
        if hasattr(self, "ocr_worker") and self.ocr_worker is not None:
            workers.append(self.ocr_worker)
        if hasattr(self, "_active_workers"):
            workers.extend(self._active_workers)

        for w in set(workers):
            if w.isRunning():
                w.requestInterruption()
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    try:
                        w.finished_ocr.disconnect()
                    except Exception:
                        pass
                w.wait(500)
        super().closeEvent(event)

    # --- Actions ---

    def copy_selected_text(self):
        full_text, _ = self.get_selected_text_and_rects()
        if full_text:
            QApplication.clipboard().setText(full_text)
            self.copy_bubble.hide()
            preview = full_text.replace("\n", " ")
            if len(preview) > 16:
                preview = preview[:16] + "..."
            QToolTip.showText(QCursor.pos(), f"已复制: \"{preview}\"", self, msecShowTime=1500)

    def copy_all_text(self):
        if not self.text_blocks:
            QToolTip.showText(QCursor.pos(), "未识别到文字", self)
            return

        lines = [b.text.strip() for b in self.text_blocks if b.text.strip()]
        full_text = "\n".join(lines)
        QApplication.clipboard().setText(full_text)
        QToolTip.showText(QCursor.pos(), f"已提取整图 {len(lines)} 行文字", self, msecShowTime=1500)

    def get_baked_pixmap(self) -> QPixmap:
        """Returns the pixmap with secondary annotations baked in."""
        pix = self.original_pixmap.copy()
        if self.annot_mgr.shapes:
            p = QPainter(pix)
            self.annot_mgr.draw_all(p, self.original_pixmap)
            p.end()
        return pix

    def copy_full_image(self):
        QApplication.clipboard().setPixmap(self.get_baked_pixmap())
        QToolTip.showText(QCursor.pos(), "已复制图片到剪贴板", self, msecShowTime=1500)

    def save_image(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存贴图", "", "PNG Image (*.png);;JPEG Image (*.jpg)")
        if path:
            self.get_baked_pixmap().save(path)

    # --- Painting ---

    def _draw_shadow(self, painter: QPainter):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = self.shadow_margin
        cw, ch = self.content_w, self.content_h

        # High-visibility White-Grey Ambient & Directional Shadow
        # Prominent whitish-grey on dark backgrounds, crisp silver-grey on light backgrounds
        c_inner = QColor(230, 235, 245, 215)
        c_mid = QColor(195, 200, 210, 125)
        c_outer = QColor(180, 185, 195, 0)

        # 1. Top
        gt = QLinearGradient(0, m, 0, 0)
        gt.setColorAt(0, c_inner)
        gt.setColorAt(0.35, c_mid)
        gt.setColorAt(1, c_outer)
        painter.fillRect(QRectF(m, 0, cw, m), gt)

        # 2. Bottom
        gb = QLinearGradient(0, m + ch, 0, 2 * m + ch)
        gb.setColorAt(0, c_inner)
        gb.setColorAt(0.4, c_mid)
        gb.setColorAt(1, c_outer)
        painter.fillRect(QRectF(m, m + ch, cw, m), gb)

        # 3. Left
        gl = QLinearGradient(m, 0, 0, 0)
        gl.setColorAt(0, c_inner)
        gl.setColorAt(0.35, c_mid)
        gl.setColorAt(1, c_outer)
        painter.fillRect(QRectF(0, m, m, ch), gl)

        # 4. Right
        gr = QLinearGradient(m + cw, 0, 2 * m + cw, 0)
        gr.setColorAt(0, c_inner)
        gr.setColorAt(0.4, c_mid)
        gr.setColorAt(1, c_outer)
        painter.fillRect(QRectF(m + cw, m, m, ch), gr)

        # 5. Corners (Radial gradients)
        for cx, cy, rx, ry in [
            (m, m, 0, 0),
            (m + cw, m, m + cw, 0),
            (m, m + ch, 0, m + ch),
            (m + cw, m + ch, m + cw, m + ch)
        ]:
            rad = QRadialGradient(cx, cy, m)
            rad.setColorAt(0, c_inner)
            rad.setColorAt(0.35, c_mid)
            rad.setColorAt(1, c_outer)
            painter.fillRect(QRectF(rx, ry, m, m), rad)

        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Outer Drop Shadow
        if self.has_shadow:
            self._draw_shadow(painter)

        m = self.shadow_margin
        painter.save()
        painter.translate(m, m)

        # 2. Base image
        painter.drawPixmap(0, 0, self.content_w, self.content_h, self.original_pixmap)

        # Subtle 1.5px crisp whitish-grey outline around image when shadow is enabled
        if self.has_shadow:
            painter.setPen(QPen(QColor(220, 225, 235, 220), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(0, 0, self.content_w - 1, self.content_h - 1)

        # 3. Vector annotations (Secondary markup)
        if self.annot_mgr.shapes:
            self.annot_mgr.draw_all(painter, self.original_pixmap)
        if self.current_drawing_shape is not None:
            self.current_drawing_shape.draw(painter, self.original_pixmap)

        # 4. Live Text Highlight (character-level precision in content space)
        if not self.is_annot_mode:
            _, highlight_rects = self.get_selected_text_and_rects()
            if highlight_rects:
                painter.setBrush(QBrush(QColor(0, 120, 215, 85)))
                painter.setPen(QPen(QColor(0, 120, 215, 180), 1))
                for hr in highlight_rects:
                    painter.drawRoundedRect(hr, 2, 2)

        # 5. OCR progress indicator
        if self.is_ocr_running:
            painter.setFont(QFont("Segoe UI", 8))
            badge_rect = QRectF(self.content_w - 85, self.content_h - 20, 80, 16)
            painter.setBrush(QColor(0, 0, 0, 140))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, 3, 3)
            painter.setPen(QColor(0, 255, 180))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "OCR 识别中...")

        painter.restore()
