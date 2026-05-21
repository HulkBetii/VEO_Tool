"""NAV TOOLS - YouTube to Prompt page."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
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
from services.youtube_analyzer import DEFAULT_STYLE_PRESET, STYLE_PRESETS, YouTubeAnalyzer, assemble_prompt
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


class YouTubePromptPage(QWidget):
    send_to_char_video = Signal(list)
    send_to_video_flow = Signal(list)
    auto_start_config = Signal(dict)
    start_video_task = Signal(dict)
    send_single_prompt = Signal(dict)
    cancel_video_task = Signal()
    concat_videos = Signal()
    retry_video_row = Signal(int)

    youtube_start_video = start_video_task
    youtube_cancel = cancel_video_task
    youtube_retry_row = retry_video_row
    youtube_auto_start = auto_start_config
    youtube_send = send_single_prompt

    _concat_done_signal = Signal(str)
    _concat_error_signal = Signal(str)

    def __init__(self, db=None, browser_mgr=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._browser_mgr = browser_mgr
        self._analyzer = None
        self._results = []
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

    def _on_suggest_context(self):
        url = self.url_input.text().strip()
        if not url:
            self.status_label.setText("Nhap URL YouTube truoc.")
            return
        self._on_suggestion_ready(f"Context from URL: {url}")

    def _on_suggestion_ready(self, text):
        self.global_context_edit.setPlainText(str(text or ""))
        self.status_label.setText("Da cap nhat global context.")

    def _on_quick_mode_toggled(self, checked):
        return None

    def _on_voice_gender_changed(self, idx=0):
        return None

    def _quick_check_duration(self, url="", return_=0):
        return 0

    def _get_character_aliases(self):
        if not hasattr(self, "image_grid") or not self.image_grid:
            return []
        return sorted(self.image_grid.get_images().keys())

    def _init_ui(self):
        self.setObjectName("youtubePromptPage")
        self.setStyleSheet(
            """
            QWidget#youtubePromptPage {
                background: #0b1326;
            }
            QWidget#youtubePromptPage QScrollArea,
            QWidget#youtubePromptPage QWidget {
                background: transparent;
            }
            QWidget#youtubePromptPage QLineEdit,
            QWidget#youtubePromptPage QPlainTextEdit,
            QWidget#youtubePromptPage QTableWidget,
            QWidget#youtubePromptPage QComboBox,
            QWidget#youtubePromptPage QSpinBox {
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
        title = QLabel("YouTube -> Prompt")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #e2e8f0;")
        subtitle = QLabel("Dán URL video, thêm ảnh tham chiếu và style để tạo prompt theo từng cảnh.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")
        ll.addWidget(title)
        ll.addWidget(subtitle)

        ll.addWidget(_field_label("URL YouTube"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://youtube.com/watch?v=...")
        ll.addWidget(self.url_input)

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

        option_row = QHBoxLayout()
        self._whisper_check = QCheckBox("Dùng Whisper")
        self._translate_vi_check = QCheckBox("Dịch transcript")
        self._quick_check = QCheckBox("Quick mode")
        self._quick_check.toggled.connect(self._on_quick_mode_toggled)
        option_row.addWidget(self._whisper_check)
        option_row.addWidget(self._translate_vi_check)
        option_row.addWidget(self._quick_check)
        ll.addLayout(option_row)
        self._auto_detect_scenes_cb = self._quick_check

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

        self._parallel_hint = QLabel("Mỗi account có thể chạy song song theo giới hạn concurrent.")
        self._parallel_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        self._lbl_estimated_time = QLabel("Ước tính: chưa có dữ liệu")
        self._lbl_estimated_time.setStyleSheet("color: #64748b; font-size: 11px;")
        ll.addWidget(self._parallel_hint)
        ll.addWidget(self._lbl_estimated_time)

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
        self._btn_suggest_ctx = QPushButton("Gợi ý context")
        self.start_btn = QPushButton("Bắt đầu tạo video")
        self.copy_btn = QPushButton("Copy prompts")
        self.cancel_btn = QPushButton("Dừng")
        self.reset_btn = QPushButton("Reset")
        self.reset_to_ai_btn = QPushButton("Reset về AI")
        self._btn_concat = QPushButton("Nối video")
        self.start_btn.setMinimumHeight(36)
        # Inline style so it overrides the page's transparent-background rule and
        # always renders as a clearly-clickable primary action button.
        _start_btn_qss = (
            "QPushButton {"
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #4d8eff,stop:1 #3b82f6);"
            "  color: #ffffff; font-weight: bold; font-size: 14px;"
            "  border: none; border-radius: 6px;"
            "}"
            "QPushButton:hover {"
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #6ba1ff,stop:1 #4d8eff);"
            "}"
            "QPushButton:pressed { background-color: #2563eb; }"
            "QPushButton:disabled { background-color: #1a2240; color: #424754; }"
        )
        self.start_btn.setStyleSheet(_start_btn_qss)
        primary_row.addWidget(self.analyze_btn)
        primary_row.addWidget(self._btn_suggest_ctx)
        secondary_row.addWidget(self.start_btn)
        secondary_row.addWidget(self.cancel_btn)
        utility_row.addWidget(self.copy_btn)
        utility_row.addWidget(self.reset_btn)
        utility_row.addWidget(self.reset_to_ai_btn)
        utility_row.addWidget(self._btn_concat)
        ll.addLayout(primary_row)
        ll.addLayout(secondary_row)
        ll.addLayout(utility_row)

        self.analyze_btn.clicked.connect(self._on_analyze)
        self._btn_suggest_ctx.clicked.connect(self._on_suggest_context)
        self.start_btn.clicked.connect(self._on_start)
        self.copy_btn.clicked.connect(self._on_copy)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.reset_btn.clicked.connect(self._on_reset)
        self.reset_to_ai_btn.clicked.connect(self._on_reset_all_to_ai)
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
        self._btn_start_header = QPushButton("Tạo video")
        self._btn_start_header.setMinimumHeight(32)
        self._btn_start_header.setStyleSheet(_start_btn_qss)
        self._btn_start_header.clicked.connect(self._on_start)
        self._btn_copy_json = QPushButton("Copy JSON")
        self._btn_copy_json.clicked.connect(self._on_copy_json)
        self._btn_load_more = QPushButton("Tải thêm cảnh")
        self._btn_load_more.clicked.connect(self._on_load_more_scenes)
        head.addWidget(self.count_label)
        head.addStretch()
        head.addWidget(self._btn_start_header)
        head.addWidget(self._btn_copy_json)
        head.addWidget(self._btn_load_more)
        rl.addLayout(head)

        self._lbl_warnings = QLabel("")
        self._lbl_warnings.setVisible(False)
        self._lbl_warnings.setWordWrap(True)
        rl.addWidget(self._lbl_warnings)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#", "Time", "Transcript", "Prompt", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().resizeSection(0, 44)
        self.table.horizontalHeader().resizeSection(1, 90)
        self.table.horizontalHeader().resizeSection(2, 260)
        self.table.horizontalHeader().resizeSection(4, 120)
        self.table.horizontalHeader().setStretchLastSection(False)
        from PySide6.QtWidgets import QHeaderView

        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        rl.addWidget(self.table, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        rl.addWidget(self.progress_bar)

        splitter.addWidget(right)
        splitter.setSizes([430, 980])

        self._start_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._start_shortcut.activated.connect(self._on_start)
        self._start_shortcut_mac = QShortcut(QKeySequence("Meta+Return"), self)
        self._start_shortcut_mac.activated.connect(self._on_start)

    def _label(self, text):
        return QLabel(str(text))

    def _auto_fit_concurrent(self, prompts_count=0):
        return None

    def _refresh_credit_labels(self):
        count = len(self._get_prompts_from_table())
        self._credit_total_label.setText(f"Tổng: ~{count} credit")
        self._lbl_estimated_time.setText(f"Ước tính: {count * 8}s video")

    def _restore_analyze_button(self):
        self.progress_bar.hide()
        self.analyze_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.analyze_btn.setText("Phân tích")

    def _do_analyze_validation(self):
        if not self.url_input.text().strip():
            QMessageBox.warning(self, "YouTube", "Thiếu URL YouTube.")
            return False
        return True

    def _on_analyze(self):
        if not self._do_analyze_validation():
            return
        self.analyze_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.analyze_btn.setText("Đang phân tích...")
        self._worker_signals = _WorkerSignals()
        self._worker_signals.progress.connect(self._on_progress, type=Qt.ConnectionType.QueuedConnection)
        self._worker_signals.finished.connect(self._on_finished, type=Qt.ConnectionType.QueuedConnection)
        self._worker_signals.error.connect(self._on_error, type=Qt.ConnectionType.QueuedConnection)
        self.progress_bar.show()
        url = self.url_input.text().strip()
        thread = threading.Thread(
            target=self._worker_thread,
            args=(url, self._get_character_aliases(), self.style_lock_edit.toPlainText().strip(), self.global_context_edit.toPlainText().strip(), self._whisper_check.isChecked(), self._quick_check.isChecked(), self._translate_vi_check.isChecked(), self.voice_gender_combo.currentData() or ""),
            daemon=True,
        )
        thread.start()

    def _worker_thread(self, url="", character_aliases=None, style_lock="", global_context="", use_whisper=False, quick_mode=False, translate_to_vi=False, voice_gender=""):
        try:
            analyzer = self._analyzer or YouTubeAnalyzer()
            self._analyzer = analyzer
            result = asyncio.run(
                analyzer.analyze(
                    url,
                    self._load_api_key(),
                    style_lock=style_lock,
                    global_context=global_context,
                    character_aliases=character_aliases,
                    use_whisper=use_whisper,
                    quick_mode=quick_mode,
                    translate_to_vi=translate_to_vi,
                    voice_gender=voice_gender,
                    progress_cb=lambda msg: self._worker_signals.progress.emit(str(msg)),
                )
            )
            self._worker_signals.finished.emit(result)
        except Exception as e:
            self._worker_signals.error.emit(str(e))

    def _worker_thread_LEGACY_v1(self, url="", alias=""):
        return self._worker_thread(url, [alias] if alias else [])

    def _on_progress(self, message, current=0, total=0):
        self.status_label.setText(str(message))

    def _on_finished(self, result):
        self._restore_analyze_button()
        scenes = result.get("scenes", result.get("captions", [])) if isinstance(result, dict) else result
        self._results = list(scenes or [])
        self.table.setRowCount(0)
        for row, item in enumerate(self._results):
            self._populate_row(row, item)
        self.count_label.setText(f"{len(self._results)} cảnh")
        self.status_label.setText("Phân tích xong.")
        self.copy_btn.setEnabled(bool(self._results))
        self._refresh_credit_labels()

    def _on_load_more_scenes(self):
        self._on_analyze()

    def _populate_row(self, row: int, item: dict):
        self.table.insertRow(row)
        prompt = item.get("prompt") or assemble_prompt(
            scene_num=item.get("scene_num", row + 1),
            subject_desc=item.get("subject_desc", item.get("transcript", "")),
            narration=item.get("transcript", ""),
            style_desc=self.style_lock_edit.toPlainText().strip() or STYLE_PRESETS.get(DEFAULT_STYLE_PRESET, ""),
        )
        self.table.setItem(row, 0, QTableWidgetItem(str(item.get("scene_num", row + 1))))
        self.table.setItem(row, 1, QTableWidgetItem(f"{item.get('start', 0)} - {item.get('end', 0)}"))
        self.table.setItem(row, 2, QTableWidgetItem(str(item.get("transcript", ""))))
        self.table.setItem(row, 3, QTableWidgetItem(prompt))
        self.table.setItem(row, 4, QTableWidgetItem(str(item.get("status", "Sẵn sàng"))))

    def _on_error(self, error_msg: str):
        self._restore_analyze_button()
        self.status_label.setText(f"Lỗi: {error_msg}")
        QMessageBox.warning(self, "YouTube analyzer", str(error_msg))

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
        if self._analyzer and hasattr(self._analyzer, "cancel"):
            self._analyzer.cancel()
        self.cancel_video_task.emit()
        self.progress_bar.hide()
        self.cancel_btn.setEnabled(False)

    def _get_prompts_from_table(self):
        prompts = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 3)
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
        self._on_style_extracted(f"Reference visual style from {names}. Keep palette, lighting and camera language consistent.")

    def _on_style_extracted(self, text):
        self.style_lock_edit.setPlainText(str(text))

    def _on_prompt_edited(self, row: int):
        return None

    def _on_prompt_edited_v2(self, row: int, new_text: str):
        if self.table.item(row, 3):
            self.table.item(row, 3).setText(new_text)

    def _on_regenerate_scene(self, row: int):
        self.retry_video_row.emit(row)

    def _on_scene_updated(self, row: int, new_result: dict):
        if 0 <= row < self.table.rowCount():
            self.table.setItem(row, 2, QTableWidgetItem(str(new_result.get("transcript", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(str(new_result.get("prompt", ""))))

    def _on_change_shot_menu(self, row: int):
        return None

    def _on_change_shot_selected(self, row: int, new_shot: str):
        return self._rebuild_with_manual_shot(row, new_shot)

    def _rebuild_with_manual_shot(self, scene_result: int, new_shot_type: str):
        item = self.table.item(scene_result, 3)
        if item:
            item.setText(f"{new_shot_type}, {item.text()}")
        return {"prompt": item.text() if item else ""}

    def _on_send_single(self, row: int):
        item = self.table.item(row, 3)
        if item and item.text().strip():
            self.send_single_prompt.emit({"prompts": [item.text().strip()]})

    def _on_copy_json(self):
        QApplication.clipboard().setText(str(self._get_prompts_from_table()))

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục output")
        if folder:
            self.output_edit.setText(folder)

    def _on_start(self):
        prompts = self._get_prompts_from_table()
        if not prompts:
            self.status_label.setText("Chưa có prompt nào — hãy phân tích YouTube trước.")
            return

        # Pre-flight: require at least one enabled Google account.
        if self._db:
            try:
                accounts = self._db.get_accounts(enabled_only=True)
            except Exception:
                accounts = []
            if not accounts:
                QMessageBox.warning(
                    self,
                    "Chưa có tài khoản",
                    "Chưa cấu hình tài khoản Google nào.\n"
                    "Vui lòng thêm tài khoản trong mục Cài đặt.",
                )
                return

        char_images = self.image_grid.get_images() if hasattr(self, "image_grid") else {}
        mode = "char_video" if char_images else "video_plain"
        config = {
            "prompts": prompts,
            "quality": self.quality_combo.currentText(),
            "aspect_ratio": self.ar_combo.currentData() or self.ar_combo.currentText(),
            "output_folder": self.output_edit.text().strip(),
            "character_images": char_images,
            "mode": mode,
            "concurrent": self.concurrent_spin.value(),
            "parallel_per_account": self.concurrent_spin.value(),
        }
        self.status_label.setText(f"Đang tạo {len(prompts)} video… Xem log để theo dõi tiến trình.")
        self.start_btn.setEnabled(False)
        self._btn_start_header.setEnabled(False)
        self.start_video_task.emit(config)

    def update_item_status(self, row: int, status: str, output_path: str = ""):
        if 0 <= row < self.table.rowCount():
            self.table.setItem(row, 4, QTableWidgetItem(str(output_path or status)))

    def _on_reset_all_to_ai(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 3)
            src = self.table.item(row, 2)
            if item is None or src is None:
                continue
            item.setText(
                assemble_prompt(
                    scene_num=row + 1,
                    subject_desc=src.text(),
                    narration=src.text(),
                    style_desc=self.style_lock_edit.toPlainText().strip() or self._style_lock_original,
                )
            )
        self.status_label.setText("Đã reset prompt về AI.")

    def _on_reset(self):
        self.url_input.clear()
        if hasattr(self, "image_grid"):
            self.image_grid.clear()
        self.table.setRowCount(0)
        self._results = []
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
        self.start_btn.setEnabled(True)
        self._btn_start_header.setEnabled(True)
        self.status_label.setText("Hoàn thành. Kiểm tra thư mục output.")
        self.update_item_status(0, "DONE")

    def _on_copy(self):
        prompts = self._get_prompts_from_table()
        QApplication.clipboard().setText("\n".join(prompts))
        self.copy_btn.setText("Đã copy")
        QTimer.singleShot(2000, lambda: self.copy_btn.setText("Copy prompts"))
        log.info(f"Copied {len(prompts)} YouTube prompts to clipboard")
