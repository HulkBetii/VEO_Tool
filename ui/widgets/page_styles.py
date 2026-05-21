"""Shared page widget helpers."""

from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QProgressBar, QSpinBox

LEFT_PANEL_WIDTH = 360
PROGRESS_HEIGHT = 8
PROGRESS_STYLE = ""


def make_title(text):
    label = QLabel(text)
    label.setProperty("class", "section-title")
    return label


def make_desc(text):
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def make_label(text):
    return QLabel(text)


def make_button(text):
    return QPushButton(text)


def make_green_button(text):
    return QPushButton(text)


def make_blue_button(text):
    return QPushButton(text)


def make_progress_bar():
    bar = QProgressBar()
    bar.setFixedHeight(PROGRESS_HEIGHT)
    return bar


def make_combo(items=None):
    combo = QComboBox()
    if items:
        combo.addItems(list(items))
    return combo


def make_spinbox(min_value=0, max_value=9999, value=0):
    spin = QSpinBox()
    spin.setRange(min_value, max_value)
    spin.setValue(value)
    return spin
