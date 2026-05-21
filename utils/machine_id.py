"""Machine identifier helper."""

from __future__ import annotations

import hashlib
import platform
import uuid


def get_machine_id():
    raw = f"{platform.node()}-{uuid.getnode()}-{platform.system()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
