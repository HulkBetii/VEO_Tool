"""VidGen AI — Account model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config.constants import AccountTier


@dataclass
class Account:
    """Google account for Flow API access."""

    id: int = 0
    email: str = ""
    enabled: bool = True
    tier: str = AccountTier.FREE
    credit: int = 0
    proxy: Optional[str] = None
    cookie_path: Optional[str] = None
    cookie_exp: Optional[datetime] = None
    token_exp: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    gemini_api_key: Optional[str] = None

    @property
    def display_email(self) -> str:
        """Truncated email for UI display."""
        if len(self.email) > 18:
            return self.email[:15] + "..."
        return self.email

    @property
    def has_credits(self) -> bool:
        return self.credit > 0

    @property
    def is_expired(self) -> bool:
        if not self.cookie_exp:
            return False
        return datetime.now() > self.cookie_exp

    @property
    def is_token_expired(self) -> bool:
        if not self.token_exp:
            return False
        return datetime.now() > self.token_exp

    @property
    def is_available(self) -> bool:
        """Account is usable for generation."""
        return self.enabled and not self.is_expired and not self.is_token_expired

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "enabled": self.enabled,
            "tier": self.tier,
            "credit": self.credit,
            "proxy": self.proxy,
            "cookie_path": self.cookie_path,
            "cookie_exp": self.cookie_exp.isoformat() if self.cookie_exp else None,
            "token_exp": self.token_exp.isoformat() if self.token_exp else None,
            "created_at": self.created_at.isoformat(),
            "gemini_api_key": self.gemini_api_key,
        }

    @classmethod
    def from_row(cls, row: tuple) -> Account:
        """Create Account from SQLite row."""
        return cls(
            id=row[0],
            email=row[1],
            enabled=bool(row[2]),
            tier=row[3] or AccountTier.FREE,
            credit=row[4] or 0,
            proxy=row[5],
            cookie_path=row[6],
            cookie_exp=datetime.fromisoformat(row[7]) if row[7] else None,
            token_exp=datetime.fromisoformat(row[9]) if len(row) > 9 and row[9] else None,
            created_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
            gemini_api_key=row[10] if len(row) > 10 else None,
        )
