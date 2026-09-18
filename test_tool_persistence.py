# -*- coding: utf-8 -*-
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QEvent
from PySide6.QtGui import QMouseEvent, QKeyEvent, QPixmap, QColor

from ui.snipper import SnipperWidget
from core.annotation import AnnotationManager

def test_tool_persistence():
    app = QApplication.instance() or QApplication(sys.argv)
    print("Testing Annotation Tool Persistence & Zero Blue Mask...")

    snipper = SnipperWidget()
    snipper.full_pixmap = QPixmap(800, 600)
    snipper.full_pixmap.fill(QColor(100, 150, 200))
    snipper.full_image = snipper.full_pixmap.toImage()
    snipper.resize(800, 600)

    # 1. Simulate initial snip selection
    snipper.prepare_and_show()
    snipper.selection_rect = QRect(100, 100, 400, 300)
    snipper.toolbar.show()
    snipper._position_toolbar()

    # Verify initial state
    assert snipper.selection_rect == QRect(100, 100, 400, 300)
    assert snipper.toolbar.isVisible() is True

    # 2. Select Arrow Tool
    snipper.toolbar.tool_buttons["arrow"].click()
    assert snipper.annot_mgr.current_tool == AnnotationManager.TOOL_ARROW

    # 3. Draw an arrow from (150, 150) to (250, 200) inside selection
    p_down = QMouseEvent(QEvent.Type.MouseButtonPress, QPoint(150, 150), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mousePressEvent(p_down)
    assert snipper.drawing_start_pt == QPointF(150, 150)

    p_move = QMouseEvent(QEvent.Type.MouseMove, QPoint(250, 200), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mouseMoveEvent(p_move)
    assert snipper.current_drawing_shape is not None

    p_up = QMouseEvent(QEvent.Type.MouseButtonRelease, QPoint(250, 200), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mouseReleaseEvent(p_up)

    # CRITICAL CHECKS:
    assert len(snipper.annot_mgr.shapes) == 1, "Arrow shape must be committed to annot_mgr"
    assert snipper.is_mouse_down is False, "is_mouse_down MUST be False after release!"
    assert snipper.has_dragged is False, "has_dragged MUST be False after release!"
    assert snipper.selection_rect == QRect(100, 100, 400, 300), f"selection_rect MUST remain unchanged! Got: {snipper.selection_rect}"
    assert snipper.toolbar.isVisible() is True, "Toolbar MUST remain visible!"

    # 4. Now simulate user moving the mouse freely (the exact user action that caused the bug)
    for test_x in [300, 350, 400, 200, 150]:
        free_move = QMouseEvent(QEvent.Type.MouseMove, QPoint(test_x, 250), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        snipper.mouseMoveEvent(free_move)
        assert snipper.selection_rect == QRect(100, 100, 400, 300), f"selection_rect destroyed during free move at {test_x}! Got: {snipper.selection_rect}"
        assert snipper.toolbar.isVisible() is True, "Toolbar must not vanish during free move!"

    print("Pass 1: Arrow tool used -> selection box and toolbar stay 100% stable during free mouse movements!")

    # 5. Draw another tool (e.g. Mosaic)
    snipper.toolbar.tool_buttons["mosaic"].click()
    assert snipper.annot_mgr.current_tool == AnnotationManager.TOOL_MOSAIC

    p_down2 = QMouseEvent(QEvent.Type.MouseButtonPress, QPoint(200, 200), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mousePressEvent(p_down2)
    p_move2 = QMouseEvent(QEvent.Type.MouseMove, QPoint(280, 260), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mouseMoveEvent(p_move2)
    p_up2 = QMouseEvent(QEvent.Type.MouseButtonRelease, QPoint(280, 260), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mouseReleaseEvent(p_up2)

    assert len(snipper.annot_mgr.shapes) == 2, "Mosaic shape must be committed"
    assert snipper.is_mouse_down is False
    assert snipper.selection_rect == QRect(100, 100, 400, 300)
    assert snipper.toolbar.isVisible() is True
    print("Pass 2: Mosaic tool used -> selection box and toolbar stay completely intact!")

    # 6. Test Right-Click: should exit active tool, NOT destroy selection!
    p_right = QMouseEvent(QEvent.Type.MouseButtonPress, QPoint(250, 250), Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)
    snipper.mousePressEvent(p_right)
    assert snipper.annot_mgr.current_tool == AnnotationManager.TOOL_NONE, "Right click must deselect active tool"
    assert snipper.selection_rect == QRect(100, 100, 400, 300), "Right click must NOT destroy selection box"
    print("Pass 3: Right click gracefully exits annotation tool while preserving screenshot selection!")

    snipper.close()
    print("\nALL PERSISTENCE TESTS PASSED 100%!")

if __name__ == "__main__":
    test_tool_persistence()
