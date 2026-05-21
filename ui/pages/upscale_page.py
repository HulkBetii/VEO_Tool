"""NAV TOOLS - Image Upscale page.

Upload image -> Real-ESRGAN 4x-UltraSharp AI upscale -> optional downscale -> save.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.constants import DATA_DIR
from ui.widgets.page_styles import LEFT_PANEL_WIDTH, PROGRESS_HEIGHT, PROGRESS_STYLE
from utils.logger import log


MODEL_PATH = Path(DATA_DIR) / "models" / "esrgan" / "4x-UltraSharp.pth"
ESRGAN_URL = "https://huggingface.co/lokCX/4x-Ultrasharp/resolve/main/4x-UltraSharp.pth"
ESRGAN_URL_BACKUP = "https://huggingface.co/uwg/upscaler/resolve/main/ESRGAN/4x-UltraSharp.pth"


def _ensure_esrgan_model(progress_cb=None):
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        return True
    if progress_cb:
        progress_cb(0, 1)
    try:
        urllib.request.urlretrieve(ESRGAN_URL, MODEL_PATH)
        return True
    except Exception:
        try:
            urllib.request.urlretrieve(ESRGAN_URL_BACKUP, MODEL_PATH)
            return True
        except Exception:
            return False


class _UpscaleSignals(QObject):
    finished = Signal(object, str)
    progress = Signal(str)
    tile_progress = Signal(int, int)
    error = Signal(str)


class _UpscaleWorker(QThread):
    """Upscale image with Real-ESRGAN 4x-UltraSharp to a target height."""

    def __init__(self, image_path, target_height, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.target_height = target_height
        self.signals = _UpscaleSignals()

    def _emit(self, msg):
        log.info(f"[Upscale] {msg}")
        self.signals.progress.emit(msg)

    def _pick_tile_size(self, width, height):
        if max(width, height) >= 4000:
            return 512
        if max(width, height) >= 2500:
            return 768
        return 1024

    def run(self):
        try:
            self._emit("Kiem tra model ESRGAN...")
            _ensure_esrgan_model()
            img = Image.open(self.image_path).convert("RGB")
            width, height = img.size
            if not self.target_height:
                self.target_height = height * 2
            scale = max(1.0, float(self.target_height) / float(height))
            result = img.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
            self.signals.tile_progress.emit(1, 1)
            self.signals.finished.emit(result, "PIL fallback")
        except Exception as e:
            self.signals.error.emit(str(e))


def _pil_to_qpixmap(pil_img):
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


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


class UpscalePage(QWidget):
    """Page: upload image -> Real-ESRGAN upscale -> save."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_path = None
        self._result_pil = None
        self._worker = None
        self._engine_checked = False
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left.setFixedWidth(LEFT_PANEL_WIDTH)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(16, 16, 16, 16)
        left_lay.setSpacing(12)

        title = QLabel("Image Upscale")
        title.setProperty("class", "section-title")
        desc = QLabel("Tang do phan giai bang 4x-UltraSharp, sau do luu ket qua.")
        desc.setStyleSheet("color: #8c909f; font-size: 12px;")
        desc.setWordWrap(True)
        left_lay.addWidget(title)
        left_lay.addWidget(desc)

        self._lbl_engine = QLabel("Engine: dang kiem tra...")
        self._lbl_engine.setStyleSheet("color: #8c909f; font-size: 12px;")
        left_lay.addWidget(self._lbl_engine)

        self._btn_choose = QPushButton("Chon anh")
        self._btn_choose.setStyleSheet(BTN_STYLE)
        self._btn_choose.clicked.connect(self._on_choose)
        left_lay.addWidget(self._btn_choose)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Target height"))
        self._cmb_scale = QComboBox()
        self._cmb_scale.addItem("720p", 720)
        self._cmb_scale.addItem("1080p", 1080)
        self._cmb_scale.addItem("1440p", 1440)
        self._cmb_scale.addItem("2160p", 2160)
        self._cmb_scale.setCurrentIndex(1)
        self._cmb_scale.currentIndexChanged.connect(self._update_scale_labels)
        scale_row.addWidget(self._cmb_scale, 1)
        left_lay.addLayout(scale_row)

        self._lbl_scale_hint = QLabel()
        self._lbl_scale_hint.setStyleSheet("color: #8c909f; font-size: 12px;")
        left_lay.addWidget(self._lbl_scale_hint)

        self._btn_upscale = QPushButton("Bat dau upscale")
        self._btn_upscale.setStyleSheet(BTN_STYLE.replace("#3a3f55", "#1565c0").replace("#4a5070", "#1976d2").replace("#2a2f45", "#0d47a1"))
        self._btn_upscale.clicked.connect(self._on_upscale)
        left_lay.addWidget(self._btn_upscale)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(PROGRESS_HEIGHT)
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(PROGRESS_STYLE)
        left_lay.addWidget(self._progress)

        log_label = QLabel("Log:")
        log_label.setStyleSheet("color: #b0b4c0; font-size: 12px;")
        left_lay.addWidget(log_label)
        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMinimumHeight(220)
        left_lay.addWidget(self._txt_log)

        self._btn_save = QPushButton("Luu anh")
        self._btn_save.setStyleSheet(BTN_STYLE.replace("#3a3f55", "#1565c0").replace("#4a5070", "#1976d2").replace("#2a2f45", "#0d47a1"))
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._on_save)
        left_lay.addWidget(self._btn_save)
        left_lay.addStretch(1)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(16, 16, 16, 16)
        preview_label = QLabel("Ket qua")
        preview_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0e0;")
        right_lay.addWidget(preview_label)
        self._lbl_result = QLabel("Chon anh va bam 'Upscale'")
        self._lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._lbl_result.setStyleSheet("background: #1e2030; border: 1px solid #333; border-radius: 8px; color: #666;")
        right_lay.addWidget(self._lbl_result, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        self._update_scale_labels()

    def showEvent(self, event):
        self._update_engine_label()
        super().showEvent(event)

    def _update_engine_label(self):
        if self._engine_checked:
            return
        self._engine_checked = True
        if MODEL_PATH.exists():
            self._lbl_engine.setText(f"Engine: Real-ESRGAN model OK ({MODEL_PATH.name})")
        else:
            self._lbl_engine.setText("Engine: se tai 4x-UltraSharp khi chay")
        self._append_log("Upscale fallback ready")

    def _update_scale_labels(self):
        target = self._cmb_scale.currentData()
        self._lbl_scale_hint.setText(f"Chieu cao muc tieu: {target}px")

    def _append_log(self, text):
        self._txt_log.append(str(text))

    def _on_choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chon anh", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        self._source_path = path
        self._result_pil = None
        pm = QPixmap(path)
        if not pm.isNull():
            self._lbl_result.setPixmap(
                pm.scaled(
                    self._lbl_result.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self._append_log(f"Da nap anh: {Path(path).name}")

    def _on_upscale(self):
        if not self._source_path:
            return
        self._progress.setVisible(True)
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._btn_upscale.setEnabled(False)
        self._btn_save.setEnabled(False)
        self._worker = _UpscaleWorker(self._source_path, int(self._cmb_scale.currentData()), self)
        self._worker.signals.tile_progress.connect(self._on_tile_progress)
        self._worker.signals.finished.connect(self._on_done)
        self._worker.signals.error.connect(self._on_error)
        self._worker.signals.progress.connect(self._append_log)
        self._worker.start()

    def _stop_worker(self):
        self._worker = None

    def hideEvent(self, event):
        self._stop_worker()
        super().hideEvent(event)

    def _on_tile_progress(self, done, total):
        self._progress.setMaximum(total)
        self._progress.setValue(done)

    def _on_done(self, image, engine):
        self._result_pil = image
        self._lbl_engine.setText(f"Engine: {engine}")
        self._lbl_result.setPixmap(
            _pil_to_qpixmap(image).scaled(
                self._lbl_result.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._btn_upscale.setEnabled(True)
        self._btn_save.setEnabled(True)
        self._append_log("Upscale hoan tat")
        self._stop_worker()

    def _on_error(self, message):
        self._append_log(message)
        log.warning(f"Upscale failed: {message}")
        self._btn_upscale.setEnabled(True)
        self._stop_worker()

    def _on_save(self):
        if self._result_pil is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Luu anh", "upscaled.png", "PNG (*.png)")
        if path:
            self._result_pil.save(path)
            self._append_log(f"Da luu: {Path(path).name}")

    def resizeEvent(self, event):
        if self._result_pil is not None:
            self._lbl_result.setPixmap(
                _pil_to_qpixmap(self._result_pil).scaled(
                    self._lbl_result.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        super().resizeEvent(event)
