"""VidGen AI — Task and TaskItem models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config.constants import ItemStatus, TaskMode, TaskStatus


@dataclass
class TaskItem:
    """Single prompt result within a task."""

    id: int = 0
    task_id: int = 0
    prompt: str = ""
    reference_image: Optional[str] = None
    start_frame: Optional[str] = None
    end_frame: Optional[str] = None
    status: str = ItemStatus.PENDING
    output_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    generation_id: Optional[str] = None
    error_message: Optional[str] = None
    credit_cost: int = 0
    completed_at: Optional[datetime] = None
    flow_project_id: Optional[str] = None
    gen_account_id: Optional[int] = None

    @property
    def is_done(self) -> bool:
        return self.status == ItemStatus.COMPLETED

    @property
    def is_error(self) -> bool:
        return self.status == ItemStatus.ERROR

    @property
    def is_pending(self) -> bool:
        return self.status == ItemStatus.PENDING

    @classmethod
    def from_row(cls, row: tuple) -> TaskItem:
        return cls(
            id=row[0],
            task_id=row[1],
            prompt=row[2],
            reference_image=row[3],
            start_frame=row[4],
            end_frame=row[5],
            status=row[6] or ItemStatus.PENDING,
            output_path=row[7],
            thumbnail_path=row[8],
            generation_id=row[9],
            error_message=row[10],
            credit_cost=row[11] or 0,
            completed_at=datetime.fromisoformat(row[12]) if row[12] else None,
            flow_project_id=row[13] if len(row) > 13 else None,
            gen_account_id=row[14] if len(row) > 14 else None,
        )


@dataclass
class VideoTask:
    """A batch task containing multiple prompts."""

    id: int = 0
    project_id: int = 0
    account_id: Optional[int] = None
    name: str = ""
    mode: str = TaskMode.VIDEO_PLAIN
    quality: str = "Veo 3.1 - Fast"
    image_model: str = "Nano Banana 2"
    aspect_ratio: str = "16:9"
    concurrent: int = 1
    parallel_per_account: int = 1
    character_images: list[str] = field(default_factory=list)
    input_folder: Optional[str] = None
    output_folder: str = ""
    status: str = TaskStatus.PENDING
    total_count: int = 0
    done_count: int = 0
    error_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    items: list[TaskItem] = field(default_factory=list)

    @property
    def progress(self) -> float:
        if self.total_count == 0:
            return 0
        return (self.done_count + self.error_count) / self.total_count

    @property
    def progress_text(self) -> str:
        return f"{self.done_count}/{self.total_count}"

    @property
    def is_running(self) -> bool:
        return self.status == TaskStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    @property
    def is_image_mode(self) -> bool:
        return self.mode in (TaskMode.IMAGE, TaskMode.CHAR_IMAGE)

    @property
    def is_video_mode(self) -> bool:
        return self.mode in (TaskMode.CHAR_VIDEO, TaskMode.VIDEO_PLAIN, TaskMode.VIDEO_REF, TaskMode.FRAME_VIDEO)

    @property
    def has_character_refs(self) -> bool:
        return self.mode in (TaskMode.CHAR_IMAGE, TaskMode.CHAR_VIDEO)

    def character_images_json(self) -> str:
        return json.dumps(self.character_images)

    @classmethod
    def from_row(cls, row: tuple) -> VideoTask:
        char_images = []
        if row[8]:
            try:
                char_images = json.loads(row[8])
            except json.JSONDecodeError:
                pass

        return cls(
            id=row[0],
            project_id=row[1],
            account_id=row[2],
            name=row[3],
            mode=row[4],
            quality=row[5],
            aspect_ratio=row[6],
            concurrent=row[7] or 1,
            character_images=char_images,
            input_folder=row[9],
            output_folder=row[10] or "",
            status=row[11] or TaskStatus.PENDING,
            total_count=row[12] or 0,
            done_count=row[13] or 0,
            error_count=row[14] or 0,
            created_at=datetime.fromisoformat(row[15]) if row[15] else datetime.now(),
            image_model=row[16] if len(row) > 16 and row[16] else "Nano Banana 2",
            parallel_per_account=row[17] if len(row) > 17 and row[17] else 1,
        )


@dataclass
class Project:
    """Project / folder grouping tasks by date."""

    id: int = 0
    name: str = ""
    folder_path: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_row(cls, row: tuple) -> Project:
        return cls(
            id=row[0],
            name=row[1],
            folder_path=row[2] or "",
            created_at=datetime.fromisoformat(row[3]) if row[3] else datetime.now(),
        )
