"""Clickable prompt table cell."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class _PromptEditDialog(QDialog):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit prompt")
        layout = QVBoxLayout(self)
        self.edit = QPlainTextEdit(text)
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        layout.addWidget(self.edit)
        layout.addWidget(ok)

    def get_text(self):
        return self.edit.toPlainText()


class _ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setWordWrap(True)
        self._refresh()

    def setFullText(self, text):
        self._full_text = str(text or "")
        self._refresh()

    def fullText(self):
        return self._full_text

    def resizeEvent(self, event):
        self._refresh()
        super().resizeEvent(event)

    def _refresh(self):
        text = self._full_text
        self.setText(text[:180] + ("..." if len(text) > 180 else ""))

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class ClickablePromptCell(QWidget):
    edited = Signal(int, str)

    def __init__(self, scene_index=0, text="", parent=None):
        super().__init__(parent)
        self.scene_index = scene_index
        layout = QVBoxLayout(self)
        self.label = _ClickableLabel(text)
        self.label.clicked.connect(self._open_editor)
        layout.addWidget(self.label)

    def _open_editor(self):
        dlg = _PromptEditDialog(self.get_text(), self)
        if dlg.exec() == QDialog.Accepted:
            self.set_text(dlg.get_text())
            self.edited.emit(self.scene_index, self.get_text())

    def get_text(self):
        return self.label.fullText()

    def set_text(self, text):
        self.label.setFullText(text)

    def set_scene_index(self, index):
        self.scene_index = index

    def set_read_only(self, read_only):
        self.setEnabled(not read_only)
