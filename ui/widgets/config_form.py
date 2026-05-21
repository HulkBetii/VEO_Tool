"""VidGen AI - Reusable config form widget."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

from config.constants import (
    ASPECT_RATIO_OPTIONS,
    DEFAULT_IMAGE_OUTPUT,
    DEFAULT_VIDEO_OUTPUT,
    IMAGE_MODEL_OPTIONS,
    QUALITY_OPTIONS,
    SAVE_MODE_OPTIONS,
    SERVICE_OPTIONS,
)
from ui.widgets.frame_upload import FrameUpload
from utils.file_utils import generate_task_name


class ConfigForm(QWidget):
    """Reusable config form for left panel - adapts per page mode."""

    _COMPACT_QSS = (
        "ConfigForm QLabel[class='field-label'] { font-size: 12px; font-weight: 600; color: #adc6ff; padding: 0; margin: 0;}"
        "ConfigForm QLineEdit, ConfigForm QComboBox, ConfigForm QSpinBox { padding: 6px 10px; font-size: 12px; min-height: 18px;}"
    )

    def __init__(self, mode: str = "video_plain", db=None, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._db = db
        self._init_ui()

    def _enabled_accounts_count(self) -> int:
        if self._db is None:
            return 5
        try:
            return len(self._db.get_accounts(enabled_only=True))
        except Exception:
            return 5

    def refresh_account_limit(self):
        return None

    def _pair_row(self, label1: str, widget1, label2: str, widget2):
        row = QHBoxLayout()
        row.setSpacing(10)

        col1 = QVBoxLayout()
        col1.setSpacing(3)
        col1.addWidget(self._label(label1))
        col1.addWidget(widget1)
        row.addLayout(col1, 1)

        col2 = QVBoxLayout()
        col2.setSpacing(3)
        col2.addWidget(self._label(label2))
        col2.addWidget(widget2)
        row.addLayout(col2, 1)
        return row

    def _init_ui(self):
        self.setStyleSheet(self._COMPACT_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        self.task_name_input = QLineEdit(generate_task_name())

        self.project_combo = QComboBox()
        self.project_combo.setEditable(True)
        self.project_combo.addItem(datetime.now().strftime("%Y-%m-%d"))
        layout.addLayout(self._pair_row("Tên task:", self.task_name_input, "Project:", self.project_combo))

        if self._mode in ("image", "char_image"):
            self._build_image_fields(layout)
        else:
            self._build_video_fields(layout)

        layout.addWidget(self._label("Thư mục lưu:"))
        out_row = QHBoxLayout()
        out_row.setSpacing(6)

        self.output_input = QLineEdit()
        if self._mode in ("image", "char_image"):
            self.output_input.setText(str(DEFAULT_IMAGE_OUTPUT))
        else:
            self.output_input.setText(str(DEFAULT_VIDEO_OUTPUT))
        self.output_input.setPlaceholderText("Chọn thư mục lưu...")

        browse_btn = QPushButton("📁")
        browse_btn.setFixedSize(34, 34)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(
            "background-color: #222a3d; border: 1px solid #2a3350; border-radius: 6px; font-size: 16px;"
        )
        browse_btn.clicked.connect(self._browse_output)

        out_row.addWidget(self.output_input, 1)
        out_row.addWidget(browse_btn)
        layout.addLayout(out_row)
        layout.addStretch()

    def _build_video_fields(self, layout):
        self.quality_combo = QComboBox()
        for quality in QUALITY_OPTIONS:
            self.quality_combo.addItem(quality)

        if self._mode == "video_plain":
            self.creation_mode_combo = QComboBox()
            self.creation_mode_combo.addItem("Text -> Video")
            layout.addLayout(self._pair_row("Chế độ tạo:", self.creation_mode_combo, "Chất lượng:", self.quality_combo))
        else:
            layout.addLayout(self._pair_row("Chất lượng:", self.quality_combo, "Tỷ lệ:", self._new_aspect_combo()))

        self._credit_per_video_label = QLabel("")
        self._credit_per_video_label.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: 600; font-style: italic;")
        self.quality_combo.currentTextChanged.connect(self._refresh_credit_label)
        layout.addWidget(self._credit_per_video_label)

        if not hasattr(self, "aspect_combo"):
            self.aspect_combo = self._new_aspect_combo()
            layout.addLayout(self._pair_row("Tỷ lệ:", self.aspect_combo, "Đồng thời:", self._new_parallel_spin()))
        else:
            layout.addLayout(self._pair_row("Đồng thời:", self._new_parallel_spin(), "Chế độ lưu:", self._new_save_mode_combo()))

        self._parallel_hint = QLabel("1 account chạy 5 task đồng thời")
        self._parallel_hint.setWordWrap(True)
        self._parallel_hint.setStyleSheet("color: #f59e0b; font-size: 11px; font-style: italic;")
        self.parallel_per_account_spin.valueChanged.connect(
            lambda value: self._parallel_hint.setText(f"1 account chạy {value} task đồng thời")
        )
        layout.addWidget(self._parallel_hint)

        warning = QLabel(
            "⚠ Mặc định 5 task song song, max 50 task. Đẩy quá cao dễ bị Google flag account "
            "(reCAPTCHA fail, account bị ban tạm)."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "color: #fbbf24; font-size: 11px; font-weight: bold; padding: 4px 6px; "
            "background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.3); border-radius: 6px;"
        )
        layout.addWidget(warning)

        formula_note = QLabel(
            "💡 Tổng task = (số account bật) × (Đồng thời). VD: 3 acc × 5 = 15 task cùng lúc.\n"
            "Tool chạy tối đa = min(số prompt, tổng task). VD: nhập 10 prompt + set 50 đồng thời -> chỉ 10 task chạy."
        )
        formula_note.setWordWrap(True)
        formula_note.setStyleSheet(
            "color: #fbbf24; font-size: 11px; font-style: italic; padding: 4px 6px; "
            "background: rgba(251,191,36,0.05); border: 1px dashed rgba(251,191,36,0.25); border-radius: 6px;"
        )
        layout.addWidget(formula_note)

        if self._mode == "frame_video":
            self.model_label = QLabel("Model (Tự động)")
            self.model_label.setProperty("class", "model-info")
            layout.addWidget(self.model_label)

            self.start_frame_upload = FrameUpload(label="🖼️  Ảnh khung đầu:")
            self.end_frame_upload = FrameUpload(label="🖼️  Ảnh khung cuối:")
            layout.addWidget(self.start_frame_upload)
            layout.addWidget(self.end_frame_upload)

        if not hasattr(self, "save_mode_combo"):
            self._new_save_mode_combo()
            layout.addLayout(self._pair_row("Chế độ lưu:", self.save_mode_combo, "", QLabel("")))

        self._refresh_credit_label()

    def _new_aspect_combo(self):
        self.aspect_combo = QComboBox()
        for display, value in ASPECT_RATIO_OPTIONS:
            self.aspect_combo.addItem(display, value)
        return self.aspect_combo

    def _new_parallel_spin(self):
        self.parallel_per_account_spin = QSpinBox()
        self.parallel_per_account_spin.setRange(1, 50)
        self.parallel_per_account_spin.setValue(5)
        self.parallel_per_account_spin.setToolTip(
            "Số video chạy song song trong 1 account (1-50).\n"
            "App tự dùng TẤT CẢ account đang enable.\n"
            "Tổng parallel = số acc enable × Đồng thời."
        )
        return self.parallel_per_account_spin

    def _new_save_mode_combo(self):
        self.save_mode_combo = QComboBox()
        for mode in SAVE_MODE_OPTIONS:
            self.save_mode_combo.addItem(mode)
        return self.save_mode_combo

    def _build_image_fields(self, layout):
        self.service_combo = QComboBox()
        for service in SERVICE_OPTIONS:
            self.service_combo.addItem(service)

        self.model_combo = QComboBox()
        for model in IMAGE_MODEL_OPTIONS:
            self.model_combo.addItem(model)
        layout.addLayout(self._pair_row("Dịch vụ:", self.service_combo, "Model:", self.model_combo))

        self.aspect_combo = QComboBox()
        for display, value in ASPECT_RATIO_OPTIONS:
            self.aspect_combo.addItem(display, value)

        self.parallel_per_account_spin = QSpinBox()
        self.parallel_per_account_spin.setRange(1, 50)
        self.parallel_per_account_spin.setValue(5)
        self.parallel_per_account_spin.setToolTip(
            "Số ảnh chạy song song trong 1 account (1-50).\n"
            "App tự dùng TẤT CẢ account đang enable."
        )
        layout.addLayout(self._pair_row("Tỷ lệ:", self.aspect_combo, "Đồng thời:", self.parallel_per_account_spin))

        self._parallel_hint = QLabel("1 account chạy 5 task đồng thời")
        self._parallel_hint.setWordWrap(True)
        self._parallel_hint.setStyleSheet("color: #f59e0b; font-size: 11px; font-style: italic;")
        self.parallel_per_account_spin.valueChanged.connect(
            lambda value: self._parallel_hint.setText(f"1 account chạy {value} task đồng thời")
        )
        layout.addWidget(self._parallel_hint)

        self.input_folder_input = QLineEdit()
        self.input_folder_input.setPlaceholderText("Chọn thư mục ảnh đầu vào...")
        input_btn = QPushButton("📁")
        input_btn.setFixedSize(34, 34)
        input_btn.clicked.connect(self._browse_input_folder)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.input_folder_input, 1)
        row.addWidget(input_btn)
        layout.addWidget(self._label("Thư mục input:"))
        layout.addLayout(row)

        self.save_mode_combo = QComboBox()
        for mode in SAVE_MODE_OPTIONS:
            self.save_mode_combo.addItem(mode)
        layout.addLayout(self._pair_row("Chế độ lưu:", self.save_mode_combo, "", QLabel("")))

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("class", "field-label")
        return label

    def _refresh_credit_label(self) -> None:
        if not hasattr(self, "_credit_per_video_label"):
            return

        quality = self.quality_combo.currentText()
        if "Quality" in quality:
            cost = 100
        elif "Lite" in quality and "Lower Priority" not in quality:
            cost = 5
        elif "Lower Priority" in quality:
            cost = 0
        else:
            cost = 10
        self._credit_per_video_label.setText(f"Credit mỗi video: {cost}")

    def update_image_models(self, models: list[str] | None = None):
        if hasattr(self, "model_combo"):
            self.model_combo.clear()
            for model in models or IMAGE_MODEL_OPTIONS:
                self.model_combo.addItem(model)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu")
        if folder:
            self.output_input.setText(folder)

    def _browse_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục input")
        if folder and hasattr(self, "input_folder_input"):
            self.input_folder_input.setText(folder)

    def get_config(self) -> dict:
        enabled_count = max(1, self._enabled_accounts_count())
        per_account = self.parallel_per_account_spin.value() if hasattr(self, "parallel_per_account_spin") else 1
        config = {
            "task_name": self.task_name_input.text(),
            "project": self.project_combo.currentText(),
            "output_folder": self.output_input.text(),
            "concurrent": enabled_count * per_account,
            "parallel_per_account": per_account,
            "aspect_ratio": self.aspect_combo.currentData() or "16:9",
        }
        if hasattr(self, "quality_combo"):
            config["quality"] = self.quality_combo.currentText()
        if hasattr(self, "service_combo"):
            config["service"] = self.service_combo.currentText()
        if hasattr(self, "model_combo"):
            model = self.model_combo.currentText()
            config["model"] = model
            config["image_model"] = model
        if hasattr(self, "save_mode_combo"):
            config["save_mode"] = self.save_mode_combo.currentText()
        if hasattr(self, "input_folder_input"):
            config["input_folder"] = self.input_folder_input.text()
        if hasattr(self, "start_frame_upload"):
            config["start_frame"] = self.start_frame_upload.get_image_path()
        if hasattr(self, "end_frame_upload"):
            config["end_frame"] = self.end_frame_upload.get_image_path()
        return config
