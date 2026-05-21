"""VidGen AI — SQLite database ORM."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.constants import DATA_DIR, DB_PATH, ItemStatus, TaskStatus
from models.account import Account
from models.task import Project, TaskItem, VideoTask


class Database:
    """SQLite database manager (thread-safe with mutex lock)."""

    def __init__(self, db_path: Path | str | None = None):
        import threading

        self._db_path = str(db_path or DB_PATH)
        self._conn = None
        self._lock = threading.Lock()

    def connect(self):
        """Open database connection and create tables."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._create_tables()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._conn:
            self.connect()
        return self._conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def commit(self):
        with self._lock:
            self.conn.commit()

    def _create_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                enabled BOOLEAN DEFAULT 1,
                tier TEXT DEFAULT 'FREE',
                credit INTEGER DEFAULT 0,
                proxy TEXT,
                cookie_path TEXT,
                cookie_exp DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                token_exp DATETIME,
                gemini_api_key TEXT
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                folder_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER REFERENCES projects(id),
                account_id INTEGER REFERENCES accounts(id),
                name TEXT NOT NULL,
                mode TEXT NOT NULL,
                quality TEXT,
                aspect_ratio TEXT,
                concurrent INTEGER DEFAULT 1,
                character_images TEXT,
                input_folder TEXT,
                output_folder TEXT,
                status TEXT DEFAULT 'PENDING',
                total_count INTEGER DEFAULT 0,
                done_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                image_model TEXT DEFAULT 'Nano Banana 2'
            );

            CREATE TABLE IF NOT EXISTS task_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,
                reference_image TEXT,
                start_frame TEXT,
                end_frame TEXT,
                status TEXT DEFAULT 'PENDING',
                output_path TEXT,
                thumbnail_path TEXT,
                generation_id TEXT,
                error_message TEXT,
                credit_cost INTEGER DEFAULT 0,
                completed_at DATETIME
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_project
                ON tasks(project_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_task_items_task
                ON task_items(task_id);
            CREATE INDEX IF NOT EXISTS idx_task_items_status
                ON task_items(status);
        """
        )
        self.commit()
        self._migrate()

    def _migrate(self):
        """Run lightweight migrations for schema changes."""
        try:
            cols = [row[1] for row in self.execute("PRAGMA table_info(accounts)").fetchall()]
            if "token_exp" not in cols:
                self.execute("ALTER TABLE accounts ADD COLUMN token_exp DATETIME")
                self.commit()
        except Exception:
            pass

        try:
            cols = [row[1] for row in self.execute("PRAGMA table_info(tasks)").fetchall()]
            if "image_model" not in cols:
                self.execute("ALTER TABLE tasks ADD COLUMN image_model TEXT DEFAULT 'Nano Banana 2'")
                self.commit()
        except Exception:
            pass

        try:
            cols = [row[1] for row in self.execute("PRAGMA table_info(accounts)").fetchall()]
            if "gemini_api_key" not in cols:
                self.execute("ALTER TABLE accounts ADD COLUMN gemini_api_key TEXT")
                self.commit()
        except Exception:
            pass

        try:
            cols = [row[1] for row in self.execute("PRAGMA table_info(task_items)").fetchall()]
            if "flow_project_id" not in cols:
                self.execute("ALTER TABLE task_items ADD COLUMN flow_project_id TEXT")
                self.commit()
            if "gen_account_id" not in cols:
                self.execute("ALTER TABLE task_items ADD COLUMN gen_account_id INTEGER")
                self.commit()
        except Exception:
            pass

        try:
            cols = [row[1] for row in self.execute("PRAGMA table_info(tasks)").fetchall()]
            if "parallel_per_account" not in cols:
                self.execute("ALTER TABLE tasks ADD COLUMN parallel_per_account INTEGER DEFAULT 1")
                self.commit()
        except Exception:
            pass

    def get_accounts(self, enabled_only: bool = False) -> list[Account]:
        sql = "SELECT * FROM accounts"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY id"
        rows = self.execute(sql).fetchall()
        return [Account.from_row(r) for r in rows]

    def get_account(self, account_id: int) -> Optional[Account]:
        row = self.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return Account.from_row(row) if row else None

    def add_account(self, email: str, proxy: str = None) -> Account:
        cursor = self.execute("INSERT INTO accounts (email, proxy) VALUES (?, ?)", (email, proxy))
        self.commit()
        return self.get_account(cursor.lastrowid)

    def update_account(self, account: Account):
        self.execute(
            """UPDATE accounts SET
                enabled=?, tier=?, credit=?, proxy=?,
                cookie_path=?, cookie_exp=?, token_exp=?,
                gemini_api_key=?
            WHERE id=?""",
            (
                account.enabled,
                account.tier,
                account.credit,
                account.proxy,
                account.cookie_path,
                account.cookie_exp.isoformat() if account.cookie_exp else None,
                account.token_exp.isoformat() if account.token_exp else None,
                account.gemini_api_key,
                account.id,
            ),
        )
        self.commit()

    def update_account_credit(self, account_id: int, credit: int):
        self.execute("UPDATE accounts SET credit = ? WHERE id = ?", (credit, account_id))
        self.commit()

    def delete_account(self, account_id: int):
        self.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self.commit()

    def get_projects(self) -> list[Project]:
        rows = self.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [Project.from_row(r) for r in rows]

    def get_or_create_project(self, name: str, folder_path: str = "") -> Project:
        row = self.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
        if row:
            return Project.from_row(row)
        cursor = self.execute("INSERT INTO projects (name, folder_path) VALUES (?, ?)", (name, folder_path))
        self.commit()
        return self.get_project(cursor.lastrowid)

    def get_project(self, project_id: int) -> Optional[Project]:
        row = self.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return Project.from_row(row) if row else None

    def create_task(self, task: VideoTask) -> VideoTask:
        cursor = self.execute(
            """INSERT INTO tasks
                (project_id, account_id, name, mode, quality, aspect_ratio,
                 concurrent, character_images, input_folder, output_folder,
                 status, total_count, image_model, parallel_per_account)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.project_id,
                task.account_id,
                task.name,
                task.mode,
                task.quality,
                task.aspect_ratio,
                task.concurrent,
                task.character_images_json(),
                task.input_folder,
                task.output_folder,
                task.status,
                task.total_count,
                task.image_model,
                task.parallel_per_account,
            ),
        )
        self.commit()
        task.id = cursor.lastrowid
        return task

    def get_task(self, task_id: int) -> Optional[VideoTask]:
        row = self.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return VideoTask.from_row(row) if row else None

    def get_tasks_by_project(self, project_id: int) -> list[VideoTask]:
        rows = self.execute("SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [VideoTask.from_row(r) for r in rows]

    def get_tasks_by_status(self, status: str) -> list[VideoTask]:
        rows = self.execute("SELECT * FROM tasks WHERE status = ?", (status,)).fetchall()
        return [VideoTask.from_row(r) for r in rows]

    def update_task_status(self, task_id: int, status: str):
        self.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        self.commit()

    def update_task_progress(self, task_id: int, done: int, errors: int):
        self.execute("UPDATE tasks SET done_count = ?, error_count = ? WHERE id = ?", (done, errors, task_id))
        self.commit()

    def count_tasks(self, project_id: int = None) -> int:
        if project_id:
            row = self.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (project_id,)).fetchone()
        else:
            row = self.execute("SELECT COUNT(*) FROM tasks").fetchone()
        return row[0] if row else 0

    def add_task_item(self, item: TaskItem) -> TaskItem:
        cursor = self.execute(
            """INSERT INTO task_items
                (task_id, prompt, reference_image, start_frame, end_frame, status)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (item.task_id, item.prompt, item.reference_image, item.start_frame, item.end_frame, item.status),
        )
        self.commit()
        item.id = cursor.lastrowid
        return item

    def add_task_items_bulk(self, items: list[TaskItem]):
        with self._lock:
            self.conn.executemany(
                """INSERT INTO task_items
                    (task_id, prompt, reference_image, start_frame, end_frame, status)
                VALUES (?, ?, ?, ?, ?, ?)""",
                [(i.task_id, i.prompt, i.reference_image, i.start_frame, i.end_frame, i.status) for i in items],
            )
            self.conn.commit()

    def get_task_items(self, task_id: int) -> list[TaskItem]:
        rows = self.execute("SELECT * FROM task_items WHERE task_id = ? ORDER BY id", (task_id,)).fetchall()
        return [TaskItem.from_row(r) for r in rows]

    def get_pending_items(self, task_id: int) -> list[TaskItem]:
        rows = self.execute(
            "SELECT * FROM task_items WHERE task_id = ? AND status = ? ORDER BY id",
            (task_id, ItemStatus.PENDING),
        ).fetchall()
        return [TaskItem.from_row(r) for r in rows]

    def update_item_status(
        self,
        item_id: int,
        status: str,
        output_path: str = None,
        thumbnail_path: str = None,
        generation_id: str = None,
        error_message: str = None,
        credit_cost: int = 0,
        flow_project_id: str = None,
        gen_account_id: int = None,
    ):
        completed = datetime.now().isoformat() if status == ItemStatus.COMPLETED else None
        self.execute(
            """UPDATE task_items SET
                status=?,
                output_path=COALESCE(?, output_path),
                thumbnail_path=COALESCE(?, thumbnail_path),
                generation_id=COALESCE(?, generation_id),
                error_message=?,
                credit_cost=?,
                flow_project_id=COALESCE(?, flow_project_id),
                gen_account_id=COALESCE(?, gen_account_id),
                completed_at=?
            WHERE id=?""",
            (
                status,
                output_path,
                thumbnail_path,
                generation_id,
                error_message,
                credit_cost,
                flow_project_id,
                gen_account_id,
                completed,
                item_id,
            ),
        )
        self.commit()

    def get_setting(self, key: str) -> Optional[str]:
        row = self.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str):
        self.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self.commit()
