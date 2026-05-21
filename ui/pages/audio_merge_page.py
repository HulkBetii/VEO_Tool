"""NAV TOOLS - Audio Merge page.

Select video + audio file -> merge with ffmpeg -> save.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.coming_soon_banner import ComingSoonBanner
from ui.widgets.page_styles import PROGRESS_HEIGHT, PROGRESS_STYLE
from utils.logger import log


def _find_ffmpeg():
    """Find ffmpeg binary."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _find_ffprobe(ffmpeg):
    path = shutil.which("ffprobe")
    if path:
        return path
    if ffmpeg:
        candidate = Path(ffmpeg).parent / "ffprobe.exe"
        if candidate.exists():
            return str(candidate)
    return None


def _has_audio_track(video_path, ffmpeg):
    ffprobe = _find_ffprobe(ffmpeg)
    if not ffprobe:
        return False
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


class _MergeSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


class _MergeWorker(QThread):
    """Merge video + audio with ffmpeg."""

    def __init__(self, video_path, audio_path, output_path, replace_audio=False, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.audio_path = audio_path
        self.output_path = output_path
        self.replace_audio = replace_audio
        self.signals = _MergeSignals()

    def run(self):
        try:
            if not Path(self.video_path).is_file():
                self.signals.error.emit(f"Video khong ton tai: {self.video_path}")
                return
            if not Path(self.audio_path).is_file():
                self.signals.error.emit(f"Audio khong ton tai: {self.audio_path}")
                return
            ffmpeg = _find_ffmpeg()
            if not ffmpeg:
                self.signals.error.emit(
                    "Khong tim thay ffmpeg!\nCai dat: pip install imageio-ffmpeg\nHoac tai ffmpeg.org roi them vao PATH"
                )
                return
            effective_mode = self.replace_audio
            if not effective_mode and not _has_audio_track(self.video_path, ffmpeg):
                log.warning("Video has no audio track, falling back to replace mode")
                effective_mode = True
            cmd = [ffmpeg, "-y", "-i", str(self.video_path), "-i", str(self.audio_path)]
            if effective_mode:
                cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0"])
            else:
                cmd.extend(
                    ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "0:a?", "-map", "1:a:0"]
                )
            cmd.append(str(self.output_path))
            log.info(" ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.signals.finished.emit(str(self.output_path))
                return
            err = result.stderr.strip() or "Merge failed"
            self.signals.error.emit(err)
        except Exception as e:
            self.signals.error.emit(str(e))


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


class AudioMergePage(QWidget):
    """Page: select video + audio -> merge -> save."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_path = None
        self._audio_path = None
        self._worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        title = QLabel("Audio Merge")
        title.setProperty("class", "section-title")
        desc = QLabel("Chon video va audio roi ghep lai bang ffmpeg.")
        desc.setStyleSheet("color: #8c909f; font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(ComingSoonBanner("Ghep audio vao video giu nguyen hinh anh goc"))

        self._lbl_ffmpeg = QLabel()
        ffmpeg = _find_ffmpeg()
        self._lbl_ffmpeg.setText(f"ffmpeg: {ffmpeg or 'khong tim thay'}")
        self._lbl_ffmpeg.setStyleSheet("color: #8c909f; font-size: 12px;")
        layout.addWidget(self._lbl_ffmpeg)

        video_row = QHBoxLayout()
        self._btn_video = QPushButton("Chon video")
        self._btn_video.setStyleSheet(BTN_STYLE)
        self._btn_video.clicked.connect(self._on_choose_video)
        self._lbl_video = QLabel("Chua chon video")
        self._lbl_video.setWordWrap(True)
        video_row.addWidget(self._btn_video)
        video_row.addWidget(self._lbl_video, 1)
        layout.addLayout(video_row)

        audio_row = QHBoxLayout()
        self._btn_audio = QPushButton("Chon audio")
        self._btn_audio.setStyleSheet(BTN_STYLE)
        self._btn_audio.clicked.connect(self._on_choose_audio)
        self._lbl_audio = QLabel("Chua chon audio")
        self._lbl_audio.setWordWrap(True)
        audio_row.addWidget(self._btn_audio)
        audio_row.addWidget(self._lbl_audio, 1)
        layout.addLayout(audio_row)

        self._chk_replace = QCheckBox("Thay audio hien co")
        self._chk_replace.setChecked(True)
        layout.addWidget(self._chk_replace)

        self._btn_merge = QPushButton("Bat dau ghep audio")
        self._btn_merge.setStyleSheet(BTN_STYLE)
        self._btn_merge.setEnabled(False)
        self._btn_merge.setToolTip("Chon video va audio truoc khi ghep")
        self._btn_merge.clicked.connect(self._on_merge)
        layout.addWidget(self._btn_merge)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(PROGRESS_HEIGHT)
        self._progress.setTextVisible(False)
        self._progress.setFormat("")
        self._progress.setStyleSheet(PROGRESS_STYLE)
        self._progress.setVisible(False)
        self._lbl_status = QLabel("San sang")
        self._lbl_status.setStyleSheet("color: #8c909f; font-size: 13px;")
        layout.addWidget(self._progress)
        layout.addWidget(self._lbl_status)
        layout.addStretch(1)

    def _check_ready(self):
        ready = bool(self._video_path and self._audio_path)
        self._btn_merge.setEnabled(ready)

    def _on_choose_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chon video",
            str(Path.home() / "Videos"),
            "Video (*.mp4 *.avi *.mov *.mkv *.webm)",
        )
        if path:
            self._video_path = path
            self._lbl_video.setText(Path(path).name)
            self._lbl_video.setStyleSheet("color: #4caf50; font-size: 12px;")
            self._check_ready()

    def _on_choose_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chon audio",
            str(Path.home() / "Music"),
            "Audio (*.mp3 *.wav *.aac *.m4a *.ogg *.flac)",
        )
        if path:
            self._audio_path = path
            self._lbl_audio.setText(Path(path).name)
            self._lbl_audio.setStyleSheet("color: #4caf50; font-size: 12px;")
            self._check_ready()

    def _on_merge(self):
        if not self._video_path or not self._audio_path:
            return
        src = Path(self._video_path)
        default = str(src.parent / f"{src.stem}_audio{src.suffix}")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Luu video",
            default,
            "MP4 (*.mp4);;AVI (*.avi);;MKV (*.mkv)",
        )
        if not path:
            return
        self._btn_merge.setEnabled(False)
        self._progress.setVisible(True)
        self._lbl_status.setText("Dang ghep audio...")
        self._lbl_status.setStyleSheet("color: #8c909f; font-size: 13px;")
        self._stop_worker()
        self._worker = _MergeWorker(
            self._video_path,
            self._audio_path,
            path,
            replace_audio=self._chk_replace.isChecked(),
            parent=self,
        )
        self._worker.signals.finished.connect(self._on_done)
        self._worker.signals.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_done(self, output_path):
        self._progress.setVisible(False)
        self._lbl_status.setText(f"Da luu: {Path(output_path).name}")
        self._lbl_status.setStyleSheet("color: #22c55e; font-size: 13px;")
        self._btn_merge.setEnabled(True)
        self._worker = None

    def _on_error(self, message):
        self._progress.setVisible(False)
        self._lbl_status.setText(f"Loi: {message}")
        self._lbl_status.setStyleSheet("color: #ef4444; font-size: 13px;")
        self._check_ready()
        self._worker = None

    def _stop_worker(self):
        self._worker = None

    def hideEvent(self, event):
        self._stop_worker()
        super().hideEvent(event)
