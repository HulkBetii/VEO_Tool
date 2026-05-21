"""Background task manager."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal

from config.constants import DEFAULT_IMAGE_OUTPUT, DEFAULT_VIDEO_OUTPUT, ItemStatus, TaskMode
from services.flow_client import FlowClient
from utils.file_utils import generate_task_name
from utils.logger import log


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
        with self._lock:
            accounts = self.db.get_accounts(enabled_only=True) if self.db else []
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
            with self._lock:
                accounts = self.db.get_accounts(enabled_only=True)
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
        self._opened_account_ids: list[int] = []
        self._loop = None

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
        self._loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(self._loop)
            self._execute()
        except Exception as e:
            self.signals.task_error.emit(self._task_id(), str(e))
        finally:
            try:
                self._close_browser_contexts()
            finally:
                try:
                    asyncio.set_event_loop(None)
                except Exception:
                    pass
                self._loop.close()
                self._loop = None

    def _execute(self):
        task_id = self._task_id()
        self.signals.task_started.emit(task_id)
        items = self._task_items()
        total = len(items)
        done = 0
        errors = 0
        for i, item in enumerate(items, 1):
            if self._cancelled:
                break
            while self._paused and not self._cancelled:
                time.sleep(0.2)
            try:
                self._run_one(item)
                done += 1
            except Exception as e:
                errors += 1
                item_id = getattr(item, "id", i - 1)
                self._update_item_status(item, ItemStatus.ERROR, error_message=str(e))
                self.signals.item_error.emit(item_id, str(e))
                log.error(f"Task item failed: {e}")
            if self.db and task_id:
                try:
                    self.db.update_task_progress(task_id, done, errors)
                except Exception as e:
                    log.warning(f"Could not update task progress: {e}")
            self.signals.task_progress.emit(task_id, i, total)
        self.signals.task_completed.emit(task_id)

    def _close_browser_contexts(self):
        """Close all browser contexts opened during this task on the worker loop."""
        if self.browser_manager is None or not self._opened_account_ids or self._loop is None:
            return
        try:
            for account_id in list(self._opened_account_ids):
                try:
                    self._loop.run_until_complete(self.browser_manager.close_context(account_id))
                except Exception as e:
                    log.warning(f"Could not close browser context {account_id}: {e}")
        finally:
            self._opened_account_ids.clear()

    def _run_one(self, item):
        return self._loop.run_until_complete(self._process_item_async(item))

    def _process_item(self, item):
        return self._run_one(item)

    async def _process_item_async(self, item):
        item_id = getattr(item, "id", 0)
        self._update_item_status(item, ItemStatus.GENERATING)
        self.signals.item_status_changed.emit(item_id, ItemStatus.GENERATING)

        account = self._acquire_account()
        if account is None:
            raise RuntimeError("No enabled Google account available")
        self._opened_account_ids.append(account.id)

        try:
            if self.browser_manager is None:
                raise RuntimeError("Browser manager is unavailable")
            page = await self.browser_manager.get_page(
                account_id=account.id,
                email=account.email,
                proxy=account.proxy,
                cookie_path=account.cookie_path,
                url=self._target_url(),
            )
            client = FlowClient(page, cookie_path=account.cookie_path, account_email=account.email)

            prompt = self._item_prompt(item)
            output_path = self._output_path_for_item(item)
            mode = self._task_value("mode", TaskMode.VIDEO_PLAIN)
            aspect_ratio = self._task_value("aspect_ratio", "16:9")

            if mode in (TaskMode.IMAGE, TaskMode.CHAR_IMAGE):
                image = await client.generate_image(
                    prompt,
                    image_paths=self._image_paths_for_item(item),
                    model=self._task_value("image_model", self._task_value("model", "Nano Banana 2")),
                    aspect_ratio=aspect_ratio,
                )
                media_id = image.get("name") or image.get("mediaId") or image.get("id")
                image_url = image.get("url") or image.get("imageUrl") or image.get("downloadUrl")
                if image_url:
                    await client.download_result(image_url, output_path)
                elif media_id:
                    await client.download_video(media_id, output_path)
                else:
                    raise RuntimeError("Image generation completed without downloadable media id/url")
            else:
                generation_id = await client.generate_video(
                    prompt,
                    image_paths=self._image_paths_for_item(item),
                    model=self._model_key_for_quality(),
                    aspect_ratio=aspect_ratio,
                    duration=8,
                    quality="720p",
                )
                if not generation_id:
                    raise RuntimeError("Video generation did not return generation id")
                self._update_item_status(item, ItemStatus.GENERATING, generation_id=str(generation_id), gen_account_id=account.id)
                result = await client.wait_for_completion(
                    generation_id,
                    cancel_check=lambda: self._cancelled,
                )
                if result.get("status") != "COMPLETED":
                    raise RuntimeError(str(result.get("error") or result))
                media = result.get("media") or result.get("result") or {}
                media_id = media.get("name") or media.get("mediaId") or generation_id
                self._update_item_status(item, ItemStatus.DOWNLOADING, generation_id=str(media_id), gen_account_id=account.id)
                self.signals.item_status_changed.emit(item_id, ItemStatus.DOWNLOADING)
                ok = await client.download_video(media_id, output_path)
                if not ok:
                    raise RuntimeError("Download failed")

            self._update_item_status(
                item,
                ItemStatus.COMPLETED,
                output_path=str(output_path),
                gen_account_id=account.id,
            )
            self.signals.item_completed.emit(item_id, str(output_path))
            return str(output_path)
        finally:
            self._release_account(account)

    def _task_items(self):
        items = getattr(self.task, "items", None)
        if items:
            return list(items)
        prompts = self._task_value("prompts", None)
        if prompts is None:
            prompt = self._task_value("prompt", "")
            prompts = [prompt] if prompt else []
        return [SimpleNamespace(id=index, prompt=str(prompt)) for index, prompt in enumerate(prompts)]

    def _task_id(self):
        if isinstance(self.task, dict):
            return int(self.task.get("id") or 0)
        return int(getattr(self.task, "id", 0) or 0)

    def _task_value(self, key, default=None):
        if isinstance(self.task, dict):
            return self.task.get(key, default)
        return getattr(self.task, key, default)

    def _item_prompt(self, item):
        if isinstance(item, dict):
            return str(item.get("prompt") or "")
        return str(getattr(item, "prompt", "") or "")

    def _image_paths_for_item(self, item):
        paths = []
        mode = self._task_value("mode", TaskMode.VIDEO_PLAIN)
        if isinstance(item, dict):
            for key in ("reference_image", "start_frame", "end_frame"):
                if item.get(key):
                    paths.append(item[key])
        else:
            for key in ("reference_image", "start_frame", "end_frame"):
                value = getattr(item, key, None)
                if value:
                    paths.append(value)

        if not paths:
            per_row = self._task_value("per_row_character_images", {}) or {}
            item_id = getattr(item, "id", 0)
            row_images = per_row.get(item_id) or per_row.get(str(item_id)) or {}
            if isinstance(row_images, dict):
                paths.extend(row_images.values())

        if not paths and mode in (TaskMode.CHAR_IMAGE, TaskMode.CHAR_VIDEO):
            char_images = self._task_value("character_images", {}) or {}
            if isinstance(char_images, dict):
                paths.extend(char_images.values())
            elif isinstance(char_images, list):
                paths.extend(char_images)

        # Fallback to task-level start_frame/end_frame only if the item
        # didn't already provide them (avoids sending duplicate/conflicting frames).
        item_frame_keys = set()
        if isinstance(item, dict):
            item_frame_keys = {k for k in ("start_frame", "end_frame") if item.get(k)}
        else:
            item_frame_keys = {k for k in ("start_frame", "end_frame") if getattr(item, k, None)}
        for key in ("start_frame", "end_frame"):
            if key not in item_frame_keys:
                value = self._task_value(key, None)
                if value:
                    paths.append(value)

        seen = set()
        result = []
        for p in paths:
            if p and Path(p).exists():
                resolved = str(Path(p))
                if resolved not in seen:
                    seen.add(resolved)
                    result.append(resolved)
        return result

    def _output_path_for_item(self, item):
        existing = getattr(item, "output_path", None) if not isinstance(item, dict) else item.get("output_path")
        if existing:
            return Path(existing)
        mode = self._task_value("mode", TaskMode.VIDEO_PLAIN)
        default_base = DEFAULT_IMAGE_OUTPUT if mode in (TaskMode.IMAGE, TaskMode.CHAR_IMAGE) else DEFAULT_VIDEO_OUTPUT
        output_folder = Path(self._task_value("output_folder", str(default_base)) or default_base)
        output_folder.mkdir(parents=True, exist_ok=True)
        index = getattr(item, "id", 0) if not isinstance(item, dict) else item.get("id", 0)
        suffix = ".png" if mode in (TaskMode.IMAGE, TaskMode.CHAR_IMAGE) else ".mp4"
        stem = generate_task_name("item")
        return output_folder / f"{stem}_{index}{suffix}"

    def _model_key_for_quality(self):
        quality = str(self._task_value("quality", "Veo 3.1 - Fast"))
        aspect_ratio = str(self._task_value("aspect_ratio", "16:9"))
        orientation = "portrait" if aspect_ratio == "9:16" else "landscape"
        if "Lite" in quality and "Lower Priority" in quality:
            return f"veo_3_1_t2v_{orientation}_lite_low_priority"
        if "Lite" in quality:
            return f"veo_3_1_t2v_{orientation}_lite"
        if "Lower Priority" in quality:
            return f"veo_3_1_t2v_{orientation}_ultra_relaxed"
        if "Quality" in quality:
            return f"veo_3_1_t2v_{orientation}"
        return f"veo_3_1_t2v_{orientation}_fast"

    def _target_url(self):
        mode = self._task_value("mode", TaskMode.VIDEO_PLAIN)
        return getattr(self.browser_manager, "GOOGLE_IMAGE_URL", None) if mode in (TaskMode.IMAGE, TaskMode.CHAR_IMAGE) else getattr(self.browser_manager, "GOOGLE_FLOW_URL", None)

    def _acquire_account(self):
        if self.account_pool is None:
            return None
        return self.account_pool.acquire()

    def _release_account(self, account):
        if self.account_pool is not None:
            self.account_pool.release(account)

    def _update_item_status(self, item, status, output_path=None, thumbnail_path=None, generation_id=None, error_message=None, credit_cost=0, flow_project_id=None, gen_account_id=None):
        item_id = getattr(item, "id", 0) if not isinstance(item, dict) else item.get("id", 0)
        if self.db and item_id:
            self.db.update_item_status(
                item_id,
                status,
                output_path=output_path,
                thumbnail_path=thumbnail_path,
                generation_id=generation_id,
                error_message=error_message,
                credit_cost=credit_cost,
                flow_project_id=flow_project_id,
                gen_account_id=gen_account_id,
            )


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
        task_id = task.get("id", id(worker)) if isinstance(task, dict) else getattr(task, "id", id(worker))
        self.workers[task_id] = worker
        worker.finished.connect(lambda tid=task_id: self._on_task_done(tid))
        parent = self.parent()
        if parent is not None:
            connections = (
                (worker.signals.task_started, getattr(parent, "_on_task_started", None)),
                (worker.signals.task_completed, getattr(parent, "_on_task_completed", None)),
                (worker.signals.task_error, getattr(parent, "_on_task_error", None)),
                (worker.signals.task_progress, getattr(parent, "_on_task_progress", None)),
                (worker.signals.item_status_changed, getattr(parent, "_on_item_status_changed", None)),
                (worker.signals.item_completed, getattr(parent, "_on_item_completed", None)),
                (worker.signals.item_error, getattr(parent, "_on_item_error", None)),
                (worker.signals.credit_updated, getattr(parent, "_on_credit_updated", None)),
                (worker.signals.account_disabled, getattr(parent, "_on_account_disabled", None)),
            )
            for signal, slot in connections:
                if callable(slot):
                    signal.connect(slot)
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
