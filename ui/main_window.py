"""VidGen AI - Main Window with TaskManager integration."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QWidget

from config.constants import APP_NAME, APP_VERSION, ASSETS_DIR, TaskMode, TaskStatus
from config.settings import Settings
from models.database import Database
from models.task import TaskItem, VideoTask
from utils.file_utils import generate_task_name
from utils.logger import log


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, db: Database, settings=None, browser_manager=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._db = db
        self.browser_manager = browser_manager
        self._browser_mgr = browser_manager
        self.settings = settings or Settings(db)
        self._settings = self.settings
        self.task_manager = None
        self._task_manager = None
        self._open_settings_dialog = None
        self._content_pages = []
        self.pages = {}
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1200, 720)
        self.resize(1440, 820)
        icon = Path(ASSETS_DIR) / "config" / "app_icon.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self._init_ui()
        self._connect_signals()
        self._apply_theme()
        self._check_accounts_on_startup()

    def _init_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        try:
            from ui.sidebar import Sidebar

            self.sidebar = Sidebar()
            layout.addWidget(self.sidebar)
        except Exception as e:
            log.warning(f"Could not create sidebar: {e}")
            self.sidebar = None

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        from ui.pages.content_page import ContentPage
        from ui.widgets.lazy_page import LazyPage

        modes = [
            TaskMode.IMAGE,
            TaskMode.CHAR_IMAGE,
            TaskMode.CHAR_VIDEO,
            TaskMode.VIDEO_PLAIN,
            TaskMode.VIDEO_REF,
            TaskMode.FRAME_VIDEO,
        ]
        mode_keys = ["image", "char_image", "char_video", "video_plain", "video_ref", "frame_video"]
        self._content_pages = []
        for key, mode in zip(mode_keys, modes):
            page = ContentPage(mode=mode, db=self.db)
            page.start_task.connect(self._on_start_task)
            page.open_settings.connect(self._open_settings)
            self._content_pages.append(page)
            self.pages[key] = page
            self.stack.addWidget(page)

        long_page = self._build_long_video_page()
        self.long_video_page = long_page
        self.pages["long_video"] = long_page
        self.stack.insertWidget(5, long_page)

        lazy_builders = [
            ("youtube", self._build_youtube_page, "YouTubePromptPage"),
            ("script", self._build_script_page, "ScriptToPromptPage"),
            ("bg_remove", self._build_bg_remove_page, "BgRemovePage"),
            ("watermark", self._build_watermark_page, "WatermarkRemovePage"),
            ("image_to_prompt", self._build_img_to_prompt_page, "ImageToPromptPage"),
            ("upscale", self._build_upscale_page, "UpscalePage"),
            ("audio_merge", self._build_audio_merge_page, "AudioMergePage"),
            ("subtitle", self._build_subtitle_page, "SubtitlePage"),
            ("batch_resize", self._build_batch_resize_page, "BatchResizePage"),
            ("log", self._build_log_page, "LogViewerPage"),
        ]
        for key, builder, name in lazy_builders:
            lazy = LazyPage(builder, name=name)
            setattr(self, f"{key}_page_lazy", lazy)
            self.pages[key] = lazy
            self.stack.addWidget(lazy)

        self.stack.setCurrentIndex(3)

    def _safe_page(self, module_name, class_name):
        try:
            module = __import__(module_name, fromlist=[class_name])
            cls = getattr(module, class_name)
            attempts = (
                lambda: cls(db=self.db, browser_mgr=self.browser_manager, settings=self.settings),
                lambda: cls(db=self.db, browser_manager=self.browser_manager, settings=self.settings),
                lambda: cls(db=self.db, settings=self.settings),
                lambda: cls(self.db, self.browser_manager, self.settings),
                lambda: cls(self.db, self.settings),
                lambda: cls(self.db),
                lambda: cls(),
            )
            for attempt in attempts:
                try:
                    return attempt()
                except TypeError:
                    continue
            return cls()
        except Exception as e:
            log.warning(f"Could not load {class_name}: {e}")
            return QWidget()

    def _connect_signals(self):
        if self.sidebar is not None:
            signal = getattr(self.sidebar, "page_changed", None) or getattr(self.sidebar, "navigation_changed", None)
            if signal is not None:
                try:
                    signal.connect(self._on_page_changed)
                except Exception:
                    pass
        for page in self.pages.values():
            self._connect_page_signals(page)
            page_loaded = getattr(page, "page_loaded", None)
            if page_loaded is not None:
                try:
                    page_loaded.connect(self._connect_page_signals)
                except Exception:
                    pass

    def _connect_page_signals(self, page):
        for name, handler in (
            ("start_task", self._on_start_task),
            ("pause_task", self._on_pause_task),
            ("stop_task", self._on_stop_task),
            ("new_task", self._on_new_task),
            ("retry_item", self._on_retry_item),
            ("retry_all", self._on_retry_all),
            ("concat_requested", self._on_concat),
            ("youtube_start_video", self._on_youtube_start_video),
            ("youtube_cancel", self._on_youtube_cancel),
            ("youtube_retry_row", self._on_youtube_retry_row),
            ("youtube_auto_start", self._on_youtube_auto_start),
            ("youtube_send", self._on_youtube_send),
            ("script_start_video", self._on_script_start_video),
            ("script_cancel", self._on_script_cancel),
            ("script_retry_row", self._on_script_retry_row),
            ("script_send_single_prompt", self._on_script_send_single_prompt),
            ("script_cancel_single_prompt", self._on_script_cancel_single_prompt),
            ("upscale_image", self._on_upscale_image),
        ):
            sig = getattr(page, name, None)
            if sig is not None:
                try:
                    sig.connect(handler)
                except Exception:
                    pass

    def _get_task_manager(self):
        if self.task_manager is None:
            try:
                from workers.task_manager import TaskManager

                self.task_manager = TaskManager(self.db, self.browser_manager, self)
            except TypeError:
                self.task_manager = TaskManager(self.db, parent=self)
            except Exception as e:
                log.warning(f"TaskManager unavailable: {e}")
                self.task_manager = None
        if self.task_manager is not None and getattr(self, "long_video_page", None) is not None:
            try:
                self.long_video_page._account_pool = self.task_manager.account_pool
            except Exception:
                pass
        return self.task_manager

    def _on_account_disabled(self, account_id, email, reason):
        QMessageBox.warning(self, "Account disabled", f"{email}: {reason}")
        self._refresh_account_headers()

    def _on_page_changed(self, page):
        if isinstance(page, int):
            index = page
        else:
            keys = list(self.pages)
            index = keys.index(page) if page in self.pages else 3
        label = ""
        if self.sidebar is not None and 0 <= index < len(getattr(self.sidebar, "ITEMS", ())):
            label = self.sidebar.ITEMS[index][1]
        if "Cài đặt" in label:
            self._open_settings()
            return
        if index < 0 or index >= self.stack.count():
            return
        widget = self.stack.widget(index)
        if hasattr(widget, "ensure_loaded") and not widget.is_loaded:
            widget.ensure_loaded()
        if "Logs" in label:
            log_page = getattr(self, "log_page", None)
            if log_page is not None and hasattr(log_page, "refresh"):
                log_page.refresh()
        self.stack.setCurrentIndex(index)

    def _build_long_video_page(self):
        try:
            from ui.pages.long_video_page import LongVideoPage

            try:
                return LongVideoPage(db=self.db, browser_mgr=self.browser_manager, settings=self.settings)
            except TypeError:
                try:
                    return LongVideoPage(self.db, self.browser_manager, self.settings)
                except TypeError:
                    return LongVideoPage()
        except Exception as e:
            log.warning(f"Could not load LongVideoPage: {e}")
            return QWidget()

    def _build_youtube_page(self):
        return self._safe_page("ui.pages.youtube_prompt_page", "YouTubePromptPage")

    def _build_script_page(self):
        return self._safe_page("ui.pages.script_to_prompt_page", "ScriptToPromptPage")

    def _build_bg_remove_page(self):
        return self._safe_page("ui.pages.bg_remove_page", "BgRemovePage")

    def _build_watermark_page(self):
        return self._safe_page("ui.pages.watermark_remove_page", "WatermarkRemovePage")

    def _build_img_to_prompt_page(self):
        return self._safe_page("ui.pages.image_to_prompt_page", "ImageToPromptPage")

    def _build_upscale_page(self):
        return self._safe_page("ui.pages.upscale_page", "UpscalePage")

    def _build_audio_merge_page(self):
        return self._safe_page("ui.pages.audio_merge_page", "AudioMergePage")

    def _build_subtitle_page(self):
        return self._safe_page("ui.pages.subtitle_page", "SubtitlePage")

    def _build_batch_resize_page(self):
        return self._safe_page("ui.pages.batch_resize_page", "BatchResizePage")

    def _build_log_page(self):
        page = self._safe_page("ui.pages.log_viewer", "LogViewerPage")
        self.log_page = page
        return page

    def _apply_theme(self):
        try:
            from ui.themes.dark import DARK_THEME_QSS

            self.setStyleSheet(DARK_THEME_QSS)
        except Exception:
            pass

    def _open_settings(self):
        try:
            from ui.dialogs.settings_dialog import SettingsDialog

            dlg = SettingsDialog(self.db, self.settings, self)
            dlg.exec()
            self._refresh_account_headers()
        except Exception as e:
            QMessageBox.warning(self, "Settings", str(e))

    def _check_accounts_on_startup(self):
        try:
            accounts = self.db.get_accounts(enabled_only=True)
            if not accounts:
                log.warning("No enabled accounts configured")
        except Exception:
            pass

    def _refresh_account_headers(self):
        for page in self.pages.values():
            fn = getattr(page, "refresh_accounts", None) or getattr(page, "refresh_account_headers", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass

    def _on_start_task(self, task):
        manager = self._get_task_manager()
        if manager and hasattr(manager, "start_task"):
            return manager.start_task(task)
        return None

    def _on_pause_task(self, task_id):
        manager = self._get_task_manager()
        if manager and hasattr(manager, "pause_task"):
            return manager.pause_task(task_id)

    def _on_stop_task(self, task_id):
        manager = self._get_task_manager()
        if manager and hasattr(manager, "stop_task"):
            return manager.stop_task(task_id)

    def _on_youtube_start_video(self, payload):
        self._do_youtube_start(payload, self.pages.get("youtube"))
        return self._on_start_task(payload)

    def _do_youtube_start(self, payload, page=None):
        try:
            from services.youtube_analyzer import YouTubeAnalyzer

            analyzer = YouTubeAnalyzer()
            if page is not None:
                setattr(page, "_youtube_analyzer", analyzer)
            return analyzer
        except Exception as e:
            QMessageBox.warning(self, "YouTube analyzer", str(e))
            return None

    def _on_youtube_cancel(self):
        page = self.pages.get("youtube")
        analyzer = getattr(page, "_youtube_analyzer", None)
        if analyzer and hasattr(analyzer, "cancel"):
            analyzer.cancel()

    def _on_youtube_retry_row(self, row):
        page = self.pages.get("youtube")
        fn = getattr(page, "retry_row", None)
        if callable(fn):
            fn(row)

    def _on_youtube_auto_start(self, *args):
        return self._on_youtube_start_video(args[0] if args else {})

    def _on_youtube_send(self, payload):
        return self._on_start_task(payload)

    def _on_script_start_video(self, payload):
        self._do_script_start(payload, self.pages.get("script"))
        return self._on_start_task(payload)

    def _do_script_start(self, payload, page=None):
        try:
            from services.script_analyzer import ScriptAnalyzer

            analyzer = ScriptAnalyzer()
            if page is not None:
                setattr(page, "_script_analyzer", analyzer)
            return analyzer
        except Exception as e:
            QMessageBox.warning(self, "Script analyzer", str(e))
            return None

    def _on_script_cancel(self):
        page = self.pages.get("script")
        analyzer = getattr(page, "_script_analyzer", None)
        if analyzer and hasattr(analyzer, "cancel"):
            analyzer.cancel()

    def _on_script_retry_row(self, row):
        page = self.pages.get("script")
        fn = getattr(page, "retry_row", None)
        if callable(fn):
            fn(row)

    def _on_script_send_single_prompt(self, prompt):
        return self._on_start_task({"prompt": prompt})

    def _on_script_cancel_single_prompt(self, *args):
        return self._on_script_cancel()

    def _on_upscale_image(self, payload):
        page = self.pages.get("upscale")
        fn = getattr(page, "start_upscale", None)
        if callable(fn):
            fn(payload)

    def _stop_spinner(self, page=None):
        fn = getattr(page, "stop_spinner", None) if page else None
        if callable(fn):
            fn()

    def _on_done(self, *args):
        log.info(f"Operation done: {args}")

    def _on_err(self, message):
        QMessageBox.warning(self, "Error", str(message))

    def _on_new_task(self, task):
        self._apply_new_task_cooldown()
        return self._on_start_task(task)

    def _apply_new_task_cooldown(self):
        return None

    def _on_resume_task(self, task_id):
        manager = self._get_task_manager()
        if manager and hasattr(manager, "resume_task"):
            return manager.resume_task(task_id)

    def _reattach_per_item_char_images(self, task):
        return task

    def _on_retry_item(self, item_id):
        manager = self._get_task_manager()
        if manager and hasattr(manager, "retry_item"):
            return manager.retry_item(item_id)

    def _on_retry_all(self, task_id):
        manager = self._get_task_manager()
        if manager and hasattr(manager, "retry_all"):
            return manager.retry_all(task_id)

    def _on_concat(self, payload):
        try:
            from services.video_concat import concat_videos

            return concat_videos(payload)
        except Exception as e:
            QMessageBox.warning(self, "Concat", str(e))

    def _on_task_started(self, task_id):
        log.info(f"Task started: {task_id}")

    def _on_task_completed(self, task_id):
        log.info(f"Task completed: {task_id}")
        page = self._get_current_content_page()
        fn = getattr(page, "on_task_finished", None)
        if callable(fn):
            try:
                fn(task_id)
            except Exception:
                pass

    def _on_task_error(self, task_id, error):
        log.warning(f"Task error {task_id}: {error}")
        # Re-enable action buttons on the active page.
        page = self._get_current_content_page()
        fn = getattr(page, "on_task_finished", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
        # Surface critical configuration errors that would otherwise be silent.
        if "No enabled Google account" in str(error):
            QMessageBox.warning(
                self,
                "Lỗi tài khoản",
                "Không có tài khoản Google nào khả dụng.\n"
                "Vui lòng thêm và xác thực tài khoản trong mục Cài đặt.",
            )

    def _cleanup_script_extra_task(self, task_id):
        return None

    def _on_task_progress(self, task_id, done, total):
        # Try the page that owns this task first; fall back to current page.
        page = self._find_page_by_task(task_id)
        fn = getattr(page, "update_task_progress", None) if page else None
        if not callable(fn):
            page = self._get_current_content_page()
            fn = getattr(page, "update_task_progress", None) if page else None
        if callable(fn):
            fn(task_id, done, total)

    def _on_item_status_changed(self, item_id, status):
        page = self._get_current_content_page()
        fn = getattr(page, "update_item_status", None) if page else None
        if callable(fn):
            fn(item_id, status)

    def _on_item_completed(self, item_id, output_path):
        page = self._get_current_content_page()
        fn = getattr(page, "update_item_status", None) if page else None
        if callable(fn):
            fn(item_id, "COMPLETED", output_path)

    def _on_item_error(self, item_id, error):
        page = self._get_current_content_page()
        # Increment the page-level error counter (used in progress display).
        on_err = getattr(page, "on_item_error", None) if page else None
        if callable(on_err):
            on_err(item_id, error)
        else:
            fn = getattr(page, "update_item_status", None) if page else None
            if callable(fn):
                fn(item_id, "ERROR")

    def _on_credit_updated(self, account_id, credit):
        self._refresh_account_headers()

    def _get_current_content_page(self):
        widget = self.stack.currentWidget()
        # Unwrap LazyPage so callers get the real page widget (with actual slots).
        real = getattr(widget, "real", None)
        if real is not None:
            return real
        return widget

    def _find_page_by_task(self, task_id):
        for page in self.pages.values():
            if getattr(page, "task_id", None) == task_id:
                return page
        return self._get_current_content_page()

    def closeEvent(self, event):
        manager = self._get_task_manager()
        if manager and hasattr(manager, "stop_all"):
            try:
                manager.stop_all()
            except Exception:
                pass
        if self.browser_manager is not None and hasattr(self.browser_manager, "stop"):
            try:
                import asyncio

                asyncio.run(self.browser_manager.stop())
            except Exception:
                pass
        super().closeEvent(event)
