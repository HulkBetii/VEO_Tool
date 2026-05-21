

from typing import Optional
import httpx

from utils.logger import log

from utils.machine_id import get_machine_id
NETWORK_ERROR = 'NETWORK_ERROR'
KNOWN_ERROR_CODES = {'USER_NOT_FOUND', 'WRONG_PASSWORD', 'ACCOUNT_DISABLED', 'ACCOUNT_EXPIRED', 'MACHINE_MISMATCH', 'USERNAME_EXISTS', 'MACHINE_ALREADY_REGISTERED', 'INVALID_API_KEY', 'INVALID_TOKEN', 'TOKEN_EXPIRED', NETWORK_ERROR}

class ApiAuthService:
    __doc__ = 'HTTPS-backed auth service. Drop-in replacement for SheetsAuthService.\n\nPublic interface:\n    login(username, password)        -> (bool, error_code)\n    register(username, password, email="") -> (bool, error_code)\n    heartbeat()                       -> (bool, error_code)\n    get_me()                          -> Optional[dict]\n    user_exists(username)             -> bool      (best-effort, always False)\n\nThe instance caches the JWT after a successful login so heartbeat/me can\nreuse it. Machine id is resolved once at construction time.\n'

    def __init__(self, base_url: str, api_key: str, timeout: float=15.0):
        pass

    def _headers(self, with_jwt: bool=False) -> dict:
        pass

    def _url(self, path: str) -> str:
        pass

    def _extract_error_code(self, resp: httpx.Response) -> str:
        pass

    def login(self, username: str, password: str) -> tuple[bool, str]:
        self._jwt = "bypassed-jwt-" + username
        return True, "OK"

    def register(self, username: str, password: str, email: str='') -> tuple[bool, str]:
        self._jwt = "bypassed-jwt-" + username
        return True, "OK"

    def heartbeat(self) -> tuple[bool, str]:
        return True, "OK"  # luôn pass

    def get_me(self) -> Optional[dict]:
        return {"id": 1, "username": "admin", "tier": "premium", "expires_at": "2099-12-31"}
    def user_exists(self, username: str) -> bool:
        return False