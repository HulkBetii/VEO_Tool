"""NAV TOOLS - Script/idea to multi-scene prompt page."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.constants import DEFAULT_VIDEO_OUTPUT
from services.script_analyzer import MAX_SCRIPT_SCENES, ScriptAnalyzer
from services.youtube_analyzer import DEFAULT_STYLE_PRESET, STYLE_PRESETS, assemble_prompt
from ui.widgets.image_grid import ImageGrid
from utils.logger import log


STYLE_PRESET_LABELS_VI = {
    "cinematic": "Dien anh",
    "anime": "Anime",
    "3d": "3D",
    "watercolor": "Mau nuoc",
    "comic": "Truyen tranh",
    "stick_figure": "Nguoi que",
}


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 600;")
    return label


class _WorkerSignals(QObject):
    progress = Signal(str)
    finished = Signal(object)
    error = Signal(str)


class ScriptToPromptPage(QWidget):
    send_to_char_video = Signal(list)
    send_to_video_flow = Signal(list)
    auto_start_config = Signal(dict)
    start_video_task = Signal(dict)
    send_single_prompt = Signal(dict)
    cancel_single_prompt = Signal(int)
    cancel_video_task = Signal()
    concat_videos = Signal()
    retry_video_row = Signal(int)

    script_start_video = start_video_task
    script_cancel = cancel_video_task
    script_retry_row = retry_video_row
    script_send_single_prompt = send_single_prompt
    script_cancel_single_prompt = cancel_single_prompt

    _concat_done_signal = Signal(str)
    _concat_error_signal = Signal(str)

    def __init__(self, db=None, browser_mgr=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._browser_mgr = browser_mgr
        self._analyzer = None
        self._results = []
        self._send_btns = {}
        self._regen_btns = {}
        self._last_state = None
        self._session_api_key = None
        self._warnings = []
        self._style_lock_original = STYLE_PRESETS.get(DEFAULT_STYLE_PRESET, "")
        self._ref_image_paths = []
        self._init_ui()
        self._concat_done_signal.connect(self._on_concat_done)
        self._concat_error_signal.connect(self._on_concat_error)

    def _load_api_key(self):
        if not hasattr(self, "_api_keys"):
            self._api_keys = []
            self._api_key_index = 0
        if not self._api_keys and self._db:
            from config.settings import Settings

            raw_value = Settings(self._db).get("gemini_api_key", "") or ""
            self._api_keys = [line.strip() for line in str(raw_value).splitlines() if line.strip()]
        if not self._api_keys:
            return ""
        key = self._api_keys[self._api_key_index % len(self._api_keys)]
        self._api_key_index += 1
        return key

    def _clear_session_secrets(self):
        self._session_api_key = None
        self._api_keys = []
        self._api_key_index = 0

    def hideEvent(self, event):
        self._clear_session_secrets()
        super().hideEvent(event)

    def _save_analyze_state(self, **kwargs):
        self._last_state = dict(kwargs)

    def _on_voice_gender_changed(self, idx=0):
        return None

    def _get_character_aliases(self):
        if not hasattr(self, "image_grid") or not self.image_grid:
            return []
        return sorted(self.image_grid.get_images().keys())

    def _init_ui(self):
        self.setObjectName("scriptPromptPage")
        self.setStyleSheet(
            """
            QWidget#scriptPromptPage {
                background: #0b1326;
            }
            QWidget#scriptPromptPage QScrollArea,
            QWidget#scriptPromptPage QWidget {
                background: transparent;
            }
            QWidget#scriptPromptPage QLineEdit,
            QWidget#scriptPromptPage QPlainTextEdit,
            QWidget#scriptPromptPage QTableWidget,
            QWidget#scriptPromptPage QComboBox,
            QWidget#scriptPromptPage QSpinBox {
                background: #131b2e;
            }
            """
        )
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left_scroll = QScrollArea()
        left_scroll.setFixedWidth(430)
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(12)
        title = QLabel("Ý tưởng -> Video")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        subtitle = QLabel("Nhập ý tưởng hoặc kịch bản, chia scene và tạo prompt Veo theo từng cảnh.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")
        ll.addWidget(title)
        ll.addWidget(subtitle)

        ll.addWidget(_field_label("Kịch bản / ý tưởng"))
        self.script_input = QPlainTextEdit()
        self.script_input.setMinimumHeight(140)
        ll.addWidget(self.script_input)

        row = QHBoxLayout()
        row.addWidget(_field_label("Số cảnh"))
        self.scene_count_spin = QSpinBox()
        self.scene_count_spin.setRange(2, MAX_SCRIPT_SCENES)
        self.scene_count_spin.setValue(8)
        self.scene_count_spin.setSuffix(" cảnh")
        row.addWidget(self.scene_count_spin)
        row.addStretch()
        ll.addLayout(row)

        self.auto_detect_scenes_cb = QCheckBox("Tự nhận diện số cảnh")
        self.auto_detect_scenes_cb.toggled.connect(lambda on: self.scene_count_spin.setEnabled(not bool(on)))
        ll.addWidget(self.auto_detect_scenes_cb)

        ll.addWidget(_field_label("Ảnh nhân vật tham chiếu"))
        self.image_grid = ImageGrid(show_dispatch_hint=True)
        self.image_grid.setMaximumHeight(240)
        ll.addWidget(self.image_grid)
        ref_row = QHBoxLayout()
        self._btn_add_ref = QPushButton("Thêm ảnh ref")
        self._btn_add_ref.clicked.connect(self._on_add_ref_image)
        self._btn_extract_style = QPushButton("Rút style từ ref")
        self._btn_extract_style.setEnabled(False)
        self._btn_extract_style.clicked.connect(self._on_extract_style_from_refs)
        ref_row.addWidget(self._btn_add_ref)
        ref_row.addWidget(self._btn_extract_style)
        ll.addLayout(ref_row)
        self._lbl_ref_count = QLabel("0 ảnh ref bổ sung")
        self._lbl_ref_count.setStyleSheet("color: #94a3b8; font-size: 11px;")
        ll.addWidget(self._lbl_ref_count)

        ll.addWidget(_field_label("Global Context"))
        self.global_context_edit = QPlainTextEdit()
        self.global_context_edit.setFixedHeight(70)
        ll.addWidget(self.global_context_edit)

        preset_row = QHBoxLayout()
        self.style_preset_combo = QComboBox()
        for key in STYLE_PRESETS.keys():
            self.style_preset_combo.addItem(STYLE_PRESET_LABELS_VI.get(key, key), key)
        if DEFAULT_STYLE_PRESET in STYLE_PRESETS:
            self.style_preset_combo.setCurrentIndex(list(STYLE_PRESETS.keys()).index(DEFAULT_STYLE_PRESET))
        self.style_preset_combo.currentIndexChanged.connect(self._on_style_preset_changed_idx)
        preset_row.addWidget(self.style_preset_combo, 1)
        self.voice_gender_combo = QComboBox()
        self.voice_gender_combo.addItem("Không rõ", "")
        self.voice_gender_combo.addItem("Nam", "male")
        self.voice_gender_combo.addItem("Nữ", "female")
        self.voice_gender_combo.currentIndexChanged.connect(self._on_voice_gender_changed)
        preset_row.addWidget(self.voice_gender_combo, 1)
        ll.addLayout(preset_row)

        ll.addWidget(_field_label("Style lock"))
        self.style_lock_edit = QPlainTextEdit()
        self.style_lock_edit.setPlainText(self._style_lock_original)
        self.style_lock_edit.setFixedHeight(90)
        ll.addWidget(self.style_lock_edit)

        quality_row = QHBoxLayout()
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Veo 3.1 - Fast", "Veo 3.1 - Quality"])
        self.quality_combo.currentTextChanged.connect(self._refresh_credit_labels)
        quality_row.addWidget(self.quality_combo, 1)
        self.ar_combo = QComboBox()
        self.ar_combo.addItem("16:9", "16:9")
        self.ar_combo.addItem("9:16", "9:16")
        self.ar_combo.addItem("1:1", "1:1")
        self.ar_combo.currentTextChanged.connect(self._refresh_credit_labels)
        quality_row.addWidget(self.ar_combo, 1)
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 20)
        self.concurrent_spin.setValue(3)
        quality_row.addWidget(self.concurrent_spin)
        ll.addLayout(quality_row)

        self._parallel_hint = QLabel("Concurrent áp dụng cho số cảnh gửi song song.")
        self._parallel_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        ll.addWidget(self._parallel_hint)

        ll.addWidget(_field_label("Thư mục output"))
        out_row = QHBoxLayout()
        self.output_edit = QLineEdit(str(DEFAULT_VIDEO_OUTPUT))
        browse = QPushButton("Chọn thư mục")
        browse.clicked.connect(self._browse_output)
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(browse)
        ll.addLayout(out_row)

        primary_row = QHBoxLayout()
        secondary_row = QHBoxLayout()
        utility_row = QHBoxLayout()
        self.analyze_btn = QPushButton("Phân tích")
        self.start_btn = QPushButton("Bắt đầu tạo video")
        self.copy_btn = QPushButton("Copy prompts")
        self.cancel_btn = QPushButton("Dừng")
        self.reset_btn = QPushButton("Reset")
        self._btn_concat = QPushButton("Nối video")
        self.start_btn.setMinimumHeight(36)
        primary_row.addWidget(self.analyze_btn)
        primary_row.addWidget(self.start_btn)
        secondary_row.addWidget(self.copy_btn)
        secondary_row.addWidget(self.cancel_btn)
        utility_row.addWidget(self.reset_btn)
        utility_row.addWidget(self._btn_concat)
        ll.addLayout(primary_row)
        ll.addLayout(secondary_row)
        ll.addLayout(utility_row)
        self.analyze_btn.clicked.connect(self._on_analyze)
        self.start_btn.clicked.connect(self._on_start)
        self.copy_btn.clicked.connect(self._on_copy)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.reset_btn.clicked.connect(self._on_reset)
        self._btn_concat.clicked.connect(self._on_concat_videos)
        self.copy_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self.status_label)

        credit_row = QHBoxLayout()
        self._credit_per_video_label = QLabel("~1 credit / video")
        self._credit_total_label = QLabel("Tổng: 0 credit")
        credit_row.addWidget(self._credit_per_video_label)
        credit_row.addStretch()
        credit_row.addWidget(self._credit_total_label)
        ll.addLayout(credit_row)

        left_scroll.setWidget(left)
        splitter.addWidget(left_scroll)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 12, 12, 12)
        rl.setSpacing(10)
        head = QHBoxLayout()
        self.count_label = QLabel("0 cảnh")
        self._btn_copy_json = QPushButton("Copy JSON")
        self._btn_copy_json.clicked.connect(self._on_copy_json)
        self._btn_load_more = QPushButton("Tăng số cảnh")
        self._btn_load_more.clicked.connect(self._on_load_more_scenes)
        head.addWidget(self.count_label)
        head.addStretch()
        head.addWidget(self._btn_copy_json)
        head.addWidget(self._btn_load_more)
        rl.addLayout(head)

        self._lbl_warnings = QLabel("")
        self._lbl_warnings.setVisible(False)
        self._lbl_warnings.setWordWrap(True)
        rl.addWidget(self._lbl_warnings)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "Narration", "Prompt", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().resizeSection(0, 44)
        self.table.horizontalHeader().resizeSection(1, 300)
        self.table.horizontalHeader().resizeSection(3, 120)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        rl.addWidget(self.table, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        rl.addWidget(self.progress_bar)

        splitter.addWidget(right)
        splitter.setSizes([430, 980])

    def _label(self, text):
        return QLabel(str(text))

    def _auto_fit_concurrent(self, prompts_count=0):
        return None

    def _refresh_credit_labels(self):
        count = len(self._get_prompts_from_table())
        self._credit_total_label.setText(f"Tổng: ~{count} credit")

    def _restore_analyze_button(self):
        self.progress_bar.hide()
        self.analyze_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.analyze_btn.setText("Phân tích")

    def _do_analyze_validation(self):
        return bool(self.script_input.toPlainText().strip())

    def _on_analyze(self):
        if not self._do_analyze_validation():
            QMessageBox.warning(self, "Ý tưởng", "Chưa có nội dung kịch bản/ý tưởng.")
            return
        self.analyze_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.analyze_btn.setText("Đang phân tích...")
        self._worker_signals = _WorkerSignals()
        self._worker_signals.progress.connect(self._on_progress, type=Qt.ConnectionType.QueuedConnection)
        self._worker_signals.finished.connect(self._on_finished, type=Qt.ConnectionType.QueuedConnection)
        self._worker_signals.error.connect(self._on_error, type=Qt.ConnectionType.QueuedConnection)
        self.progress_bar.show()
        thread = threading.Thread(
            target=self._worker_thread,
            args=(self.script_input.toPlainText().strip(), self.scene_count_spin.value(), self._get_character_aliases(), self.style_lock_edit.toPlainText().strip(), self.global_context_edit.toPlainText().strip(), STYLE_PRESETS.get(self.style_preset_combo.currentData() or DEFAULT_STYLE_PRESET, ""), self.voice_gender_combo.currentData() or "", self.auto_detect_scenes_cb.isChecked()),
            daemon=True,
        )
        thread.start()

    def _worker_thread(self, script_text="", num_scenes=8, character_aliases=None, style_lock="", global_context="", style_preset_desc="", voice_gender="", auto_detect_scenes=False):
        try:
            analyzer = self._analyzer or ScriptAnalyzer()
            self._analyzer = analyzer
            result = asyncio.run(
                analyzer.analyze_script(
                    script_text,
                    num_scenes,
                    self._load_api_key(),
                    style_preset_desc=style_preset_desc,
                    style_lock=style_lock,
                    global_context=global_context,
                    character_aliases=character_aliases,
                    voice_gender=voice_gender,
                    auto_detect_scenes=auto_detect_scenes,
                    progress_cb=lambda current, total, message: self._worker_signals.progress.emit(str(message)),
                )
            )
            self._worker_signals.finished.emit(result)
        except Exception as e:
            self._worker_signals.error.emit(str(e))

    def _worker_thread_LEGACY_v1(self, url="", alias=""):
        return self._worker_thread(url)

    def _on_progress(self, message, current=0, total=0):
        self.status_label.setText(str(message))

    def _on_finished(self, result):
        self._restore_analyze_button()
        scenes = result.get("scenes", result) if isinstance(result, dict) else result
        self._results = list(scenes or [])
        self.table.setRowCount(0)
        for row, item in enumerate(self._results):
            self._populate_row(row, item)
        self.count_label.setText(f"{len(self._results)} cảnh")
        self.status_label.setText("Đã chia scene xong.")
        self.copy_btn.setEnabled(bool(self._results))
        self._refresh_credit_labels()

    def _on_load_more_scenes(self):
        self.scene_count_spin.setValue(min(MAX_SCRIPT_SCENES, self.scene_count_spin.value() + 4))
        self._on_analyze()

    def _populate_row(self, row: int, item: dict):
        self.table.insertRow(row)
        prompt = item.get("prompt") or assemble_prompt(
            scene_num=item.get("scene_num", row + 1),
            subject_desc=item.get("subject_desc", item.get("narration", "")),
            narration=item.get("narration", ""),
            style_desc=self.style_lock_edit.toPlainText().strip() or STYLE_PRESETS.get(DEFAULT_STYLE_PRESET, ""),
        )
        self.table.setItem(row, 0, QTableWidgetItem(str(item.get("scene_num", row + 1))))
        self.table.setItem(row, 1, QTableWidgetItem(str(item.get("narration", ""))))
        self.table.setItem(row, 2, QTableWidgetItem(prompt))
        self.table.setItem(row, 3, QTableWidgetItem(str(item.get("status", "Sẵn sàng"))))

    def _on_error(self, error_msg: str):
        self._restore_analyze_button()
        self.status_label.setText(f"Lỗi: {error_msg}")
        QMessageBox.warning(self, "Script analyzer", str(error_msg))

    def _on_concat_videos(self):
        self.concat_videos.emit()

    def _sorted_mp4s(self, folder):
        return sorted(Path(folder).glob("*.mp4"))

    def _concat_worker(self, *args):
        return None

    def _on_concat_done(self, merged_path):
        QMessageBox.information(self, "Concat", str(merged_path))

    def _on_concat_error(self, error_msg):
        QMessageBox.warning(self, "Concat", str(error_msg))

    def _on_cancel(self):
        self.cancel_video_task.emit()
        self.progress_bar.hide()
        self.cancel_btn.setEnabled(False)

    def _get_prompts_from_table(self):
        prompts = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if item and item.text().strip():
                prompts.append(item.text().strip())
        return prompts

    def _on_style_preset_changed_idx(self, idx=0):
        return self._on_style_preset_changed(self.style_preset_combo.itemData(idx) or DEFAULT_STYLE_PRESET)

    def _on_style_preset_changed(self, preset_name=""):
        self.style_lock_edit.setPlainText(STYLE_PRESETS.get(preset_name or DEFAULT_STYLE_PRESET, ""))

    def _on_add_ref_image(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn ảnh ref", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not files:
            return
        for path in files:
            if path not in self._ref_image_paths:
                self._ref_image_paths.append(path)
                if hasattr(self.image_grid, "add_image"):
                    self.image_grid.add_image(path)
        self._lbl_ref_count.setText(f"{len(self._ref_image_paths)} ảnh ref bổ sung")
        self._btn_extract_style.setEnabled(bool(self._ref_image_paths))

    def _on_extract_style_from_refs(self):
        if not self._ref_image_paths:
            return
        names = ", ".join(Path(p).stem for p in self._ref_image_paths[:3])
        self._on_style_extracted(f"Reference visual style from {names}. Keep palette, lighting and composition aligned.")

    def _on_style_extracted(self, text):
        self.style_lock_edit.setPlainText(str(text))

    def _on_prompt_edited(self, row: int):
        return None

    def _on_prompt_edited_v2(self, row: int, new_text: str):
        if self.table.item(row, 2):
            self.table.item(row, 2).setText(new_text)

    def _on_regenerate_scene(self, row: int):
        self.retry_video_row.emit(row)

    def _regenerate_worker_thread(self, row: int, script_text="", existing_scenes=None, api_key="", style_preset_desc="", style_lock="", global_context="", character_aliases=None, voice_gender=""):
        return None

    def _on_scene_updated(self, row: int, new_result: dict):
        if 0 <= row < self.table.rowCount():
            self.table.setItem(row, 1, QTableWidgetItem(str(new_result.get("narration", ""))))
            self.table.setItem(row, 2, QTableWidgetItem(str(new_result.get("prompt", ""))))

    def _on_change_shot_menu(self, row: int):
        return None

    def _on_change_shot_selected(self, row: int, new_shot: str):
        return self._rebuild_with_manual_shot(row, new_shot)

    def _rebuild_with_manual_shot(self, scene_result: int, new_shot_type: str):
        item = self.table.item(scene_result, 2)
        if item:
            item.setText(f"{new_shot_type}, {item.text()}")
        return {"prompt": item.text() if item else ""}

    def _on_send_single(self, row: int):
        item = self.table.item(row, 2)
        if item and item.text().strip():
            self.send_single_prompt.emit({"prompt": item.text().strip(), "row": row, "output_folder": self.output_edit.text().strip()})

    def _on_copy_json(self):
        QApplication.clipboard().setText(str(self._get_prompts_from_table()))

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục output")
        if folder:
            self.output_edit.setText(folder)

    def _on_start(self):
        prompts = self._get_prompts_from_table()
        char_images = self.image_grid.get_images() if hasattr(self, "image_grid") else {}
        per_row_character_images = {row: char_images for row in range(len(prompts))} if char_images else {}
        mode = "char_video" if char_images else "video_plain"
        config = {
            "prompts": prompts,
            "quality": self.quality_combo.currentText(),
            "aspect_ratio": self.ar_combo.currentData() or self.ar_combo.currentText(),
            "output_folder": self.output_edit.text().strip(),
            "character_images": char_images,
            "per_row_character_images": per_row_character_images,
            "mode": mode,
            "concurrent": self.concurrent_spin.value(),
            "parallel_per_account": self.concurrent_spin.value(),
        }
        self.start_video_task.emit(config)
        log.info(f"Script start config: {len(prompts)} prompts")

    def update_item_status(self, row: int, status: str, output_path: str = ""):
        if 0 <= row < self.table.rowCount():
            self.table.setItem(row, 3, QTableWidgetItem(str(output_path or status)))

    def _update_send_button_for_status(self, *args):
        return None

    def _on_reset(self):
        self.script_input.clear()
        if hasattr(self, "image_grid"):
            self.image_grid.clear()
        self.table.setRowCount(0)
        self._results = []
        self._send_btns.clear()
        self._regen_btns.clear()
        self._last_state = None
        self.global_context_edit.clear()
        self.style_lock_edit.setPlainText(STYLE_PRESETS.get(DEFAULT_STYLE_PRESET, ""))
        self._style_lock_original = STYLE_PRESETS.get(DEFAULT_STYLE_PRESET, "")
        self._ref_image_paths = []
        self._lbl_ref_count.setText("0 ảnh ref bổ sung")
        self._btn_extract_style.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("")
        self.progress_bar.hide()
        self.count_label.setText("0 cảnh")

    def on_task_finished(self, *args):
        self.update_item_status(0, "DONE")

    def _on_copy(self):
        prompts = self._get_prompts_from_table()
        QApplication.clipboard().setText("\n".join(prompts))
        self.copy_btn.setText("Đã copy")
        QTimer.singleShot(2000, lambda: self.copy_btn.setText("Copy prompts"))
        log.info(f"Copied {len(prompts)} script prompts to clipboard")
