from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup,
    QFrame
)

PALETTE_COLORS = [
    QColor(255, 59, 48),    # Red (Snipaste default)
    QColor(255, 149, 0),   # Orange
    QColor(255, 204, 0),   # Yellow
    QColor(52, 199, 89),   # Green
    QColor(0, 122, 255),   # Blue
    QColor(175, 82, 222),  # Purple
    QColor(255, 255, 255), # White
    QColor(30, 30, 30),    # Black
]

class ColorDotButton(QPushButton):
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked():
            p.setPen(QPen(QColor(0, 150, 255), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(1, 1, 14, 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.color)
            p.drawEllipse(3, 3, 10, 10)
        else:
            p.setPen(QPen(QColor(80, 80, 80), 1))
            p.setBrush(self.color)
            p.drawEllipse(2, 2, 12, 12)

class AnnotationToolbar(QWidget):
    tool_changed = Signal(str)       # tool name
    color_changed = Signal(QColor)
    width_changed = Signal(int)
    undo_clicked = Signal()
    redo_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: #242424;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
            }
            QPushButton {
                background-color: transparent;
                color: #d0d0d0;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 12px;
                padding: 3px 7px;
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
            QPushButton#btn_action {
                color: #a0a0a0;
            }
            QPushButton#btn_action:hover {
                color: #ffffff;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(4)

        # Row 1: Tool buttons
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(3)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(False)

        tools = [
            ("rect", "⬜ 矩形"),
            ("ellipse", "⭕ 椭圆"),
            ("arrow", "↗️ 箭头"),
            ("pen", "✏️ 画笔"),
            ("highlighter", "🖍️ 荧光笔"),
            ("text", "🔤 文字"),
            ("mosaic", "🏁 马赛克"),
        ]

        self.tool_buttons = {}
        for tool_id, label in tools:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, tid=tool_id: self._on_tool_clicked(tid, checked))
            self.tool_group.addButton(btn)
            row1.addWidget(btn)
            self.tool_buttons[tool_id] = btn

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background-color: #444; width: 1px;")
        row1.addWidget(sep)

        # Undo / Redo buttons
        self.btn_undo = QPushButton("↩️ 撤销")
        self.btn_undo.setObjectName("btn_action")
        self.btn_undo.clicked.connect(self.undo_clicked.emit)
        row1.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↪️ 重做")
        self.btn_redo.setObjectName("btn_action")
        self.btn_redo.clicked.connect(self.redo_clicked.emit)
        row1.addWidget(self.btn_redo)

        main_layout.addLayout(row1)

        # Row 2: Secondary options (Palette & Stroke Width)
        self.options_widget = QWidget(self)
        row2 = QHBoxLayout(self.options_widget)
        row2.setContentsMargins(2, 2, 2, 2)
        row2.setSpacing(6)

        # Palette dots
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        for i, col in enumerate(PALETTE_COLORS):
            dot = ColorDotButton(col)
            dot.clicked.connect(lambda checked, c=col: self.color_changed.emit(c))
            self.color_group.addButton(dot)
            row2.addWidget(dot)
            if i == 0:
                dot.setChecked(True)

        row2.addSpacing(6)

        # Stroke Widths: 细 (2px), 中 (4px), 粗 (7px)
        self.width_group = QButtonGroup(self)
        self.width_group.setExclusive(True)
        widths = [("细", 2), ("中", 4), ("粗", 7)]
        for lbl, w in widths:
            wb = QPushButton(lbl)
            wb.setCheckable(True)
            wb.clicked.connect(lambda checked, width=w: self.width_changed.emit(width))
            self.width_group.addButton(wb)
            row2.addWidget(wb)
            if w == 4:
                wb.setChecked(True)

        row2.addStretch()
        main_layout.addWidget(self.options_widget)
        self.options_widget.hide()  # hidden until an annotation tool is active

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
