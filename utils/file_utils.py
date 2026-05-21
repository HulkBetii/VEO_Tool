"""File utility helpers."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from config.constants import DEFAULT_VIDEO_OUTPUT


def natural_sort_key(path):
    text = str(path)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def get_images_from_folder(folder):
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    return sorted([p for p in Path(folder).iterdir() if p.suffix.lower() in exts], key=natural_sort_key)


def ensure_even_dimensions(width, height):
    return int(width) // 2 * 2, int(height) // 2 * 2


def generate_task_name(prefix="task"):
    return f"{safe_filename(prefix)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def safe_filename(name):
    text = re.sub(r'[<>:"/\\\\|?*]+', "_", str(name or "untitled"))
    text = re.sub(r"\s+", "_", text).strip("._")
    return text or "untitled"


def get_output_folder(base=None, task_name=None):
    folder = Path(base or DEFAULT_VIDEO_OUTPUT)
    if task_name:
        folder = folder / safe_filename(task_name)
    folder.mkdir(parents=True, exist_ok=True)
    return folder
