import ctypes
from typing import Optional, List
from PySide6.QtCore import Qt, QRect, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QGuiApplication,
    QCursor, QFont, QFontMetrics, QKeySequence
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QFileDialog, QApplication,
    QToolTip, QInputDialog, QFrame, QButtonGroup, QColorDialog
)

from core.annotation import (
    AnnotationManager, RectShape, EllipseShape, ArrowShape,
    PenShape, TextShape, MosaicShape
)
from core.window_detector import get_window_rect_at_point
from ui.magnifier import MagnifierHUD, MagnifierOverlayWidget
from ui.annotation_bar import PALETTE_COLORS, ColorDotButton

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def force_foreground_window(hwnd: int):
    """Force window to foreground by attaching thread input (bypasses Windows foreground lock)."""
    try:
        fore_hwnd = user32.GetForegroundWindow()
        if fore_hwnd == hwnd:
            return
        fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
        app_thread = kernel32.GetCurrentThreadId()

        if fore_thread != 0 and fore_thread != app_thread:
            user32.AttachThreadInput(fore_thread, app_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.AttachThreadInput(fore_thread, app_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
    except Exception as e:
        print(f"[Snipper] Error setting foreground: {e}")

class UnifiedSnipperToolbar(QWidget):
    """Snipaste-style all-in-one horizontal toolbar with annotations, actions, and palette row."""
    pin_clicked = Signal()
    copy_clicked = Signal()
    save_clicked = Signal()
    close_clicked = Signal()
    tool_changed = Signal(str)
    color_changed = Signal(QColor)
    width_changed = Signal(int)
    undo_clicked = Signal()
    redo_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget#main_panel {
                background-color: #242424;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
            }
            QPushButton {
                background-color: transparent;
                color: #e0e0e0;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 12px;
                padding: 4px 8px;
                border: 1px solid transparent;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #383838;
                color: #ffffff;
            }
            QPushButton:checked {
                background-color: #0078d4;
                color: #ffffff;
                border: 1px solid #1084d8;
            }
            QPushButton#pin_btn {
                font-weight: bold;
                color: #00d084;
            }
            QPushButton#pin_btn:hover {
                background-color: #007a4d;
                color: #ffffff;
            }
        """)

        container = QVBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        container.setSpacing(3)

        self.panel = QWidget(self)
        self.panel.setObjectName("main_panel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(6, 4, 6, 4)
        panel_layout.setSpacing(4)

        # Row 1: All tools & finish actions in one flat bar
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(3)

        # Annotation tool buttons
        self.tool_buttons = {}
        tools = [
            ("rect", "⬜ 矩形"),
            ("ellipse", "⭕ 椭圆"),
            ("arrow", "↗️ 箭头"),
            ("pen", "✏️ 画笔"),
            ("highlighter", "🖍️ 荧光笔"),
            ("text", "🔤 文字"),
            ("mosaic", "🏁 马赛克"),
        ]
        for tid, lbl in tools:
            b = QPushButton(lbl)
            b.setCheckable(True)
            b.clicked.connect(lambda checked, t=tid: self._on_tool_clicked(t, checked))
            row1.addWidget(b)
            self.tool_buttons[tid] = b

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("background-color: #444; width: 1px;")
        row1.addWidget(sep1)

        # Undo / Redo
        btn_undo = QPushButton("↩️")
        btn_undo.setToolTip("撤销 (Ctrl+Z)")
        btn_undo.clicked.connect(self.undo_clicked.emit)
        row1.addWidget(btn_undo)

        btn_redo = QPushButton("↪️")
        btn_redo.setToolTip("重做 (Ctrl+Y)")
        btn_redo.clicked.connect(self.redo_clicked.emit)
        row1.addWidget(btn_redo)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("background-color: #444; width: 1px;")
        row1.addWidget(sep2)

        # Finish buttons
        btn_pin = QPushButton("📌 贴图 (F3 / 中键)")
        btn_pin.setObjectName("pin_btn")
        btn_pin.clicked.connect(self.pin_clicked.emit)
        row1.addWidget(btn_pin)

        btn_copy = QPushButton("📋 复制")
        btn_copy.clicked.connect(self.copy_clicked.emit)
        row1.addWidget(btn_copy)

        btn_save = QPushButton("💾 保存")
        btn_save.clicked.connect(self.save_clicked.emit)
        row1.addWidget(btn_save)

        btn_close = QPushButton("❌ 取消")
        btn_close.clicked.connect(self.close_clicked.emit)
        row1.addWidget(btn_close)

        panel_layout.addLayout(row1)

        # Row 2: Secondary palette & stroke width row (visible when tool is active)
        self.options_widget = QWidget(self.panel)
        row2 = QHBoxLayout(self.options_widget)
        row2.setContentsMargins(2, 2, 2, 2)
        row2.setSpacing(6)

        # Palette dots
        self.current_selected_color = QColor(PALETTE_COLORS[0])
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        for i, col in enumerate(PALETTE_COLORS):
            dot = ColorDotButton(col)
            dot.clicked.connect(lambda checked, c=col: self._on_preset_color_clicked(c))
            self.color_group.addButton(dot)
            row2.addWidget(dot)
            if i == 0:
                dot.setChecked(True)

        # Custom color picker button (🎨)
        self.btn_custom_color = QPushButton("🎨")
        self.btn_custom_color.setCheckable(True)
        self.btn_custom_color.setToolTip("自定义取色器 (调色板 / 屏幕取色)")
        self.btn_custom_color.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 1px 5px;
                background-color: #333333;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #444444;
                border: 1px solid #0078d4;
            }
            QPushButton:checked {
                background-color: #0078d4;
                border: 2px solid #ffffff;
            }
        """)
        self.btn_custom_color.clicked.connect(self._open_custom_color_picker)
        self.color_group.addButton(self.btn_custom_color)
        row2.addWidget(self.btn_custom_color)

        row2.addSpacing(8)

        # Width options
        self.width_group = QButtonGroup(self)
        self.width_group.setExclusive(True)
        for lbl, w in [("细", 2), ("中", 4), ("粗", 7)]:
            wb = QPushButton(lbl)
            wb.setCheckable(True)
            wb.clicked.connect(lambda checked, width=w: self.width_changed.emit(width))
            self.width_group.addButton(wb)
            row2.addWidget(wb)
            if w == 4:
                wb.setChecked(True)

        row2.addStretch()
        panel_layout.addWidget(self.options_widget)
        self.options_widget.hide()

        container.addWidget(self.panel)

    def _on_tool_clicked(self, tool_id: str, checked: bool):
        for tid, btn in self.tool_buttons.items():
            if tid != tool_id and btn.isChecked():
                btn.setChecked(False)

        if checked:
            self.options_widget.show()
            self.tool_changed.emit(tool_id)
        else:
            self.options_widget.hide()
            self.tool_changed.emit("none")
        self.adjustSize()

    def _on_preset_color_clicked(self, color_hex: str):
        col = QColor(color_hex)
        self.current_selected_color = col
        self.btn_custom_color.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 1px 5px;
                background-color: #333333;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #444444;
                border: 1px solid #0078d4;
            }
            QPushButton:checked {
                background-color: #0078d4;
                border: 2px solid #ffffff;
            }
        """)
        self.color_changed.emit(col)

    def _open_custom_color_picker(self):
        col = QColorDialog.getColor(
            self.current_selected_color,
            self,
            "选择标注颜色",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if col.isValid():
            self.current_selected_color = col
            self.btn_custom_color.setChecked(True)
            self.btn_custom_color.setStyleSheet(f"""
                QPushButton {{
                    font-size: 12px;
                    padding: 1px 5px;
                    background-color: {col.name()};
                    border: 2px solid #ffffff;
                    border-radius: 4px;
                }}
            """)
            self.color_changed.emit(col)

    def reset_tools(self):
        for btn in self.tool_buttons.values():
            btn.setChecked(False)
        self.options_widget.hide()
        self.tool_changed.emit("none")
        self.adjustSize()

class SnipperWidget(QWidget):
    snip_done = Signal(QPixmap, QPoint)  # Cropped pixmap, global top-left pos

    HANDLE_TL = 0
    HANDLE_TC = 1
    HANDLE_TR = 2
    HANDLE_MR = 3
    HANDLE_BR = 4
    HANDLE_BC = 5
    HANDLE_BL = 6
    HANDLE_ML = 7
    HANDLE_MOVE = 8
    HANDLE_NONE = -1

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        screen = QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())

        self.full_pixmap = QPixmap(1, 1)
        self.full_image = None

        # Pre-cache drawing objects
        self.badge_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        self.badge_fm = QFontMetrics(self.badge_font)
        self.border_pen = QPen(QColor(0, 150, 255), 2)
        self.handle_pen = QPen(QColor(0, 120, 215), 1)
        self.handle_brush = QBrush(QColor(255, 255, 255))
        self.badge_bg_color = QColor(30, 30, 30, 220)
        self.badge_text_color = QColor(240, 240, 240)
        self.mask_brush = QBrush(QColor(0, 0, 0, 95))  # Mask only outside selection

        # Interactive state
        self.selection_rect = QRect()
        self.press_pos = QPoint()
        self.hovered_pos = QPoint(0, 0)
        self.is_mouse_down = False
        self.has_dragged = False
        self.active_handle = self.HANDLE_NONE
        self.drag_origin_rect = QRect()

        # Magnifier Overlay & Window detector
        self.magnifier_overlay = MagnifierOverlayWidget(self)
        self.magnifier_overlay.setGeometry(self.rect())
        self.magnifier_overlay.show()
        self.hovered_window_rect: Optional[QRect] = None

        # Text editing state (movable & scalable text)
        self.selected_text_shape: Optional[TextShape] = None
        self.text_drag_mode: str = "none"  # "none", "move", "scale"
        self.text_drag_start_pos = QPointF()
        self.text_orig_pos = QPointF()
        self.text_orig_font_size = 16
        self.text_orig_rect = QRectF()

        # Vector Annotation System
        self.annot_mgr = AnnotationManager()
        self.current_drawing_shape = None
        self.drawing_pen_points: List[QPointF] = []
        self.drawing_start_pt: Optional[QPointF] = None

        # All-in-one unified toolbar
        self.toolbar = UnifiedSnipperToolbar(self)
        self.toolbar.pin_clicked.connect(self.confirm_pin)
        self.toolbar.copy_clicked.connect(self.confirm_copy)
        self.toolbar.save_clicked.connect(self.confirm_save)
        self.toolbar.close_clicked.connect(self.cancel_snip)
        self.toolbar.tool_changed.connect(self._on_annot_tool_changed)
        self.toolbar.color_changed.connect(lambda c: setattr(self.annot_mgr, "current_color", c))
        self.toolbar.width_changed.connect(self._on_width_changed)
        self.toolbar.undo_clicked.connect(self._undo_annot)
        self.toolbar.redo_clicked.connect(self._redo_annot)
        self.toolbar.hide()

    def _on_width_changed(self, w: int):
        self.annot_mgr.current_width = w
        if (self.selection_rect.isValid() and
            self.annot_mgr.current_tool in (AnnotationManager.TOOL_MOSAIC, AnnotationManager.TOOL_HIGHLIGHTER, AnnotationManager.TOOL_PEN)):
            if self.selection_rect.contains(self.hovered_pos):
                self.setCursor(self._get_tool_circle_cursor(self.annot_mgr.current_tool))
        self.update()

    def _create_circle_cursor(self, diameter: int, color: Optional[QColor] = None) -> QCursor:
        size = max(16, diameter + 6)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = size / 2.0
        radius = diameter / 2.0

        # Outer 1px dark shadow outline
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(center, center), radius + 0.5, radius + 0.5)

        # Main 1px crisp white outline
        p.setPen(QPen(QColor(255, 255, 255, 230), 1))
        fill_col = QColor(color) if color else QColor(255, 255, 255, 30)
        if color:
            fill_col.setAlpha(40)
        p.setBrush(QBrush(fill_col))
        p.drawEllipse(QPointF(center, center), radius, radius)

        # Center dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawEllipse(QPointF(center, center), 1.5, 1.5)

        p.end()
        return QCursor(pixmap, int(center), int(center))

    def _get_brush_diameter(self, tool_id: str) -> int:
        return self.annot_mgr.get_brush_diameter(tool_id)

    def _get_tool_circle_cursor(self, tool_id: str) -> QCursor:
        diam = self._get_brush_diameter(tool_id)
        col = self.annot_mgr.current_color if tool_id in (AnnotationManager.TOOL_PEN, AnnotationManager.TOOL_HIGHLIGHTER) else None
        return self._create_circle_cursor(diam, col)

    def _on_annot_tool_changed(self, tool_id: str):
        self.annot_mgr.current_tool = tool_id
        if tool_id != AnnotationManager.TOOL_TEXT:
            for s in self.annot_mgr.shapes:
                if isinstance(s, TextShape):
                    s.is_selected = False
            self.selected_text_shape = None
            self.text_drag_mode = "none"
        self.update()

    def _undo_annot(self):
        if self.annot_mgr.undo():
            self.update()

    def _redo_annot(self):
        if self.annot_mgr.redo():
            self.update()

    def prepare_and_show(self):
        """Called when hotkey is triggered. 100% crystal-clear transparent without darkening."""
        screen = QGuiApplication.primaryScreen()
        self.full_pixmap = screen.grabWindow(0)
        self.full_image = self.full_pixmap.toImage()
        self.setGeometry(screen.geometry())

        # Reset all states
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.selection_rect = QRect()
        self.is_mouse_down = False
        self.has_dragged = False
        self.active_handle = self.HANDLE_NONE
        self.hovered_window_rect = None
        self.hovered_pos = QCursor.pos()
        self.selected_text_shape = None
        self.text_drag_mode = "none"
        self.annot_mgr.clear()
        self.toolbar.reset_tools()
        self.toolbar.hide()

        # Magnifier overlay
        self.magnifier_overlay.setGeometry(self.rect())
        self.magnifier_overlay.show()
        self.magnifier_overlay.raise_()

        # Instant show & native focus takeover
        self.show()
        self.raise_()
        self.activateWindow()
        force_foreground_window(int(self.winId()))
        self.update()

    def safe_release_mouse(self):
        if self.mouseGrabber() == self:
            self.releaseMouse()

    def cancel_snip(self):
        self.safe_release_mouse()
        self.magnifier_overlay.hide()
        self.toolbar.hide()
        self.hide()

    # --- 8-Handle Resizing & Move Detection ---

    def get_handle_positions(self) -> dict:
        r = self.selection_rect
        return {
            self.HANDLE_TL: r.topLeft(),
            self.HANDLE_TC: QPoint(r.center().x(), r.top()),
            self.HANDLE_TR: r.topRight(),
            self.HANDLE_MR: QPoint(r.right(), r.center().y()),
            self.HANDLE_BR: r.bottomRight(),
            self.HANDLE_BC: QPoint(r.center().x(), r.bottom()),
            self.HANDLE_BL: r.bottomLeft(),
            self.HANDLE_ML: QPoint(r.left(), r.center().y()),
        }

    def get_handle_at(self, pt: QPoint) -> int:
        if not self.selection_rect.isValid() or self.selection_rect.width() <= 10:
            return self.HANDLE_NONE

        # 1. Check the 8 handles (radius = 9px)
        handles = self.get_handle_positions()
        for hid, hpos in handles.items():
            if (pt - hpos).manhattanLength() <= 16:
                return hid

        # 2. Check inside selection (if no annotation tool is selected, dragging inside moves selection)
        if self.selection_rect.contains(pt) and self.annot_mgr.current_tool == AnnotationManager.TOOL_NONE:
            return self.HANDLE_MOVE

        return self.HANDLE_NONE

    def update_cursor_for_handle(self, handle: int):
        if handle in (self.HANDLE_TL, self.HANDLE_BR):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in (self.HANDLE_TR, self.HANDLE_BL):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle in (self.HANDLE_TC, self.HANDLE_BC):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in (self.HANDLE_ML, self.HANDLE_MR):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif handle == self.HANDLE_MOVE:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # --- Mouse Events (Instant drag, 8-handle resize, movable/scalable text, window snap) ---

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        self.press_pos = pos
        self.is_mouse_down = True
        self.has_dragged = False

        # Hide color picking magnifier during any click / drag / resize operation
        if event.button() == Qt.MouseButton.LeftButton:
            source_img = self.full_image if self.full_image is not None else self.full_pixmap
            self.magnifier_overlay.update_cursor(pos, source_img, is_active=False)

        # 1. Check 8 resize handles first (so handles always take precedence over drawing)
        if self.selection_rect.isValid():
            h = self.get_handle_at(pos)
            if h not in (self.HANDLE_NONE, self.HANDLE_MOVE):
                if event.button() == Qt.MouseButton.LeftButton:
                    self.grabMouse()
                    self.active_handle = h
                    self.drag_origin_rect = QRect(self.selection_rect)
                    self.update()
                return

        # 2. Check Text Tool interaction (select / move / scale existing text, or add new text)
        if self.selection_rect.isValid() and self.annot_mgr.current_tool == AnnotationManager.TOOL_TEXT:
            pt_f = QPointF(pos)
            clicked_text: Optional[TextShape] = None
            clicked_scale = False

            if self.selected_text_shape and self.selected_text_shape.is_on_scale_handle(pt_f):
                clicked_text = self.selected_text_shape
                clicked_scale = True
            else:
                for shape in reversed(self.annot_mgr.shapes):
                    if isinstance(shape, TextShape) and shape.contains(pt_f):
                        clicked_text = shape
                        break

            if clicked_text is not None:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.grabMouse()
                    for s in self.annot_mgr.shapes:
                        if isinstance(s, TextShape):
                            s.is_selected = False
                    clicked_text.is_selected = True
                    self.selected_text_shape = clicked_text
                    self.text_drag_start_pos = pt_f

                    if clicked_scale:
                        self.text_drag_mode = "scale"
                        self.text_orig_font_size = clicked_text.font_size
                        self.text_orig_rect = clicked_text.get_bounding_rect()
                    else:
                        self.text_drag_mode = "move"
                        self.text_orig_pos = QPointF(clicked_text.pos)

                    self.update()
                    return
            else:
                # Deselect text if clicked outside text shapes
                for s in self.annot_mgr.shapes:
                    if isinstance(s, TextShape):
                        s.is_selected = False
                self.selected_text_shape = None

                # Clicked empty area inside selection to create new text
                if event.button() == Qt.MouseButton.LeftButton and self.selection_rect.contains(pos):
                    self.is_mouse_down = False
                    self.has_dragged = False
                    text, ok = QInputDialog.getText(self, "添加文字标注", "输入文字:")
                    if ok and text.strip():
                        new_shape = TextShape(
                            pos=pt_f,
                            text=text.strip(),
                            color=self.annot_mgr.current_color,
                            font_size=max(12, self.annot_mgr.current_width * 4),
                            is_selected=True
                        )
                        self.annot_mgr.add_shape(new_shape)
                        self.selected_text_shape = new_shape
                        self.update()
                    if self.selection_rect.isValid() and self.selection_rect.width() > 10 and self.selection_rect.height() > 10:
                        self._position_toolbar()
                        self.toolbar.show()
                    return

        # 3. If LeftButton and other annotation tool is active and click is inside selection: start drawing
        if (event.button() == Qt.MouseButton.LeftButton and
            self.selection_rect.isValid() and
            self.selection_rect.contains(pos) and
            self.annot_mgr.current_tool not in (AnnotationManager.TOOL_NONE, AnnotationManager.TOOL_TEXT)):

            tool = self.annot_mgr.current_tool
            pt = QPointF(pos)
            self.drawing_start_pt = pt
            if tool in (AnnotationManager.TOOL_PEN, AnnotationManager.TOOL_HIGHLIGHTER):
                self.drawing_pen_points = [pt]
                is_high = (tool == AnnotationManager.TOOL_HIGHLIGHTER)
                self.current_drawing_shape = PenShape(points=list(self.drawing_pen_points), color=self.annot_mgr.current_color, width=self.annot_mgr.current_width, is_highlighter=is_high)
            elif tool == AnnotationManager.TOOL_MOSAIC:
                self.drawing_pen_points = [pt]
                diam = self._get_brush_diameter(AnnotationManager.TOOL_MOSAIC)
                self.current_drawing_shape = MosaicShape(points=list(self.drawing_pen_points), brush_width=diam, block_size=10)
            self.update()
            return

        # 4. Standard selection click / drag
        if event.button() == Qt.MouseButton.LeftButton:
            self.grabMouse()
            if self.selection_rect.isValid():
                self.active_handle = self.get_handle_at(pos)
                self.drag_origin_rect = QRect(self.selection_rect)
            else:
                self.active_handle = self.HANDLE_NONE
            self.update()

        elif event.button() == Qt.MouseButton.RightButton:
            if self.selected_text_shape:
                for s in self.annot_mgr.shapes:
                    if isinstance(s, TextShape):
                        s.is_selected = False
                self.selected_text_shape = None
                self.update()
            elif self.annot_mgr.current_tool != AnnotationManager.TOOL_NONE:
                # Cancel active tool back to normal pointer mode, keep selection intact
                self.toolbar.reset_tools()
                self.update()
            elif self.selection_rect.isValid():
                self.selection_rect = QRect()
                self.toolbar.hide()
                self.annot_mgr.clear()
                self.update()
            else:
                self.cancel_snip()

        elif event.button() == Qt.MouseButton.MiddleButton:
            if self.selection_rect.isValid() and self.selection_rect.width() > 10:
                self.confirm_pin()
            else:
                self.selection_rect = self.rect()
                self.confirm_pin()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        self.hovered_pos = pos

        source_img = self.full_image if self.full_image is not None else self.full_pixmap

        # Handle text shape dragging / scaling
        if self.text_drag_mode == "move" and self.selected_text_shape:
            self.magnifier_overlay.update_cursor(pos, source_img, is_active=False)
            delta = QPointF(pos) - self.text_drag_start_pos
            self.selected_text_shape.pos = self.text_orig_pos + delta
            self.update()
            return

        if self.text_drag_mode == "scale" and self.selected_text_shape:
            self.magnifier_overlay.update_cursor(pos, source_img, is_active=False)
            delta_y = pos.y() - self.text_drag_start_pos.y()
            orig_h = max(15.0, self.text_orig_rect.height())
            scale_ratio = max(0.4, (orig_h + delta_y) / orig_h)
            new_size = max(8, min(120, int(self.text_orig_font_size * scale_ratio)))
            self.selected_text_shape.font_size = new_size
            self.update()
            return

        # Active drawing of annotation shape
        if self.drawing_start_pt is not None and self.annot_mgr.current_tool != AnnotationManager.TOOL_NONE:
            self.magnifier_overlay.update_cursor(pos, source_img, is_active=False)
            tool = self.annot_mgr.current_tool
            pt = QPointF(pos)

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
                self.drawing_pen_points.append(pt)
                diam = self._get_brush_diameter(AnnotationManager.TOOL_MOSAIC)
                self.current_drawing_shape = MosaicShape(points=list(self.drawing_pen_points), brush_width=diam, block_size=10)

            self.update()
            return

        if self.is_mouse_down:
            # Hide magnifier during box selection or handle resizing (Requirement 2)
            self.magnifier_overlay.update_cursor(pos, source_img, is_active=False)

            # Check if user dragged beyond 3 pixels
            if not self.has_dragged and (pos - self.press_pos).manhattanLength() > 3:
                self.has_dragged = True

            if self.has_dragged:
                if self.active_handle == self.HANDLE_NONE or not self.selection_rect.isValid():
                    # Direct instant drag-selection
                    self.selection_rect = QRect(self.press_pos, pos).normalized()
                    self.toolbar.hide()
                elif self.active_handle == self.HANDLE_MOVE:
                    # Move selection rectangle
                    delta = pos - self.press_pos
                    new_rect = QRect(self.drag_origin_rect)
                    new_rect.translate(delta)
                    self.selection_rect = new_rect
                    self._position_toolbar()
                else:
                    # Resize selection via handle
                    self._resize_selection_by_handle(pos)
                    self._position_toolbar()

            self.update()

        else:
            # Hover cursor update (Check text handles, brush circle cursor, 8 handles, or window detection)
            if self.selection_rect.isValid():
                # Check text tool interaction cursors
                if self.annot_mgr.current_tool == AnnotationManager.TOOL_TEXT and self.selected_text_shape:
                    pt_f = QPointF(pos)
                    if self.selected_text_shape.is_on_scale_handle(pt_f):
                        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                        self._update_magnifier(pos)
                        self.update()
                        return
                    elif self.selected_text_shape.contains(pt_f):
                        self.setCursor(Qt.CursorShape.SizeAllCursor)
                        self._update_magnifier(pos)
                        self.update()
                        return

                h = self.get_handle_at(pos)
                if h != self.HANDLE_NONE:
                    self.update_cursor_for_handle(h)
                elif (self.selection_rect.contains(pos) and
                      self.annot_mgr.current_tool in (AnnotationManager.TOOL_MOSAIC, AnnotationManager.TOOL_HIGHLIGHTER, AnnotationManager.TOOL_PEN)):
                    self.setCursor(self._get_tool_circle_cursor(self.annot_mgr.current_tool))
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                # Detect window under mouse for snapping (picking color mode)
                self.setCursor(Qt.CursorShape.ArrowCursor)
                detected = get_window_rect_at_point(pos)
                if detected != self.hovered_window_rect:
                    self.hovered_window_rect = detected

            self._update_magnifier(pos)
            self.update()

    def _update_magnifier(self, pos: QPoint):
        show_mag = (not self.is_mouse_down and self.drawing_start_pt is None and self.text_drag_mode == "none")
        source_img = self.full_image if self.full_image is not None else self.full_pixmap
        self.magnifier_overlay.update_cursor(pos, source_img, is_active=show_mag)

    def _resize_selection_by_handle(self, pos: QPoint):
        x1 = self.drag_origin_rect.left()
        y1 = self.drag_origin_rect.top()
        x2 = self.drag_origin_rect.right()
        y2 = self.drag_origin_rect.bottom()
        h = self.active_handle

        if h == self.HANDLE_TL:
            x1, y1 = pos.x(), pos.y()
        elif h == self.HANDLE_TC:
            y1 = pos.y()
        elif h == self.HANDLE_TR:
            x2, y1 = pos.x(), pos.y()
        elif h == self.HANDLE_MR:
            x2 = pos.x()
        elif h == self.HANDLE_BR:
            x2, y2 = pos.x(), pos.y()
        elif h == self.HANDLE_BC:
            y2 = pos.y()
        elif h == self.HANDLE_BL:
            x1, y2 = pos.x(), pos.y()
        elif h == self.HANDLE_ML:
            x1 = pos.x()

        left, right = min(x1, x2), max(x1, x2)
        top, bottom = min(y1, y2), max(y1, y2)
        self.selection_rect = QRect(QPoint(left, top), QPoint(right, bottom))

    def mouseReleaseEvent(self, event):
        if self.text_drag_mode != "none":
            self.safe_release_mouse()
            self.text_drag_mode = "none"
            self.is_mouse_down = False
            self.has_dragged = False
            self._update_magnifier(event.position().toPoint())
            self.update()
            return

        self.safe_release_mouse()
        self.is_mouse_down = False
        self.has_dragged = False
        self.active_handle = self.HANDLE_NONE

        # Finalize drawing annotation shape
        if self.drawing_start_pt is not None:
            if self.current_drawing_shape is not None:
                self.annot_mgr.add_shape(self.current_drawing_shape)
                self.current_drawing_shape = None
            self.drawing_start_pt = None
            self.drawing_pen_points = []
            if self.selection_rect.isValid() and self.selection_rect.width() > 10 and self.selection_rect.height() > 10:
                self._position_toolbar()
                self.toolbar.show()
            self._update_magnifier(event.position().toPoint())
            self.update()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # If user just clicked without dragging and no selection yet -> snap to window!
            if not self.has_dragged and not self.selection_rect.isValid():
                if self.hovered_window_rect:
                    self.selection_rect = self.hovered_window_rect.intersected(self.rect())

            if self.selection_rect.isValid() and self.selection_rect.width() > 10 and self.selection_rect.height() > 10:
                self._position_toolbar()
                self.toolbar.show()
                if self.annot_mgr.current_tool == AnnotationManager.TOOL_NONE:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.selection_rect = QRect()
                self.toolbar.hide()
                self.setCursor(Qt.CursorShape.ArrowCursor)

            self._update_magnifier(event.position().toPoint())
            self.update()

    def mouseDoubleClickEvent(self, event):
        if self.annot_mgr.current_tool == AnnotationManager.TOOL_TEXT and self.selected_text_shape:
            pt_f = QPointF(event.position().toPoint())
            if self.selected_text_shape.contains(pt_f):
                new_text, ok = QInputDialog.getText(self, "编辑文字", "修改文字:", text=self.selected_text_shape.text)
                if ok and new_text.strip():
                    self.selected_text_shape.text = new_text.strip()
                    self.update()
                return

        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            if not self.selection_rect.isValid() or self.selection_rect.width() <= 10:
                self.selection_rect = self.rect()
            self.confirm_pin()

    def _position_toolbar(self):
        tb_size = self.toolbar.sizeHint()
        x = self.selection_rect.right() - tb_size.width()
        y = self.selection_rect.bottom() + 10
        if y + tb_size.height() > self.height() - 5:
            y = self.selection_rect.bottom() - tb_size.height() - 10
        if x < 10:
            x = 10
        self.toolbar.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)

        # 1. Base Desktop: 100% natural and transparent (NO full screen darkening!)
        painter.drawPixmap(0, 0, self.full_pixmap)

        # 1.1 Screen Perimeter Border: visual indicator when entering snipping mode (F2 / F1)
        if not self.selection_rect.isValid():
            painter.save()
            painter.setPen(QPen(QColor(0, 150, 255), 3))  # 3px sleek Snipaste blue border around screen
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
            painter.restore()

        # 2. Window auto-snapping highlight (only when NO selection exists)
        # 100% transparent: NoBrush (NO blue mask fill!)
        if not self.selection_rect.isValid() and not self.is_mouse_down and self.hovered_window_rect:
            if self.hovered_window_rect != self.rect():
                painter.save()
                painter.setPen(QPen(QColor(0, 150, 255, 220), 2, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(self.hovered_window_rect)
                painter.restore()

        # 3. If selection exists: Dim the area OUTSIDE the selection (Highlighting the selection)
        if self.selection_rect.isValid() and self.selection_rect.width() > 0:
            sel = self.selection_rect
            sw, sh = self.width(), self.height()

            # 4 surrounding darkened rectangles (zero overlap, perfectly seamless)
            painter.fillRect(QRect(0, 0, sw, sel.top()), self.mask_brush)                               # Top
            painter.fillRect(QRect(0, sel.bottom() + 1, sw, sh - (sel.bottom() + 1)), self.mask_brush)  # Bottom
            painter.fillRect(QRect(0, sel.top(), sel.left(), sel.height()), self.mask_brush)            # Left
            painter.fillRect(QRect(sel.right() + 1, sel.top(), sw - (sel.right() + 1), sel.height()), self.mask_brush) # Right

            # Draw vector annotations (clipped to inside selection)
            painter.save()
            painter.setClipRect(self.selection_rect)
            self.annot_mgr.draw_all(painter, self.full_pixmap)
            if self.current_drawing_shape is not None:
                self.current_drawing_shape.draw(painter, self.full_pixmap)

            # Circle brush preview on canvas when hovering with Mosaic / Highlighter / Pen
            if (self.selection_rect.contains(self.hovered_pos) and
                self.annot_mgr.current_tool in (AnnotationManager.TOOL_MOSAIC, AnnotationManager.TOOL_HIGHLIGHTER, AnnotationManager.TOOL_PEN) and
                self.drawing_start_pt is None):
                diam = self._get_brush_diameter(self.annot_mgr.current_tool)
                rad = diam / 2.0
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QColor(255, 255, 255, 220), 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(self.hovered_pos), rad, rad)

            painter.restore()

            # Selection Border
            painter.setPen(self.border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.selection_rect)

            # 8 Handles (White square with blue outline)
            painter.setPen(self.handle_pen)
            painter.setBrush(self.handle_brush)
            for hid, hpos in self.get_handle_positions().items():
                painter.drawRect(hpos.x() - 4, hpos.y() - 4, 8, 8)

            # Dimension badge
            dim_str = f" {self.selection_rect.width()} × {self.selection_rect.height()} "
            badge_rect = self.badge_fm.boundingRect(dim_str)
            badge_x = self.selection_rect.x()
            badge_y = max(0, self.selection_rect.y() - badge_rect.height() - 8)
            badge_box = QRect(badge_x, badge_y, badge_rect.width() + 10, badge_rect.height() + 6)

            painter.setBrush(self.badge_bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_box, 4, 4)

            painter.setPen(self.badge_text_color)
            painter.setFont(self.badge_font)
            painter.drawText(badge_box, Qt.AlignmentFlag.AlignCenter, dim_str)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_snip()
        elif event.key() == Qt.Key.Key_C:
            # Global color copy: works anytime under cursor!
            img = self.full_image if self.full_image is not None else (self.full_pixmap.toImage() if not self.full_pixmap.isNull() else None)
            if img is not None:
                pos = self.hovered_pos
                if 0 <= pos.x() < img.width() and 0 <= pos.y() < img.height():
                    col = img.pixelColor(pos.x(), pos.y())
                    col_str = self.magnifier_overlay.hud.get_color_str(col)
                    QApplication.clipboard().setText(col_str)
                    QToolTip.showText(QCursor.pos(), f"已复制颜色: {col_str}", self, msecShowTime=1500)
        elif event.key() == Qt.Key.Key_Shift:
            # Toggle magnifier color format (HEX <-> RGB)
            self.magnifier_overlay.hud.toggle_format()
            self.magnifier_overlay.update()
        elif event.matches(QKeySequence.StandardKey.Undo):
            self._undo_annot()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self._redo_annot()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F3):
            if self.selection_rect.isValid() and self.selection_rect.width() > 10:
                self.confirm_pin()
        elif event.matches(QKeySequence.StandardKey.Copy):
            if self.selection_rect.isValid() and self.selection_rect.width() > 10:
                self.confirm_copy()

    def get_cropped_pixmap(self) -> QPixmap:
        """Returns the cropped selection with all vector annotations baked in."""
        if self.selection_rect.isValid() and self.selection_rect.width() > 0:
            cropped = self.full_pixmap.copy(self.selection_rect)
            if self.annot_mgr.shapes:
                p = QPainter(cropped)
                p.translate(-self.selection_rect.x(), -self.selection_rect.y())
                self.annot_mgr.draw_all(p, self.full_pixmap, is_exporting=True)
                p.end()
            return cropped
        return QPixmap()

    def confirm_pin(self):
        self.safe_release_mouse()
        pixmap = self.get_cropped_pixmap()
        if not pixmap.isNull():
            global_pos = self.mapToGlobal(self.selection_rect.topLeft())
            self.snip_done.emit(pixmap, global_pos)
        self.toolbar.hide()
        self.hide()

    def confirm_copy(self):
        self.safe_release_mouse()
        pixmap = self.get_cropped_pixmap()
        if not pixmap.isNull():
            clipboard = QApplication.clipboard()
            clipboard.setPixmap(pixmap)
        self.toolbar.hide()
        self.hide()

    def confirm_save(self):
        self.safe_release_mouse()
        pixmap = self.get_cropped_pixmap()
        if not pixmap.isNull():
            path, _ = QFileDialog.getSaveFileName(self, "保存截图", "", "Images (*.png *.jpg *.bmp)")
            if path:
                pixmap.save(path)
        self.toolbar.hide()
        self.hide()

    def hideEvent(self, event):
        self.safe_release_mouse()
        super().hideEvent(event)
