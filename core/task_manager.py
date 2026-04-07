"""
Task Manager — manages tasks with Qt signals for UI updates.
CC-aligned V2: supports owner, blocks/blockedBy, activeForm, metadata, deleted status.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from config import TASKS_FILE


@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: str = "pending"        # pending, in_progress, completed, deleted
    activeForm: str = ""           # CC: present continuous form for spinner
    owner: str = ""                # CC: agent name
    blocks: list = field(default_factory=list)      # CC: task IDs this blocks
    blockedBy: list = field(default_factory=list)    # CC: task IDs blocking this
    metadata: dict = field(default_factory=dict)     # CC: arbitrary KV
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "status": self.status,
            "activeForm": self.activeForm,
            "owner": self.owner,
            "blocks": list(self.blocks),
            "blockedBy": list(self.blockedBy),
            "metadata": dict(self.metadata),
            "created_at": self.created_at or time.time(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(
            id=str(d.get("id", "0")),
            subject=d.get("subject", ""),
            description=d.get("description", ""),
            status=d.get("status", "pending"),
            activeForm=d.get("activeForm", ""),
            owner=d.get("owner", ""),
            blocks=list(d.get("blocks", [])),
            blockedBy=list(d.get("blockedBy", [])),
            metadata=dict(d.get("metadata", {})),
            created_at=d.get("created_at", 0),
        )


class TaskManager(QObject):
    """Manages task lifecycle with persistent storage and signals.
    CC-aligned V2: file-based storage, high water mark IDs, dependencies."""

    task_created = pyqtSignal(object)    # Task
    task_updated = pyqtSignal(object)    # Task
    task_completed = pyqtSignal(object)  # Task

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: list[Task] = []
        self._high_water_mark: int = 0
        self._load()

    def _load(self):
        if TASKS_FILE.exists():
            try:
                data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # New format: {tasks: [...], highWaterMark: N}
                    self._tasks = [Task.from_dict(d) for d in data.get("tasks", [])]
                    self._high_water_mark = data.get("highWaterMark", 0)
                elif isinstance(data, list):
                    # Legacy format: [task, task, ...]
                    self._tasks = [Task.from_dict(d) for d in data]
                    self._high_water_mark = 0
            except Exception:
                self._tasks = []
                self._high_water_mark = 0
        # Sync high water mark with loaded tasks
        if self._tasks:
            max_id = max(int(t.id) for t in self._tasks if t.id.isdigit())
            self._high_water_mark = max(self._high_water_mark, max_id)

    def _save(self):
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TASKS_FILE.write_text(
            json.dumps({
                "tasks": [t.to_dict() for t in self._tasks],
                "highWaterMark": self._high_water_mark,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def all_tasks(self) -> list[Task]:
        """Return all non-deleted tasks."""
        return [t for t in self._tasks if t.status != "deleted"]

    def get(self, task_id) -> "Task | None":
        task_id = str(task_id)
        for t in self._tasks:
            if t.id == task_id:
                return t
        return None

    def create(self, subject: str, description: str,
               activeForm: str = "", metadata: dict | None = None) -> Task:
        task = Task(
            id=self._next_id(),
            subject=subject,
            description=description,
            activeForm=activeForm,
            metadata=metadata or {},
            created_at=time.time(),
        )
        self._tasks.append(task)
        self._save()
        self.task_created.emit(task)
        return task

    def update(self, task_id, **kwargs) -> "Task | None":
        """CC-aligned generic update. Supports all fields + addBlocks/addBlockedBy."""
        task_id = str(task_id)
        task = self.get(task_id)
        if task is None:
            return None

        old_status = task.status

        # Simple field updates
        for key in ("subject", "description", "status", "activeForm", "owner"):
            if key in kwargs and kwargs[key] is not None:
                setattr(task, key, kwargs[key])

        # Metadata merge (CC: merge keys, null value deletes key)
        if "metadata" in kwargs and kwargs["metadata"]:
            for k, v in kwargs["metadata"].items():
                if v is None:
                    task.metadata.pop(k, None)
                else:
                    task.metadata[k] = v

        # Dependency updates (additive, CC-aligned)
        if "addBlocks" in kwargs and kwargs["addBlocks"]:
            for bid in kwargs["addBlocks"]:
                bid = str(bid)
                if bid not in task.blocks:
                    task.blocks.append(bid)

        if "addBlockedBy" in kwargs and kwargs["addBlockedBy"]:
            for bid in kwargs["addBlockedBy"]:
                bid = str(bid)
                if bid not in task.blockedBy:
                    task.blockedBy.append(bid)

        self._save()
        self.task_updated.emit(task)

        if task.status == "completed" and old_status != "completed":
            self.task_completed.emit(task)

        return task

    def update_status(self, task_id, status: str):
        """Legacy compat — delegates to update()."""
        self.update(task_id, status=status)

    def _next_id(self) -> str:
        """CC-aligned: high water mark prevents ID reuse after deletion."""
        self._high_water_mark += 1
        return str(self._high_water_mark)
