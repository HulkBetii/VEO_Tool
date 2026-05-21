"""Pre-import heavy ML modules + pre-spawn Playwright binaries in a
background thread so the user's first task launches instantly.

Two problems this solves:

1. **Heavy ML imports**: numpy + torch + spandrel + scipy take ~10-15s
   first import on Windows. Without warmup, MainWindow init pays this
   when UpscalePage / WatermarkRemovePage construct.

2. **Antivirus first-scan delay**: when EXE first spawns
   `chrome.exe` + `node.exe` from the bundled playwright-browsers/,
   Windows Defender scans them on first execution → 30s+ block.
   User clicks "Tạo" and app appears frozen. Pre-spawning each binary
   with `--version` flag warms the AV cache while user is still on the
   login screen.

The thread is daemon + best-effort: failures are logged but never block
the app. Users with smooth setups get a fast first task; users with AV
delays still see correct behavior, just with normal first-launch latency.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path


class _LazyLog:
    def _get(self):
        from utils.logger import log

        return log

    def info(self, msg):
        self._get().info(msg)

    def warning(self, msg):
        self._get().warning(msg)

    def debug(self, msg):
        self._get().debug(msg)

    def error(self, msg):
        self._get().error(msg)


log = _LazyLog()

_HEAVY_MODULES: tuple[str, ...] = (
    "numpy",
    "torch",
    "scipy",
    "scipy.ndimage",
    "PIL.Image",
    "spandrel",
    "rembg",
    "cv2",
    "playwright.async_api",
    "google.genai",
)


def _prewarm_playwright_binaries() -> None:
    """Spawn chrome.exe + node.exe with --version so Windows Defender
    scans them in background. Without this, the first `pw.chromium.launch()`
    blocks 30s+ while AV scans both binaries on first execution.

    `--version` is a fast no-op (~100ms) but forces the OS loader + AV
    to fully process the binary, leaving it warm-cached for the real launch.
    """
    if sys.platform != "win32":
        return
    if not getattr(sys, "frozen", False):
        return

    app_dir = Path(sys.executable).parent
    chrome_exe = app_dir / "playwright-browsers" / "chromium-1208" / "chrome-win64" / "chrome.exe"
    node_exe = app_dir / "_internal" / "playwright" / "driver" / "node.exe"

    targets = [
        ("chrome", chrome_exe, ["--version"]),
        ("node", node_exe, ["--version"]),
    ]

    for name, exe, args in targets:
        if not exe.exists():
            log.debug(f"[warmup] {name} binary not found at {exe} — skip")
            continue

        try:
            t0 = time.perf_counter()
            subprocess.run(
                [str(exe)] + args,
                capture_output=True,
                timeout=60,
                check=False,
                creationflags=0x08000000,
            )
            elapsed = time.perf_counter() - t0
            log.info(f"[warmup] {name}.exe AV-scan warm in {elapsed:.1f}s")
        except subprocess.TimeoutExpired:
            log.warning(
                f"[warmup] {name}.exe --version timed out (60s) — likely AV scanning. "
                "First task may still be slow."
            )
        except Exception as e:
            log.debug(f"[warmup] {name}.exe spawn failed: {e}")


def _warmup_worker() -> None:
    """Import heavy modules + pre-spawn Playwright binaries. Daemon thread."""
    t0 = time.perf_counter()
    succeeded = []
    failed = []

    for name in _HEAVY_MODULES:
        try:
            __import__(name)
            succeeded.append(name)
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {str(e)[:60]}"))

    try:
        import torch

        _ = torch.zeros(1)
    except Exception:
        pass

    elapsed = time.perf_counter() - t0
    if failed:
        log.info(
            f"[warmup] preloaded {len(succeeded)}/{len(_HEAVY_MODULES)} modules in {elapsed:.1f}s — failed: "
            + ", ".join(f"{n} ({why})" for n, why in failed)
        )
    else:
        log.info(
            f"[warmup] preloaded {len(succeeded)} heavy modules in {elapsed:.1f}s — "
            "MainWindow init should now be near-instant"
        )

    _prewarm_playwright_binaries()


def start_warmup() -> threading.Thread:
    """Fire warmup in a daemon thread and return immediately.

    Call this AFTER QApplication is constructed (so user sees UI quickly)
    but ideally BEFORE the user clicks anything that needs Playwright/torch
    so the imports + AV scans complete in parallel with human-speed clicking.
    """
    t = threading.Thread(target=_warmup_worker, name="eager_warmup", daemon=True)
    t.start()
    log.info("[warmup] started background pre-import + binary AV-scan warm")
    return t
