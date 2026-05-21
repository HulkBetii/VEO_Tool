"""NAV TOOLS - Long video extend-chain page."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.constants import ASPECT_RATIO_OPTIONS, DEFAULT_VIDEO_OUTPUT, QUALITY_OPTIONS, estimate_credits
from ui.widgets.image_grid import ImageGrid
from utils.file_utils import generate_task_name
from utils.logger import log


IMG_MODE_REFERENCE = "Anh tham chieu"
IMG_MODE_START_FRAME = "Anh mo dau"
IMG_MODE_NONE = "Khong dung anh"


class LongVideoWorker(QThread):
    chain_started = Signal(str)
    scene_started = Signal(int, int)
    scene_done = Signal(int, str)
    scene_failed = Signal(int, str)
    progress = Signal(str)
    all_done = Signal(str)
    error = Signal(str)

    def __init__(self, account_pool, prompts, output_dir, quality=None, aspect_ratio=None, start_image=None, parent=None):
        super().__init__(parent)
        self.account_pool = account_pool
        self.prompts = list(prompts or [])
        self.output_dir = Path(output_dir)
        self.quality = quality
        self.aspect_ratio = aspect_ratio
        self.start_image = start_image
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.chain_started.emit(str(self.output_dir))
            outputs = []
            for index, prompt in enumerate(self.prompts, 1):
                if self._cancelled:
                    self.progress.emit("Da dung")
                    return
                self.scene_started.emit(index, len(self.prompts))
                out = self.output_dir / f"scene_{index:03d}.txt"
                out.write_text(prompt, encoding="utf-8")
                outputs.append(str(out))
                self.scene_done.emit(index, str(out))
            final = self.output_dir / "long_video_outputs.txt"
            final.write_text("\n".join(outputs), encoding="utf-8")
            self.all_done.emit(str(final))
        except Exception as e:
            self.error.emit(str(e))


class _PromptRow(QFrame):
    delete_requested = Signal(object)
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)

    def __init__(self, index, text="", parent=None):
        super().__init__(parent)
        self.index = index
        self._text = text
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("QFrame { background: #131a2c; border: 1px solid #2d3449; border-radius: 8px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.index_label = QLabel(f"Cảnh {self.index}")
        self.index_label.setStyleSheet("color: #fbbf24; font-weight: 600; min-width: 56px;")
        layout.addWidget(self.index_label, 0, Qt.AlignmentFlag.AlignTop)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("color: #e5e7eb;")
        self.preview.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.preview.mousePressEvent = lambda event: self._open_editor()
        layout.addWidget(self.preview, 1)

        menu_btn = QPushButton("...")
        menu_btn.setFixedWidth(34)
        menu_btn.clicked.connect(self._open_menu)
        layout.addWidget(menu_btn, 0, Qt.AlignmentFlag.AlignTop)
        self._refresh()

    def _refresh(self):
        text = self._text.strip() or "Nhan de nhap prompt cho canh nay"
        short = text[:240] + ("..." if len(text) > 240 else "")
        self.preview.setText(short)

    def _open_editor(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Sua prompt - Canh {self.index}")
        dialog.setMinimumSize(620, 360)
        dlg_layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(self._text)
        dlg_layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)
        if dialog.exec():
            self.set_text(editor.toPlainText())

    def _open_menu(self):
        menu = QMenu(self)
        menu.addAction("Len tren", lambda: self.move_up_requested.emit(self))
        menu.addAction("Xuong duoi", lambda: self.move_down_requested.emit(self))
        menu.addAction("Copy", self._copy_text)
        menu.addAction("Xoa noi dung", lambda: self.set_text(""))
        menu.addAction("Xoa canh", lambda: self.delete_requested.emit(self))
        menu.exec(QCursor.pos())

    def _copy_text(self):
        QApplication.clipboard().setText(self.get_text())

    def set_index(self, index):
        self.index = index
        self.index_label.setText(f"Cảnh {index}")

    def get_text(self):
        return self._text

    def set_text(self, text):
        self._text = str(text or "")
        self._refresh()

    def set_read_only(self, value):
        self.setEnabled(not value)


class LongVideoPage(QWidget):
    DEFAULT_SCENES = 3
    MAX_SCENES = 20

    def __init__(self, db=None, browser_mgr=None, settings=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._browser_mgr = browser_mgr
        self._settings = settings
        self._account_pool = None
        self._worker = None
        self._prompt_rows = []
        self._start_image_path = None
        self._final_path = None
        self._init_ui()

    def _get_account_pool(self):
        return self._account_pool

    def _init_ui(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._scroll_inner = QWidget()
        left_scroll.setWidget(self._scroll_inner)
        left = QVBoxLayout(self._scroll_inner)
        left.setContentsMargins(16, 16, 16, 16)
        left.setSpacing(12)

        title = QLabel("Long Video")
        title.setProperty("class", "section-title")
        desc = QLabel("Tao chuoi video dai bang nhieu canh lien tiep, moi canh mot prompt.")
        desc.setStyleSheet("color: #8c909f; font-size: 12px;")
        desc.setWordWrap(True)
        left.addWidget(title)
        left.addWidget(desc)

        top_actions = QHBoxLayout()
        self._add_btn = QPushButton("+ Them canh")
        self._add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._add_btn.clicked.connect(self._on_add_scene)
        self._import_btn = QPushButton("Import")
        self._import_btn.setToolTip("Nap danh sach prompt tu file txt")
        self._import_btn.clicked.connect(self._on_import_from_file)
        top_actions.addWidget(self._add_btn)
        top_actions.addWidget(self._import_btn)
        left.addLayout(top_actions)

        self._scene_count_label = QLabel()
        self._scene_count_label.setStyleSheet("color: #8c909f; font-size: 12px;")
        left.addWidget(self._scene_count_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMinimumHeight(320)
        self._scroll.setStyleSheet("QScrollArea { border: 1px solid #2d3449; border-radius: 8px; }")
        rows_host = QWidget()
        self._rows_layout = QVBoxLayout(rows_host)
        self._rows_layout.setContentsMargins(10, 10, 10, 10)
        self._rows_layout.setSpacing(8)
        self._scroll.setWidget(rows_host)
        left.addWidget(self._scroll)

        quality_grid = QGridLayout()
        quality_grid.addWidget(QLabel("Chat luong"), 0, 0)
        self.quality_combo = QComboBox()
        for item in QUALITY_OPTIONS:
            self.quality_combo.addItem(str(item))
        quality_grid.addWidget(self.quality_combo, 0, 1)
        quality_grid.addWidget(QLabel("Ti le"), 1, 0)
        self.ar_combo = QComboBox()
        for item in ASPECT_RATIO_OPTIONS:
            self.ar_combo.addItem(str(item))
        quality_grid.addWidget(self.ar_combo, 1, 1)
        left.addLayout(quality_grid)

        self._credit_per_video_label = QLabel()
        self._credit_total_label = QLabel()
        self._credit_per_video_label.setStyleSheet("color: #8c909f; font-size: 12px;")
        self._credit_total_label.setStyleSheet("color: #8c909f; font-size: 12px;")
        left.addWidget(self._credit_per_video_label)
        left.addWidget(self._credit_total_label)
        self.quality_combo.currentTextChanged.connect(self._refresh_credit_labels)
        self.ar_combo.currentTextChanged.connect(self._refresh_credit_labels)

        left.addWidget(QLabel("Che do anh"))
        self.img_mode_combo = QComboBox()
        self.img_mode_combo.addItem(IMG_MODE_REFERENCE)
        self.img_mode_combo.addItem(IMG_MODE_START_FRAME)
        self.img_mode_combo.addItem(IMG_MODE_NONE)
        self.img_mode_combo.currentIndexChanged.connect(self._on_img_mode_changed)
        left.addWidget(self.img_mode_combo)

        self.ref_panel = QFrame()
        self.ref_panel.setFrameShape(QFrame.Shape.StyledPanel)
        ref_layout = QVBoxLayout(self.ref_panel)
        ref_layout.addWidget(QLabel("Anh tham chieu nhan vat"))
        self.image_grid = ImageGrid(show_dispatch_hint=False)
        self.image_grid.setFixedHeight(220)
        ref_layout.addWidget(self.image_grid)
        left.addWidget(self.ref_panel)

        self.start_panel = QFrame()
        self.start_panel.setFrameShape(QFrame.Shape.StyledPanel)
        sp = QVBoxLayout(self.start_panel)
        sp.addWidget(QLabel("Anh mo dau"))
        self.start_img_label = QLabel("Chua chon anh mo dau")
        self.start_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_img_label.setMinimumHeight(120)
        self.start_img_label.setStyleSheet("background: #1e2030; border: 1px solid #2d3449; border-radius: 8px;")
        sp.addWidget(self.start_img_label)
        sp_buttons = QHBoxLayout()
        self.pick_img_btn = QPushButton("Chon anh")
        self.pick_img_btn.clicked.connect(self._on_pick_start_image)
        self.clear_img_btn = QPushButton("Xoa")
        self.clear_img_btn.setFixedSize(52, 32)
        self.clear_img_btn.setEnabled(False)
        self.clear_img_btn.clicked.connect(self._on_clear_start_image)
        sp_buttons.addWidget(self.pick_img_btn)
        sp_buttons.addWidget(self.clear_img_btn)
        sp.addLayout(sp_buttons)
        left.addWidget(self.start_panel)

        out_row = QHBoxLayout()
        self.output_edit = QLineEdit(str(DEFAULT_VIDEO_OUTPUT))
        browse_out = QPushButton("Thu muc")
        browse_out.clicked.connect(self._on_browse_output)
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(browse_out)
        left.addLayout(out_row)

        action_row = QHBoxLayout()
        self.start_btn = QPushButton("Bat dau tao video")
        self.start_btn.clicked.connect(self._on_start)
        self.cancel_btn = QPushButton("Dung")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self._on_reset)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.cancel_btn)
        action_row.addWidget(self.reset_btn)
        left.addLayout(action_row)

        self.progress_label = QLabel("San sang")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        left.addWidget(self.progress_label)
        left.addWidget(self.progress_bar)
        left.addStretch(1)

        right = QVBoxLayout()
        right_host = QWidget()
        right_host.setLayout(right)
        right.setContentsMargins(16, 16, 16, 16)
        right.setSpacing(12)

        self.status_table = QTableWidget()
        self.status_table.setColumnCount(3)
        self.status_table.setHorizontalHeaderLabels(["Canh", "Trang thai", "Output"])
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setShowGrid(False)
        self.status_table.verticalHeader().setDefaultSectionSize(34)
        self.status_table.horizontalHeader().resizeSection(0, 80)
        self.status_table.horizontalHeader().resizeSection(1, 140)
        self.status_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        right.addWidget(self.status_table, 1)

        self.final_label = QLabel("Ket qua cuoi se hien thi tai day")
        self.final_label.setOpenExternalLinks(False)
        self.final_label.setWordWrap(True)
        right.addWidget(self.final_label)

        self.preview_btn = QPushButton("Mo thu muc output")
        self.preview_btn.clicked.connect(lambda: self._on_final_link(self._final_path) if self._final_path else None)
        right.addWidget(self.preview_btn, 0, Qt.AlignmentFlag.AlignLeft)

        main.addWidget(left_scroll, 0)
        main.addWidget(right_host, 1)

        for _ in range(self.DEFAULT_SCENES):
            self._add_row("")
        self.img_mode_combo.setCurrentIndex(0)
        self._on_img_mode_changed()
        self._refresh_scene_count()
        self._set_running_ui(False)

    def _label(self, text):
        return QLabel(str(text))

    def _add_row(self, text=""):
        row = _PromptRow(len(self._prompt_rows) + 1, text)
        row.delete_requested.connect(self._on_delete_row)
        row.move_up_requested.connect(self._move_row_up)
        row.move_down_requested.connect(self._move_row_down)
        self._prompt_rows.append(row)
        self._rows_layout.addWidget(row)
        self._refresh_scene_count()
        return row

    def _relayout_prompts(self):
        for idx, row in enumerate(self._prompt_rows, 1):
            row.set_index(idx)
        self._refresh_scene_count()

    def _move_row_up(self, row):
        index = self._prompt_rows.index(row)
        if index > 0:
            self._prompt_rows[index - 1], self._prompt_rows[index] = self._prompt_rows[index], self._prompt_rows[index - 1]
            self._rebuild_rows()

    def _move_row_down(self, row):
        index = self._prompt_rows.index(row)
        if index < len(self._prompt_rows) - 1:
            self._prompt_rows[index + 1], self._prompt_rows[index] = self._prompt_rows[index], self._prompt_rows[index + 1]
            self._rebuild_rows()

    def _rebuild_rows(self):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        for row in self._prompt_rows:
            self._rows_layout.addWidget(row)
        self._relayout_prompts()

    def _on_add_scene(self):
        if len(self._prompt_rows) >= self.MAX_SCENES:
            return
        self._add_row("")

    def _on_import_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import prompt", "", "Text (*.txt)")
        if not path:
            return
        for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
            text = line.strip()
            if text:
                self._add_row(text)

    def _on_delete_row(self, row):
        if len(self._prompt_rows) <= 1:
            return
        if row in self._prompt_rows:
            self._prompt_rows.remove(row)
            row.setParent(None)
            self._rebuild_rows()

    def _refresh_scene_count(self):
        self._scene_count_label.setText(f"So canh: {len(self._prompt_rows)}")
        self._refresh_credit_labels()

    def _refresh_credit_labels(self):
        try:
            total = estimate_credits(self.quality_combo.currentText(), len(self._prompt_rows))
        except Exception:
            total = len(self._prompt_rows)
        per_video = max(1, total // max(1, len(self._prompt_rows)))
        self._credit_per_video_label.setText(f"Credit / canh: {per_video}")
        self._credit_total_label.setText(f"Tong credit uoc tinh: {total}")

    def _on_img_mode_changed(self, *args):
        mode = self.img_mode_combo.currentText()
        self.ref_panel.setVisible(mode == IMG_MODE_REFERENCE)
        self.start_panel.setVisible(mode == IMG_MODE_START_FRAME)

    def _collect_character_images(self):
        data = self.image_grid.get_images()
        return list(data.values())

    def _collect_prompts(self):
        return [row.get_text().strip() for row in self._prompt_rows if row.get_text().strip()]

    def _on_browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Chon thu muc output")
        if path:
            self.output_edit.setText(path)

    def _on_pick_start_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chon anh mo dau", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        self._start_image_path = path
        self.start_img_label.setText(Path(path).name)
        self.clear_img_btn.setEnabled(True)

    def _on_clear_start_image(self):
        self._start_image_path = None
        self.start_img_label.setText("Chua chon anh mo dau")
        self.clear_img_btn.setEnabled(False)

    def _set_running_ui(self, running):
        self.start_btn.setEnabled(not running)
        self.start_btn.setText("Dang chay..." if running else "Bat dau tao video")
        self.cancel_btn.setEnabled(running)
        self._add_btn.setEnabled((not running) and len(self._prompt_rows) < self.MAX_SCENES)
        self._import_btn.setEnabled(not running)
        for row in self._prompt_rows:
            row.set_read_only(running)
        self.quality_combo.setEnabled(not running)
        self.ar_combo.setEnabled(not running)
        self.output_edit.setEnabled(not running)
        self.pick_img_btn.setEnabled(not running)
        self.clear_img_btn.setEnabled((not running) and bool(self._start_image_path))
        self.img_mode_combo.setEnabled(not running)
        self.image_grid.setEnabled(not running)
        self.reset_btn.setEnabled(not running)

    def _populate_status_table(self, prompts):
        self.status_table.setRowCount(len(prompts))
        for idx, _ in enumerate(prompts, 1):
            self.status_table.setItem(idx - 1, 0, QTableWidgetItem(str(idx)))
            self.status_table.setItem(idx - 1, 1, QTableWidgetItem("Cho"))
            self.status_table.setItem(idx - 1, 2, QTableWidgetItem(""))

    def _on_start(self):
        prompts = self._collect_prompts()
        if not prompts:
            QMessageBox.warning(self, "Long video", "Chua co prompt.")
            return
        out_dir = Path(self.output_edit.text().strip() or DEFAULT_VIDEO_OUTPUT) / generate_task_name("long_video")
        self._populate_status_table(prompts)
        self.progress_bar.show()
        self.progress_bar.setRange(0, len(prompts))
        self.progress_bar.setValue(0)
        self.progress_label.setText("Dang khoi tao...")
        self.final_label.setText("Dang xu ly...")
        self._final_path = None
        self._worker = LongVideoWorker(
            self._get_account_pool(),
            prompts,
            out_dir,
            self.quality_combo.currentText(),
            self.ar_combo.currentText(),
            self._start_image_path,
            self,
        )
        self._worker.chain_started.connect(self._on_chain_started)
        self._worker.scene_started.connect(self._on_scene_started)
        self._worker.scene_done.connect(self._on_scene_done)
        self._worker.scene_failed.connect(self._on_scene_failed)
        self._worker.progress.connect(self._on_progress)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._set_running_ui(True)
        self._worker.start()

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
        self._set_running_ui(False)

    def _on_chain_started(self, output_dir):
        self.progress_label.setText(f"Output: {output_dir}")

    def _on_scene_started(self, index, total):
        self.progress_label.setText(f"Cảnh {index}/{total}")
        self.status_table.setItem(index - 1, 1, QTableWidgetItem("Dang chay"))

    def _on_scene_done(self, index, path):
        self.progress_bar.setValue(index)
        self.status_table.setItem(index - 1, 1, QTableWidgetItem("Xong"))
        self.status_table.setItem(index - 1, 2, QTableWidgetItem(path))

    def _on_scene_failed(self, index, error):
        self.status_table.setItem(index - 1, 1, QTableWidgetItem("Loi"))
        self.status_table.setItem(index - 1, 2, QTableWidgetItem(str(error)))

    def _on_progress(self, text):
        self.progress_label.setText(str(text))

    def _on_all_done(self, final_path):
        self._final_path = final_path
        self.progress_label.setText("Hoan tat")
        self.final_label.setText(final_path)

    def _on_worker_error(self, message):
        self.progress_label.setText(str(message))
        log.warning(message)

    def _on_worker_finished(self):
        self._set_running_ui(False)
        self._worker = None

    def _on_final_link(self, path):
        if path:
            self._open_video(path)

    def _open_video(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_preview(self, path):
        self._open_video(path)

    def _retry_from_scene(self, index):
        self._on_start()

    def _on_reset(self):
        for row in list(self._prompt_rows):
            row.setParent(None)
        self._prompt_rows.clear()
        self.image_grid.clear()
        self._start_image_path = None
        self.start_img_label.setText("Chua chon anh mo dau")
        self.clear_img_btn.setEnabled(False)
        self.status_table.setRowCount(0)
        self.progress_bar.hide()
        self.final_label.setText("Ket qua cuoi se hien thi tai day")
        for _ in range(self.DEFAULT_SCENES):
            self._add_row("")
        self._refresh_scene_count()

    def closeEvent(self, event):
        self._on_cancel()
        super().closeEvent(event)
