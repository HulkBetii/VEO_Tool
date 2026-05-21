"""NAV TOOLS - Image to Prompt page.

Upload image -> Gemini Vision describes it -> editable prompt output.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from services.gemini_with_fallback import generate_with_fallback
except Exception:
    def generate_with_fallback(*args, **kwargs):
        raise RuntimeError("Gemini service is unavailable")
from ui.widgets.page_styles import LEFT_PANEL_WIDTH, PROGRESS_HEIGHT, PROGRESS_STYLE
from utils.logger import log


PROMPT_TEMPLATE = (
    "Describe this image in detail as a cinematic video generation prompt. "
    "Include: scene description, lighting, camera angle, mood/atmosphere, "
    "character appearance (clothing, hair, expression), background environment, "
    "color palette, and art style. Be specific and vivid. Output as a single "
    "paragraph prompt suitable for AI video generation."
)


class _AnalyzeSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


class _AnalyzeWorker(QThread):
    """Analyze image with Gemini Vision."""

    def __init__(self, image_path, api_key, custom_instruction, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.api_key = api_key
        self.custom_instruction = custom_instruction
        self.signals = _AnalyzeSignals()

    def run(self):
        response = None
        try:
            from PIL import Image
            from google import genai

            client = genai.Client(api_key=self.api_key)
            img = Image.open(self.image_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            prompt = self.custom_instruction or PROMPT_TEMPLATE
            response = generate_with_fallback(client, contents=[prompt, img])
            text = ""
            if response:
                try:
                    text = (response.text or "").strip()
                except Exception:
                    text = ""
            if text:
                log.info(f"Image->Prompt OK: {len(text)} chars")
                self.signals.finished.emit(text)
                return
            self.signals.error.emit("Gemini tra ve rong (co the bi chan noi dung)")
        except Exception as e:
            try:
                if response and getattr(response, "candidates", None):
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "text") and part.text:
                            self.signals.finished.emit(part.text.strip())
                            return
            except Exception:
                pass
            log.warning(f"Image->Prompt error: {e}")
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


class ImageToPromptPage(QWidget):
    """Page: upload image -> Gemini describes -> editable prompt."""

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._source_path = None
        self._worker = None
        self._init_ui()

    def _get_gemini_key(self):
        if self._db is None:
            return ""
        for name in ("get_setting", "get_config", "get_value"):
            fn = getattr(self._db, name, None)
            if callable(fn):
                for key in ("gemini_api_key", "GEMINI_API_KEY"):
                    try:
                        value = fn(key)
                    except Exception:
                        continue
                    if value:
                        return str(value)
        return ""

    def _init_ui(self):
        self.setObjectName("imageToPromptPage")
        self.setStyleSheet(
            """
            QWidget#imageToPromptPage {
                background: #0b1326;
            }
            QWidget#imageToPromptPage QLabel {
                color: #dae2fd;
            }
            QWidget#imageToPromptPage QTextEdit {
                background: #131b2e;
                color: #dae2fd;
                border: 1px solid #2a3350;
                border-radius: 8px;
                padding: 10px 14px;
            }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left.setFixedWidth(LEFT_PANEL_WIDTH)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(12)

        title = QLabel("Image to Prompt")
        title.setProperty("class", "section-title")
        desc = QLabel(
            "Tải ảnh lên, Gemini Vision sẽ phân tích nội dung và trả ra prompt để chỉnh sửa."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8c909f; font-size: 12px;")

        self._btn_choose = QPushButton("Chọn ảnh")
        self._btn_choose.setStyleSheet(BTN_STYLE)
        self._btn_choose.clicked.connect(self._on_choose)

        instruction_label = QLabel("Hướng dẫn phân tích")
        instruction_label.setStyleSheet("font-weight: 600;")

        self._txt_instruction = QTextEdit()
        self._txt_instruction.setPlaceholderText("Nhập hướng dẫn riêng hoặc để mặc định.")
        self._txt_instruction.setMinimumHeight(180)
        self._txt_instruction.setPlainText(PROMPT_TEMPLATE)

        self._btn_analyze = QPushButton("Phân tích")
        self._btn_analyze.setStyleSheet(BTN_STYLE)
        self._btn_analyze.clicked.connect(self._on_analyze)

        self._btn_copy = QPushButton("Copy")
        self._btn_copy.setStyleSheet(BTN_STYLE)
        self._btn_copy.setEnabled(False)
        self._btn_copy.clicked.connect(self._on_copy)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(PROGRESS_HEIGHT)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(PROGRESS_STYLE)
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)

        ll.addWidget(title)
        ll.addWidget(desc)
        ll.addWidget(self._btn_choose)
        ll.addWidget(instruction_label)
        ll.addWidget(self._txt_instruction)
        ll.addWidget(self._btn_analyze)
        ll.addWidget(self._btn_copy)
        ll.addWidget(self._progress)
        ll.addStretch(1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 16)
        rl.setSpacing(12)

        preview_label = QLabel("Ảnh gốc")
        preview_label.setStyleSheet("font-weight: 600;")
        self._lbl_original = QLabel("Chưa chọn ảnh")
        self._lbl_original.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_original.setMinimumHeight(320)
        self._lbl_original.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._lbl_original.setStyleSheet("background: #1e2030; border: 1px solid #33384a; border-radius: 8px;")

        result_label = QLabel("Prompt kết quả")
        result_label.setStyleSheet("font-weight: 600;")
        self._txt_result = QTextEdit()
        self._txt_result.setPlaceholderText("Kết quả prompt sẽ hiển thị tại đây.")

        rl.addWidget(preview_label)
        rl.addWidget(self._lbl_original, 1)
        rl.addWidget(result_label)
        rl.addWidget(self._txt_result, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

    def _on_choose(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn ảnh",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        self._source_path = path
        self._btn_copy.setEnabled(False)
        pm = QPixmap(path)
        if not pm.isNull():
            scaled = pm.scaled(
                self._lbl_original.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._lbl_original.setPixmap(scaled)
        self._txt_result.clear()

    def _on_analyze(self):
        if not self._source_path:
            return
        self._progress.setVisible(True)
        self._btn_analyze.setEnabled(False)
        self._btn_choose.setEnabled(False)
        self._btn_copy.setEnabled(False)
        self._txt_result.setText("Đang phân tích...")
        self._worker = _AnalyzeWorker(
            self._source_path,
            self._get_gemini_key(),
            self._txt_instruction.toPlainText().strip(),
            self,
        )
        self._worker.signals.finished.connect(self._on_done)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _stop_worker(self):
        self._worker = None

    def hideEvent(self, event):
        self._stop_worker()
        super().hideEvent(event)

    def _on_done(self, text):
        self._progress.setVisible(False)
        self._btn_analyze.setEnabled(True)
        self._btn_choose.setEnabled(True)
        self._btn_copy.setEnabled(True)
        self._txt_result.setText(text)
        self._worker = None

    def _on_error(self, msg):
        self._progress.setVisible(False)
        self._btn_analyze.setEnabled(True)
        self._btn_choose.setEnabled(True)
        self._txt_result.setText(f"Lỗi: {msg}")
        self._worker = None

    def _on_copy(self):
        text = self._txt_result.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._btn_copy.setText("Da copy!")
        from PySide6.QtCore import QTimer

        QTimer.singleShot(2000, lambda: self._btn_copy.setText("Copy"))
