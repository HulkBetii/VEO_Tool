"""NAV TOOLS — LaMa inpainting service for watermark removal."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image

from config.constants import DATA_DIR
from utils.logger import log


_DATA_DIR = Path(DATA_DIR)
MODEL_DIR = _DATA_DIR / "models" / "lama"
MODEL_PATH = MODEL_DIR / "big-lama.pt"
LAMA_MODEL_URL = "https://huggingface.co/smartywu/big-lama/resolve/main/big-lama.pt"
LAMA_MODEL_URL_BACKUP = "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt"

_cached_model = None
_cached_device = None


def model_exists():
    """Check if LaMa weights are present on disk."""
    return MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 10000000


def download_model(progress_cb: Optional[Callable[[int, int], None]] = None):
    """Download big-lama.pt weights if missing."""
    if model_exists():
        return True
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = MODEL_PATH.with_suffix(".pt.tmp")
    for url in (LAMA_MODEL_URL, LAMA_MODEL_URL_BACKUP):
        log.info(f"[lama] Downloading from {url}")
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                done = 0
                with open(tmp_path, "wb") as f:
                    while True:
                        data = resp.read(1048576)
                        if not data:
                            break
                        f.write(data)
                        done += len(data)
                        if progress_cb:
                            progress_cb(done, total)
            tmp_path.replace(MODEL_PATH)
            log.info(f"[lama] Downloaded {MODEL_PATH.stat().st_size // 1024 // 1024} MB")
            return True
        except Exception as e:
            log.warning(f"[lama] Download failed from {url}: {e}")
            try:
                tmp_path.unlink()
            except Exception:
                pass
    log.error("[lama] All download mirrors failed")
    return False


def load_model(device=None):
    """Load LaMa model via spandrel. Cached — safe to call repeatedly."""
    global _cached_model, _cached_device
    if not model_exists():
        raise RuntimeError(f"LaMa model not found at {MODEL_PATH}. Call download_model() first.")

    import torch

    if device is None:
        device = "cpu"
        try:
            if torch.cuda.is_available():
                _ = torch.zeros(1).to("cuda")
                device = "cuda"
        except Exception as e:
            log.warning(f"[lama] CUDA probe failed, using CPU: {e}")
            device = "cpu"

    if _cached_model is not None and _cached_device == device:
        return _cached_model

    log.info(f"[lama] Loading model from {MODEL_PATH} on {device}")
    try:
        from spandrel import ModelLoader

        descriptor = ModelLoader().load_from_file(str(MODEL_PATH))
    except NotImplementedError:
        log.warning("[lama] spandrel can't handle TorchScript, loading via torch.jit")
        descriptor = torch.jit.load(str(MODEL_PATH), map_location=device)

    descriptor.eval()
    try:
        descriptor = descriptor.to(device)
    except Exception as e:
        log.warning(f"[lama] .to(cuda) failed, retry CPU: {e}")
        device = "cpu"
        descriptor = descriptor.to("cpu")

    _cached_model = descriptor
    _cached_device = device
    return descriptor


def inpaint_image_crop(image: Image.Image, mask: Image.Image, bbox, padding=32, device=None):
    """Inpaint a RECTANGULAR region of an image using LaMa."""
    import torch

    descriptor = load_model(device)
    target_device = next(descriptor.model.parameters()).device if hasattr(descriptor, "model") else next(descriptor.parameters()).device

    orig_mode = image.mode
    alpha = image.getchannel("A") if image.mode == "RGBA" else None
    image = image.convert("RGB")
    mask = mask.convert("L")
    fw, fh = image.size
    x, y, w, h = bbox
    cx0 = max(0, x - padding)
    cy0 = max(0, y - padding)
    cx1 = min(fw, x + w + padding)
    cy1 = min(fh, y + h + padding)
    cw, ch = cx1 - cx0, cy1 - cy0

    img_crop = image.crop((cx0, cy0, cx1, cy1))
    mask_crop = mask.crop((cx0, cy0, cx1, cy1))
    img_arr = np.array(img_crop).astype(np.float32) / 255.0
    mask_arr = (np.array(mask_crop).astype(np.float32) / 255.0)[..., None]

    img_t = torch.from_numpy(img_arr).permute(2, 0, 1).unsqueeze(0).to(target_device)
    mask_t = torch.from_numpy(mask_arr).permute(2, 0, 1).unsqueeze(0).to(target_device)
    inp = torch.cat([img_t, mask_t], dim=1)
    with torch.no_grad():
        model = descriptor.model if hasattr(descriptor, "model") else descriptor
        out = model(inp)
        if isinstance(out, (list, tuple)):
            out = out[0]
        out = torch.clamp(out, 0, 1)
    result_np = (out.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
    result_crop = Image.fromarray(result_np)
    feather = _make_feather_mask(cw, ch, min(padding, 24))

    full_out = image.copy()
    full_out.paste(result_crop, (cx0, cy0), feather)
    if alpha is not None:
        full_out.putalpha(alpha)
    if orig_mode != full_out.mode:
        full_out = full_out.convert(orig_mode)
    return full_out


def _make_feather_mask(w, h, feather_px):
    """Build a grayscale mask that fades at the edges."""
    mask = np.full((h, w), 255, dtype=np.uint8)
    if feather_px > 0:
        for i in range(min(feather_px, h // 2)):
            alpha = int(255 * (i + 1) / (feather_px + 1))
            mask[i, :] = np.minimum(mask[i, :], alpha)
            mask[h - 1 - i, :] = np.minimum(mask[h - 1 - i, :], alpha)
        for j in range(min(feather_px, w // 2)):
            alpha = int(255 * (j + 1) / (feather_px + 1))
            mask[:, j] = np.minimum(mask[:, j], alpha)
            mask[:, w - 1 - j] = np.minimum(mask[:, w - 1 - j], alpha)
    return Image.fromarray(mask, mode="L")


def build_rect_mask(image_size, rect):
    """Create a black image with a white filled rectangle at `rect`."""
    from PIL import ImageDraw

    w, h = image_size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    x, y, rw, rh = rect
    draw.rectangle([x, y, x + rw, y + rh], fill=255)
    return mask


def _probe_video(video_path):
    """Return (width, height, fps, duration_sec) for a video via ffprobe."""
    from config.constants import FFMPEG_PATH

    ffmpeg_dir = Path(FFMPEG_PATH).parent
    ffprobe = ffmpeg_dir / "ffprobe.exe"
    cmd = [
        str(ffprobe if ffprobe.exists() else "ffprobe"),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,duration",
        "-of",
        "json",
        str(video_path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(out.stdout)
        stream = data["streams"][0]
        num, den = stream.get("r_frame_rate", "25/1").split("/")
        fps = float(num) / float(den)
        return int(stream["width"]), int(stream["height"]), fps, float(stream.get("duration") or 0)
    except Exception as e:
        log.warning(f"[lama video] ffprobe failed: {e}")
        raise RuntimeError(getattr(e, "stderr", str(e)))


def inpaint_video(input_path, output_path, rect, padding=32, device=None, progress_cb=None):
    """Remove a rectangular watermark region from a video using LaMa."""
    from config.constants import FFMPEG_PATH

    if not model_exists():
        log.error("[lama video] Model not downloaded yet")
        return False

    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="lama_"))
    frames_in = tmp / "in"
    frames_out = tmp / "out"
    frames_in.mkdir()
    frames_out.mkdir()

    try:
        if progress_cb:
            progress_cb(0, 0, "Đang đọc metadata video...")
        width, height, fps, duration = _probe_video(input_path)
        log.info(f"[lama video] {width}x{height} {fps:.2f}fps {duration:.1f}s")

        cmd = [str(FFMPEG_PATH), "-y", "-i", str(input_path), str(frames_in / "%08d.png")]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(result.stderr)
            return False

        frame_files = sorted(frames_in.glob("*.png"))
        n = len(frame_files)
        mask = build_rect_mask((width, height), rect)
        load_model(device)
        for i, frame_path in enumerate(frame_files, 1):
            if progress_cb:
                progress_cb(i, n, "Đang xóa watermark...")
            img = Image.open(frame_path)
            cleaned = inpaint_image_crop(img, mask, rect, padding=padding, device=device)
            cleaned.save(frames_out / frame_path.name)

        cmd = [
            str(FFMPEG_PATH),
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_out / "%08d.png"),
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(result.stderr)
            return False
        return output_path.exists() and output_path.stat().st_size > 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
