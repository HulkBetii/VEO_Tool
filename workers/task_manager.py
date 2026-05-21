"""Background task manager."""

from __future__ import annotations

import threading
import time
from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal


class WorkerSignals(QObject):
    task_started = Signal(int)
    task_completed = Signal(int)
    task_error = Signal(int, str)
    task_progress = Signal(int, int, int)
    item_status_changed = Signal(int, str)
    item_completed = Signal(int, str)
    item_error = Signal(int, str)
    credit_updated = Signal(int, int)
    account_disabled = Signal(int, str, str)


class AccountPool:
    def __init__(self, db):
        self.db = db
        self._busy = set()
        self._lock = threading.Lock()

    def acquire(self):
        accounts = self.db.get_accounts(enabled_only=True) if self.db else []
        with self._lock:
            for account in accounts:
                if account.id not in self._busy:
                    self._busy.add(account.id)
                    return account
        return None

    def release(self, account):
        if account:
            with self._lock:
                self._busy.discard(account.id)

    def available_count(self):
        try:
            accounts = self.db.get_accounts(enabled_only=True)
            with self._lock:
                return len([a for a in accounts if a.id not in self._busy])
        except Exception:
            return 0


class TaskWorker(QThread):
    def __init__(self, task, db=None, browser_manager=None, account_pool=None, parent=None):
        super().__init__(parent)
        self.task = task
        self.db = db
        self.browser_manager = browser_manager
        self.account_pool = account_pool
        self.signals = WorkerSignals()
        self._cancelled = False
        self._paused = False

    def _cancellable_sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self._cancelled:
                return False
            time.sleep(0.1)
        return True

    def cancel(self):
        self._cancelled = True

    def _schedule_close(self):
        return None

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def run(self):
        try:
            self._execute()
        except Exception as e:
            self.signals.task_error.emit(getattr(self.task, "id", 0), str(e))

    def _execute(self):
        task_id = getattr(self.task, "id", 0)
        self.signals.task_started.emit(task_id)
        items = getattr(self.task, "items", []) or []
        total = len(items)
        for i, item in enumerate(items, 1):
            if self._cancelled:
                break
            while self._paused and not self._cancelled:
                time.sleep(0.2)
            self._run_one(item)
            self.signals.task_progress.emit(task_id, i, total)
        self.signals.task_completed.emit(task_id)

    def _run_one(self, item):
        return self._process_item(item)

    def _process_item(self, item):
        item_id = getattr(item, "id", 0)
        self.signals.item_status_changed.emit(item_id, "RUNNING")
        self.signals.item_completed.emit(item_id, getattr(item, "output_path", "") or "")


class UpscaleSignals(QObject):
    done = Signal(str)
    error = Signal(str)


class UpscaleRunnable(QRunnable):
    def __init__(self, image_path, output_path=None):
        super().__init__()
        self.image_path = image_path
        self.output_path = output_path
        self.signals = UpscaleSignals()

    def run(self):
        try:
            self._execute()
        except Exception as e:
            self.signals.error.emit(str(e))

    def _execute(self):
        self.signals.done.emit(str(self.output_path or self.image_path))


class TaskManager(QObject):
    def __init__(self, db=None, browser_manager=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.browser_manager = browser_manager
        self.account_pool = AccountPool(db)
        self.workers = {}
        self.thread_pool = QThreadPool.globalInstance()

    def start_task(self, task):
        worker = TaskWorker(task, self.db, self.browser_manager, self.account_pool)
        task_id = getattr(task, "id", id(worker))
        self.workers[task_id] = worker
        worker.finished.connect(lambda tid=task_id: self._on_task_done(tid))
        worker.start()
        return worker

    def _get_all_workers(self):
        return list(self.workers.values())

    def pause_task(self, task_id):
        worker = self.workers.get(task_id)
        if worker:
            worker.pause()

    def resume_task(self, task_id):
        worker = self.workers.get(task_id)
        if worker:
            worker.resume()

    def run_upscale(self, image_path, output_path=None):
        runnable = UpscaleRunnable(image_path, output_path)
        self.thread_pool.start(runnable)
        return runnable

    def cancel_task(self, task_id):
        worker = self.workers.get(task_id)
        if worker:
            worker.cancel()

    def cancel_all(self):
        for worker in self._get_all_workers():
            worker.cancel()

    stop_all = cancel_all
    stop_task = cancel_task

    def _on_task_done(self, task_id):
        self.workers.pop(task_id, None)

    def active_tasks(self):
        return list(self.workers)

    def available_accounts(self):
        return self.account_pool.available_count()
