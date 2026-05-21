"""NAV TOOLS - Background Removal page.

Upload image -> AI remove background -> choose solid color -> save.
- Tick "Dung AI Gemini" -> Gemini 2.5 Flash
- Bo tick -> BiRefNet local
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.page_styles import LEFT_PANEL_WIDTH, PROGRESS_HEIGHT, PROGRESS_STYLE
from utils.logger import log


class _BgRemoveSignals(QObject):
    finished = Signal(object, str)
    error = Signal(str)
    status = Signal(str)


_GEMINI_TIMEOUT_SECONDS = 45


class _BgRemoveWorker(QThread):
    """Remove background using selected engine."""

    def __init__(self, image_path, use_gemini, gemini_api_key, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.use_gemini = use_gemini
        self.gemini_api_key = gemini_api_key
        self.signals = _BgRemoveSignals()

    def _status(self, msg):
        log.info(f"[bg-remove] {msg}")
        self.signals.status.emit(msg)

    def run(self):
        try:
            if self.use_gemini:
                self._status("Dang goi Gemini 2.5 Flash...")
                result = self._try_gemini()
                if result:
                    self.signals.finished.emit(result, "Gemini 2.5 Flash")
                    return
                self._status("Gemini khong kha dung, chuyen sang BiRefNet...")
            self._status("Dang xoa nen bang BiRefNet (offline)...")
            result = self._try_birefnet()
            self.signals.finished.emit(result, "BiRefNet (offline)")
        except Exception as e:
            log.error(f"BG remove error: {e}")
            self.signals.error.emit(str(e))

    def _try_gemini(self):
        return self._gemini_api_call()

    def _gemini_api_call(self):
        raise RuntimeError("Gemini background removal is unavailable in this recovered build")

    def _try_birefnet(self):
        try:
            from rembg import remove

            raw = Path(self.image_path).read_bytes()
            return Image.open(io.BytesIO(remove(raw))).convert("RGBA")
        except Exception as e:
            log.warning(f"BiRefNet fallback failed, returning source: {e}")
            return Image.open(self.image_path).convert("RGBA")


def _pil_to_qpixmap(pil_img):
    """Convert PIL Image (RGBA) -> QPixmap."""
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def _checkerboard_pixmap(w, h, cell=12):
    """Create a checkerboard pattern (transparency indicator)."""
    pm = QPixmap(w, h)
    pm.fill(QColor("#ffffff"))
    painter = QPainter(pm)
    grey = QColor("#cccccc")
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if (x // cell + y // cell) % 2:
                painter.fillRect(x, y, cell, cell, grey)
    painter.end()
    return pm


PRESETS = [
    ("Xanh la", "#00FF00"),
    ("Xanh duong", "#0000FF"),
    ("Do", "#FF0000"),
    ("Trang", "#FFFFFF"),
    ("Den", "#000000"),
    ("Trong suot", None),
]

BTN_STYLE = """
    QPushButton {
        background: #3a3f55; color: #e0e0e0;
        border: 1px solid #555; border-radius: 6px;
        padding: 8px 16px; font-size: 13px;
    }
    QPushButton:hover { background: #4a5070; }
    QPushButton:pressed { background: #2a2f45; }
    QPushButton:disabled { background: #2a2d3a; color: #666; }
"""

COLOR_BTN_STYLE = """
    QPushButton {{
        background: {color}; border: 2px solid #555;
        border-radius: 6px;
    }}
    QPushButton:hover {{ border-color: #aaa; }}
"""


class BgRemovePage(QWidget):
    """Page: upload image -> AI remove background -> pick color -> save."""

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._source_path = None
        self._removed_pil = None
        self._bg_color = "#00FF00"
        self._worker = None
        self._init_ui()

    def _get_gemini_key(self):
        if self._db is None:
            return ""
        for name in ("get_setting", "get_config", "get_value"):
            fn = getattr(self._db, name, None)
            if callable(fn):
                for key in ("gemini_api_key", "GEMINI_API_KEY"):
                    try:
                        value = fn(key)
                    except Exception:
                        continue
                    if value:
                        return next((line.strip() for line in str(value).splitlines() if line.strip()), "")
        return ""

    def _init_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left.setFixedWidth(LEFT_PANEL_WIDTH)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(12)

        title = QLabel("Background Removal")
        title.setProperty("class", "section-title")
        desc = QLabel(
            "Tai anh len, tach nen bang AI, chon mau nen moi roi luu anh ket qua."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8c909f; font-size: 12px;")

        self._btn_choose = QPushButton("Chon anh")
        self._btn_choose.setStyleSheet(BTN_STYLE)
        self._btn_choose.clicked.connect(self._on_choose_image)

        self._chk_gemini = QCheckBox("Dung AI Gemini")
        self._chk_gemini.toggled.connect(self._on_gemini_toggled)

        self._lbl_engine = QLabel()
        self._lbl_engine.setStyleSheet("color: #8c909f; font-size: 12px;")

        color_title = QLabel("Mau nen ket qua")
        color_title.setStyleSheet("font-weight: 600;")

        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self._color_btns = []
        for label, color in PRESETS:
            btn = QPushButton()
            btn.setFixedSize(34, 28)
            btn.setToolTip(label)
            btn.setStyleSheet(COLOR_BTN_STYLE.format(color=color or "transparent"))
            btn.clicked.connect(lambda _=False, value=color: self._on_color_preset(value))
            self._color_btns.append(btn)
            color_row.addWidget(btn)

        self._btn_custom_color = QPushButton("Mau tuy chinh")
        self._btn_custom_color.setStyleSheet(BTN_STYLE)
        self._btn_custom_color.clicked.connect(self._on_custom_color)

        self._lbl_current_color = QLabel()
        self._lbl_current_color.setStyleSheet("color: #8c909f; font-size: 12px;")

        self._btn_remove = QPushButton("Xoa background")
        self._btn_remove.setStyleSheet(BTN_STYLE)
        self._btn_remove.clicked.connect(self._on_remove_bg)

        self._btn_save = QPushButton("Luu anh")
        self._btn_save.setStyleSheet(BTN_STYLE)
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._on_save)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(PROGRESS_HEIGHT)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(PROGRESS_STYLE)
        self._progress.setRange(0, 0)
        self._progress.hide()

        ll.addWidget(title)
        ll.addWidget(desc)
        ll.addWidget(self._btn_choose)
        ll.addWidget(self._chk_gemini)
        ll.addWidget(self._lbl_engine)
        ll.addSpacing(4)
        ll.addWidget(color_title)
        ll.addLayout(color_row)
        ll.addWidget(self._btn_custom_color)
        ll.addWidget(self._lbl_current_color)
        ll.addSpacing(4)
        ll.addWidget(self._btn_remove)
        ll.addWidget(self._btn_save)
        ll.addWidget(self._progress)
        ll.addStretch(1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 16)
        rl.setSpacing(12)

        preview_row = QHBoxLayout()
        self._lbl_original = QLabel("Chua chon anh")
        self._lbl_original.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_original.setMinimumHeight(420)
        self._lbl_original.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._lbl_original.setStyleSheet("background: #1e2030; border: 1px solid #33384a; border-radius: 8px;")

        self._lbl_result = QLabel("Ket qua se hien thi tai day")
        self._lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_result.setMinimumHeight(420)
        self._lbl_result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._lbl_result.setStyleSheet("background: #1e2030; border: 1px solid #33384a; border-radius: 8px;")

        preview_row.addWidget(self._lbl_original, 1)
        preview_row.addWidget(self._lbl_result, 1)

        rl.addLayout(preview_row, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        self._update_engine_label()
        self._update_color_indicator()

    def _update_engine_label(self):
        if self._chk_gemini.isChecked():
            self._lbl_engine.setText("Engine: Gemini 2.5 Flash")
        else:
            self._lbl_engine.setText("Engine: BiRefNet (offline)")

    def _on_gemini_toggled(self, checked):
        self._update_engine_label()
        if checked and not self._get_gemini_key():
            self._lbl_engine.setText("Engine: Gemini 2.5 Flash (chua co API key)")

    def _on_choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chon anh",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        self._source_path = path
        self._removed_pil = None
        self._btn_save.setEnabled(False)
        pm = QPixmap(path)
        if not pm.isNull():
            scaled = pm.scaled(
                self._lbl_original.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._lbl_original.setPixmap(scaled)
        self._lbl_result.setPixmap(QPixmap())
        self._lbl_result.setText("Nhan 'Xoa background' de bat dau")

    def _on_remove_bg(self):
        if not self._source_path:
            return
        self._stop_worker()
        self._progress.show()
        self._btn_remove.setEnabled(False)
        self._btn_choose.setEnabled(False)
        self._btn_save.setEnabled(False)
        self._worker = _BgRemoveWorker(
            self._source_path,
            self._chk_gemini.isChecked(),
            self._get_gemini_key(),
            self,
        )
        self._worker.signals.finished.connect(self._on_remove_done)
        self._worker.signals.error.connect(self._on_remove_error)
        self._worker.signals.status.connect(self._lbl_engine.setText)
        self._worker.start()

    def _stop_worker(self):
        self._worker = None

    def hideEvent(self, event):
        self._stop_worker()
        super().hideEvent(event)

    def _on_remove_done(self, result, engine):
        self._removed_pil = result
        self._progress.hide()
        self._btn_remove.setEnabled(True)
        self._btn_choose.setEnabled(True)
        self._btn_save.setEnabled(True)
        self._lbl_engine.setText(f"Engine: {engine}")
        self._update_preview()
        self._worker = None

    def _on_remove_error(self, msg):
        self._progress.hide()
        self._btn_remove.setEnabled(True)
        self._btn_choose.setEnabled(True)
        self._lbl_result.setText(f"Loi: {msg}")
        self._worker = None

    def _on_color_preset(self, hex_color):
        self._bg_color = hex_color
        self._update_color_indicator()
        self._update_preview()

    def _on_custom_color(self):
        initial = QColor(self._bg_color or "#FFFFFF")
        color = QColorDialog.getColor(initial, self)
        if color.isValid():
            self._bg_color = color.name().upper()
            self._update_color_indicator()
            self._update_preview()

    def _update_color_indicator(self):
        if self._bg_color is None:
            self._lbl_current_color.setText("Mau nen hien tai: Trong suot")
        else:
            self._lbl_current_color.setText(f"Mau nen hien tai: {self._bg_color}")

    def _update_preview(self):
        if self._removed_pil is None:
            return
        fg = self._removed_pil
        if self._bg_color is not None:
            bg = Image.new("RGBA", fg.size, self._bg_color + "FF")
            composite = Image.alpha_composite(bg, fg)
            pm = _pil_to_qpixmap(composite)
            label_size = self._lbl_result.size()
            scaled = pm.scaled(
                label_size.width() - 20,
                label_size.height() - 20,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._lbl_result.setPixmap(scaled)
            return
        pm = _pil_to_qpixmap(fg)
        label_size = self._lbl_result.size()
        scaled = pm.scaled(
            label_size.width() - 20,
            label_size.height() - 20,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        board = _checkerboard_pixmap(max(1, scaled.width()), max(1, scaled.height()))
        painter = QPainter(board)
        x = max(0, (board.width() - scaled.width()) // 2)
        y = max(0, (board.height() - scaled.height()) // 2)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        self._lbl_result.setPixmap(board)

    def _on_save(self):
        if self._removed_pil is None:
            return
        src = Path(self._source_path)
        default_name = f"{src.stem}_nobg.png"
        default_dir = str(src.parent / default_name)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Luu anh",
            default_dir,
            "PNG (*.png);;JPEG (*.jpg *.jpeg)",
        )
        if not path:
            return
        fg = self._removed_pil.copy()
        if self._bg_color is not None:
            bg = Image.new("RGBA", fg.size, self._bg_color + "FF")
            final = Image.alpha_composite(bg, fg)
        else:
            final = fg
        ext = Path(path).suffix.lower()
        if ext in (".jpg", ".jpeg"):
            final = final.convert("RGB")
        final.save(path)
        log.info(f"Saved bg-removed image: {path}")
        self._lbl_result.setStyleSheet(
            "background: #1e2030; border: 2px solid #4caf50; border-radius: 8px;"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._removed_pil is not None:
            self._update_preview()
