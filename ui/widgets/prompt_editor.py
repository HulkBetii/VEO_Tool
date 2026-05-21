"""VidGen AI - Prompt editor widget with import button."""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class PromptEditor(QWidget):
    """Prompt input area with label + import TXT button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("Danh sách Prompt")
        title.setProperty("class", "field-label")
        header.addWidget(title)
        header.addStretch()

        import_btn = QPushButton("📄 Nhập Prompts (TXT)")
        import_btn.setObjectName("btn-ghost")
        import_btn.clicked.connect(self._import_txt)
        header.addWidget(import_btn)
        layout.addLayout(header)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Nhập prompt, mỗi dòng 1 prompt...\n\n"
            "Ví dụ:\n"
            "A cat running through autumn leaves\n"
            "A futuristic city at sunset\n"
            "An underwater scene with coral reefs"
        )
        self.editor.setMinimumHeight(120)
        layout.addWidget(self.editor)

    def _import_txt(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Nhập Prompts",
            "",
            "Text files (*.txt);;All files (*.*)",
        )
        if path:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.editor.setPlainText(content)

    def get_prompts(self) -> list[str]:
        text = self.editor.toPlainText()
        return [line.strip() for line in text.split("\n") if line.strip()]

    def set_prompts(self, prompts: list[str]):
        self.editor.setPlainText("\n".join(prompts))

    def clear(self):
        self.editor.clear()
