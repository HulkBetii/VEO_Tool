"""NAV TOOLS - Sidebar navigation (BIG icon + text below)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from config.constants import APP_NAME, APP_VERSION, SIDEBAR_WIDTH


_SIDEBAR_INNER_WIDTH = max(SIDEBAR_WIDTH - 12, 128)
_SIDEBAR_OUTER_WIDTH = _SIDEBAR_INNER_WIDTH + 12


class SidebarButton(QWidget):
    """Sidebar item: large centered icon + small label below."""

    clicked = Signal()

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.setFixedWidth(_SIDEBAR_INNER_WIDTH)
        self.setFixedHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("class", "sidebar-btn")
        self.setProperty("active", False)
        self._active = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_label = QLabel(icon)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFont(QFont("Segoe UI Emoji", 24))
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.icon_label)

        self.text_label = QLabel(label)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setFont(QFont("Segoe UI", 10))
        self.text_label.setFixedWidth(_SIDEBAR_INNER_WIDTH - 10)
        self.text_label.setMinimumHeight(28)
        self.text_label.setWordWrap(False)
        self.text_label.setStyleSheet("background: transparent; border: none; color: #8c909f;")
        layout.addWidget(self.text_label, 0, Qt.AlignmentFlag.AlignHCenter)

    def mousePressEvent(self, event):
        self.clicked.emit()
        return None

    def set_active(self, active: bool):
        self._active = active
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.text_label.setStyleSheet(
            "background: transparent; border: none; color: #adc6ff; font-weight: bold;"
            if active
            else "background: transparent; border: none; color: #8c909f;"
        )
        self.icon_label.setStyleSheet("background: transparent; border: none;")


class Sidebar(QWidget):
    """Vertical sidebar - icon + text layout."""

    page_changed = Signal(int)

    ITEMS = (
        ("🖼️", "Tạo ảnh"),
        ("👥", "Ảnh đồng\nnhất"),
        ("🎞️", "Video đồng\nnhất"),
        ("🎬", "Video Flow"),
        ("🎥", "Video từ ảnh"),
        ("🎦", "Video dài\n(extend)"),
        ("🔗", "Nối khung\nhình"),
        ("🔍", "YouTube\n→ Prompt"),
        ("📝", "Ý tưởng\n→ Video"),
        ("✂️", "Xóa nền\nảnh"),
        ("🧹", "Xóa logo\nVeo"),
        ("🔎", "Ảnh\n→ Prompt"),
        ("🔺", "Upscale\nảnh"),
        ("🎵", "Ghép nhạc\nvideo"),
        ("💬", "Tạo phụ\nđề"),
        ("📐", "Batch\nResize"),
        ("📋", "Logs"),
        ("⚙️", "Cài đặt"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(_SIDEBAR_OUTER_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 8, 3, 8)
        layout.setSpacing(2)

        from config.constants import ASSETS_DIR

        icon_png = Path(ASSETS_DIR) / "config" / "app_icon.png"
        if icon_png.exists():
            logo_label = QLabel()
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pix = QPixmap(str(icon_png))
            logo_label.setPixmap(
                pix.scaled(
                    40,
                    40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            logo_label.setStyleSheet("background: transparent; border: none; margin-top: 4px;")
            layout.addWidget(logo_label)
            layout.addSpacing(2)

        title = QLabel(APP_NAME)
        title.setObjectName("sidebar-logo")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #555; border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )

        btn_container = QWidget()
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(2)

        self._buttons = []
        for i, (icon, label) in enumerate(self.ITEMS):
            btn = SidebarButton(icon, label)
            btn.clicked.connect(lambda idx=i: self._on_click(idx))
            btn_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._buttons.append(btn)

        btn_layout.addStretch()
        scroll.setWidget(btn_container)
        layout.addWidget(scroll, 1)

        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("sidebar-version")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        self.set_active(3)

    def _on_click(self, index):
        self.set_active(index)
        self.page_changed.emit(index)

    def set_active(self, index: int):
        for i, btn in enumerate(self._buttons):
            btn.set_active(i == index)

    def set_enabled_all(self, enabled: bool):
        for btn in self._buttons:
            btn.setEnabled(enabled)
            btn.setCursor(
                Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor
            )
