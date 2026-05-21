"""NAV TOOLS - Settings dialog with Google account management."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME, ASSETS_DIR, BASE_DIR, BROWSER_PROFILE_DIR
from config.settings import Settings
from models.account import Account
from models.database import Database
from utils.logger import log
from utils.platform import find_chrome


def _read_chrome_cookies(profile_dir: Path):
    """Read email and cookie expiry from a Chrome profile."""
    info = {"email": None, "cookie_exp": None}
    profile_dir = Path(profile_dir)
    for prefs_name in ("Default/Preferences", "Default/Secure Preferences"):
        prefs_file = profile_dir / prefs_name
        if not prefs_file.exists() or info["email"]:
            continue
        try:
            with prefs_file.open("r", encoding="utf-8") as f:
                prefs = json.load(f)
            account_info = prefs.get("account_info") or []
            if account_info:
                info["email"] = account_info[0].get("email")
            signin = prefs.get("signin") or {}
            info["email"] = info["email"] or signin.get("allowed_username") or signin.get("username")
        except Exception as e:
            log.warning(f"Could not read {prefs_file}: {e}")

    cookies_db = profile_dir / "Default" / "Network" / "Cookies"
    tmp_db = profile_dir / "cookies_copy.db"
    if cookies_db.exists():
        try:
            shutil.copy2(cookies_db, tmp_db)
            conn = sqlite3.connect(str(tmp_db))
            row = conn.execute("SELECT MAX(expires_utc) FROM cookies WHERE host_key LIKE '%google.com%'").fetchone()
            conn.close()
            if row and row[0]:
                chrome_epoch = datetime(1601, 1, 1)
                info["cookie_exp"] = chrome_epoch + timedelta(microseconds=int(row[0]))
        except Exception as e:
            log.warning(f"Could not read Cookies DB: {e}")
        finally:
            try:
                os.remove(tmp_db)
            except Exception:
                pass
    return info


class _LoginSignals(QObject):
    success = Signal(str, str, object, object, object)
    status = Signal(str)
    failed = Signal(str)
    finished = Signal()


class _RenewSignals(QObject):
    success = Signal(int, object, object, object)
    failed = Signal(int, str)
    finished = Signal()


class SettingsDialog(QDialog):
    """Settings and account management dialog."""

    def __init__(self, db: Database, settings: Settings | None = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.settings = settings or Settings(db)
        self.accounts: list[Account] = []
        self._login_thread = None
        self._renew_thread = None
        self.setWindowTitle(f"{APP_NAME} — Cài đặt hệ thống")
        self.setMinimumSize(950, 550)
        self.setModal(True)
        self._init_ui()
        self._load_accounts()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self._build_accounts_tab(self.tabs)
        self._build_general_tab(self.tabs)
        self._build_donate_tab(self.tabs)
        actions = QHBoxLayout()
        actions.addStretch()
        save_btn = QPushButton("Lưu")
        save_btn.clicked.connect(self._save_settings)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(save_btn)
        actions.addWidget(close_btn)
        root.addLayout(actions)

    def _build_accounts_tab(self, tabs):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Tìm email tài khoản...")
        self.search_edit.textChanged.connect(self._filter_accounts)
        add_btn = QPushButton("Thêm tài khoản Google")
        add_btn.clicked.connect(self._add_account)
        top.addWidget(self.search_edit)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self.accounts_table = QTableWidget(0, 7)
        self.accounts_table.setHorizontalHeaderLabels(["Email", "Gói", "Credit", "Cookie Exp", "Bật", "Gemini Key", "Thao tác"])
        self.accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.accounts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.accounts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.accounts_table)
        tabs.addTab(tab, "🌐 Tài khoản Google")

    def _build_general_tab(self, tabs):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(str(self.settings.get("theme", "dark")))
        self.gemini_key_edit = QLineEdit(str(self.settings.get("gemini_api_key", "") or ""))
        self.gemini_key_edit.setEchoMode(QLineEdit.Password)
        self.auto_retry_check = QCheckBox("Tự retry tác vụ lỗi")
        self.auto_retry_check.setChecked(bool(self.settings.get("auto_retry_on_error", True)))
        guide_btn = QPushButton("Hướng dẫn lấy Gemini API key")
        guide_btn.clicked.connect(self._show_gemini_key_guide)
        layout.addWidget(QLabel("Theme"))
        layout.addWidget(self.theme_combo)
        layout.addWidget(QLabel("Gemini API key"))
        layout.addWidget(self.gemini_key_edit)
        layout.addWidget(self.auto_retry_check)
        layout.addWidget(guide_btn)
        layout.addStretch()
        tabs.addTab(tab, "⚙️ Cài đặt chung")

    def _toggle_inline_gemini_guide(self):
        self._show_gemini_key_guide()

    def _load_gemini_screenshot(self, label, filename, width):
        path = Path(ASSETS_DIR) / filename
        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                label.setPixmap(pix.scaledToWidth(width, Qt.SmoothTransformation))
                return True
        return False

    def _show_gemini_key_guide(self):
        QMessageBox.information(
            self,
            "Gemini API key",
            "Mở Google AI Studio, tạo API key rồi dán vào ô Gemini API key.",
        )

    def _try_fetch_gemini_key(self, account_id=None):
        return None

    def _start_clipboard_watch_for_gemini_key(self):
        return None

    def _get_or_fetch_qr(self):
        qr = Path(ASSETS_DIR) / "donate_qr.png"
        return qr if qr.exists() else None

    def _build_donate_tab(self, tabs):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Ủng hộ NAV Tools"))
        qr = QLabel()
        if self._get_or_fetch_qr():
            self._load_gemini_screenshot(qr, "donate_qr.png", 260)
        layout.addWidget(qr)
        layout.addStretch()
        tabs.addTab(tab, "❤️ Ủng hộ team")

    def _copy_to_clipboard(self, text, button=None):
        app = self.window().windowHandle()
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(str(text or ""))
        if button:
            old = button.text()
            button.setText("Copied")
            QThread.msleep(150)
            button.setText(old)

    def _make_tier_badge(self, tier):
        label = QLabel(str(tier or "FREE"))
        label.setAlignment(Qt.AlignCenter)
        return label

    def _make_action_buttons(self, account):
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        renew = QPushButton("Gia hạn")
        edit = QPushButton("Sửa")
        delete = QPushButton("Xóa")
        renew.clicked.connect(lambda _, a=account: self._renew_session(a))
        edit.clicked.connect(lambda _, a=account: self._edit_account(a))
        delete.clicked.connect(lambda _, a=account: self._delete_account(a))
        layout.addWidget(renew)
        layout.addWidget(edit)
        layout.addWidget(delete)
        return box

    def _load_accounts(self):
        try:
            self.accounts = self.db.get_accounts()
        except Exception as e:
            log.warning(f"Could not load accounts: {e}")
            self.accounts = []
        self.accounts_table.setRowCount(0)
        for row, account in enumerate(self.accounts):
            self.accounts_table.insertRow(row)
            self.refresh_account_row(row, account)

    def refresh_account_row(self, row, account):
        self.accounts_table.setItem(row, 0, QTableWidgetItem(account.email))
        self.accounts_table.setCellWidget(row, 1, self._make_tier_badge(account.tier))
        self.accounts_table.setItem(row, 2, QTableWidgetItem(str(account.credit)))
        exp = account.cookie_exp.isoformat(sep=" ", timespec="minutes") if account.cookie_exp else ""
        self.accounts_table.setItem(row, 3, QTableWidgetItem(exp))
        enabled = QCheckBox()
        enabled.setChecked(bool(account.enabled))
        enabled.toggled.connect(lambda checked, a=account: self._toggle_account(a, checked))
        self.accounts_table.setCellWidget(row, 4, self._center(enabled))
        self.accounts_table.setItem(row, 5, QTableWidgetItem("Yes" if account.gemini_api_key else ""))
        self.accounts_table.setCellWidget(row, 6, self._make_action_buttons(account))

    def _center(self, widget):
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        layout.addWidget(widget)
        layout.addStretch()
        return box

    def _filter_accounts(self, text):
        needle = str(text or "").lower()
        for row, account in enumerate(self.accounts):
            self.accounts_table.setRowHidden(row, needle not in account.email.lower())

    def _add_account(self):
        chrome = find_chrome()
        if not chrome:
            QMessageBox.warning(self, "Không tìm thấy Chrome", "Đăng nhập Google cần Chrome.")
            return
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([chrome, f"--user-data-dir={BROWSER_PROFILE_DIR}", "https://accounts.google.com/"], cwd=str(BASE_DIR))
        self._monitor_login_and_fetch()

    def _monitor_login_and_fetch(self):
        thread = threading.Thread(target=lambda: asyncio.run(self._async_monitor_login()), daemon=True)
        thread.start()
        self._login_thread = thread

    async def _async_monitor_login(self):
        for _ in range(180):
            info = _read_chrome_cookies(Path(BROWSER_PROFILE_DIR))
            if info.get("email"):
                self._on_login_success(info["email"], str(BROWSER_PROFILE_DIR), info.get("cookie_exp"), None, None)
                return
            await asyncio.sleep(1)
        self._on_login_failed("Đăng nhập quá thời gian chờ.")

    def _on_login_success(self, email, cookie_path, cookie_exp=None, token_exp=None, gemini_api_key=None):
        account = None
        for existing in self.db.get_accounts():
            if existing.email == email:
                account = existing
                break
        if account is None:
            account = self.db.add_account(email)
        account.cookie_path = cookie_path
        account.cookie_exp = cookie_exp
        account.token_exp = token_exp
        account.gemini_api_key = gemini_api_key or account.gemini_api_key
        self.db.update_account(account)
        self._load_accounts()
        QMessageBox.information(self, "Đã lưu đăng nhập", f"Đã lưu tài khoản: {email}")

    def _on_login_status(self, text):
        log.info(text)

    def _on_login_failed(self, message):
        QMessageBox.warning(self, "Đăng nhập thất bại", str(message))

    def _on_login_finished(self):
        self._login_thread = None

    def _renew_session(self, account):
        if not account:
            return
        thread = threading.Thread(target=lambda: self._run_renew(account.id, account.email, account.cookie_path, None), daemon=True)
        thread.start()
        self._renew_thread = thread

    def _run_renew(self, account_id, email, cookie_path, progress=None):
        try:
            asyncio.run(self._async_renew(account_id, email, cookie_path, progress))
        except Exception as e:
            self._on_renew_failed(account_id, str(e))

    def _cleanup_renew_chrome(self, profile_dir):
        return None

    async def _async_renew(self, account_id, email, cookie_path, progress=None):
        await asyncio.sleep(0.5)
        info = _read_chrome_cookies(Path(cookie_path or BROWSER_PROFILE_DIR))
        self._on_renew_success(account_id, info.get("cookie_exp"), None, info.get("email") or email)

    def _on_renew_success(self, account_id, cookie_exp=None, token_exp=None, email=None):
        account = self.db.get_account(account_id)
        if account:
            account.cookie_exp = cookie_exp or account.cookie_exp
            account.token_exp = token_exp or account.token_exp
            account.email = email or account.email
            self.db.update_account(account)
        self._load_accounts()

    def _on_renew_failed(self, account_id, message):
        QMessageBox.warning(self, "Gia hạn thất bại", str(message))

    def _on_renew_finished(self):
        self._renew_thread = None

    def _toggle_account(self, account, enabled):
        account.enabled = bool(enabled)
        self.db.update_account(account)

    def _edit_account(self, account):
        if not account:
            return
        key, ok = QMessageBox.question(self, "Sửa tài khoản", f"Bật/tắt tài khoản {account.email}?"), True
        if ok:
            account.enabled = not account.enabled
            self.db.update_account(account)
            self._load_accounts()

    def _delete_account(self, account):
        if not account:
            return
        if QMessageBox.question(self, "Xóa tài khoản", f"Xóa {account.email}?") == QMessageBox.Yes:
            self.db.delete_account(account.id)
            self._load_accounts()

    def _save_settings(self):
        self.settings.set("theme", self.theme_combo.currentText())
        self.settings.set("gemini_api_key", self.gemini_key_edit.text().strip())
        self.settings.set("auto_retry_on_error", self.auto_retry_check.isChecked())
        self.accept()

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)
