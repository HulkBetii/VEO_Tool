"""LazyPage wrapper - defer heavy page construction until first navigation.

Without this, MainWindow.__init__ pays the full import + UI cost of
EVERY page upfront, even ones the user never visits in this session.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from utils.logger import log


class LazyPage(QWidget):
    """Placeholder QWidget that swaps in a real page on first access."""

    page_loaded = Signal(QWidget)

    def __init__(
        self,
        factory: Callable[[], QWidget],
        name: str = "page",
        loading_text: str = "Đang tải trang...",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._factory = factory
        self._name = name
        self._real = None
        self._loading = True
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel(loading_text)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #94a3b8; font-size: 14px; font-style: italic; padding: 40px;")
        self._layout.addWidget(self._placeholder)

    @property
    def is_loaded(self) -> bool:
        return self._real is not None

    @property
    def real(self) -> Optional[QWidget]:
        """The real page widget, or None if not yet loaded."""
        return self._real

    def ensure_loaded(self) -> QWidget:
        """Construct the real page on first call. Subsequent calls cheap."""
        if self._real is not None:
            return self._real

        self._placeholder.setText("⏳ Đang tải… giây lát")
        QApplication.processEvents()

        import time

        t0 = time.perf_counter()
        try:
            self._real = self._factory()
            self._layout.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None
            self._layout.addWidget(self._real)
            self._loading = False
            elapsed = time.perf_counter() - t0
            log.info(f"[LazyPage] {self._name} created in {elapsed * 1000:.0f}ms")
            self.page_loaded.emit(self._real)
            return self._real
        except Exception as e:
            log.error(f"[LazyPage] {self._name} factory failed: {e}")
            self._placeholder.setText(f"⚠ Không tải được trang: {type(e).__name__}: {e}")
            self._placeholder.setStyleSheet("color: #ef4444; font-size: 13px; padding: 40px;")
            return self
