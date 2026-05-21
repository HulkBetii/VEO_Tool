"""v1.2.12 — Bundle smoke test (exhaustive edition).

Runs against a BUILT bundle (`NAVTools.exe --smoke-test`) OR the dev tree
(`python scripts/bundle_smoke_test.py`) to verify every module and every
runtime side-effect a user-facing feature actually touches.
"""

from __future__ import annotations

import importlib
import importlib.metadata as im
import io
import os
import sys
import tempfile
import traceback

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

MODULES: list[tuple[str, str, bool]] = [
    ("PySide6", "PySide6", True),
    ("PySide6.QtWidgets", "PySide6.QtWidgets", True),
    ("PySide6.QtCore", "PySide6.QtCore", True),
    ("PySide6.QtGui", "PySide6.QtGui", True),
    ("PySide6.QtSvg", "PySide6.QtSvg", True),
    ("numpy", "numpy", True),
    ("scipy", "scipy", True),
    ("scipy.ndimage", "scipy.ndimage", True),
    ("scipy.special", "scipy.special", True),
    ("scipy.signal", "scipy.signal", True),
    ("scipy.linalg", "scipy.linalg", True),
    ("torch", "torch", True),
    ("torch.nn", "torch.nn", True),
    ("torch.nn.functional", "torch.nn.functional", True),
    ("torchvision", "torchvision", True),
    ("torchvision.transforms", "torchvision.transforms", True),
    ("torchvision.transforms.functional", "torchvision.transforms.functional", True),
    ("torchvision.ops", "torchvision.ops", True),
    ("torchvision.ops.poolers", "torchvision.ops.poolers (upscale crash path)", True),
    ("torchvision.ops.roi_align", "torchvision.ops.roi_align", True),
    ("sympy", "sympy (torch._dynamo dep)", True),
    ("sympy.core.assumptions", "sympy.core.assumptions (GC crash site)", True),
    ("sympy.core.numbers", "sympy.core.numbers", True),
    ("mpmath", "mpmath (sympy numerical backend)", True),
    ("PIL", "Pillow", True),
    ("PIL.Image", "PIL.Image", True),
    ("cv2", "opencv-python-headless", True),
    ("pymatting", "pymatting (rembg dep)", True),
    ("pymatting.alpha", "pymatting.alpha", True),
    ("pymatting.foreground", "pymatting.foreground", True),
    ("pymatting.laplacian", "pymatting.laplacian", True),
    ("pymatting.preconditioner", "pymatting.preconditioner", True),
    ("rembg", "rembg", True),
    ("onnxruntime", "onnxruntime", True),
    ("spandrel", "spandrel", True),
    ("spandrel.architectures", "spandrel.architectures", True),
    ("imageio", "imageio", True),
    ("imageio_ffmpeg", "imageio-ffmpeg", True),
    ("ffmpeg", "ffmpeg-python", True),
    ("moviepy", "moviepy", True),
    ("yt_dlp", "yt-dlp", True),
    ("whisper", "openai-whisper", True),
    ("scenedetect", "scenedetect", True),
    ("google.genai", "google-genai", True),
    ("gspread", "gspread", True),
    ("google.oauth2.service_account", "google.oauth2.service_account", True),
    ("playwright", "playwright", True),
    ("playwright.sync_api", "playwright.sync_api", True),
    ("httpx", "httpx", True),
    ("requests", "requests", True),
    ("config.constants", "config.constants", True),
    ("models.database", "models.database", True),
    ("models.account", "models.account", True),
    ("models.task", "models.task", True),
    ("ui.main_window", "ui.main_window", True),
]

METADATA_CHECKS: list[tuple[str, str, bool]] = [
    ("PySide6", "PySide6", True),
    ("numpy", "numpy", True),
    ("scipy", "scipy", True),
    ("torch", "torch", True),
    ("torchvision", "torchvision", True),
    ("Pillow", "Pillow", True),
    ("opencv-python-headless", "opencv-python-headless", False),
    ("rembg", "rembg", True),
    ("onnxruntime", "onnxruntime", True),
    ("spandrel", "spandrel", True),
    ("imageio", "imageio", True),
    ("imageio-ffmpeg", "imageio-ffmpeg", True),
    ("yt-dlp", "yt-dlp", True),
    ("openai-whisper", "openai-whisper", False),
    ("scenedetect", "scenedetect", True),
    ("google-genai", "google-genai", False),
    ("gspread", "gspread", True),
    ("playwright", "playwright", True),
]


def _smoke_qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication.instance() or QApplication([])
    label = QLabel("smoke")
    label.setObjectName("smoke")
    label.deleteLater()
    app.processEvents()


def _smoke_spandrel():
    from spandrel import ModelLoader

    ModelLoader()


def _smoke_rembg():
    import rembg

    getattr(rembg, "new_session", None)


def _smoke_cv2_unicode_write():
    import cv2
    import numpy as np

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "ảnh_kiểm_tra.png")
        ok = cv2.imwrite(path, np.zeros((4, 4, 3), dtype=np.uint8))
        if not ok or not os.path.exists(path):
            raise RuntimeError("cv2.imwrite failed for unicode path")


def _smoke_scipy_ndimage():
    import numpy as np
    from scipy import ndimage

    ndimage.gaussian_filter(np.zeros((3, 3), dtype=float), 1)


def _smoke_torch_basic():
    import torch

    x = torch.zeros((1, 1))
    if tuple(x.shape) != (1, 1):
        raise RuntimeError("torch tensor shape mismatch")


def _smoke_ffmpeg():
    from utils.platform import find_ffmpeg

    find_ffmpeg()


def _smoke_database():
    from models.database import Database

    with tempfile.TemporaryDirectory() as td:
        db = Database(os.path.join(td, "smoke.db"))
        db.connect()
        db.set_setting("smoke", "ok")
        if db.get_setting("smoke") != "ok":
            raise RuntimeError("database setting roundtrip failed")
        db.close()


def _smoke_playwright_chromium_bundled():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        getattr(p, "chromium")


def _smoke_rembg_birefnet_session():
    import rembg

    getattr(rembg, "new_session", None)


def _smoke_yt_dlp_instantiate():
    import yt_dlp

    ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
    ydl.close()


def _smoke_whisper_models():
    import whisper

    getattr(whisper, "available_models")()


def _smoke_scenedetect_detector():
    from scenedetect.detectors import ContentDetector

    ContentDetector()


def _smoke_google_genai_client():
    from google import genai

    getattr(genai, "Client")


def _smoke_gspread_oauth_chain():
    import gspread
    from google.oauth2 import service_account

    getattr(gspread, "authorize")
    getattr(service_account, "Credentials")


def _smoke_cv2_video_capture():
    import cv2

    cap = cv2.VideoCapture()
    cap.release()


def _smoke_lama_torchscript_load():
    import torch

    getattr(torch.jit, "load")


def _smoke_esrgan_load():
    from spandrel import ModelLoader

    ModelLoader()


def _smoke_pil_basic():
    from PIL import Image

    img = Image.new("RGB", (2, 2), "black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")


def _smoke_imageio_ffmpeg():
    import imageio_ffmpeg

    imageio_ffmpeg.get_ffmpeg_exe()


RUNTIME_CHECKS = [
    ("Qt offscreen app", _smoke_qt, True),
    ("spandrel ModelLoader", _smoke_spandrel, True),
    ("rembg import/session path", _smoke_rembg, True),
    ("cv2 unicode write", _smoke_cv2_unicode_write, True),
    ("scipy ndimage", _smoke_scipy_ndimage, True),
    ("torch basic", _smoke_torch_basic, True),
    ("ffmpeg lookup", _smoke_ffmpeg, True),
    ("database sqlite", _smoke_database, True),
    ("playwright chromium", _smoke_playwright_chromium_bundled, False),
    ("rembg birefnet session", _smoke_rembg_birefnet_session, False),
    ("yt_dlp instantiate", _smoke_yt_dlp_instantiate, True),
    ("whisper models", _smoke_whisper_models, False),
    ("scenedetect detector", _smoke_scenedetect_detector, True),
    ("google genai client", _smoke_google_genai_client, False),
    ("gspread oauth chain", _smoke_gspread_oauth_chain, True),
    ("cv2 VideoCapture", _smoke_cv2_video_capture, True),
    ("LaMa torchscript loader", _smoke_lama_torchscript_load, True),
    ("ESRGAN loader", _smoke_esrgan_load, True),
    ("PIL basic", _smoke_pil_basic, True),
    ("imageio ffmpeg", _smoke_imageio_ffmpeg, True),
]


def _check_import(module_name: str, label: str, critical: bool) -> bool:
    try:
        importlib.import_module(module_name)
        print(f"[OK] import {label}")
        return True
    except Exception as e:
        print(f"[FAIL] import {label}: {type(e).__name__}: {e}")
        traceback.print_exc()
        return not critical


def _check_metadata(dist_name: str, label: str, critical: bool) -> bool:
    try:
        version = im.version(dist_name)
        print(f"[OK] metadata {label}: {version}")
        return True
    except Exception as e:
        print(f"[FAIL] metadata {label}: {type(e).__name__}: {e}")
        return not critical


def run() -> int:
    print("=== NAVTools bundle smoke test ===")
    ok = True

    for module_name, label, critical in MODULES:
        ok = _check_import(module_name, label, critical) and ok

    for dist_name, label, critical in METADATA_CHECKS:
        ok = _check_metadata(dist_name, label, critical) and ok

    for label, fn, critical in RUNTIME_CHECKS:
        try:
            fn()
            print(f"[OK] runtime {label}")
        except Exception as e:
            print(f"[FAIL] runtime {label}: {type(e).__name__}: {e}")
            traceback.print_exc()
            if critical:
                ok = False

    print("=== smoke test passed ===" if ok else "=== smoke test failed ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
