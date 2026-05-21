"""NAV TOOLS - Batch Resize page.

Select multiple images -> resize for platform presets -> save all.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.coming_soon_banner import ComingSoonBanner
from ui.widgets.page_styles import PROGRESS_HEIGHT, PROGRESS_STYLE
from utils.logger import log


PLATFORM_PRESETS = {
    "Tuy chinh": (0, 0),
    "Instagram Post (1080x1080)": (1080, 1080),
    "Instagram Story (1080x1920)": (1080, 1920),
    "YouTube Thumbnail (1280x720)": (1280, 720),
    "TikTok (1080x1920)": (1080, 1920),
    "Facebook Cover (820x312)": (820, 312),
    "Twitter Header (1500x500)": (1500, 500),
    "Wallpaper HD (1920x1080)": (1920, 1080),
    "Wallpaper 4K (3840x2160)": (3840, 2160),
}


class _ResizeSignals(QObject):
    progress = Signal(int, int)
    finished = Signal(int, list)
    error = Signal(str)


MODE_STRETCH = "stretch"
MODE_FIT = "fit"
MODE_PAD = "pad"


class _ResizeWorker(QThread):
    """Batch resize images with multiple resize modes."""

    def __init__(self, files, output_dir, width, height, mode=MODE_FIT, output_format="original", pad_color=(0, 0, 0), parent=None):
        super().__init__(parent)
        self.files = files
        self.output_dir = Path(output_dir)
        self.width = width
        self.height = height
        self.mode = mode
        self.output_format = output_format
        self.pad_color = pad_color
        self.signals = _ResizeSignals()

    def _resize_one(self, img):
        """Resize image according to selected mode."""
        target = (self.width, self.height)
        if self.mode == MODE_STRETCH:
            return img.resize(target, Image.Resampling.LANCZOS)
        if self.mode == MODE_FIT:
            return ImageOps.fit(img, target, method=Image.Resampling.LANCZOS)
        if self.mode == MODE_PAD:
            return ImageOps.pad(img, target, method=Image.Resampling.LANCZOS, color=self.pad_color)
        return img.resize(target, Image.Resampling.LANCZOS)

    def run(self):
        outputs = []
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            total = len(self.files)
            for index, path in enumerate(self.files, 1):
                src = Path(path)
                img = Image.open(src).convert("RGB")
                out = self._resize_one(img)
                ext = src.suffix.lower()
                if self.output_format == "png":
                    ext = ".png"
                elif self.output_format == "jpg":
                    ext = ".jpg"
                out_path = self.output_dir / f"{src.stem}{ext}"
                out.save(out_path)
                outputs.append(str(out_path))
                self.signals.progress.emit(index, total)
            self.signals.finished.emit(total, outputs)
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


class BatchResizePage(QWidget):
    """Page: select images -> pick size -> batch resize -> save."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files = []
        self._worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Batch Resize")
        title.setProperty("class", "section-title")
        desc = QLabel("Chon nhieu anh, dat preset kich thuoc va resize hang loat.")
        desc.setStyleSheet("color: #8c909f; font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(ComingSoonBanner("Ho tro resize co day du preset, mode va dinh dang xuat"))

        preset_row = QHBoxLayout()
        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(list(PLATFORM_PRESETS.keys()))
        self._cmb_preset.setCurrentIndex(3)
        self._cmb_preset.currentTextChanged.connect(self._on_preset_changed)
        preset_row.addWidget(QLabel("Preset"))
        preset_row.addWidget(self._cmb_preset, 1)
        preset_row.addStretch(1)
        layout.addLayout(preset_row)

        size_row = QHBoxLayout()
        self._spn_w = QSpinBox()
        self._spn_w.setRange(1, 99999)
        self._spn_w.setValue(1280)
        self._spn_h = QSpinBox()
        self._spn_h.setRange(1, 99999)
        self._spn_h.setValue(720)
        size_row.addWidget(QLabel("Width"))
        size_row.addWidget(self._spn_w)
        size_row.addWidget(QLabel("Height"))
        size_row.addWidget(self._spn_h)
        layout.addLayout(size_row)

        mode_row = QHBoxLayout()
        self._cmb_mode = QComboBox()
        self._cmb_mode.addItem("Fit", MODE_FIT)
        self._cmb_mode.addItem("Pad", MODE_PAD)
        self._cmb_mode.addItem("Stretch", MODE_STRETCH)
        self._cmb_format = QComboBox()
        self._cmb_format.addItem("Giu nguyen", "original")
        self._cmb_format.addItem("PNG", "png")
        self._cmb_format.addItem("JPG", "jpg")
        mode_row.addWidget(QLabel("Mode"))
        mode_row.addWidget(self._cmb_mode)
        mode_row.addWidget(QLabel("Format"))
        mode_row.addWidget(self._cmb_format)
        layout.addLayout(mode_row)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("Them anh")
        self._btn_add.setStyleSheet(BTN_STYLE)
        self._btn_add.clicked.connect(self._on_add_files)
        self._btn_remove = QPushButton("Xoa dong")
        self._btn_remove.setStyleSheet(BTN_STYLE)
        self._btn_remove.clicked.connect(self._on_remove_selected)
        self._btn_clear = QPushButton("Xoa het")
        self._btn_clear.setStyleSheet(BTN_STYLE)
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        btn_row.addWidget(self._btn_clear)
        layout.addLayout(btn_row)

        self._lbl_count = QLabel("0 file")
        self._lbl_count.setStyleSheet("color: #8c909f; font-size: 12px;")
        layout.addWidget(self._lbl_count)

        self._table = QTableWidget()
        self._table.setColumnCount(1)
        self._table.setHorizontalHeaderLabels(["Image"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)

        self._btn_resize = QPushButton("Bat dau resize")
        self._btn_resize.setStyleSheet(BTN_STYLE)
        self._btn_resize.setEnabled(False)
        self._btn_resize.setToolTip("Chon file truoc khi resize")
        self._btn_resize.clicked.connect(self._on_resize)
        layout.addWidget(self._btn_resize)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(PROGRESS_HEIGHT)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(PROGRESS_STYLE)
        self._progress.setVisible(False)
        self._lbl_status = QLabel("San sang")
        self._lbl_status.setStyleSheet("color: #8c909f; font-size: 12px;")
        layout.addWidget(self._progress)
        layout.addWidget(self._lbl_status)

        self._on_preset_changed(self._cmb_preset.currentText())

    def _on_preset_changed(self, name):
        width, height = PLATFORM_PRESETS.get(name, (0, 0))
        if width and height:
            self._spn_w.setValue(width)
            self._spn_h.setValue(height)
        custom = name == "Tuy chinh"
        self._spn_w.setEnabled(custom)
        self._spn_h.setEnabled(custom)

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chon anh",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        for path in files:
            if path in self._files:
                continue
            self._files.append(path)
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(path))
        self._lbl_count.setText(f"{len(self._files)} file")
        self._btn_resize.setEnabled(bool(self._files))

    def _on_clear(self):
        self._files.clear()
        self._table.setRowCount(0)
        self._lbl_count.setText("0 file")
        self._btn_resize.setEnabled(False)

    def _on_remove_selected(self):
        rows = sorted({index.row() for index in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._table.removeRow(row)
            if 0 <= row < len(self._files):
                self._files.pop(row)
        self._lbl_count.setText(f"{len(self._files)} file")
        self._btn_resize.setEnabled(bool(self._files))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self._on_remove_selected()
            return
        super().keyPressEvent(event)

    def _set_processing(self, processing):
        self._btn_resize.setEnabled(not processing and bool(self._files))
        self._btn_add.setEnabled(not processing)
        self._btn_clear.setEnabled(not processing)
        self._btn_remove.setEnabled(not processing)
        self._cmb_preset.setEnabled(not processing)
        self._cmb_mode.setEnabled(not processing)
        self._cmb_format.setEnabled(not processing)
        can_edit_size = (not processing) and self._cmb_preset.currentText() == "Tuy chinh"
        self._spn_w.setEnabled(can_edit_size)
        self._spn_h.setEnabled(can_edit_size)

    def _on_resize(self):
        if not self._files:
            return
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Chon thu muc luu",
            str(Path.home() / "Pictures"),
        )
        if not output_dir:
            return
        w = self._spn_w.value()
        h = self._spn_h.value()
        mode = self._cmb_mode.currentData()
        fmt = self._cmb_format.currentData()
        self._set_processing(True)
        self._progress.setVisible(True)
        self._progress.setRange(0, len(self._files))
        self._progress.setValue(0)
        self._lbl_status.setText("Dang resize...")
        self._lbl_status.setStyleSheet("color: #8c909f; font-size: 12px;")
        self._worker = _ResizeWorker(
            self._files,
            output_dir,
            w,
            h,
            mode=mode,
            output_format=fmt,
            parent=self,
        )
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.finished.connect(self._on_done)
        self._worker.signals.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_progress(self, done, total):
        self._progress.setRange(0, total)
        self._progress.setValue(done)
        self._lbl_status.setText(f"Dang resize {done}/{total}")

    def _on_done(self, count, outputs):
        self._set_processing(False)
        self._progress.setVisible(False)
        self._lbl_status.setText(f"Hoan tat {count} file")
        self._lbl_status.setStyleSheet("color: #22c55e; font-size: 12px;")
        self._worker = None

    def _on_error(self, message):
        log.warning(f"Batch resize failed: {message}")
        self._set_processing(False)
        self._progress.setVisible(False)
        self._lbl_status.setText(f"Loi: {message}")
        self._lbl_status.setStyleSheet("color: #ef4444; font-size: 12px;")
        self._worker = None
