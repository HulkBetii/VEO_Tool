"""NAV TOOLS - Watermark removal page."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.inpaint_lama import build_rect_mask, download_model, inpaint_image_crop, inpaint_video, model_exists
from ui.widgets.page_styles import LEFT_PANEL_WIDTH, PROGRESS_HEIGHT, PROGRESS_STYLE
from utils.logger import log


IMAGE_EXTS = frozenset({".bmp", ".jpg", ".png", ".jpeg", ".webp"})
VIDEO_EXTS = frozenset({".avi", ".mkv", ".mov", ".mp4", ".webm"})


class _InpaintSignals(QObject):
    item_started = Signal(int, str)
    item_progress = Signal(int, int, int, str)
    item_done = Signal(int, str, str)
    item_error = Signal(int, str)
    all_done = Signal()
    download_progress = Signal(int, int)
    log_msg = Signal(str)


class _InpaintWorker(QThread):
    """Sequential queue processor: for each file, call the right LaMa API."""

    def __init__(self, items, rect, output_folder, padding=32, parent=None):
        super().__init__(parent)
        self.items = items
        self.rect = rect
        self.output_folder = output_folder
        self.padding = padding
        self.signals = _InpaintSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if not model_exists():
                self.signals.log_msg.emit("Dang tai model LaMa...")
                ok = download_model(lambda done, total: self.signals.download_progress.emit(done, total))
                if not ok:
                    raise RuntimeError("Khong tai duoc model LaMa")
            out_dir = Path(self.output_folder) if self.output_folder else None
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
            for index, item in enumerate(self.items):
                if self._cancelled:
                    break
                path = Path(item["path"])
                rect = item["rect"] or self.rect
                target_dir = out_dir or path.parent
                target_dir.mkdir(parents=True, exist_ok=True)
                output_path = target_dir / f"{path.stem}_clean{path.suffix}"
                self.signals.item_started.emit(index, str(path))
                try:
                    if item["is_video"]:
                        ok = inpaint_video(
                            path,
                            output_path,
                            rect,
                            padding=self.padding,
                            progress_cb=lambda done, total, msg="Dang xu ly video...": self.signals.item_progress.emit(index, done, total, msg),
                        )
                        if not ok:
                            raise RuntimeError("Xu ly video that bai")
                    else:
                        img = Image.open(path)
                        mask = build_rect_mask(img.size, rect)
                        result = inpaint_image_crop(img, mask, rect, padding=self.padding)
                        result.save(output_path)
                    self.signals.item_done.emit(index, str(path), str(output_path))
                except Exception as e:
                    self.signals.item_error.emit(index, str(e))
        finally:
            self.signals.all_done.emit()


class WatermarkRemovePage(QWidget):
    """Dedicated page for removing static watermarks from images/videos."""

    DEFAULT_RECT_W = 180
    DEFAULT_RECT_H = 60

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._worker = None
        self._files = []
        self._init_ui()

    def _init_ui(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main.addWidget(splitter)

        left_scroll = QScrollArea()
        left_scroll.setFixedWidth(LEFT_PANEL_WIDTH)
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(12)

        title = QLabel("Watermark Removal")
        title.setProperty("class", "section-title")
        title.setFont(QFont("", 12, QFont.Weight.Bold))
        desc = QLabel(
            "Xoa watermark tinh tren anh hoac video bang LaMa inpaint. Ho tro xu ly theo hang doi."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8c909f; font-size: 12px;")
        ll.addWidget(title)
        ll.addWidget(desc)

        btn_row = QHBoxLayout()
        self._btn_pick_files = QPushButton("Them file")
        self._btn_pick_files.setFixedHeight(36)
        self._btn_pick_files.clicked.connect(self._on_pick_files)
        self._btn_pick_folder = QPushButton("Them folder")
        self._btn_pick_folder.setFixedHeight(36)
        self._btn_pick_folder.clicked.connect(self._on_pick_folder)
        btn_row.addWidget(self._btn_pick_files)
        btn_row.addWidget(self._btn_pick_folder)
        ll.addLayout(btn_row)

        queue_label = QLabel("Hang doi")
        queue_label.setStyleSheet("font-weight: 600;")
        ll.addWidget(queue_label)

        self._queue_list = QListWidget()
        self._queue_list.setMinimumHeight(220)
        ll.addWidget(self._queue_list)

        btn_row2 = QHBoxLayout()
        self._btn_clear = QPushButton("Xoa het")
        self._btn_clear.clicked.connect(self._on_clear_queue)
        self._btn_remove = QPushButton("Bo muc chon")
        self._btn_remove.clicked.connect(self._on_remove_selected)
        btn_row2.addWidget(self._btn_clear)
        btn_row2.addWidget(self._btn_remove)
        ll.addLayout(btn_row2)

        region_label = QLabel("Che do vung xoa")
        region_label.setStyleSheet("font-weight: 600;")
        region_hint = QLabel("Auto dat watermark o goc duoi phai. Manual dung toa do X/Y/W/H.")
        region_hint.setWordWrap(True)
        region_hint.setStyleSheet("color: #8c909f; font-size: 12px;")
        ll.addWidget(region_label)
        ll.addWidget(region_hint)

        self._region_group = QButtonGroup(self)
        self._rb_auto = QRadioButton("Auto")
        self._rb_manual = QRadioButton("Manual")
        self._rb_auto.setChecked(True)
        self._region_group.addButton(self._rb_auto)
        self._region_group.addButton(self._rb_manual)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self._rb_auto)
        mode_row.addWidget(self._rb_manual)
        ll.addLayout(mode_row)

        self._manual_widget = QWidget()
        mg = QVBoxLayout(self._manual_widget)
        mg.setContentsMargins(0, 0, 0, 0)
        mg.setSpacing(8)
        self._spin_x = self._make_spin(0, 99999, 0)
        self._spin_y = self._make_spin(0, 99999, 0)
        self._spin_w = self._make_spin(1, 99999, self.DEFAULT_RECT_W)
        self._spin_h = self._make_spin(1, 99999, self.DEFAULT_RECT_H)
        for text, spin in (
            ("X", self._spin_x),
            ("Y", self._spin_y),
            ("W", self._spin_w),
            ("H", self._spin_h),
        ):
            spin_pair = QHBoxLayout()
            spin_pair.addWidget(self._label(text))
            spin_pair.addWidget(spin)
            mg.addLayout(spin_pair)
        ll.addWidget(self._manual_widget)

        out_row = QHBoxLayout()
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("De trong de luu cung thu muc voi file goc")
        self._btn_out_browse = QPushButton("Thu muc luu")
        self._btn_out_browse.clicked.connect(self._on_browse_output)
        out_row.addWidget(self._out_edit, 1)
        out_row.addWidget(self._btn_out_browse)
        ll.addLayout(out_row)

        self._btn_start = QPushButton("Bat dau")
        self._btn_start.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_start.setToolTip("Xu ly lan luot tung file trong hang doi")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel = QPushButton("Dung")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_cancel)
        start_row = QHBoxLayout()
        start_row.addWidget(self._btn_start)
        start_row.addWidget(self._btn_cancel)
        ll.addLayout(start_row)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(PROGRESS_HEIGHT)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(PROGRESS_STYLE)
        self._progress.hide()
        self._status_label = QLabel("San sang")
        self._status_label.setStyleSheet("color: #8c909f; font-size: 12px;")
        ll.addWidget(self._progress)
        ll.addWidget(self._status_label)
        ll.addStretch(1)

        left_scroll.setWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 16)
        rl.setSpacing(12)
        log_title = QLabel("Nhat ky xu ly")
        log_title.setStyleSheet("font-weight: 600;")
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        rl.addWidget(log_title)
        rl.addWidget(self._log_view, 1)

        splitter.addWidget(left_scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        self._rb_auto.toggled.connect(self._on_region_mode_changed)
        self._rb_manual.toggled.connect(self._on_region_mode_changed)
        self._on_region_mode_changed()

    def _label(self, text):
        return QLabel(str(text))

    def _make_spin(self, min_value, max_value, value):
        spin = QSpinBox()
        spin.setRange(min_value, max_value)
        spin.setValue(value)
        return spin

    def _log(self, text):
        self._log_view.append(str(text))

    def _on_region_mode_changed(self, *args):
        manual = self._rb_manual.isChecked()
        self._manual_widget.setEnabled(manual)

    def _on_pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chon file",
            "",
            "Media (*.png *.jpg *.jpeg *.webp *.bmp *.mp4 *.mov *.mkv *.avi *.webm)",
        )
        self._add_files(files)

    def _on_pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chon folder")
        if not folder:
            return
        files = []
        for path in sorted(Path(folder).iterdir()):
            if path.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS:
                files.append(str(path))
        self._add_files(files)

    def _add_files(self, files):
        for path in files or []:
            suffix = Path(path).suffix.lower()
            if suffix not in IMAGE_EXTS | VIDEO_EXTS:
                continue
            if any(entry["path"] == path for entry in self._files):
                continue
            item = {
                "path": path,
                "is_video": suffix in VIDEO_EXTS,
                "status": "pending",
                "rect": self._compute_rect_for_file(path),
            }
            self._files.append(item)
            label = f"{Path(path).name} [{'VIDEO' if item['is_video'] else 'IMAGE'}]"
            self._queue_list.addItem(QListWidgetItem(label))
        self._status_label.setText(f"Da nap {len(self._files)} file")

    def _on_clear_queue(self):
        self._files.clear()
        self._queue_list.clear()
        self._status_label.setText("Da xoa hang doi")

    def _on_remove_selected(self):
        rows = sorted({index.row() for index in self._queue_list.selectedIndexes()}, reverse=True)
        for row in rows:
            self._queue_list.takeItem(row)
            if 0 <= row < len(self._files):
                self._files.pop(row)
        self._status_label.setText(f"Con {len(self._files)} file")

    def _on_browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chon thu muc luu")
        if folder:
            self._out_edit.setText(folder)

    def _compute_rect_for_file(self, path):
        if self._rb_manual.isChecked():
            return (
                self._spin_x.value(),
                self._spin_y.value(),
                self._spin_w.value(),
                self._spin_h.value(),
            )
        try:
            if Path(path).suffix.lower() in IMAGE_EXTS:
                w, h = Image.open(path).size
            else:
                return (0, 0, self.DEFAULT_RECT_W, self.DEFAULT_RECT_H)
            rw = min(self.DEFAULT_RECT_W, w)
            rh = min(self.DEFAULT_RECT_H, h)
            return (max(0, w - rw - 24), max(0, h - rh - 24), rw, rh)
        except Exception as e:
            self._log(f"Khong doc duoc kich thuoc file:\n{e}")
            return (0, 0, self.DEFAULT_RECT_W, self.DEFAULT_RECT_H)

    def _on_start(self):
        if not self._files:
            QMessageBox.warning(self, "Trong", "Them file vao hang doi truoc.")
            return
        if self._worker and self._worker.isRunning():
            return
        output_folder = self._out_edit.text().strip()
        items_to_process = []
        first_rect = None
        for entry in self._files:
            entry["rect"] = self._compute_rect_for_file(entry["path"])
            entry["status"] = "queued"
            items_to_process.append(dict(entry))
            if first_rect is None:
                first_rect = entry["rect"]
        if not items_to_process:
            QMessageBox.warning(self, "Loi", "Khong co file nao can xu ly.")
            return
        self._status_label.setText(f"Bat dau xu ly {len(items_to_process)} file, rect={first_rect}")
        self._status_label.setStyleSheet("color: #8c909f; font-size: 12px;")
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._progress.show()
        self._progress.setRange(0, max(1, len(items_to_process)))
        self._progress.setValue(0)
        self._worker = _InpaintWorker(items=items_to_process, rect=first_rect, output_folder=output_folder, parent=self)
        self._worker.signals.item_started.connect(self._on_item_started)
        self._worker.signals.item_progress.connect(self._on_item_progress)
        self._worker.signals.item_done.connect(self._on_item_done)
        self._worker.signals.item_error.connect(self._on_item_error)
        self._worker.signals.all_done.connect(self._on_all_done)
        self._worker.signals.download_progress.connect(self._on_download_progress)
        self._worker.signals.log_msg.connect(self._log)
        self._worker.start()

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
            self._log("Da gui yeu cau dung.")

    def _on_item_started(self, index, path):
        if 0 <= index < len(self._files):
            self._files[index]["status"] = "running"
        self._status_label.setText(f"Dang xu ly: {Path(path).name}")
        self._log(f"Bat dau: {path}")

    def _on_item_progress(self, index, done, total, message):
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(done)
        self._log(f"[{index + 1}] {message} ({done}/{total})")

    def _on_item_done(self, index, path, output):
        if 0 <= index < len(self._files):
            self._files[index]["status"] = "done"
        self._progress.setValue(min(self._progress.maximum(), self._progress.value() + 1))
        self._log(f"Done: {output}")

    def _on_item_error(self, index, error):
        if 0 <= index < len(self._files):
            self._files[index]["status"] = "error"
        self._progress.setValue(min(self._progress.maximum(), self._progress.value() + 1))
        self._log(f"Loi: {error}")
        log.warning(error)

    def _on_all_done(self):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._progress.hide()
        done = sum(1 for f in self._files if f["status"] == "done")
        errs = sum(1 for f in self._files if f["status"] == "error")
        self._status_label.setText(f"Hoan tat: {done} OK, {errs} loi")
        self._status_label.setStyleSheet("color: #22c55e; font-size: 12px;")
        self._log(self._status_label.text())
        self._worker = None

    def _on_download_progress(self, done, total):
        if total > 0:
            percent = int(done * 100 / total)
            self._log(f"Tai model: {percent}%")
        else:
            self._log(f"Tai model: {done} bytes")
