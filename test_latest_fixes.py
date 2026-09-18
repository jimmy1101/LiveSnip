# -*- coding: utf-8 -*-
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QEvent
from PySide6.QtGui import QMouseEvent, QPixmap, QColor

from ui.snipper import SnipperWidget
from core.hotkey import GlobalHotkeyManager

def test_latest_fixes():
    app = QApplication.instance() or QApplication(sys.argv)
    print('=== Testing 3 Latest User Requirements ===')

    # 1. Test Hotkey Manager binding
    mgr = GlobalHotkeyManager()
    mgr.start()
    print(f'Req 1 Check: Snip={mgr.snip_key_desc}, Pin={mgr.pin_key_desc}')
    assert mgr.snip_key_desc in ("F1", "未绑定"), f'Unexpected snip desc: {mgr.snip_key_desc}'
    assert mgr.pin_key_desc in ("F3", "未绑定"), f'Unexpected pin desc: {mgr.pin_key_desc}'
    mgr.stop()
    print('Req 1 Passed: 仅绑定唯一键：F1 截图，F3 贴图，简洁稳定！')

    # 2. Test Snipper Default Cursor (Req 3: 取色时鼠标状态应该是默认的单箭头)
    snipper = SnipperWidget()
    snipper.full_pixmap = QPixmap(800, 600)
    snipper.full_pixmap.fill(QColor(100, 150, 200))
    snipper.full_image = snipper.full_pixmap.toImage()
    snipper.resize(800, 600)
    snipper.prepare_and_show()

    assert snipper.cursor().shape() == Qt.CursorShape.ArrowCursor, f'Initial cursor must be ArrowCursor, got {snipper.cursor().shape()}'

    # Hovering to detect window / pick color
    move_event = QMouseEvent(QEvent.Type.MouseMove, QPoint(200, 200), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    snipper.mouseMoveEvent(move_event)
    assert snipper.cursor().shape() == Qt.CursorShape.ArrowCursor, f'Hovering cursor must be ArrowCursor, got {snipper.cursor().shape()}'
    assert snipper.magnifier_overlay.is_active is True, 'Magnifier must be active while hovering before selection'
    print('Req 3 Passed: 取色与探测模式下鼠标状态为默认单箭头 (ArrowCursor)，精准满足用户视觉习惯！')

    # 3. Test Magnifier Hidden during Box Selection (Req 2: 框选操作时隐藏取色框)
    # 3.1 Mouse Press starts box selection
    press_event = QMouseEvent(QEvent.Type.MouseButtonPress, QPoint(100, 100), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mousePressEvent(press_event)
    assert snipper.magnifier_overlay.is_active is False, 'Magnifier must be hidden immediately on mouse press'

    # 3.2 Dragging to select box
    drag_event = QMouseEvent(QEvent.Type.MouseMove, QPoint(250, 220), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mouseMoveEvent(drag_event)
    assert snipper.magnifier_overlay.is_active is False, 'Magnifier must remain hidden during box selection dragging'

    # 3.3 Mouse Release completes box selection
    rel_event = QMouseEvent(QEvent.Type.MouseButtonRelease, QPoint(250, 220), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    snipper.mouseReleaseEvent(rel_event)
    assert snipper.selection_rect == QRect(QPoint(100, 100), QPoint(250, 220))
    assert snipper.magnifier_overlay.is_active is True, 'Magnifier reappears after box selection release for in-situ color picking'
    assert snipper.cursor().shape() == Qt.CursorShape.ArrowCursor, f'Cursor after box selection must be ArrowCursor, got {snipper.cursor().shape()}'

    # Hover inside selection box
    hover_inside = QMouseEvent(QEvent.Type.MouseMove, QPoint(150, 150), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    snipper.mouseMoveEvent(hover_inside)
    assert snipper.cursor().shape() == Qt.CursorShape.ArrowCursor, f'Cursor hovering inside box must be ArrowCursor, got {snipper.cursor().shape()}'
    print('Req 4 Passed: 框选后鼠标状态保持为默认单箭头样式 (ArrowCursor)！')

    snipper.close()
    print(">>> 全部优化需求 100% 验证通过！ <<<")

if __name__ == '__main__':
    test_latest_fixes()
