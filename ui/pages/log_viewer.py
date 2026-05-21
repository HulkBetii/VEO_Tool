"""VidGen AI - Log viewer page."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.constants import LOG_DIR
from utils.platform import open_folder


class LogViewerPage(QWidget):
    """Full-width log viewer page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_log_path = None
        self._init_ui()
        self._load_log_files()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Application Logs")
        title.setProperty("class", "section-title")
        header.addWidget(title)

        self.dir_label = QLabel(f"Log Directory: {LOG_DIR}")
        self.dir_label.setStyleSheet("color: #8c909f; font-size: 11px;")
        header.addWidget(self.dir_label)
        header.addStretch(1)

        open_folder_btn = QPushButton("Open Folder")
        open_folder_btn.setObjectName("btn-secondary")
        open_folder_btn.clicked.connect(self._open_folder)
        header.addWidget(open_folder_btn)
        layout.addLayout(header)

        body = QHBoxLayout()

        file_col = QVBoxLayout()
        file_col.addWidget(QLabel("Log Files:"))
        self.file_list = QListWidget()
        self.file_list.setFixedWidth(220)
        self.file_list.currentItemChanged.connect(self._on_file_selected)
        file_col.addWidget(self.file_list, 1)

        content_col = QVBoxLayout()
        content_col.addWidget(QLabel("Log Content:"))

        toolbar = QHBoxLayout()
        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("btn-ghost")
        copy_btn.clicked.connect(self._copy_content)
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("btn-ghost")
        clear_btn.clicked.connect(self._clear_log)
        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("btn-danger")
        delete_btn.clicked.connect(self._delete_log)
        export_btn = QPushButton("Export Logs to Desktop")
        export_btn.setObjectName("btn-primary")
        export_btn.clicked.connect(self._export_logs)
        toolbar.addWidget(copy_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(delete_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(export_btn)
        content_col.addLayout(toolbar)

        self.log_viewer = QTextEdit()
        self.log_viewer.setObjectName("logViewer")
        self.log_viewer.setReadOnly(True)
        content_col.addWidget(self.log_viewer, 1)

        body.addLayout(file_col)
        body.addLayout(content_col, 1)
        layout.addLayout(body, 1)

    def _load_log_files(self):
        self.file_list.clear()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(LOG_DIR.glob("vidgen_*.log"), reverse=True)
        for f in files:
            size = f.stat().st_size
            label = f"{f.name} ({size // 1024} KB)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self.file_list.addItem(item)
        if files:
            self.file_list.setCurrentRow(0)

    def _on_file_selected(self, current, previous=None):
        if current is None:
            self._current_log_path = None
            self.log_viewer.clear()
            return
        self._current_log_path = Path(current.data(Qt.ItemDataRole.UserRole))
        self._load_log_content()

    def _load_log_content(self):
        if not self._current_log_path or not self._current_log_path.exists():
            self.log_viewer.clear()
            return
        text = self._current_log_path.read_text(encoding="utf-8", errors="ignore")
        self.log_viewer.setPlainText(self._colorize_log(text))

    def showEvent(self, event):
        self._refresh_timer.start(2000)
        self.refresh()
        super().showEvent(event)

    def hideEvent(self, event):
        self._refresh_timer.stop()
        super().hideEvent(event)

    def _auto_refresh(self):
        self._load_log_content()

    def _colorize_log(self, text):
        return text

    def _copy_content(self):
        text = self.log_viewer.toPlainText()
        QApplication.clipboard().setText(text)

    def _clear_log(self):
        if self._current_log_path and self._current_log_path.exists():
            self._current_log_path.write_text("", encoding="utf-8")
            self._load_log_content()

    def _delete_log(self):
        if self._current_log_path and self._current_log_path.exists():
            self._current_log_path.unlink()
            self._current_log_path = None
            self.refresh()

    def _open_folder(self):
        open_folder(str(LOG_DIR))

    def _export_logs(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Logs",
            str(Path.home() / "Desktop" / "vidgen_logs.txt"),
            "Text files (*.txt)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as out:
            for f in sorted(LOG_DIR.glob("vidgen_*.log")):
                out.write(f"=== {f.name} ===\n")
                with open(f, "r", encoding="utf-8") as inp:
                    out.write(inp.read())
                out.write("\n\n")

    def refresh(self):
        self._load_log_files()


LogViewer = LogViewerPage
