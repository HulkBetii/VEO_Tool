"""Application logger."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from config.constants import LOG_DIR


def setup_logger(name="navtools"):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        file_handler = logging.FileHandler(LOG_DIR / f"{datetime.now():%Y%m%d}.log", encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(stream)
        logger.addHandler(file_handler)
    return logger


def cleanup_old_logs(days=30):
    cutoff = datetime.now() - timedelta(days=days)
    for path in Path(LOG_DIR).glob("*.log"):
        if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
            path.unlink(missing_ok=True)


log = setup_logger()
