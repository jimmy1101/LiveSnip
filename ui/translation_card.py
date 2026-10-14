import sys
from typing import Optional
from PySide6.QtCore import Qt, QPoint, Signal, QRect
from PySide6.QtGui import (
    QColor, QGuiApplication, QClipboard
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QFrame, QGraphicsDropShadowEffect, QApplication
)

from core.translator import (
    LANGUAGE_MAP, get_language_display_name, TranslationWorker
)
from core.ocr_engine import OcrWorker

class TranslationCard(QWidget):
    """
    Modern floating dark-themed translation card.
    Supports auto-language detection, OCR from pixmap, and direct text translation.
    """
    closed = Signal()
    pin_requested = Signal(str)  # Emits translated text for pinning

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.drag_position = QPoint()
        self.ocr_worker: Optional[OcrWorker] = None
        self.trans_worker: Optional[TranslationWorker] = None
        self.current_raw_text = ""
        self.current_translated_text = ""
        self.detected_src_lang = "auto"

        self._init_ui()

    def _init_ui(self):
        # Outer layout with margins for drop shadow
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)

        # Main inner container
        self.container = QFrame(self)
        self.container.setObjectName("card_container")
        self.container.setStyleSheet("""
            QFrame#card_container {
                background-color: #202124;
                border: 1px solid #3c4043;
                border-radius: 8px;
            }
            QLabel {
                color: #e8eaed;
                font-family: "Segoe UI", "Microsoft YaHei";
            }
            QTextEdit {
                background-color: #292a2d;
                color: #f1f3f4;
                border: 1px solid #3c4043;
                border-radius: 6px;
                padding: 6px;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 13px;
                selection-background-color: #0078d4;
            }
            QComboBox {
                background-color: #303134;
                color: #ffffff;
                border: 1px solid #5f6368;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #303134;
                color: #ffffff;
                selection-background-color: #0078d4;
                border: 1px solid #5f6368;
            }
            QPushButton {
                background-color: #303134;
                color: #e8eaed;
                border: 1px solid #5f6368;
                border-radius: 4px;
                padding: 5px 12px;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3c4043;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #202124;
            }
            QPushButton#btn_primary {
                background-color: #0078d4;
                border: 1px solid #1084d8;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton#btn_primary:hover {
                background-color: #106ebe;
            }
            QPushButton#btn_close {
                border: none;
                background: transparent;
                font-size: 14px;
                color: #9aa0a6;
                padding: 2px 6px;
            }
            QPushButton#btn_close:hover {
                color: #ffffff;
                background-color: #d93025;
                border-radius: 3px;
            }
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.container)
        card_layout.setContentsMargins(14, 12, 14, 14)
        card_layout.setSpacing(10)

        # --- Header (Draggable) ---
        header = QHBoxLayout()
        header.setSpacing(8)

        lbl_title = QLabel("🌐 智能翻译")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #8ab4f8;")
        header.addWidget(lbl_title)

        header.addSpacing(6)

        self.lbl_source_lang = QLabel("识别中...")
        self.lbl_source_lang.setStyleSheet("color: #9aa0a6; font-size: 12px;")
        header.addWidget(self.lbl_source_lang)

        lbl_arrow = QLabel("➔")
        lbl_arrow.setStyleSheet("color: #5f6368; font-weight: bold;")
        header.addWidget(lbl_arrow)

        # Target language dropdown
        self.combo_target = QComboBox()
        for code, label in LANGUAGE_MAP.items():
            self.combo_target.addItem(label, code)
        self.combo_target.currentIndexChanged.connect(self._on_target_lang_changed)
        header.addWidget(self.combo_target)

        header.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setObjectName("btn_close")
        btn_close.setToolTip("关闭 (Esc)")
        btn_close.clicked.connect(self.close)
        header.addWidget(btn_close)

        card_layout.addLayout(header)

        # --- Status Label ---
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #fbbc04; font-size: 11px;")
        self.lbl_status.hide()
        card_layout.addWidget(self.lbl_status)

        # --- Original Text Area ---
        lbl_orig_title = QLabel("原文:")
        lbl_orig_title.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        card_layout.addWidget(lbl_orig_title)

        self.txt_original = QTextEdit()
        self.txt_original.setPlaceholderText("原文将在此显示...")
        self.txt_original.setFixedHeight(75)
        card_layout.addWidget(self.txt_original)

        # --- Translated Text Area ---
        lbl_trans_title = QLabel("译文:")
        lbl_trans_title.setStyleSheet("color: #8ab4f8; font-size: 11px; font-weight: bold;")
        card_layout.addWidget(lbl_trans_title)

        self.txt_translated = QTextEdit()
        self.txt_translated.setPlaceholderText("译文将在此显示...")
        self.txt_translated.setFixedHeight(95)
        card_layout.addWidget(self.txt_translated)

        # --- Footer Actions ---
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.btn_copy = QPushButton("📋 复制译文")
        self.btn_copy.setObjectName("btn_primary")
        self.btn_copy.clicked.connect(self._copy_translation)
        footer.addWidget(self.btn_copy)

        self.btn_pin = QPushButton("📌 贴图展示")
        self.btn_pin.setToolTip("将译文生成贴图悬浮在屏幕上")
        self.btn_pin.clicked.connect(self._pin_translation)
        footer.addWidget(self.btn_pin)

        self.btn_retry = QPushButton("🔄 重试")
        self.btn_retry.clicked.connect(self._retry_translation)
        footer.addWidget(self.btn_retry)

        footer.addStretch()
        card_layout.addLayout(footer)

        outer_layout.addWidget(self.container)
        self.resize(440, 360)

    # --- Mouse Drag Support for Frameless Window ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.ocr_worker and self.ocr_worker.isRunning():
            self.ocr_worker.requestInterruption()
            self.ocr_worker.wait(500)
        if self.trans_worker and self.trans_worker.isRunning():
            self.trans_worker.requestInterruption()
            self.trans_worker.wait(1000)
        self.closed.emit()
        super().closeEvent(event)

    # --- Public Translation Triggers ---

    def start_ocr_and_translate(self, pixmap: QPixmap, pos: Optional[QPoint] = None):
        """Perform OCR on the cropped pixmap, then auto-translate the detected text."""
        self._position_safely(pos)
        self.show()
        self.raise_()
        self.activateWindow()

        self.txt_original.clear()
        self.txt_translated.clear()
        self.lbl_source_lang.setText("🔍 正在识别...")
        self.lbl_status.setText("⏳ 正在调用 RapidOCR 识别图像文字...")
        self.lbl_status.show()

        if self.ocr_worker and self.ocr_worker.isRunning():
            self.ocr_worker.requestInterruption()
            self.ocr_worker.wait(500)

        self.ocr_worker = OcrWorker(pixmap, parent=None)
        self.ocr_worker.finished_ocr.connect(self._on_ocr_finished)
        self.ocr_worker.finished.connect(self.ocr_worker.deleteLater)
        self.ocr_worker.start()

    def start_translate_text(self, text: str, pos: Optional[QPoint] = None):
        """Directly translate given text with automatic language detection."""
        self._position_safely(pos)
        self.show()
        self.raise_()
        self.activateWindow()

        self.current_raw_text = text.strip()
        self.txt_original.setPlainText(self.current_raw_text)
        self.txt_translated.clear()

        if not self.current_raw_text:
            self.lbl_status.setText("⚠️ 待翻译内容为空")
            self.lbl_status.show()
            return

        self._trigger_translation()

    # --- Internal Handlers ---

    def _on_ocr_finished(self, blocks):
        self.lbl_status.hide()
        if not blocks:
            self.lbl_source_lang.setText("未识别到文字")
            self.txt_original.setPlainText("未在框选区域内识别到可提取的文字内容。")
            self.txt_translated.setPlainText("请重新框选包含清晰文字的区域。")
            return

        full_text = "\n".join([b.text for b in blocks if b.text and b.text.strip()])
        if not full_text.strip():
            self.lbl_source_lang.setText("未识别到文字")
            self.txt_original.setPlainText("未在框选区域内识别到可提取的文字内容。")
            return

        self.current_raw_text = full_text.strip()
        self.txt_original.setPlainText(self.current_raw_text)
        self._trigger_translation()

    def _trigger_translation(self):
        target_code = self.combo_target.currentData() or "zh-CN"
        self.lbl_status.setText("🌐 正在翻译中...")
        self.lbl_status.show()
        self.lbl_source_lang.setText("检测语种中...")

        if self.trans_worker and self.trans_worker.isRunning():
            self.trans_worker.requestInterruption()
            self.trans_worker.wait(500)

        self.trans_worker = TranslationWorker(
            text=self.current_raw_text,
            target_lang=target_code,
            source_lang="auto",
            parent=None
        )
        self.trans_worker.finished_translation.connect(self._on_translation_finished)
        self.trans_worker.finished.connect(self.trans_worker.deleteLater)
        self.trans_worker.start()

    def _on_translation_finished(self, result: dict):
        self.lbl_status.hide()
        if result.get("success"):
            self.current_translated_text = result.get("translated", "")
            self.detected_src_lang = result.get("source_lang", "auto")
            tgt_lang = result.get("target_lang", "zh-CN")

            # Update language badge
            src_name = get_language_display_name(self.detected_src_lang)
            self.lbl_source_lang.setText(f"检测为: {src_name}")

            # Sync target combobox without triggering loop
            self.combo_target.blockSignals(True)
            for idx in range(self.combo_target.count()):
                if self.combo_target.itemData(idx) == tgt_lang:
                    self.combo_target.setCurrentIndex(idx)
                    break
            self.combo_target.blockSignals(False)

            self.txt_translated.setPlainText(self.current_translated_text)
        else:
            err = result.get("error", "未知错误")
            self.lbl_status.setText(f"❌ 翻译失败: {err}")
            self.lbl_status.show()

    def _on_target_lang_changed(self):
        """User manually switched target language -> re-translate."""
        if self.current_raw_text:
            target_code = self.combo_target.currentData() or "zh-CN"
            self.lbl_status.setText("🌐 正在重新翻译...")
            self.lbl_status.show()

            if self.trans_worker and self.trans_worker.isRunning():
                self.trans_worker.requestInterruption()
                self.trans_worker.wait(500)

            self.trans_worker = TranslationWorker(
                text=self.current_raw_text,
                target_lang=target_code,
                source_lang=self.detected_src_lang if self.detected_src_lang != "auto" else "auto",
                parent=None
            )
            self.trans_worker.finished_translation.connect(self._on_translation_finished)
            self.trans_worker.finished.connect(self.trans_worker.deleteLater)
            self.trans_worker.start()

    def _copy_translation(self):
        text = self.txt_translated.toPlainText().strip()
        if text:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(text)
            orig_text = self.btn_copy.text()
            self.btn_copy.setText("✅ 已复制!")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_copy.setText(orig_text))

    def _pin_translation(self):
        text = self.txt_translated.toPlainText().strip()
        if text:
            self.pin_requested.emit(text)

    def _retry_translation(self):
        if self.current_raw_text:
            self._trigger_translation()

    def _position_safely(self, pos: Optional[QPoint]):
        screen = QGuiApplication.primaryScreen().geometry()
        w = self.width()
        h = self.height()

        if pos is not None:
            # Place near requested position (e.g. bottom-right of snip)
            target_x = pos.x() + 15
            target_y = pos.y() + 15
        else:
            # Center of primary screen
            target_x = screen.center().x() - w // 2
            target_y = screen.center().y() - h // 2

        # Clamp inside screen boundaries
        target_x = max(screen.left() + 20, min(target_x, screen.right() - w - 20))
        target_y = max(screen.top() + 30, min(target_y, screen.bottom() - h - 40))
        self.move(target_x, target_y)
