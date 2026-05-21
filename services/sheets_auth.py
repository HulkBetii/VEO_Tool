"""NAV TOOLS — Google Sheets Authentication Service."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from utils.logger import log
from utils.machine_id import get_machine_id


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

COL_USERNAME = 1
COL_PASSWORD = 2
COL_EMAIL = 3
COL_CREATED = 4
COL_EXPIRES = 5
COL_ACTIVE = 6
COL_TIER = 7
COL_MACHINE_ID = 8

HEADERS = (
    "username",
    "password_hash",
    "email",
    "created_at",
    "expires_at",
    "is_active",
    "tier",
    "machine_id",
)


class SheetsAuthService:
    """Authenticate users against a Google Sheet."""

    def __init__(
        self,
        credentials_path,
        sheet_id,
        worksheet_name="users",
        default_expiry_days=30,
        default_expiry_hours: Optional[int] = None,
    ):
        self._creds_path = credentials_path
        self._sheet_id = sheet_id
        self._ws_name = worksheet_name
        self._default_expiry_days = default_expiry_days
        self._default_expiry_hours = default_expiry_hours
        self._client = None
        self._ws = None
        if not Path(credentials_path).exists():
            raise FileNotFoundError(f"Service account key not found: {credentials_path}")

    def _connect(self):
        creds = Credentials.from_service_account_file(self._creds_path, scopes=SCOPES)
        self._client = gspread.authorize(creds)
        spreadsheet = self._client.open_by_key(self._sheet_id)
        self._ws = spreadsheet.worksheet(self._ws_name)
        self._ensure_machine_id_column()
        return self._ws

    def _ensure_machine_id_column(self):
        ws = self._ws
        headers = ws.row_values(1)
        if len(headers) < len(HEADERS):
            headers = list(headers) + list(HEADERS[len(headers) :])
            ws.update("A1:H1", [headers])

    def _find_user_row_number(self, username):
        ws = self._connect()
        values = ws.col_values(COL_USERNAME)
        target = str(username).strip().lower()
        for i, value in enumerate(values, 1):
            if str(value).strip().lower() == target:
                return i
        return None

    def _update_machine_id(self, row_number, machine_id):
        ws = self._connect()
        ws.update_cell(row_number, COL_MACHINE_ID, machine_id)

    def _reconnect(self):
        self._client = None
        self._ws = None
        return self._connect()

    def _safe_call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            self._reconnect()
            return fn(*args, **kwargs)

    def get_user_row(self, username) -> Optional[dict]:
        ws = self._connect()
        row_number = self._find_user_row_number(username)
        if not row_number:
            return None
        values = self._safe_call(ws.row_values, row_number)
        values = list(values) + [""] * max(0, len(HEADERS) - len(values))
        row = dict(zip(HEADERS, values))
        row["_row_number"] = row_number
        return row

    def user_exists(self, username) -> bool:
        return self.get_user_row(username) is not None

    def login(self, username, password_hash):
        """Validate credentials against the Sheet."""
        try:
            user = self.get_user_row(username)
        except Exception as e:
            log.warning(f"Login network error: {e}")
            return False, "NETWORK_ERROR"
        if user is None:
            return False, "USER_NOT_FOUND"

        stored_hash = str(user.get("password_hash", ""))
        if stored_hash != password_hash:
            return False, "WRONG_PASSWORD"

        is_active = str(user.get("is_active", "TRUE")).strip().upper()
        if is_active == "FALSE":
            return False, "ACCOUNT_DISABLED"

        expires_str = str(user.get("expires_at", ""))
        if expires_str:
            try:
                expires_at = datetime.fromisoformat(expires_str)
                if expires_at < datetime.now():
                    return False, "ACCOUNT_EXPIRED"
            except Exception:
                pass

        stored_machine = str(user.get("machine_id", "")).strip()
        current_machine = get_machine_id()
        if stored_machine and stored_machine != current_machine:
            log.warning(f"Machine mismatch for {username}: stored='{stored_machine}', current='{current_machine}'")
            return False, "MACHINE_MISMATCH"
        if not stored_machine:
            self._update_machine_id(user["_row_number"], current_machine)
            log.info(f"Auto-bound {username} to machine '{current_machine}'")

        log.info(f"Sheets auth OK: {username} (tier={user.get('tier', 'FREE')}, machine={current_machine})")
        return True, "OK"

    def register(self, username, password_hash, email):
        """Register a new user in the Sheet."""
        try:
            if self.user_exists(username):
                return False, "USERNAME_EXISTS"

            now = datetime.now()
            if self._default_expiry_hours is not None:
                expires = now + timedelta(hours=self._default_expiry_hours)
            else:
                expires = now + timedelta(days=self._default_expiry_days)

            new_row = [
                username,
                password_hash,
                email,
                now.isoformat(),
                expires.isoformat(),
                "FALSE",
                "FREE",
                get_machine_id(),
            ]
            ws = self._connect()
            self._safe_call(ws.append_row, new_row, value_input_option="RAW")
            log.info(f"Registered new user in Sheet: {username} (expires: {expires.isoformat()})")
            return True, "OK"
        except Exception as e:
            log.error(f"Register failed: {e}")
            return False, "NETWORK_ERROR"
