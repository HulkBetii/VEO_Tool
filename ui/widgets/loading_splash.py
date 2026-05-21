"""Loading splash with progress bar - shown while MainWindow init runs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout


class LoadingSplash(QDialog):
    def __init__(self, title: str = "NAV TOOLS", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setFixedSize(420, 180)
        self.setModal(False)

        try:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)
        except Exception:
            pass

        from PySide6.QtWidgets import QFrame

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("splashCard")
        card.setStyleSheet("QFrame#splashCard { background-color: #0d1529; border: 1px solid #1e2d4a;}")
        outer_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "color: #4ec9b0; font-size: 20px; font-weight: bold; "
            "background: transparent; border: none; letter-spacing: 1px;"
        )
        layout.addWidget(title_lbl)

        self._status = QLabel("Đang khởi động...")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: #8c909f; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet(
            "QProgressBar { background: #1e2d4a; border: none; border-radius: 3px;}"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4ec9b0, stop:1 #7be3cf); border-radius: 3px;}"
        )
        layout.addWidget(self._bar)

        footer = QLabel("Khởi động lần đầu hơi lâu, lần sau nhanh hơn")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            "color: #555e7a; font-size: 10px; background: transparent; border: none; font-style: italic;"
        )
        layout.addWidget(footer)

    def set_progress(self, percent: int, status: str = "") -> None:
        """Update progress bar and status text. Caller should processEvents()."""
        self._bar.setValue(max(0, min(100, percent)))
        if status:
            self._status.setText(status)
        QApplication.processEvents()
