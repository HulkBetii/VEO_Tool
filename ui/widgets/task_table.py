"""VidGen AI - Task table widget for displaying prompt results."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.constants import ItemStatus


class PromptDetailDialog(QDialog):
    """Dialog showing full prompt text with copy button."""

    def __init__(self, prompt, parent=None):
        super().__init__(parent)
        self._prompt = prompt
        self.setWindowTitle("Chi tiết Prompt")
        self.setFixedSize(520, 360)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Nội dung Prompt")
        title.setProperty("class", "field-label")
        layout.addWidget(title)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(self._prompt)
        layout.addWidget(self.text_edit, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.copy_btn = QPushButton("📋  Copy")
        self.copy_btn.setObjectName("btn-primary")
        self.copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(self.copy_btn)

        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("btn-ghost")
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_copy(self):
        QApplication.clipboard().setText(self._prompt)
        self.copy_btn.setText("✓  Đã copy!")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("📋  Copy"))


class PromptCellWidget(QWidget):
    def __init__(self, prompt, parent=None):
        super().__init__(parent)
        self._prompt = prompt
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        self.label = QLabel(self._prompt)
        self.label.setStyleSheet("color: #dae2fd; background: transparent; padding: 0;")
        self.label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.label.setToolTip("Click để xem chi tiết")
        self.label.mousePressEvent = self._on_label_click
        layout.addWidget(self.label, 1)

        copy_btn = QPushButton("📋")
        copy_btn.setFixedSize(26, 26)
        copy_btn.setToolTip("Copy prompt")
        copy_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #2d3449; border-radius: 4px; font-size: 13px; padding: 0; }"
            "QPushButton:hover { background: #222a3d; border-color: #4d8eff; }"
        )
        copy_btn.clicked.connect(self._on_copy)
        layout.addWidget(copy_btn)

    def _on_label_click(self, event):
        PromptDetailDialog(self._prompt, self).exec()

    def _on_copy(self):
        QApplication.clipboard().setText(self._prompt)

    def set_prompt(self, prompt: str):
        self._prompt = prompt
        self.label.setText(prompt)


class ThumbnailCellWidget(QWidget):
    retry_clicked = Signal()

    def __init__(self, output_path="", thumbnail_path="", item_id=0, parent=None):
        super().__init__(parent)
        self.output_path = output_path
        self.thumbnail_path = thumbnail_path
        self.item_id = item_id
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.label = QLabel(Path(self.output_path or self.thumbnail_path or "").name)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #dae2fd; background: transparent;")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.open_btn = QPushButton("Mở")
        self.open_btn.setFixedHeight(24)
        self.open_btn.clicked.connect(self._open_target)
        layout.addWidget(self.open_btn)

    def _open_target(self):
        target = self.output_path or self.thumbnail_path
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        else:
            self.retry_clicked.emit()

    def update_output(self, output_path):
        self.output_path = output_path
        self.label.setText(Path(output_path).name if output_path else "")


class ActionCellWidget(QWidget):
    retry_requested = Signal()

    def __init__(self, output_path="", parent=None):
        super().__init__(parent)
        self.output_path = output_path
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        retry = QPushButton("Retry")
        retry.clicked.connect(self.retry_requested.emit)
        layout.addWidget(retry)

    def update_output(self, output_path):
        self.output_path = output_path


class TaskTable(QWidget):
    """Right panel - task table showing prompts, thumbnails, status."""

    item_retry = Signal(int)
    item_open_file = Signal(int)

    def __init__(self, mode: str = "video_plain", parent=None):
        super().__init__(parent)
        self._mode = mode
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        self.task_header = QLabel("Chế độ tạo mới")
        self.task_header.setProperty("class", "field-label")
        header_row.addWidget(self.task_header)
        header_row.addStretch()

        self.count_badge = QLabel("0 prompts")
        self.count_badge.setStyleSheet(
            "color: #64748b; font-size: 11px; padding: 2px 8px; background: #1e293b; border-radius: 8px;"
        )
        header_row.addWidget(self.count_badge)
        layout.addLayout(header_row)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            """
            QTableWidget { background: transparent; border: none; }
            QTableWidget::item { padding: 4px 6px; border-bottom: 1px solid #222a3d; }
            QHeaderView::section {
                background: #131b2e;
                color: #8c909f;
                font-weight: 600;
                font-size: 11px;
                padding: 4px 6px;
                border: none;
                border-bottom: 1px solid #424754;
            }
        """
        )
        layout.addWidget(self.table, 1)
        self._setup_columns()

    def _setup_columns(self):
        if self._mode in ("image", "char_image"):
            cols = ["#", "Prompt", "Tham khảo", "Ảnh kết quả", "Trạng thái"]
        elif self._mode in ("video_ref",):
            cols = ["#", "Preview", "Filename", "Prompt", "Trạng thái"]
        elif self._mode in ("frame_video",):
            cols = ["#", "Start", "→", "End", "Prompt", "Trạng thái"]
        else:
            cols = ["#", "Prompt", "Video", "Trạng thái"]

        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.resizeSection(0, 36)

        prompt_col = 1 if self._mode not in ("video_ref", "frame_video") else 3
        if self._mode == "frame_video":
            prompt_col = 4
        header.setSectionResizeMode(prompt_col, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(len(cols) - 1, 120)

        if self._mode in ("image", "char_image"):
            header.resizeSection(2, 140)
            header.resizeSection(3, 120)
        elif self._mode == "video_ref":
            header.resizeSection(1, 110)
            header.resizeSection(2, 180)
        elif self._mode == "frame_video":
            header.resizeSection(1, 140)
            header.resizeSection(2, 28)
            header.resizeSection(3, 140)
        else:
            header.resizeSection(2, 120)

    def set_items(self, items: list):
        self.table.setRowCount(len(items))
        self.table.verticalHeader().setDefaultSectionSize(62)
        self.count_badge.setText(f"{len(items)} prompts")

        for row, item in enumerate(items):
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, num_item)

            status_col = self.table.columnCount() - 1

            if self._mode == "video_ref":
                thumb = ThumbnailCellWidget(item.output_path, item.thumbnail_path, item.id)
                thumb.retry_clicked.connect(lambda _=False, value=item.id: self.item_retry.emit(value))
                self.table.setCellWidget(row, 1, thumb)
                self.table.setItem(row, 2, QTableWidgetItem(item.reference_image or ""))
                self.table.setCellWidget(row, 3, PromptCellWidget(item.prompt))
                self._set_status(row, status_col, item.status)
                continue

            if self._mode == "frame_video":
                self.table.setItem(row, 1, QTableWidgetItem(item.start_frame or ""))
                arrow_item = QTableWidgetItem("→")
                arrow_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 2, arrow_item)
                self.table.setItem(row, 3, QTableWidgetItem(item.end_frame or ""))
                self.table.setCellWidget(row, 4, PromptCellWidget(item.prompt))
                self._set_status(row, status_col, item.status)
                continue

            if self._mode in ("image", "char_image"):
                self.table.setCellWidget(row, 1, PromptCellWidget(item.prompt))
                self.table.setItem(row, 2, QTableWidgetItem(item.reference_image or ""))
                thumb = ThumbnailCellWidget(item.output_path, item.thumbnail_path, item.id)
                thumb.retry_clicked.connect(lambda _=False, value=item.id: self.item_retry.emit(value))
                self.table.setCellWidget(row, 3, thumb)
                self._set_status(row, status_col, item.status)
                continue

            self.table.setCellWidget(row, 1, PromptCellWidget(item.prompt))
            thumb = ThumbnailCellWidget(item.output_path, item.thumbnail_path, item.id)
            thumb.retry_clicked.connect(lambda _=False, value=item.id: self.item_retry.emit(value))
            self.table.setCellWidget(row, 2, thumb)
            self._set_status(row, status_col, item.status)

    def _set_status(self, row: int, col: int, status: str):
        status_labels = {
            ItemStatus.PENDING: ("Đang chờ", "#94a3b8"),
            ItemStatus.UPLOADING: ("Đang tải lên", "#4d8eff"),
            ItemStatus.GENERATING: ("Đang tạo", "#4d8eff"),
            ItemStatus.DOWNLOADING: ("Đang tải", "#4d8eff"),
            ItemStatus.COMPLETED: ("Hoàn thành", "#22c55e"),
            ItemStatus.ERROR: ("Lỗi", "#ef4444"),
        }
        text, color = status_labels.get(status, ("?", "#94a3b8"))
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(color))
        self.table.setItem(row, col, item)

    def clear(self):
        self.table.setRowCount(0)
        self.count_badge.setText("0 prompts")
        self.task_header.setText("Chế độ tạo mới")

    def update_item_status(self, row: int, status: str):
        col = self.table.columnCount() - 1
        self._set_status(row, col, status)

    def update_item_output(self, row: int, output_path: str):
        if self._mode in ("image", "char_image"):
            thumb_col = 3
        elif self._mode == "video_ref":
            thumb_col = 1
        else:
            thumb_col = 2
        widget = self.table.cellWidget(row, thumb_col)
        if isinstance(widget, ThumbnailCellWidget):
            widget.update_output(output_path)

    def update_item_error(self, row: int, error_msg: str):
        col = self.table.columnCount() - 1
        error_labels = {
            "RESOURCE_EXHAUSTED": "Hết quota",
            "USER_QUOTA_REACHED": "Hết quota",
            "PERMISSION_DENIED": "Không có quyền",
            "MODEL_ACCESS_DENIED": "Model bị chặn",
            "INVALID_ARGUMENT": "Google API lỗi - thử lại sau",
            "Media not found": "Media không tìm thấy",
            "RECAPTCHA": "Lỗi reCAPTCHA",
            "Session hết hạn": "Session hết hạn",
            "không an toàn": "Prompt vi phạm chính sách",
            "bị chặn": "Prompt bị chặn",
            "Hết quota tạo ảnh": "Hết quota ảnh",
            "Hết quota tạo video": "Hết quota video",
            "HTTP 400": "Google API lỗi (400)",
            "HTTP 403": "Bị từ chối (403)",
            "HTTP 429": "Quá tải - thử lại sau",
            "HTTP 500": "Google server lỗi (500)",
            "Download failed": "Tải thất bại",
            "Storyboard failed": "Lỗi tạo storyboard",
            "Image download failed": "Tải ảnh thất bại",
        }
        short_msg = "Lỗi"
        lowered = (error_msg or "").lower()
        for key, label in error_labels.items():
            if key.lower() in lowered:
                short_msg = label
                break

        display_msg = short_msg
        if short_msg != (error_msg or ""):
            if len(error_msg or "") < 120:
                display_msg = error_msg or short_msg
            else:
                display_msg = (error_msg or "")[:100] + "..."

        item = QTableWidgetItem(display_msg)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        item.setForeground(Qt.GlobalColor.red)
        item.setToolTip(error_msg or "")
        self.table.setItem(row, col, item)
