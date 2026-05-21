"""NAV TOOLS - Bottom action bar (big buttons, part of scroll)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget


class ActionBar(QWidget):
    """Action bar with large, clearly visible buttons."""

    start_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    save_clicked = Signal()
    retry_all_clicked = Signal()
    concat_clicked = Signal()
    new_task_clicked = Signal()
    resume_clicked = Signal()

    def __init__(self, mode: str = "video_plain", parent=None):
        super().__init__(parent)
        self._mode = mode
        self.setObjectName("actionBar")
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 6)
        outer.setSpacing(6)

        is_video = self._mode in ("char_video", "video_plain", "video_ref", "frame_video")
        unit = "video" if is_video else "ảnh"

        self.start_btn = self._btn("▶  Bắt đầu tạo", "action-start", height=40, font_size=13, bold=True)
        self.start_btn.setToolTip(
            f"Bắt đầu tạo {unit} từ tất cả prompt trong bảng.\n"
            "Chia đều task lên các account đang bật."
        )
        self.start_btn.clicked.connect(self.start_clicked.emit)
        outer.addWidget(self.start_btn)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.pause_btn = self._btn("⏸  Tạm dừng", "action-pause", height=32)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setToolTip(
            "Tạm dừng worker - task đang chạy sẽ chạy nốt rồi nghỉ.\n"
            "Bấm 'Chạy tiếp' để chạy phần còn lại từ chỗ dừng."
        )
        self.pause_btn.clicked.connect(self.pause_clicked.emit)
        row2.addWidget(self.pause_btn, 1)

        self.stop_btn = self._btn("⏹  Dừng hẳn", "action-stop", height=32)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip(
            "Hủy toàn bộ task đang chạy NGAY LẬP TỨC.\n"
            "Các task đang gen sẽ bị bỏ dở (mất credit nếu Veo đã trừ)."
        )
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        row2.addWidget(self.stop_btn, 1)
        outer.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(6)
        self.new_task_btn = self._btn("🔄  Tạo task mới", "action-save", height=32)
        self.new_task_btn.setToolTip(
            "Xóa hết kết quả hiện tại + tạo task mới với prompt vừa nhập.\n"
            "Lịch sử task cũ vẫn nằm trong tab Tasks."
        )
        self.new_task_btn.clicked.connect(self.new_task_clicked.emit)
        self.new_task_btn.clicked.connect(self.save_clicked.emit)
        row3.addWidget(self.new_task_btn, 1)

        self.resume_btn = self._btn("▶  Chạy tiếp", "action-resume", height=32)
        self.resume_btn.setEnabled(False)
        self.resume_btn.setToolTip(
            "Chạy tiếp các task chưa hoàn tất từ lần trước.\n"
            "Pending/Error -> đưa lại vào queue. Đã Done -> bỏ qua."
        )
        self.resume_btn.clicked.connect(self.resume_clicked.emit)
        row3.addWidget(self.resume_btn, 1)
        outer.addLayout(row3)

        row4 = QHBoxLayout()
        row4.setSpacing(6)
        self.retry_btn = self._btn("🔄  Làm lại lỗi", "action-retry", height=32)
        self.retry_btn.setToolTip(
            f"Tạo lại các {unit} bị lỗi (Error / Failed).\n"
            f"Các {unit} đã tạo thành công vẫn giữ nguyên, không bị tạo lại."
        )
        self.retry_btn.clicked.connect(self.retry_all_clicked.emit)
        row4.addWidget(self.retry_btn, 1)

        self.concat_btn = self._btn("✂  Ghép Video", "action-concat", height=32)
        self.concat_btn.setToolTip(
            "Ghép tất cả video đã tạo xong thành 1 file MP4 duy nhất.\n"
            "Theo thứ tự cột # trong bảng. Có thể re-encode để mượt nối."
        )
        self.concat_btn.clicked.connect(self.concat_clicked.emit)
        row4.addWidget(self.concat_btn, 1)
        outer.addLayout(row4)

    def _btn(
        self,
        text: str,
        obj_name: str,
        height: int = 32,
        font_size: int = 11,
        bold: bool = False,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(obj_name)
        btn.setFixedHeight(height)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        font = QFont("Segoe UI", font_size)
        font.setBold(bold)
        btn.setFont(font)
        return btn

    def set_running_state(self):
        self.start_btn.setText("⏳  Đang chạy...")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)

    def set_idle_state(self):
        self.start_btn.setText("▶   Bắt đầu tạo")
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

    def set_paused_state(self):
        self.start_btn.setText("▶   Chạy tiếp")
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def set_resume_enabled(self, enabled: bool):
        self.resume_btn.setEnabled(enabled)

    @property
    def retry_clicked(self):
        return self.retry_all_clicked
