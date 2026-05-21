"""NAV TOOLS - Single frame image upload widget.

A compact upload widget for selecting a single image (start frame / end frame).
Shows thumbnail preview with drag-and-drop support.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


_DROP_ZONE_EMPTY_QSS = """
            QWidget#frameDropZone {
                background-color: #131b2e;
                border: 2px dashed #2a3350;
                border-radius: 10px;
            }
            QWidget#frameDropZone:hover {
                border-color: #4d8eff;
                background-color: #171f33;
            }
        """

_DROP_ZONE_FILLED_QSS = """
            QWidget#frameDropZone {
                background-color: #131b2e;
                border: 2px solid #3b82f6;
                border-radius: 10px;
            }
            QWidget#frameDropZone:hover {
                border-color: #4d8eff;
                background-color: #171f33;
            }
        """


class FrameUpload(QWidget):
    """Single image upload widget with thumbnail preview."""

    image_changed = Signal(str)

    def __init__(self, label: str = "Ảnh khung hình", parent=None):
        super().__init__(parent)
        self._image_path = ""
        self._label_text = label
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel(self._label_text)
        title.setProperty("class", "field-label")
        layout.addWidget(title)

        self._drop_zone = QWidget()
        self._drop_zone.setObjectName("frameDropZone")
        self._drop_zone.setFixedHeight(140)
        self._drop_zone.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drop_zone.setStyleSheet(_DROP_ZONE_EMPTY_QSS)

        drop_layout = QHBoxLayout(self._drop_zone)
        drop_layout.setContentsMargins(12, 8, 12, 8)
        drop_layout.setSpacing(12)

        self._thumbnail = QLabel()
        self._thumbnail.setFixedSize(110, 110)
        self._thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbnail.setStyleSheet("background: #0b1326; border-radius: 8px; border: 1px solid #222a3d;")
        self._thumbnail.hide()
        drop_layout.addWidget(self._thumbnail)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        self._icon_label = QLabel("📷")
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setFont(QFont("Segoe UI Emoji", 28))
        self._icon_label.setStyleSheet("background: transparent; border: none;")
        info_layout.addWidget(self._icon_label)

        self._hint_label = QLabel("Kéo thả ảnh hoặc nhấn để chọn")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet("color: #8c909f; font-size: 12px; background: transparent; border: none;")
        info_layout.addWidget(self._hint_label)

        self._filename_label = QLabel("")
        self._filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._filename_label.setStyleSheet("color: #adc6ff; font-size: 11px; background: transparent; border: none;")
        self._filename_label.hide()
        info_layout.addWidget(self._filename_label)

        drop_layout.addLayout(info_layout, 1)

        self._remove_btn = QPushButton("✕")
        self._remove_btn.setFixedSize(28, 28)
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #93000a;
                color: #ffb4ab;
                border-radius: 14px;
                font-size: 14px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #ba1a1a;
            }
        """
        )
        self._remove_btn.clicked.connect(self.clear)
        self._remove_btn.hide()
        drop_layout.addWidget(self._remove_btn, 0, Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._drop_zone)
        self._drop_zone.mousePressEvent = self._on_click

    def _on_click(self, event):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Chọn {self._label_text}",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if path:
            self.set_image(path)

    def set_image(self, path: str):
        if not path or not os.path.isfile(path):
            return

        self._image_path = path
        filename = os.path.basename(path)
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                110,
                110,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumbnail.setPixmap(scaled)
            self._thumbnail.show()

        self._icon_label.hide()
        self._hint_label.setText("Đã chọn:")
        self._filename_label.setText(filename)
        self._filename_label.show()
        self._remove_btn.show()
        self._drop_zone.setStyleSheet(_DROP_ZONE_FILLED_QSS)
        self.image_changed.emit(path)

    def clear(self):
        self._image_path = ""
        self._thumbnail.clear()
        self._thumbnail.hide()
        self._icon_label.show()
        self._hint_label.setText("Kéo thả ảnh hoặc nhấn để chọn")
        self._filename_label.hide()
        self._remove_btn.hide()
        self._drop_zone.setStyleSheet(_DROP_ZONE_EMPTY_QSS)
        self.image_changed.emit("")

    def get_image_path(self) -> str:
        return self._image_path

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile().lower()
                if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                self.set_image(path)
                return
