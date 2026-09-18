from typing import Optional
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QFont, QImage
)

class MagnifierOverlayWidget(QWidget):
    """Full-screen pass-through transparent overlay widget that ensures MagnifierHUD
    is rendered above all sibling child widgets (including UnifiedSnipperToolbar)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hud = MagnifierHUD()
        self.cursor_pos = QPoint(0, 0)
        self.source_img = None
        self.is_active = True

    def update_cursor(self, cursor_pos: QPoint, source_img, is_active: bool = True):
        self.cursor_pos = cursor_pos
        self.source_img = source_img
        self.is_active = is_active
        self.raise_()  # Always raise above sibling child widgets like toolbar
        self.update()

    def paintEvent(self, event):
        if not self.is_active or self.source_img is None:
            return
        painter = QPainter(self)
        self.hud.draw(painter, self.cursor_pos, self.source_img, self.rect())

class MagnifierHUD:
    """Renders a pixel-level magnifying glass HUD with RGB/HEX color picker."""

    def __init__(self):
        self.grid_count = 17       # 17x17 pixels (odd number so there is an exact center pixel)
        self.zoom_factor = 7       # Each sampled pixel is rendered 7x7
        self.view_size = self.grid_count * self.zoom_factor  # 119px
        self.hud_w = self.view_size + 16
        self.hud_h = self.view_size + 52
        self.format_hex = True

    def toggle_format(self):
        self.format_hex = not self.format_hex

    def get_color_str(self, color: QColor) -> str:
        if self.format_hex:
            return color.name(QColor.NameFormat.HexRgb).upper()
        else:
            return f"rgb({color.red()}, {color.green()}, {color.blue()})"

    def draw(self, painter: QPainter, cursor_pos: QPoint, full_pixmap, screen_rect: QRect):
        if full_pixmap.isNull():
            return

        cx, cy = cursor_pos.x(), cursor_pos.y()

        # Sample pixel color under cursor (supports either QImage or QPixmap)
        img = full_pixmap if isinstance(full_pixmap, QImage) else full_pixmap.toImage()
        if not (0 <= cx < img.width() and 0 <= cy < img.height()):
            return
        curr_color = img.pixelColor(cx, cy)

        # Determine HUD placement (smart collision with screen edge)
        hx = cx + 22
        hy = cy + 22
        if hx + self.hud_w > screen_rect.right() - 10:
            hx = cx - self.hud_w - 22
        if hy + self.hud_h > screen_rect.bottom() - 10:
            hy = cy - self.hud_h - 22

        hud_rect = QRect(hx, hy, self.hud_w, self.hud_h)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # 1. Background container
        painter.setPen(QPen(QColor(60, 60, 60, 240), 1))
        painter.setBrush(QColor(24, 24, 24, 235))
        painter.drawRoundedRect(hud_rect, 6, 6)

        # 2. Render 8x zoomed pixel grid
        grid_x = hx + 8
        grid_y = hy + 8
        half = self.grid_count // 2

        # Draw each sampled pixel
        for gy in range(self.grid_count):
            for gx in range(self.grid_count):
                sx = cx - half + gx
                sy = cy - half + gy
                if 0 <= sx < img.width() and 0 <= sy < img.height():
                    px_color = img.pixelColor(sx, sy)
                else:
                    px_color = QColor(0, 0, 0)

                rx = grid_x + gx * self.zoom_factor
                ry = grid_y + gy * self.zoom_factor
                painter.fillRect(QRect(rx, ry, self.zoom_factor, self.zoom_factor), px_color)

        # 3. Draw grid lines
        painter.setPen(QPen(QColor(0, 0, 0, 45), 1))
        for i in range(self.grid_count + 1):
            # Vertical
            vx = grid_x + i * self.zoom_factor
            painter.drawLine(vx, grid_y, vx, grid_y + self.view_size)
            # Horizontal
            vy = grid_y + i * self.zoom_factor
            painter.drawLine(grid_x, vy, grid_x + self.view_size, vy)

        # 4. Highlight center pixel with red crosshair
        center_rx = grid_x + half * self.zoom_factor
        center_ry = grid_y + half * self.zoom_factor
        center_box = QRect(center_rx, center_ry, self.zoom_factor, self.zoom_factor)

        painter.setPen(QPen(QColor(255, 60, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(center_box)

        # Crosshair lines outside the box
        painter.drawLine(center_rx - 4, center_ry + self.zoom_factor // 2, center_rx - 1, center_ry + self.zoom_factor // 2)
        painter.drawLine(center_box.right() + 1, center_ry + self.zoom_factor // 2, center_box.right() + 4, center_ry + self.zoom_factor // 2)
        painter.drawLine(center_rx + self.zoom_factor // 2, center_ry - 4, center_rx + self.zoom_factor // 2, center_ry - 1)
        painter.drawLine(center_rx + self.zoom_factor // 2, center_box.bottom() + 1, center_rx + self.zoom_factor // 2, center_box.bottom() + 4)

        # 5. Color info & coordinates footer
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color_swatch_rect = QRect(grid_x, grid_y + self.view_size + 8, 14, 14)
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
        painter.setBrush(curr_color)
        painter.drawRoundedRect(color_swatch_rect, 2, 2)

        color_text = self.get_color_str(curr_color)
        painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(grid_x + 20, grid_y + self.view_size + 20, color_text)

        coord_text = f"({cx}, {cy})"
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor(180, 180, 180))
        painter.drawText(grid_x, grid_y + self.view_size + 38, coord_text)

        hint_text = "C:复制 Shift:格式"
        painter.drawText(QRect(grid_x + 50, grid_y + self.view_size + 26, self.hud_w - 60, 16), Qt.AlignmentFlag.AlignRight, hint_text)

        painter.restore()
