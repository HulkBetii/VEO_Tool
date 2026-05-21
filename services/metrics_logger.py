"""Structured JSONL metrics for YouTube → Prompt + Idea → Video pipelines."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.constants import DATA_DIR


log = logging.getLogger("navtools.metrics")
_METRICS_DIR = Path(DATA_DIR) / "metrics"
_WRITE_LOCK = threading.Lock()


def _current_file() -> Path:
    """One file per month — cheap rotation, no external logrotate."""
    _METRICS_DIR.mkdir(parents=True, exist_ok=True)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return _METRICS_DIR / f"{month}.jsonl"


def emit(event: str, **fields: Any) -> None:
    """Append one JSONL line. Never raises — metrics must not break callers."""
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with _WRITE_LOCK:
            with open(_current_file(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        log.debug(f"[metrics] emit '{event}' failed: {e}")


def emit_analyze_complete(
    source: str,
    num_scenes: int,
    num_character_refs: int,
    ai_tier_used: str,
    fallback_count: int,
    latency_ms: int,
    success: bool,
    **extra: Any,
) -> None:
    """Called once per analyze() invocation — covers both pages."""
    emit(
        "analyze_complete",
        source=source,
        num_scenes=num_scenes,
        num_character_refs=num_character_refs,
        has_multimodal=num_character_refs > 0,
        ai_tier_used=ai_tier_used,
        fallback_count=fallback_count,
        latency_ms=latency_ms,
        success=success,
        **extra,
    )


def emit_gemini_fallback(from_model: str, to_model: str, error_type: str) -> None:
    """Fire every time the fallback chain advances to the next tier."""
    emit("gemini_fallback", from_model=from_model, to_model=to_model, error_type=error_type)


def emit_render_complete(
    source: str,
    task_id: int,
    num_items: int,
    num_success: int,
    num_error: int,
    duration_seconds: float,
) -> None:
    """Called once when a video render task finishes."""
    emit(
        "render_complete",
        source=source,
        task_id=task_id,
        num_items=num_items,
        num_success=num_success,
        num_error=num_error,
        success_rate=(num_success / num_items if num_items else 0),
        duration_seconds=round(duration_seconds, 1),
    )
