"""NAV TOOLS - App login/register screen."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME, APP_VERSION, ASSETS_DIR, DarkColors
from models.database import Database
from utils.logger import log


def _hash_pwd(password):
    """SHA-256 hash with legacy salt."""
    salt = "navtools_v1_salt_2024"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


class _AuthWorker(QThread):
    """Background thread for Sheets API calls."""

    finished = Signal(bool, str)

    def __init__(self, func, *args, parent=None):
        super().__init__(parent)
        self._func = func
        self._args = args

    def run(self):
        try:
            ok, message = self._func(*self._args)
        except Exception as e:
            log.warning(f"Auth worker failed: {e}")
            ok, message = False, "NETWORK_ERROR"
        self.finished.emit(bool(ok), str(message))


class LoginScreen(QDialog):
    """Dark login/register dialog."""

    login_success = Signal(str)

    def __init__(self, db: Database, sheets_auth, parent=None):
        super().__init__(parent)
        self._db = db
        self._sheets = sheets_auth
        self._worker = None
        self._pending_username = ""
        self._drag_pos = None
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(420, 640)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        icon_path = Path(ASSETS_DIR) / "config" / "app_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._init_ui()
        self._load_saved_credentials()
        self._center_on_screen()

    def _init_ui(self):
        self.setObjectName("loginRoot")
        self.setStyleSheet(
            f"""
            QDialog#loginRoot {{
                background: {DarkColors.BG};
                border: 1px solid {DarkColors.OUTLINE_VARIANT};
                border-radius: 16px;
            }}
            QFrame#loginCard {{
                background: {DarkColors.SURFACE_CONTAINER_LOW};
                border: 1px solid {DarkColors.OUTLINE_VARIANT};
                border-radius: 18px;
            }}
            QFrame#heroPanel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {DarkColors.SURFACE_CONTAINER},
                    stop:1 {DarkColors.SURFACE_CONTAINER_HIGH});
                border: 1px solid rgba(173,198,255,0.10);
                border-radius: 14px;
            }}
            QLabel#heroTitle {{
                color: {DarkColors.TEXT_PRIMARY};
                font-size: 24px;
                font-weight: 800;
            }}
            QLabel#heroSubtitle {{
                color: {DarkColors.TEXT_SECONDARY};
                font-size: 12px;
                line-height: 1.4;
            }}
            QLabel#chipLabel {{
                background: rgba(77,142,255,0.16);
                color: {DarkColors.PRIMARY};
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            QLabel#tabTitle {{
                color: {DarkColors.TEXT_PRIMARY};
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel#statusLabel {{
                color: {DarkColors.WARNING};
                font-size: 12px;
                padding: 6px 2px 0 2px;
            }}
            QLabel#switchLabel {{
                color: {DarkColors.TEXT_MUTED};
                font-size: 12px;
            }}
            QLineEdit {{
                background: {DarkColors.SURFACE_CONTAINER};
                color: {DarkColors.TEXT_PRIMARY};
                border: 1px solid {DarkColors.OUTLINE_VARIANT};
                border-radius: 10px;
                padding: 12px 14px;
                font-size: 14px;
                min-height: 22px;
            }}
            QLineEdit:focus {{
                border: 1px solid {DarkColors.PRIMARY_CONTAINER};
            }}
            QPushButton {{
                border-radius: 10px;
                min-height: 42px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#primaryBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {DarkColors.PRIMARY_CONTAINER},
                    stop:1 {DarkColors.ACCENT_BLUE});
                color: white;
                border: none;
            }}
            QPushButton#primaryBtn:hover {{
                background: {DarkColors.PRIMARY_CONTAINER};
            }}
            QPushButton#ghostBtn {{
                background: transparent;
                color: {DarkColors.PRIMARY};
                border: 1px solid {DarkColors.OUTLINE_VARIANT};
            }}
            QPushButton#ghostBtn:hover {{
                background: rgba(77,142,255,0.10);
            }}
            QPushButton#topBtn {{
                min-height: 28px;
                max-width: 28px;
                border-radius: 14px;
                background: transparent;
                color: {DarkColors.TEXT_MUTED};
                border: 1px solid transparent;
            }}
            QPushButton#topBtn:hover {{
                background: rgba(255,255,255,0.06);
                border-color: {DarkColors.OUTLINE_VARIANT};
            }}
            QCheckBox {{
                color: {DarkColors.TEXT_SECONDARY};
                spacing: 8px;
                font-size: 12px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {DarkColors.OUTLINE};
                background: {DarkColors.SURFACE_CONTAINER};
            }}
            QCheckBox::indicator:checked {{
                background: {DarkColors.PRIMARY_CONTAINER};
                border-color: {DarkColors.PRIMARY_CONTAINER};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("loginCard")
        root.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.addStretch()
        min_btn = QPushButton("—")
        min_btn.setObjectName("topBtn")
        min_btn.clicked.connect(self.showMinimized)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("topBtn")
        close_btn.clicked.connect(self.reject)
        top_bar.addWidget(min_btn)
        top_bar.addWidget(close_btn)
        card_layout.addLayout(top_bar)

        hero = QFrame()
        hero.setObjectName("heroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 16, 16)
        hero_layout.setSpacing(10)

        hero_top = QHBoxLayout()
        hero_top.setSpacing(10)
        hero_top.addWidget(self._build_logo_badge())
        hero_top.addStretch()
        chip = QLabel(f"v{APP_VERSION}")
        chip.setObjectName("chipLabel")
        hero_top.addWidget(chip)
        hero_layout.addLayout(hero_top)

        hero_title = QLabel(APP_NAME)
        hero_title.setObjectName("heroTitle")
        hero_layout.addWidget(hero_title)

        hero_subtitle = QLabel(
            "Đăng nhập để đồng bộ tài khoản, lưu cấu hình và sử dụng toàn bộ workflow tạo ảnh, video, prompt."
        )
        hero_subtitle.setObjectName("heroSubtitle")
        hero_subtitle.setWordWrap(True)
        hero_layout.addWidget(hero_subtitle)
        card_layout.addWidget(hero)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_login_form())
        self.stack.addWidget(self._build_register_form())
        card_layout.addWidget(self.stack, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.status_label)

    def _build_logo_badge(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(
            f"background: rgba(173,198,255,0.08); border: 1px solid rgba(173,198,255,0.12); border-radius: 12px;"
        )
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setFixedSize(36, 36)
        icon_path = Path(ASSETS_DIR) / "config" / "app_icon.ico"
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        mini = QLabel("Workspace")
        mini.setStyleSheet(f"color: {DarkColors.TEXT_MUTED}; font-size: 10px;")
        stamp = QLabel(datetime.now().strftime("%Y-%m-%d"))
        stamp.setStyleSheet(f"color: {DarkColors.TEXT_PRIMARY}; font-size: 12px; font-weight: 700;")
        text_col.addWidget(mini)
        text_col.addWidget(stamp)
        layout.addLayout(text_col)
        return wrap

    def _build_login_form(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(12)

        title = QLabel("Đăng nhập")
        title.setObjectName("tabTitle")
        layout.addWidget(title)

        desc = QLabel("Sử dụng tài khoản đã đăng ký để tiếp tục vào ứng dụng.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {DarkColors.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(desc)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Tên đăng nhập")
        self.password_edit = self._make_password_field("Mật khẩu")
        self.remember_check = QCheckBox("Ghi nhớ tài khoản")
        self.login_btn = self._make_primary_btn("Đăng nhập")
        self.login_btn.clicked.connect(self._do_login)

        switch_row = QHBoxLayout()
        switch_row.addStretch()
        switch_row.addWidget(self._make_switch_button("Chưa có tài khoản?", "Tạo tài khoản", self._show_register))

        layout.addWidget(self.username_edit)
        layout.addWidget(self.password_edit)
        layout.addWidget(self.remember_check)
        layout.addWidget(self.login_btn)
        layout.addLayout(switch_row)
        layout.addStretch()
        return page

    def _build_register_form(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(12)

        title = QLabel("Tạo tài khoản")
        title.setObjectName("tabTitle")
        layout.addWidget(title)

        desc = QLabel("Tạo tài khoản mới để đăng ký quyền truy cập và chờ kích hoạt.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {DarkColors.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(desc)

        self.reg_username_edit = QLineEdit()
        self.reg_username_edit.setPlaceholderText("Tên đăng nhập")
        self.reg_email_edit = QLineEdit()
        self.reg_email_edit.setPlaceholderText("Email")
        self.reg_password_edit = self._make_password_field("Mật khẩu")
        self.reg_confirm_edit = self._make_password_field("Nhập lại mật khẩu")
        self.reg_btn = self._make_primary_btn("Đăng ký")
        self.reg_btn.clicked.connect(self._do_register)

        switch_row = QHBoxLayout()
        switch_row.addStretch()
        switch_row.addWidget(self._make_switch_button("Đã có tài khoản?", "Quay lại đăng nhập", self._show_login))

        layout.addWidget(self.reg_username_edit)
        layout.addWidget(self.reg_email_edit)
        layout.addWidget(self.reg_password_edit)
        layout.addWidget(self.reg_confirm_edit)
        layout.addWidget(self.reg_btn)
        layout.addLayout(switch_row)
        layout.addStretch()
        return page

    def _make_switch_button(self, prefix: str, action_text: str, callback) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        label = QLabel(prefix)
        label.setObjectName("switchLabel")
        btn = QPushButton(action_text)
        btn.setObjectName("ghostBtn")
        btn.setMinimumHeight(34)
        btn.clicked.connect(callback)
        row.addWidget(label)
        row.addWidget(btn)
        return wrap

    def _make_password_field(self, placeholder):
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    def _make_primary_btn(self, text):
        btn = QPushButton(text)
        btn.setObjectName("primaryBtn")
        btn.setMinimumHeight(44)
        return btn

    def _show_login(self):
        self.status_label.clear()
        self.stack.setCurrentIndex(0)

    def _show_register(self):
        self.status_label.clear()
        self.stack.setCurrentIndex(1)

    def _do_login(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self.status_label.setText("Nhập tên đăng nhập và mật khẩu.")
            return
        self._pending_username = username
        self.status_label.setText("Đang đăng nhập...")
        self.login_btn.setEnabled(False)
        self._worker = _AuthWorker(self._sheets.login, username, password, parent=self)
        self._worker.finished.connect(self._on_login_result)
        self._worker.start()

    def _on_login_result(self, ok, message):
        self.login_btn.setEnabled(True)
        if ok:
            self._on_login_ok(self._pending_username)
        else:
            self.status_label.setText(str(message).replace("_", " ").title())
        self._worker = None

    def _do_register(self):
        username = self.reg_username_edit.text().strip()
        email = self.reg_email_edit.text().strip()
        password = self.reg_password_edit.text()
        confirm = self.reg_confirm_edit.text()
        if not username or not email or not password:
            self.status_label.setText("Điền đầy đủ thông tin đăng ký.")
            return
        if password != confirm:
            self.status_label.setText("Mật khẩu xác nhận không khớp.")
            return
        self._pending_username = username
        self.status_label.setText("Đang gửi đăng ký...")
        self.reg_btn.setEnabled(False)
        self._worker = _AuthWorker(self._sheets.register, username, password, email, parent=self)
        self._worker.finished.connect(self._on_register_result)
        self._worker.start()

    def _on_register_result(self, ok, message):
        self.reg_btn.setEnabled(True)
        if ok:
            self._show_login()
            self.status_label.setText("Đăng ký thành công. Chờ kích hoạt rồi đăng nhập.")
        else:
            self.status_label.setText(str(message).replace("_", " ").title())
        self._worker = None

    @staticmethod
    def _obfuscate(text):
        return "".join(chr(ord(ch) ^ 23) for ch in str(text or ""))

    @staticmethod
    def _deobfuscate(text):
        return "".join(chr(ord(ch) ^ 23) for ch in str(text or ""))

    def _on_login_ok(self, username):
        if self.remember_check.isChecked():
            try:
                self._db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    ("remembered_login", self._obfuscate(username)),
                )
                self._db.commit()
            except Exception as e:
                log.warning(f"Could not save remembered login: {e}")
        self.login_success.emit(username)
        self.accept()

    def _load_saved_credentials(self):
        try:
            row = self._db.execute("SELECT value FROM settings WHERE key = ?", ("remembered_login",)).fetchone()
            if row and row[0]:
                self.username_edit.setText(self._deobfuscate(row[0]))
                self.remember_check.setChecked(True)
        except Exception:
            pass

    def _center_on_screen(self):
        try:
            from PySide6.QtWidgets import QApplication

            screen = QApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
        except Exception:
            pass

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._do_login() if self.stack.currentIndex() == 0 else self._do_register()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag_pos") and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)
