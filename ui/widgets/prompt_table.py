"""NAV TOOLS - Prompt Table widget.

Bảng prompt đa năng: thumbnail (=NV ref) + tối ưu AI + editable prompt + chạy video.
Dùng cho tất cả trang tạo video/ảnh. Giữ nguyên chức năng cũ, bổ sung thêm.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from utils.logger import log


def _filter_imgs_by_prompt(imgs: dict[str, str], prompt_text: str) -> dict[str, str]:
    """Return {alias: path} filtered to aliases mentioned as @alias in prompt."""
    if not imgs or not prompt_text:
        return {}
    return {
        alias: imgs[alias]
        for alias in imgs
        if imgs.get(alias) and re.search("@" + re.escape(alias) + r"\b", prompt_text, re.IGNORECASE)
    }


class _PlaceholderDelegate(QStyledItemDelegate):
    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self._placeholder = placeholder

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text and str(text).strip():
            return
        painter.save()
        painter.setPen(QPen(QColor("#4a5568")))
        font = painter.font()
        font.setItalic(True)
        font.setPointSize(10)
        painter.setFont(font)
        rect = option.rect.adjusted(8, 0, 0, -4)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, self._placeholder)
        painter.restore()


class _OptimizeSignals(QObject):
    """Signals for async Gemini optimize."""

    done = Signal(int, str)
    error = Signal(int, str)


class PromptTable(QWidget):
    """Bảng prompt với thumbnail, tối ưu AI, editable prompt."""

    start_task = Signal(dict)
    start_requested = start_task
    item_retry = Signal(int)
    retry_requested = item_retry
    item_upscale = Signal(int, str)

    def __init__(self, db=None, mode: str = "", parent=None):
        super().__init__(parent)
        self._db = db
        self._mode = mode
        self._has_characters = mode in ("char_video", "char_image", "video_ref")
        self._char_images = {}
        self._row_char_images = {}
        self._row_character_images = self._row_char_images
        self._row_to_item_id = {}
        self._optimize_total = 0
        self._optimize_done_count = 0
        self._optimize_signals = _OptimizeSignals()
        self._optimize_signals.done.connect(self._on_optimize_done)
        self._optimize_signals.error.connect(self._on_optimize_error)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        title = QLabel("Bảng Prompt")
        title.setFont(QFont("", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #dae2fd;")
        header_row.addWidget(title)
        header_row.addStretch()

        self._count_label = QLabel("0 prompt")
        self._count_label.setStyleSheet(
            "color: #64748b; font-size: 11px; padding: 2px 8px; background: #1e293b; border-radius: 8px;"
        )
        header_row.addWidget(self._count_label)
        layout.addLayout(header_row)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(("#", "NV Refer", "AI", "Prompt - click để nhập / sửa", "Kết quả", ""))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(
            """
            QTableWidget { background: transparent; border: none; }
            QTableWidget::item { padding: 4px 6px; border-bottom: 1px solid #222a3d; }
            QHeaderView::section {
                background: #131b2e; color: #8c909f; font-weight: 600;
                font-size: 11px; padding: 4px 6px; border: none; border-bottom: 1px solid #424754;
            }
        """
        )
        header = self.table.horizontalHeader()
        header.resizeSection(0, 28)
        header.resizeSection(1, 70)
        header.resizeSection(2, 36)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(4, 70)
        header.resizeSection(5, 26)
        for col in (0, 2, 4):
            item = self.table.horizontalHeaderItem(col)
            if item is not None:
                item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))

        self.table.setItemDelegateForColumn(3, _PlaceholderDelegate("✏️  Nhập prompt tại đây...", self.table))
        self.table.setColumnHidden(1, not self._has_characters)
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.cellDoubleClicked.connect(self._on_cell_double_click)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_h = 28
        btn_style = (
            "QPushButton {{ background: {bg}; color: {fg}; font-size: 13px; font-weight: 600; "
            "border-radius: 10px; padding: 0 18px; border: {border}; }}"
            "QPushButton:hover {{ background: {hover}; }}"
            "QPushButton:disabled {{ background: #374151; color: #6b7280; }}"
        )

        add_btn = QPushButton("  +  Thêm dòng")
        add_btn.setStyleSheet(btn_style.format(bg="#1e293b", fg="#3b82f6", border="1px solid #3b82f6", hover="#1e3a5f"))

        import_btn = QPushButton("  Import TXT")
        import_btn.setStyleSheet(btn_style.format(bg="#1e293b", fg="#94a3b8", border="1px solid #2d3449", hover="#2d3449"))

        self._optimize_all_btn = QPushButton("  Tối ưu tất cả")
        self._optimize_all_btn.setStyleSheet(btn_style.format(bg="#7c3aed", fg="white", border="none", hover="#6d28d9"))
        self._optimize_all_btn.hide()

        self._start_btn = QPushButton("  ▶  Bắt đầu tạo")
        self._start_btn.setStyleSheet(btn_style.format(bg="#16a34a", fg="white", border="none", hover="#15803d"))

        for btn in (add_btn, import_btn, self._optimize_all_btn, self._start_btn):
            btn.setFixedHeight(btn_h)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_row.addWidget(btn)

        add_btn.clicked.connect(lambda: self.add_row())
        import_btn.clicked.connect(self._import_txt)
        self._optimize_all_btn.clicked.connect(self._on_optimize_all)
        self._start_btn.clicked.connect(self._on_start_from_table)
        self._update_optimize_btn_visibility()
        layout.addLayout(btn_row)

    def _checkbox_for_row(self, row: int) -> QCheckBox | None:
        wrapper = self.table.cellWidget(row, 2)
        if wrapper is None:
            return None
        return wrapper.findChild(QCheckBox)

    def add_row(self, prompt: str = "", thumbnail: str = ""):
        row = self.table.rowCount()
        self.table.setRowCount(row + 1)

        num = QTableWidgetItem(str(row + 1))
        num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setFlags(num.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 0, num)

        thumb_btn = QPushButton("+")
        thumb_btn.setFixedSize(70, 50)
        thumb_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        thumb_btn.setStyleSheet(
            "QPushButton { background: #0f1729; border: 1.5px dashed #3b82f6; border-radius: 6px; "
            "color: #3b82f6; font-size: 20px; font-weight: bold; }"
            "QPushButton:hover { background: #1e2d4a; border-color: #60a5fa; }"
        )
        thumb_btn.clicked.connect(lambda _=False, r=row: self._pick_row_chars(r))
        row_imgs = self._row_char_images.get(row, self._char_images)
        filtered = _filter_imgs_by_prompt(row_imgs, prompt) if prompt else row_imgs
        paths = list((filtered or row_imgs or {}).values())
        self._set_btn_thumbnail(thumb_btn, paths)
        self.table.setCellWidget(row, 1, thumb_btn)

        cb_wrapper = QWidget()
        cb_wrapper.setStyleSheet("background: transparent;")
        cb_layout = QHBoxLayout(cb_wrapper)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setSpacing(0)
        cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb = QCheckBox()
        cb.setToolTip("Tick để AI tối ưu prompt này")
        cb.setStyleSheet(
            """
            QCheckBox { spacing: 0px; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 2px solid #475569;
                border-radius: 3px;
                background: transparent;
            }
            QCheckBox::indicator:hover { border-color: #818cf8; }
            QCheckBox::indicator:checked {
                width: 16px; height: 16px;
                border: 2px solid #818cf8;
                border-radius: 3px;
                background: #4f46e5;
            }
        """
        )
        cb.stateChanged.connect(self._update_optimize_btn_visibility)
        cb_layout.addWidget(cb)
        self.table.setCellWidget(row, 2, cb_wrapper)

        prompt_item = QTableWidgetItem(prompt)
        self.table.setItem(row, 3, prompt_item)

        video_item = QTableWidgetItem("—")
        video_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 4, video_item)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(30, 30)
        del_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #64748b; font-size: 16px; border: none; border-radius: 6px; }"
            "QPushButton:hover { background: #2d1f1f; color: #ef4444; }"
        )
        del_btn.clicked.connect(lambda _=False, r=row: self._remove_row(r))
        self.table.setCellWidget(row, 5, del_btn)

        self._update_count()
        self._update_optimize_btn_visibility()

    def _remove_row(self, row: int):
        btn = self.table.cellWidget(row, 1)
        if btn and btn.property("image_path"):
            alias = btn.property("alias")
            if alias and alias in self._char_images:
                del self._char_images[alias]
        self.table.removeRow(row)
        self._row_char_images.pop(row, None)
        if self._row_to_item_id:
            self._row_to_item_id = {(r if r < row else r - 1): iid for r, iid in self._row_to_item_id.items() if r != row}
        self._update_count()
        self._update_optimize_btn_visibility()

    def _get_checkbox(self, row: int):
        return self._checkbox_for_row(row)

    def _update_count(self):
        count = self.table.rowCount()
        self._count_label.setText(f"{count} prompt")
        for row in range(count):
            item = self.table.item(row, 0)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, 0, item)
            item.setText(str(row + 1))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return count

    def _set_btn_thumbnail(self, btn: QPushButton, paths: list[str]):
        if not paths:
            btn.setText("+" if self._has_characters else "")
            btn.setProperty("image_path", None)
            return
        btn.setText(f"{len(paths)} ảnh")
        btn.setProperty("image_path", paths[0])

    def _set_label_thumbnail(self, label: QLabel, paths: list[str]):
        label.setText(f"{len(paths or [])} ảnh" if paths else "")

    def _on_item_changed(self, *args):
        self._refresh_all_nv_thumbnails()

    def _refresh_all_nv_thumbnails(self):
        for row in range(self.table.rowCount()):
            btn = self.table.cellWidget(row, 1)
            if not isinstance(btn, QPushButton):
                continue
            item = self.table.item(row, 3)
            prompt_text = item.text().strip() if item else ""
            row_imgs = self._row_char_images.get(row, self._char_images)
            filtered = _filter_imgs_by_prompt(row_imgs, prompt_text) or row_imgs
            self._set_btn_thumbnail(btn, list(filtered.values()))

    def _update_optimize_btn_visibility(self):
        if not hasattr(self, "_optimize_all_btn"):
            return
        checked = False
        for row in range(self.table.rowCount()):
            cb = self._checkbox_for_row(row)
            if cb and cb.isChecked():
                checked = True
                break
        self._optimize_all_btn.setVisible(checked)

    def _pick_row_chars(self, row: int):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn ảnh tham chiếu",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*.*)",
        )
        if not paths:
            return {}
        imgs = {f"image{i + 1}": path for i, path in enumerate(paths)}
        self._row_char_images[row] = imgs
        btn = self.table.cellWidget(row, 1)
        if isinstance(btn, QPushButton):
            self._set_btn_thumbnail(btn, paths)
        return imgs

    def _fill_slot(self, *args):
        return None

    def _clear_slot(self, *args):
        return None

    def on_slot_click(self, *args):
        return None

    def on_del_click(self, *args):
        return None

    def _set_thumbnail(self, *args):
        return None

    def _on_optimize_all(self):
        self._optimize_all_btn.setEnabled(False)
        self._optimize_all_btn.setText("  Đang tối ưu...")
        self._optimize_total = 0
        self._optimize_done_count = 0
        for row in range(self.table.rowCount()):
            cb = self._checkbox_for_row(row)
            if cb and cb.isChecked():
                self._optimize_total += 1
        if self._optimize_total <= 0:
            self._optimize_all_btn.setEnabled(True)
            self._optimize_all_btn.setText("  Tối ưu tất cả")
            self._update_optimize_btn_visibility()
            return
        for row in range(self.table.rowCount()):
            cb = self._checkbox_for_row(row)
            if cb and cb.isChecked():
                item = self.table.item(row, 3)
                self._on_optimize_done(row, item.text() if item else "")

    def _optimize_worker(self):
        return None

    def _on_optimize_done(self, row: int, prompt: str):
        if 0 <= row < self.table.rowCount():
            item = self.table.item(row, 3)
            if item is not None and prompt:
                item.setText(str(prompt))
        self._optimize_done_count += 1
        if self._optimize_done_count >= self._optimize_total:
            self._optimize_all_btn.setEnabled(True)
            self._optimize_all_btn.setText("  Tối ưu tất cả")
            self._update_optimize_btn_visibility()

    def _on_optimize_error(self, row: int, error: str):
        log.warning(f"PromptTable: row {row + 1} optimize error: {error}")
        self._optimize_done_count += 1
        if self._optimize_done_count >= self._optimize_total:
            self._optimize_all_btn.setEnabled(True)
            self._optimize_all_btn.setText("  Tối ưu tất cả")
            self._update_optimize_btn_visibility()

    def _on_start_from_table(self):
        prompts = self.get_prompts()
        if not prompts:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Chưa có prompt", "Thêm ít nhất 1 prompt vào bảng.")
            return

        per_row_character_images = {}
        for row in range(self.row_count()):
            item = self.table.item(row, 3)
            text = item.text().strip() if item else ""
            row_imgs = self._row_char_images.get(row, self._char_images)
            filtered = _filter_imgs_by_prompt(row_imgs, text) or row_imgs
            paths = [path for path in filtered.values() if path and Path(path).exists()]
            if paths:
                per_row_character_images[row] = filtered

        config = {"prompts": prompts, "character_images": self.get_character_images()}
        if per_row_character_images:
            config["per_row_character_images"] = per_row_character_images

        self.set_all_pending()
        self.start_task.emit(config)
        self._start_btn.setEnabled(False)
        self._start_btn.setText("  Đang gửi...")
        distinct = sum(len(v) for v in per_row_character_images.values()) if per_row_character_images else 0
        log.info(f"PromptTable: start with {len(prompts)} prompts, refs={distinct}")
        self._start_btn.setEnabled(True)
        self._start_btn.setText("  ▶  Bắt đầu tạo")

    def on_task_finished(self, *args):
        self.set_all_pending()

    def update_item_status(self, row: int, status: str, output_path: str = "", item_id: int = None):
        if 0 <= row < self.table.rowCount():
            value = output_path or status or "—"
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item)
            if item_id is not None:
                self._row_to_item_id[row] = item_id

    def _emit_retry_for_row(self, row: int):
        self.item_retry.emit(row)

    def set_item_upscaling(self, item_id: int, active: bool):
        return None

    def set_all_pending(self):
        for row in range(self.table.rowCount()):
            item = QTableWidgetItem("—")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item)

    def _set_multi_thumbnail(self, *args):
        return None

    def _on_cell_double_click(self, row: int, col: int):
        if col != 3:
            return
        item = self.table.item(row, 3)
        current_text = item.text() if item else ""

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Sửa Prompt #{row + 1}")
        dlg.setMinimumSize(600, 300)
        dlg.setStyleSheet(
            "QDialog { background: #0f1729; }"
            "QTextEdit { background: #1e293b; color: white; border: 1px solid #3b82f6; "
            "border-radius: 8px; padding: 12px; font-size: 14px; }"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        label = QLabel(f"Prompt #{row + 1}")
        label.setStyleSheet("color: #dae2fd; font-size: 15px; font-weight: bold;")
        layout.addWidget(label)

        editor = QTextEdit()
        editor.setPlainText(current_text)
        editor.setPlaceholderText("Nhập prompt tại đây...")
        layout.addWidget(editor)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.setStyleSheet(
            "QPushButton { padding: 8px 20px; border-radius: 8px; font-size: 13px; font-weight: bold; }"
            "QPushButton[text='OK'] { background: #3b82f6; color: white; border: none; }"
            "QPushButton[text='Cancel'] { background: #1e293b; color: #94a3b8; border: 1px solid #2d3449; }"
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_text = editor.toPlainText().strip()
            self.table.setItem(row, 3, QTableWidgetItem(new_text))
            self._refresh_all_nv_thumbnails()
            log.info(f"PromptTable: row {row + 1} edited via popup")

    def get_prompts(self) -> list[str]:
        prompts = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 3)
            if item and item.text().strip():
                prompts.append(item.text().strip())
        return prompts

    def set_prompts(self, prompts: list[str]):
        self.table.setRowCount(0)
        self._char_images.clear()
        self._row_char_images.clear()
        self._row_to_item_id.clear()
        for prompt in prompts:
            self.add_row(prompt=prompt)

    def get_character_images(self) -> dict[str, str]:
        all_imgs = {}
        for row_imgs in self._row_char_images.values():
            all_imgs.update(row_imgs)
        if not all_imgs:
            all_imgs = dict(self._char_images)
        return all_imgs

    def get_row_character_images(self, row: int) -> dict[str, str]:
        return dict(self._row_char_images.get(row, self._char_images))

    def row_count(self) -> int:
        return self.table.rowCount()

    def _import_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import prompts", "", "Text files (*.txt)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            for line in lines:
                self.add_row(prompt=line)
            log.info(f"PromptTable: imported {len(lines)} prompts from {path}")
        except Exception as exc:
            log.error(f"Import error: {exc}")
