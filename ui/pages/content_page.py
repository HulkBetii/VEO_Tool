"""NAV TOOLS - Base content page with resizable splitter."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from config.constants import CONFIG_PANEL_WIDTH, MODE_LABELS
from ui.widgets.action_bar import ActionBar
from ui.widgets.config_form import ConfigForm
from ui.widgets.image_grid import ImageGrid
from ui.widgets.prompt_editor import PromptEditor
from ui.widgets.prompt_table import PromptTable
from ui.widgets.task_table import TaskTable


_FREE_BADGE_QSS = (
    "background-color: #2d3449; color: #8c909f; border-radius: 4px; "
    "padding: 4px 10px; font-size: 12px; font-weight: bold;"
)
_PAID_BADGE_QSS = (
    "background-color: #1a2a4a; color: #4d8eff; border-radius: 4px; "
    "padding: 4px 10px; font-size: 12px; font-weight: bold;"
)


class ContentPage(QWidget):
    """Two-panel page with resizable splitter: left config + right task table."""

    start_task = Signal(dict)
    open_settings = Signal()

    def __init__(self, mode: str = None, db=None, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._db = db
        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setChildrenCollapsible(False)

        left_widget = QWidget()
        left_widget.setObjectName("configPanel")
        left_widget.setMinimumWidth(400)
        left_outer = QVBoxLayout(left_widget)
        left_outer.setContentsMargins(0, 0, 0, 0)
        left_outer.setSpacing(0)
        left_outer.addWidget(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        config_container = QWidget()
        config_layout = QVBoxLayout(config_container)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(0)

        self.config_form = ConfigForm(mode=self._mode, db=self._db)
        config_layout.addWidget(self.config_form)

        if self._mode in ("char_image", "char_video", "video_ref"):
            img_wrapper = QWidget()
            img_layout = QVBoxLayout(img_wrapper)
            img_layout.setContentsMargins(16, 8, 16, 12)
            img_layout.setSpacing(8)
            self.image_grid = ImageGrid(show_dispatch_hint=self._mode == "video_ref")
            img_layout.addWidget(self.image_grid)
            config_layout.addWidget(img_wrapper)

        prompt_wrapper = QWidget()
        prompt_layout = QVBoxLayout(prompt_wrapper)
        prompt_layout.setContentsMargins(16, 8, 16, 12)
        prompt_layout.setSpacing(8)
        self.prompt_editor = PromptEditor()
        prompt_layout.addWidget(self.prompt_editor)
        config_layout.addWidget(prompt_wrapper)

        action_wrapper = QWidget()
        action_layout = QVBoxLayout(action_wrapper)
        action_layout.setContentsMargins(16, 8, 16, 16)
        action_layout.setSpacing(8)
        self.action_bar = ActionBar(mode=self._mode)
        self.action_bar.start_clicked.connect(self._on_start)
        action_layout.addWidget(self.action_bar)
        config_layout.addWidget(action_wrapper)
        config_layout.addSpacing(20)

        scroll.setWidget(config_container)
        left_outer.addWidget(scroll, 1)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.prompt_table = PromptTable(db=self._db, mode=self._mode)
        self.prompt_table.start_task.connect(self._on_start_from_prompt_table)
        self.task_table = TaskTable(mode=self._mode)
        self.task_table.hide()
        right_layout.addWidget(self.prompt_table)
        right_layout.addWidget(self.task_table)
        splitter.addWidget(right_widget)

        splitter.setSizes([CONFIG_PANEL_WIDTH, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(8)

        title = QLabel(MODE_LABELS.get(self._mode, ""))
        title.setProperty("class", "section-title")
        layout.addWidget(title)

        self.tier_badge = QLabel("Gói: FREE")
        self.tier_badge.setProperty("class", "badge-free")
        self.tier_badge.setStyleSheet(_FREE_BADGE_QSS)
        layout.addWidget(self.tier_badge)
        layout.addStretch()

        self.upgrade_btn = QPushButton("Nâng cấp")
        self.upgrade_btn.setObjectName("btn-primary")
        self.upgrade_btn.setFixedHeight(32)
        self.upgrade_btn.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4d8eff, stop:1 #3b82f6); "
            "color: #fff; border-radius: 6px; padding: 4px 14px; font-weight: bold; font-size: 13px;"
        )
        layout.addWidget(self.upgrade_btn)

        gear_btn = QPushButton("Cài đặt")
        gear_btn.setObjectName("btn-ghost")
        gear_btn.setFixedHeight(32)
        gear_btn.clicked.connect(lambda: self.open_settings.emit())
        layout.addWidget(gear_btn)
        return header

    def set_account_info(self, email: str = "", tier: str = "FREE", credit: int = 0):
        if tier and tier != "FREE":
            self.tier_badge.setText(f"Gói: {tier}")
            self.tier_badge.setStyleSheet(_PAID_BADGE_QSS)
            self.upgrade_btn.hide()
            return
        self.tier_badge.setText("Gói: FREE")
        self.tier_badge.setStyleSheet(_FREE_BADGE_QSS)
        self.upgrade_btn.show()

    def _on_start(self):
        editor_prompts = self.prompt_editor.get_prompts() if hasattr(self, "prompt_editor") else []
        if editor_prompts and hasattr(self, "prompt_table"):
            self.prompt_table.set_prompts(editor_prompts)
            char_images = self.image_grid.get_images() if hasattr(self, "image_grid") else {}
            if char_images:
                from ui.widgets.prompt_table import _filter_imgs_by_prompt

                self.prompt_table._char_images = dict(char_images)
                for row in range(self.prompt_table.row_count()):
                    self.prompt_table._row_char_images[row] = dict(char_images)
                    btn = self.prompt_table.table.cellWidget(row, 1)
                    if not isinstance(btn, QPushButton):
                        continue
                    item = self.prompt_table.table.item(row, 3)
                    prompt_text = item.text().strip() if item else ""
                    filtered = _filter_imgs_by_prompt(char_images, prompt_text)
                    self.prompt_table._set_btn_thumbnail(btn, list(filtered.values()))
            self.prompt_table._on_start_from_table()
            return

        if hasattr(self, "prompt_table") and self.prompt_table.row_count() > 0:
            self.prompt_table._on_start_from_table()
            return

        config = self.config_form.get_config()
        config["mode"] = self._mode
        config["prompts"] = []
        self.start_task.emit(config)

    def _on_start_from_prompt_table(self, table_config: dict):
        config = self.config_form.get_config()
        config["mode"] = self._mode
        config["prompts"] = table_config["prompts"]
        char_images = table_config.get("character_images", {})
        if char_images:
            config["character_images"] = char_images
        elif hasattr(self, "image_grid"):
            config["character_images"] = self.image_grid.get_images()
        if "per_row_character_images" in table_config:
            config["per_row_character_images"] = table_config["per_row_character_images"]
        self.start_task.emit(config)

    def set_left_panel_enabled(self, enabled: bool):
        self.config_form.setEnabled(enabled)
        self.prompt_editor.setEnabled(enabled)
        if hasattr(self, "image_grid"):
            self.image_grid.setEnabled(enabled)
        if hasattr(self, "prompt_table"):
            self.prompt_table.table.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked
                if enabled
                else QAbstractItemView.EditTrigger.NoEditTriggers
            )
            if getattr(self.prompt_table, "_optimize_all_btn", None) is not None and self.prompt_table._optimize_all_btn.isVisible():
                self.prompt_table._optimize_all_btn.setEnabled(enabled)
        if hasattr(self.config_form, "start_frame_upload"):
            self.config_form.start_frame_upload.setEnabled(enabled)
        if hasattr(self.config_form, "end_frame_upload"):
            self.config_form.end_frame_upload.setEnabled(enabled)
        self.action_bar.start_btn.setEnabled(enabled)
        if hasattr(self.action_bar, "new_task_btn"):
            self.action_bar.new_task_btn.setEnabled(enabled)
        elif hasattr(self.action_bar, "save_btn"):
            self.action_bar.save_btn.setEnabled(enabled)
        if hasattr(self.action_bar, "resume_btn"):
            self.action_bar.resume_btn.setEnabled(enabled)
        if hasattr(self.action_bar, "retry_btn"):
            self.action_bar.retry_btn.setEnabled(enabled)
        if hasattr(self.action_bar, "concat_btn"):
            self.action_bar.concat_btn.setEnabled(enabled)
        self.upgrade_btn.setEnabled(enabled)

    def refresh(self):
        return None
