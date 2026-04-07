"""
Task Tools — CC-aligned V2: create, update, list, and get tasks.
Supports owner, blocks/blockedBy, activeForm, metadata, deleted status.
All operations go through TaskManager so Qt signals fire properly.
"""

import json
from typing import Any

from tools.base import BaseTool


class TaskCreateTool(BaseTool):
    name = "TaskCreate"
    description = (
        "Create a new task with a subject and description.\n\n"
        "Use this when the user asks you to track work, create a TODO, or manage tasks.\n"
        "The task starts with status 'pending'.\n"
        "Returns the task ID and subject."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Brief task title"},
            "description": {"type": "string", "description": "What needs to be done"},
            "activeForm": {
                "type": "string",
                "description": "Present continuous form shown in spinner when in_progress (e.g. 'Running tests')",
            },
            "metadata": {
                "type": "object",
                "description": "Arbitrary metadata to attach to the task",
            },
        },
        "required": ["subject", "description"],
    }
    is_read_only = False

    _task_manager = None  # set by ToolRegistry

    def execute(self, input_data: dict) -> str:
        if self._task_manager is None:
            return "Error: TaskManager not connected."
        task = self._task_manager.create(
            subject=input_data["subject"],
            description=input_data["description"],
            activeForm=input_data.get("activeForm", ""),
            metadata=input_data.get("metadata"),
        )
        return json.dumps({"task": {"id": task.id, "subject": task.subject}})


class TaskUpdateTool(BaseTool):
    name = "TaskUpdate"
    description = (
        "Update a task's fields: status, subject, description, owner, dependencies, metadata.\n\n"
        "Status workflow: pending → in_progress → completed\n"
        "Use 'deleted' to permanently remove a task.\n"
        "Use addBlocks/addBlockedBy to set up task dependencies."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string", "description": "The task ID to update"},
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed", "deleted"],
                "description": "New status for the task",
            },
            "subject": {"type": "string", "description": "New subject for the task"},
            "description": {"type": "string", "description": "New description"},
            "activeForm": {"type": "string", "description": "Present continuous form for spinner"},
            "owner": {"type": "string", "description": "New owner (agent name)"},
            "addBlocks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Task IDs that this task blocks",
            },
            "addBlockedBy": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Task IDs that block this task",
            },
            "metadata": {
                "type": "object",
                "description": "Metadata keys to merge (set key to null to delete it)",
            },
        },
        "required": ["taskId"],
    }
    is_read_only = False

    _task_manager = None  # set by ToolRegistry

    def execute(self, input_data: dict) -> str:
        if self._task_manager is None:
            return "Error: TaskManager not connected."

        task_id = str(input_data["taskId"])
        task = self._task_manager.get(task_id)
        if task is None:
            return f"Error: Task #{task_id} not found"

        # Build kwargs for TaskManager.update()
        kwargs = {}
        for key in ("status", "subject", "description", "activeForm", "owner"):
            if key in input_data:
                kwargs[key] = input_data[key]
        if "addBlocks" in input_data:
            kwargs["addBlocks"] = input_data["addBlocks"]
        if "addBlockedBy" in input_data:
            kwargs["addBlockedBy"] = input_data["addBlockedBy"]
        if "metadata" in input_data:
            kwargs["metadata"] = input_data["metadata"]

        result = self._task_manager.update(task_id, **kwargs)
        if result is None:
            return f"Error: Task #{task_id} not found"

        return json.dumps({
            "task": {"id": result.id, "subject": result.subject, "status": result.status}
        })


class TaskListTool(BaseTool):
    name = "TaskList"
    description = (
        "List all tasks with their IDs, subjects, statuses, owners, and dependencies.\n"
        "Returns a summary of each task. Deleted tasks are excluded."
    )
    input_schema = {
        "type": "object",
        "properties": {},
    }
    is_read_only = True

    _task_manager = None  # set by ToolRegistry

    def execute(self, input_data: dict) -> str:
        if self._task_manager is None:
            return "Error: TaskManager not connected."

        tasks = self._task_manager.all_tasks()  # excludes deleted
        if not tasks:
            return "No tasks."

        # CC-aligned: filter out completed tasks from blockedBy display
        completed_ids = {t.id for t in tasks if t.status == "completed"}

        lines = []
        for t in tasks:
            status_icon = {
                "pending": "⬜", "in_progress": "🔄", "completed": "✅"
            }.get(t.status, "⬜")

            parts = [f"#{t.id}. [{status_icon} {t.status}] {t.subject}"]

            if t.owner:
                parts.append(f"  owner: {t.owner}")

            # Show only open (non-completed) blockers
            open_blockers = [b for b in t.blockedBy if b not in completed_ids]
            if open_blockers:
                parts.append(f"  blockedBy: {open_blockers}")

            lines.append("\n".join(parts))

        return "\n".join(lines)


class TaskGetTool(BaseTool):
    name = "TaskGet"
    description = (
        "Get full details of a specific task by ID.\n"
        "Returns all task fields including description, dependencies, and metadata."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string", "description": "The task ID"},
        },
        "required": ["taskId"],
    }
    is_read_only = True

    _task_manager = None  # set by ToolRegistry

    def execute(self, input_data: dict) -> str:
        if self._task_manager is None:
            return "Error: TaskManager not connected."

        task_id = str(input_data["taskId"])
        task = self._task_manager.get(task_id)
        if task is None:
            return f"Error: Task #{task_id} not found"

        return json.dumps(task.to_dict(), ensure_ascii=False, indent=2)
