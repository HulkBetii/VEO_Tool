"""Cleanup orphan browser resources."""

from __future__ import annotations

import shutil
from pathlib import Path

from utils.logger import log


def _get_log():
    return log


def _kill_orphan_chromes():
    return 0


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
