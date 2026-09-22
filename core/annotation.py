import math
from typing import List, Optional
from dataclasses import dataclass, field
from PySide6.QtCore import Qt, QRectF, QPointF, QRect
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QFont, QFontMetrics, QPainterPath,
    QPainterPathStroker
)

class AnnotationShape:
    def draw(self, painter: QPainter, base_pixmap: Optional[QPixmap] = None):
        raise NotImplementedError

@dataclass
class RectShape(AnnotationShape):
    rect: QRectF
    color: QColor
    width: int = 3
    filled: bool = False

    def draw(self, painter: QPainter, base_pixmap: Optional[QPixmap] = None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.filled:
            painter.setBrush(QBrush(self.color))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self.color, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawRoundedRect(self.rect, 2, 2)
        painter.restore()

@dataclass
class EllipseShape(AnnotationShape):
    rect: QRectF
    color: QColor
    width: int = 3
    filled: bool = False

    def draw(self, painter: QPainter, base_pixmap: Optional[QPixmap] = None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.filled:
            painter.setBrush(QBrush(self.color))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self.color, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawEllipse(self.rect)
        painter.restore()

@dataclass
class ArrowShape(AnnotationShape):
    start: QPointF
    end: QPointF
    color: QColor
    width: int = 3

    def draw(self, painter: QPainter, base_pixmap: Optional[QPixmap] = None):
        if self.start == self.end:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.color, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QBrush(self.color))

        # Main shaft line
        painter.drawLine(self.start, self.end)

        # Arrow head geometry
        dx = self.end.x() - self.start.x()
        dy = self.end.y() - self.start.y()
        angle = math.atan2(dy, dx)

        arrow_len = max(12.0, self.width * 3.5)
        arrow_deg = math.radians(28)

        p1 = QPointF(
            self.end.x() - arrow_len * math.cos(angle - arrow_deg),
            self.end.y() - arrow_len * math.sin(angle - arrow_deg)
        )
        p2 = QPointF(
            self.end.x() - arrow_len * math.cos(angle + arrow_deg),
            self.end.y() - arrow_len * math.sin(angle + arrow_deg)
        )

        # Draw filled triangle head
        path = QPainterPath()
        path.moveTo(self.end)
        path.lineTo(p1)
        path.lineTo(p2)
        path.closeSubpath()
        painter.drawPath(path)
        painter.restore()

@dataclass
class PenShape(AnnotationShape):
    points: List[QPointF]
    color: QColor
    width: int = 3
    is_highlighter: bool = False

    def draw(self, painter: QPainter, base_pixmap: Optional[QPixmap] = None):
        if len(self.points) < 2:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.is_highlighter:
            c = QColor(self.color)
            c.setAlpha(110)
            pen = QPen(c, max(12, self.width * 3), Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.BevelJoin)
        else:
            pen = QPen(self.color, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(self.points[0])
        for p in self.points[1:]:
            path.lineTo(p)
        painter.drawPath(path)
        painter.restore()

@dataclass
class TextShape(AnnotationShape):
    pos: QPointF
    text: str
    color: QColor
    font_size: int = 16
    font_family: str = "Segoe UI"
    font: Optional[QFont] = None
    is_selected: bool = False

    def __post_init__(self):
        if self.font is not None:
            sz = self.font.pointSize()
            if sz > 0:
                self.font_size = sz
            fam = self.font.family()
            if fam:
                self.font_family = fam

    def get_font(self) -> QFont:
        return QFont(self.font_family, max(8, int(self.font_size)), QFont.Weight.Bold)

    def get_bounding_rect(self) -> QRectF:
        if not self.text:
            return QRectF(self.pos.x(), self.pos.y(), 40, 24)
        font = self.get_font()
        fm = QFontMetrics(font)
        lines = self.text.splitlines() or [""]
        w = max([fm.horizontalAdvance(l) for l in lines] or [30])
        h = max(24, len(lines) * fm.lineSpacing())
        return QRectF(self.pos.x() - 4, self.pos.y() - 4, w + 12, h + 8)

    def get_scale_handle_rect(self) -> QRectF:
        r = self.get_bounding_rect()
        return QRectF(r.right() - 5, r.bottom() - 5, 10, 10)

    def contains(self, pt: QPointF) -> bool:
        return self.get_bounding_rect().contains(pt)

    def is_on_scale_handle(self, pt: QPointF) -> bool:
        return self.get_scale_handle_rect().contains(pt)

    def draw(self, painter: QPainter, base_pixmap: Optional[QPixmap] = None, is_exporting: bool = False):
        if not self.text:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = self.get_font()
        painter.setFont(font)
        painter.setPen(self.color)
        fm = painter.fontMetrics()
        y = self.pos.y() + fm.ascent()
        for line in self.text.splitlines():
            painter.drawText(QPointF(self.pos.x(), y), line)
            y += fm.lineSpacing()

        # If selected and not exporting to final image: draw selection outline and scale handle
        if self.is_selected and not is_exporting:
            r = self.get_bounding_rect()
            painter.setPen(QPen(QColor(0, 150, 255, 220), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)

            # Draw 8x8 white square handle with blue border at bottom-right
            hr = self.get_scale_handle_rect()
            painter.setPen(QPen(QColor(0, 120, 215), 1))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawRect(hr)

        painter.restore()

class MosaicShape(AnnotationShape):
    def __init__(
        self,
        rect: Optional[QRectF] = None,
        block_size: int = 10,
        points: Optional[List[QPointF]] = None,
        brush_width: int = 20,
    ):
        self.rect = rect
        self.block_size = max(2, block_size)
        self.points: List[QPointF] = list(points) if points else []
        self.brush_width = brush_width

    def draw(self, painter: QPainter, base_pixmap: Optional[QPixmap] = None):
        if base_pixmap is None or base_pixmap.isNull():
            return

        if self.points:
            # Brush-based Mosaic (Stroke Mosaic)
            if len(self.points) == 1:
                fill_path = QPainterPath()
                r = self.brush_width / 2.0
                fill_path.addEllipse(self.points[0], r, r)
            else:
                path = QPainterPath()
                path.moveTo(self.points[0])
                for pt in self.points[1:]:
                    path.lineTo(pt)
                stroker = QPainterPathStroker()
                stroker.setWidth(self.brush_width)
                stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
                stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                fill_path = stroker.createStroke(path)

            path_bounds = fill_path.boundingRect().toAlignedRect()
            bounded_rect = path_bounds.intersected(base_pixmap.rect())
            if bounded_rect.isEmpty():
                return

            # Align bounded_rect to multiples of block_size for flicker-free / jitter-free mosaic grid
            bs = self.block_size
            x0 = max(0, (bounded_rect.left() // bs) * bs)
            y0 = max(0, (bounded_rect.top() // bs) * bs)
            x1 = min(base_pixmap.width(), ((bounded_rect.right() + bs) // bs) * bs)
            y1 = min(base_pixmap.height(), ((bounded_rect.bottom() + bs) // bs) * bs)

            grid_rect = QRect(x0, y0, x1 - x0, y1 - y0)
            if grid_rect.isEmpty():
                return

            crop = base_pixmap.copy(grid_rect)
            small_w = max(1, grid_rect.width() // bs)
            small_h = max(1, grid_rect.height() // bs)
            downscaled = crop.scaled(small_w, small_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
            mosaic_pixmap = downscaled.scaled(grid_rect.width(), grid_rect.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setClipPath(fill_path, Qt.ClipOperation.IntersectClip)
            painter.drawPixmap(grid_rect.topLeft(), mosaic_pixmap)
            painter.restore()

        elif self.rect is not None and self.rect.width() > 2 and self.rect.height() > 2:
            # Rectangular Mosaic (Legacy / fallback)
            r = self.rect.toRect()
            bounded_rect = r.intersected(base_pixmap.rect())
            if bounded_rect.isEmpty():
                return

            bs = self.block_size
            x0 = max(0, (bounded_rect.left() // bs) * bs)
            y0 = max(0, (bounded_rect.top() // bs) * bs)
            x1 = min(base_pixmap.width(), ((bounded_rect.right() + bs) // bs) * bs)
            y1 = min(base_pixmap.height(), ((bounded_rect.bottom() + bs) // bs) * bs)
            grid_rect = QRect(x0, y0, x1 - x0, y1 - y0)
            if grid_rect.isEmpty():
                return

            crop = base_pixmap.copy(grid_rect)
            small_w = max(1, grid_rect.width() // bs)
            small_h = max(1, grid_rect.height() // bs)
            downscaled = crop.scaled(small_w, small_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
            mosaic_pixmap = downscaled.scaled(grid_rect.width(), grid_rect.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)

            painter.save()
            painter.setClipRect(bounded_rect, Qt.ClipOperation.IntersectClip)
            painter.drawPixmap(grid_rect.topLeft(), mosaic_pixmap)
            painter.restore()

class AnnotationManager:
    """Manages annotation shapes, active tool, undo/redo history, and canvas drawing."""
    TOOL_NONE = "none"
    TOOL_RECT = "rect"
    TOOL_ELLIPSE = "ellipse"
    TOOL_ARROW = "arrow"
    TOOL_PEN = "pen"
    TOOL_HIGHLIGHTER = "highlighter"
    TOOL_TEXT = "text"
    TOOL_MOSAIC = "mosaic"

    def __init__(self):
        self.shapes: List[AnnotationShape] = []
        self.undo_stack: List[List[AnnotationShape]] = []
        self.redo_stack: List[List[AnnotationShape]] = []

        self.current_tool: str = self.TOOL_NONE
        self.current_color: QColor = QColor(255, 59, 48)  # Snipaste classic vibrant red
        self.current_width: int = 3
        self.is_filled: bool = False

    def get_brush_diameter(self, tool_id: Optional[str] = None) -> int:
        tid = tool_id or self.current_tool
        w = self.current_width
        if tid == self.TOOL_MOSAIC:
            if w <= 2:
                return 14
            elif w <= 4:
                return 26
            elif w <= 7:
                return 44
            else:
                return max(10, w * 6)
        elif tid == self.TOOL_HIGHLIGHTER:
            if w <= 2:
                return 12
            elif w <= 4:
                return 18
            elif w <= 7:
                return 26
            else:
                return max(8, w * 4)
        elif tid == self.TOOL_PEN:
            if w <= 2:
                return 6
            elif w <= 4:
                return 10
            elif w <= 7:
                return 16
            else:
                return max(2, w * 2)
        return 14

    def push_state(self):
        self.undo_stack.append(list(self.shapes))
        self.redo_stack.clear()
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def add_shape(self, shape: AnnotationShape):
        self.push_state()
        self.shapes.append(shape)

    def undo(self) -> bool:
        if self.undo_stack:
            self.redo_stack.append(list(self.shapes))
            self.shapes = self.undo_stack.pop()
            return True
        elif self.shapes:
            self.redo_stack.append(list(self.shapes))
            self.shapes.clear()
            return True
        return False

    def redo(self) -> bool:
        if self.redo_stack:
            self.undo_stack.append(list(self.shapes))
            self.shapes = self.redo_stack.pop()
            return True
        return False

    def clear(self):
        if self.shapes:
            self.push_state()
            self.shapes.clear()

    def draw_all(self, painter: QPainter, base_pixmap: Optional[QPixmap] = None, is_exporting: bool = False):
        for shape in self.shapes:
            if isinstance(shape, TextShape):
                shape.draw(painter, base_pixmap, is_exporting=is_exporting)
            else:
                shape.draw(painter, base_pixmap)
