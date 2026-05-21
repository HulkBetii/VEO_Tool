"""Cleanup orphan browser resources."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from utils.logger import log


def _get_log():
    return log


def _kill_orphan_chromes():
    """Kill Chrome/Chromium processes that were launched with our profile dir.

    Only targets processes whose command line explicitly contains the app
    browser-profile directory marker, to avoid touching user's real Chrome.
    """
    try:
        from config.constants import BROWSER_PROFILE_DIR
        marker = str(BROWSER_PROFILE_DIR)
    except Exception:
        return 0

    killed = 0
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "process", "where", f"name like '%chrome%'", "get", "ProcessId,CommandLine", "/format:csv"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.splitlines():
                if marker in line:
                    parts = line.strip().split(",")
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[-1].strip())
                            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=5)
                            killed += 1
                        except Exception:
                            pass
        except Exception as e:
            log.debug(f"_kill_orphan_chromes (win32): {e}")
    else:
        try:
            result = subprocess.run(
                ["pgrep", "-af", "chrom"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.splitlines():
                if marker not in line:
                    continue
                parts = line.split(None, 1)
                if not parts:
                    continue
                try:
                    pid = int(parts[0])
                    os.kill(pid, signal.SIGTERM)
                    killed += 1
                except (ProcessLookupError, ValueError):
                    pass
                except Exception:
                    pass
        except Exception as e:
            log.debug(f"_kill_orphan_chromes (posix): {e}")
    return killed


def _remove_stale_temp_profiles(base_dir=None):
    import tempfile
    base = Path(base_dir) if base_dir else Path(tempfile.gettempdir())
    removed = 0
    for pattern in ("vidgen_recaptcha_*", "navtools_*"):
        for path in base.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
    return removed


def cleanup_orphan_resources():
    killed = _kill_orphan_chromes()
    removed = _remove_stale_temp_profiles()
    log.info(f"cleanup orphan resources: killed={killed}, removed={removed}")
    return {"killed": killed, "removed": removed}
