"""Image preview dialog."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout


class ImagePreviewDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.pixmap = QPixmap(image_path)
        layout = QVBoxLayout(self)
        self.label = QLabel()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(self.label)
        layout.addWidget(close)
        self._rescale_pixmap()

    def _rescale_pixmap(self):
        if not self.pixmap.isNull():
            self.label.setPixmap(self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        self._rescale_pixmap()
        super().resizeEvent(event)
