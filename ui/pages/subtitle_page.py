"""NAV TOOLS - Subtitle Generator page.

Upload video -> Whisper AI transcribes audio -> generate SRT subtitle file.
Fully offline, free.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.coming_soon_banner import ComingSoonBanner
from ui.widgets.page_styles import LEFT_PANEL_WIDTH, PROGRESS_HEIGHT, PROGRESS_STYLE
from utils.logger import log


def _find_ffmpeg():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _format_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _segments_to_srt(segments):
    lines = []
    for idx, seg in enumerate(segments or [], 1):
        lines.append(
            f"{idx}\n{_format_timestamp(float(seg.get('start', 0)))} --> "
            f"{_format_timestamp(float(seg.get('end', 0)))}\n{seg.get('text', '').strip()}\n"
        )
    return "\n".join(lines)


WHISPER_MODEL_SIZES = {
    "tiny": 75,
    "base": 142,
    "small": 466,
    "medium": 1465,
    "large": 2950,
}


def _whisper_model_exists(model_size):
    return model_size in WHISPER_MODEL_SIZES


class _SubtitleSignals(QObject):
    finished = Signal(str, list)
    progress = Signal(str)
    error = Signal(str)


class _SubtitleWorker(QThread):
    """Extract audio -> Whisper transcribe -> SRT."""

    def __init__(self, video_path, model_size, language, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.model_size = model_size
        self.language = language
        self.signals = _SubtitleSignals()

    def run(self):
        tmp_audio = None
        try:
            if not Path(self.video_path).is_file():
                self.signals.error.emit(f"Video khong ton tai: {self.video_path}")
                return
            self.signals.progress.emit("Dang trich xuat audio tu video...")
            ffmpeg = _find_ffmpeg()
            if not ffmpeg:
                self.signals.error.emit("Khong tim thay ffmpeg!\nCai: pip install imageio-ffmpeg")
                return
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                tmp_audio = tf.name
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(self.video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                tmp_audio,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                self.signals.error.emit(f"ffmpeg error:\n{result.stderr}")
                return
            if not _whisper_model_exists(self.model_size):
                self.signals.error.emit(f"Model Whisper khong hop le: {self.model_size}")
                return
            size_mb = WHISPER_MODEL_SIZES.get(self.model_size, "?")
            self.signals.progress.emit(
                f"Dang tai Whisper model '{self.model_size}' (~{size_mb}MB)...\nLan dau se mat vai phut."
            )
            import whisper

            model = whisper.load_model(self.model_size)
            self.signals.progress.emit(f"Dang nhan dang giong noi (Whisper {self.model_size})...")
            result = model.transcribe(tmp_audio, language=None if self.language == "auto" else self.language, verbose=False)
            segments = result.get("segments", [])
            if not segments:
                self.signals.error.emit("Khong nhan dang duoc giong noi trong video")
                return
            srt = _segments_to_srt(segments)
            log.info(f"Whisper OK: {len(segments)} segments, lang={result.get('language')}")
            self.signals.finished.emit(srt, segments)
        except Exception as e:
            log.warning(f"Subtitle error: {e}")
            self.signals.error.emit(str(e))
        finally:
            if tmp_audio:
                Path(tmp_audio).unlink(missing_ok=True)


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


class SubtitlePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_path = None
        self._worker = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left.setFixedWidth(LEFT_PANEL_WIDTH)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(12)

        title = QLabel("Subtitle Generator")
        title.setProperty("class", "section-title")
        desc = QLabel("Tai video len, Whisper se trich xuat audio va tao file SRT.")
        desc.setStyleSheet("color: #8c909f; font-size: 12px;")
        desc.setWordWrap(True)
        ll.addWidget(title)
        ll.addWidget(desc)
        ll.addWidget(ComingSoonBanner("Nhan dang offline bang Whisper, xuat SRT de chinh sua"))

        self._btn_choose = QPushButton("Chon video")
        self._btn_choose.setStyleSheet(BTN_STYLE)
        self._btn_choose.clicked.connect(self._on_choose)
        ll.addWidget(self._btn_choose)

        self._lbl_video = QLabel("Chua chon video")
        self._lbl_video.setWordWrap(True)
        ll.addWidget(self._lbl_video)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model"))
        self._cmb_model = QComboBox()
        self._cmb_model.addItems(list(WHISPER_MODEL_SIZES.keys()))
        self._cmb_model.setCurrentText("small")
        model_row.addWidget(self._cmb_model, 1)
        ll.addLayout(model_row)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Ngon ngu"))
        self._cmb_lang = QComboBox()
        self._cmb_lang.addItem("Tu dong", "auto")
        self._cmb_lang.addItem("Vietnamese", "vi")
        self._cmb_lang.addItem("English", "en")
        lang_row.addWidget(self._cmb_lang, 1)
        ll.addLayout(lang_row)

        self._btn_generate = QPushButton("Tao phu de")
        self._btn_generate.setStyleSheet(BTN_STYLE)
        self._btn_generate.clicked.connect(self._on_generate)
        self._btn_save = QPushButton("Luu file SRT")
        self._btn_save.setStyleSheet(BTN_STYLE)
        self._btn_save.clicked.connect(self._on_save)
        ll.addWidget(self._btn_generate)
        ll.addWidget(self._btn_save)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(PROGRESS_HEIGHT)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(PROGRESS_STYLE)
        self._progress.setVisible(False)
        self._lbl_status = QLabel("San sang")
        self._lbl_status.setStyleSheet("color: #8c909f; font-size: 12px;")
        ll.addWidget(self._progress)
        ll.addWidget(self._lbl_status)
        ll.addStretch(1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 16)
        rl.setSpacing(12)
        rl.addWidget(QLabel("Noi dung SRT"))
        self._txt_result = QTextEdit()
        rl.addWidget(self._txt_result, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

    def _on_choose(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chon video",
            str(Path.home() / "Videos"),
            "Video (*.mp4 *.mkv *.mov *.avi *.webm)",
        )
        if path:
            self._video_path = path
            self._lbl_video.setText(Path(path).name)
            self._lbl_video.setStyleSheet("color: #4caf50; font-size: 12px;")

    def _on_generate(self):
        if not self._video_path:
            return
        lang = self._cmb_lang.currentData()
        model_size = self._cmb_model.currentText()
        self._btn_generate.setEnabled(False)
        self._btn_choose.setEnabled(False)
        self._progress.setVisible(True)
        self._stop_worker()
        self._worker = _SubtitleWorker(self._video_path, model_size, lang, parent=self)
        self._worker.signals.progress.connect(self._lbl_status.setText)
        self._worker.signals.finished.connect(self._on_done)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _stop_worker(self):
        self._worker = None

    def hideEvent(self, event):
        self._stop_worker()
        super().hideEvent(event)

    def _on_done(self, srt, segments):
        self._progress.setVisible(False)
        self._btn_generate.setEnabled(True)
        self._btn_choose.setEnabled(True)
        self._txt_result.setPlainText(srt)
        self._lbl_status.setText(f"Hoan tat: {len(segments)} segments")
        self._lbl_status.setStyleSheet("color: #22c55e; font-size: 12px;")
        self._worker = None

    def _on_error(self, msg):
        self._progress.setVisible(False)
        self._btn_generate.setEnabled(True)
        self._btn_choose.setEnabled(True)
        self._txt_result.setPlainText(f"Loi: {msg}")
        self._lbl_status.setText("That bai")
        self._lbl_status.setStyleSheet("color: #ef4444; font-size: 12px;")
        self._worker = None

    def _on_save(self):
        srt = self._txt_result.toPlainText()
        if not srt:
            return
        src = Path(self._video_path)
        default = str(src.parent / f"{src.stem}.srt")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Luu file phu de",
            default,
            "SRT (*.srt);;Text (*.txt)",
        )
        if path:
            if not Path(path).suffix:
                path += ".srt"
            Path(path).write_text(srt, encoding="utf-8")
            log.info(f"Saved subtitle: {path}")
            self._lbl_status.setText(f"Da luu: {Path(path).name}")
