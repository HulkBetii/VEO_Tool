"""VidGen AI — Runtime settings (persisted in SQLite)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.constants import DATA_DIR, DEFAULT_IMAGE_OUTPUT, DEFAULT_VIDEO_OUTPUT


class Settings:
    """Key-value settings stored in SQLite `settings` table."""

    _defaults: dict[str, Any] = {
        "theme": "dark",
        "max_concurrent_tasks": 5,
        "poll_interval": 5,
        "max_retry": 3,
        "default_image_output": str(DEFAULT_IMAGE_OUTPUT),
        "default_video_output": str(DEFAULT_VIDEO_OUTPUT),
        "default_quality": "Veo 3.1 - Fast",
        "default_aspect_ratio": "16:9",
        "default_concurrent_prompts": 1,
        "default_service": "Flow",
        "default_image_model": "Nano Banana 2",
        "default_save_mode": "1 Thư mục mỗi Task",
        "auto_retry_on_error": True,
        "log_retention_days": 30,
    }

    def __init__(self, db=None):
        self._db = db
        self._cache = {}
        self._load_all()

    def _load_all(self):
        """Load all settings from DB into cache."""
        if self._db:
            rows = self._db.execute("SELECT key, value FROM settings").fetchall()
            for key, value in rows:
                try:
                    self._cache[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    self._cache[key] = value
        return None

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        if key in self._cache:
            return self._cache[key]
        return self._defaults.get(key, default)

    def set(self, key: str, value: Any):
        """Set a setting value and persist to DB."""
        self._cache[key] = value
        if self._db:
            serialized = json.dumps(value)
            self._db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, serialized))
            self._db.commit()
        return None

    def get_all(self) -> dict[str, Any]:
        """Get all settings merged with defaults."""
        result = dict(self._defaults)
        result.update(self._cache)
        return result

    @property
    def theme(self) -> str:
        return self.get("theme", "dark")

    @theme.setter
    def theme(self, value: str):
        self.set("theme", value)

    @property
    def max_concurrent_tasks(self) -> int:
        return self.get("max_concurrent_tasks", 5)

    @property
    def poll_interval(self) -> float:
        return self.get("poll_interval", 5)

    @property
    def max_retry(self) -> int:
        return self.get("max_retry", 3)

    @property
    def default_quality(self) -> str:
        return self.get("default_quality", "Veo 3.1 - Fast")

    @property
    def default_aspect_ratio(self) -> str:
        return self.get("default_aspect_ratio", "16:9")
