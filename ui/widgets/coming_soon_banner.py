"""Coming soon banner."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class ComingSoonBanner(QLabel):
    def __init__(self, text="Coming soon", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("padding:12px;border:1px dashed #64748b;border-radius:8px;")
