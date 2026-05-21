"""VidGen AI — FFmpeg video concatenation service."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Iterable

from config.constants import FFMPEG_PATH
from utils.file_utils import ensure_even_dimensions, natural_sort_key
from utils.logger import log


def concat_videos(input_paths: Iterable, output_path, timeout=600, re_encode=True):
    """Concat MP4 clips into one long video via ffmpeg."""
    paths = [Path(p) for p in input_paths if Path(p).exists()]
    if not paths:
        log.error("concat_videos: no input files")
        return False

    ffmpeg = Path(FFMPEG_PATH) if FFMPEG_PATH else None
    if not ffmpeg or not ffmpeg.exists():
        log.error(f"concat_videos: ffmpeg not found ({FFMPEG_PATH})")
        return False

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.with_suffix(".concat.txt")
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in paths:
                safe = str(p.absolute()).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe}'\n")

        cmd = [str(ffmpeg), "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
        if re_encode:
            cmd += [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
            ]
            mode_label = "re-encode (libx264 crf18)"
        else:
            cmd += ["-c", "copy"]
            mode_label = "copy (lossless, fast)"
        cmd.append(str(output_path))

        log.info(f"ffmpeg concat ({mode_label}): {len(paths)} clips -> {output_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            size_mb = output_path.stat().st_size / 1048576
            log.info(f"concat_videos OK: {output_path.name} ({size_mb:.1f} MB)")
            return True
        log.error(f"ffmpeg concat failed (rc={result.returncode}): {(result.stderr or 'no stderr')[-500:]}")
        return False
    except subprocess.TimeoutExpired:
        log.error(f"ffmpeg concat timeout after {timeout}s")
        return False
    except Exception as e:
        log.error(f"ffmpeg concat exception: {e}")
        return False
    finally:
        try:
            list_file.unlink(missing_ok=True)
        except Exception:
            pass


class VideoConcatenator:
    def __init__(self, ffmpeg_path=FFMPEG_PATH):
        self._ffmpeg = ffmpeg_path

    def concat_videos(self, input_dir, output_path, pattern="*.mp4"):
        input_dir = Path(input_dir)
        files = sorted(input_dir.glob(pattern), key=lambda p: natural_sort_key(p.name))
        normalized = []
        for p in files:
            normalized.append(ensure_even_dimensions(p))
        return concat_videos(normalized, output_path)

    def get_video_info(self, video_path):
        """Get video metadata using ffprobe."""
        try:
            ffprobe = str(Path(self._ffmpeg).parent / "ffprobe")
            if not Path(ffprobe).exists():
                ffprobe = self._ffmpeg.replace("ffmpeg", "ffprobe")
            cmd = [
                ffprobe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return None
            return json.loads(result.stdout)
        except Exception as e:
            log.debug(f"ffprobe failed: {e}")
            return None
