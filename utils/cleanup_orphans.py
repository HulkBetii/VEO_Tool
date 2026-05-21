"""Cleanup orphan browser resources."""

from __future__ import annotations

import csv
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
        # Use PowerShell + Get-CimInstance (works on Windows 10/11).
        # wmic is deprecated and removed from Windows 11 22H2+.
        ps_script = (
            "Get-CimInstance Win32_Process -Filter \\\"name like '%chrome%'\\\" "
            "| Select-Object ProcessId,CommandLine "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for row in csv.reader(result.stdout.splitlines()):
                if not row or row[0] == "ProcessId":
                    continue
                pid_text = str(row[0]).strip()
                command_line = row[1] if len(row) > 1 else ""
                if marker not in command_line:
                    continue
                try:
                    pid = int(pid_text)
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
