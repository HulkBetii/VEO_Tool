"""Video preview dialog."""

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QSlider, QVBoxLayout


class VideoPreviewDialog(QDialog):
    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        layout = QVBoxLayout(self)
        self.video = QVideoWidget()
        self.player = QMediaPlayer(self)
        self.player.setVideoOutput(self.video)
        self.slider = QSlider()
        controls = QHBoxLayout()
        play = QPushButton("Play")
        restart = QPushButton("Restart")
        play.clicked.connect(self._toggle_play)
        restart.clicked.connect(self._restart)
        controls.addWidget(play)
        controls.addWidget(restart)
        layout.addWidget(self.video)
        layout.addWidget(self.slider)
        layout.addLayout(controls)
        self.player.setSource(QUrl.fromLocalFile(video_path))

    def _fmt_time(self, ms):
        s = int(ms / 1000)
        return f"{s // 60:02d}:{s % 60:02d}"

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _restart(self):
        self.player.setPosition(0)
        self.player.play()

    def _on_slider_moved(self, value):
        self.player.setPosition(value)

    def _on_position_changed(self, value):
        self.slider.setValue(value)

    def _on_duration_changed(self, value):
        self.slider.setMaximum(value)

    def _on_status_changed(self, status):
        return None

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)
