"""Thumbnail extraction."""

from __future__ import annotations

import subprocess
from pathlib import Path

from utils.platform import find_ffmpeg, get_subprocess_flags


def extract_thumbnail(video_path, output_path=None, time_sec=1):
    output = Path(output_path) if output_path else Path(video_path).with_suffix(".jpg")
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    cmd = [ffmpeg, "-y", "-ss", str(time_sec), "-i", str(video_path), "-frames:v", "1", str(output)]
    proc = subprocess.run(cmd, capture_output=True, creationflags=get_subprocess_flags())
    return str(output) if proc.returncode == 0 and output.exists() else None
