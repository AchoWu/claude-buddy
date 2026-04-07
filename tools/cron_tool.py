"""
Cron Scheduling Tools — CronCreateTool, CronDeleteTool, CronListTool.
Aligned with Claude Code's ScheduleCronTool pattern.

In-memory cron scheduler using QTimer. Jobs live in session only.
Supports recurring (cron expression) and one-shot tasks.
"""

from __future__ import annotations
import re
import time
from typing import Optional, Any
from tools.base import BaseTool


class CronJob:
    """In-memory cron job."""
    def __init__(self, job_id: str, cron: str, prompt: str, recurring: bool = True):
        self.id = job_id
        self.cron = cron
        self.prompt = prompt
        self.recurring = recurring
        self.created_at = time.time()
        self.last_fired: float | None = None
        self.fire_count = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cron": self.cron,
            "prompt": self.prompt[:100],
            "recurring": self.recurring,
            "fire_count": self.fire_count,
            "created_at": self.created_at,
        }


class CronScheduler:
    """
    In-memory cron job store. Jobs are session-only.
    The actual timer triggering is handled by the UI layer (QTimer).
    """
    def __init__(self):
        self._jobs: dict[str, CronJob] = {}
        self._next_id = 1

    def create(self, cron: str, prompt: str, recurring: bool = True) -> CronJob:
        job_id = f"cron_{self._next_id}"
        self._next_id += 1
        job = CronJob(job_id, cron, prompt, recurring)
        self._jobs[job_id] = job
        return job

    def delete(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    def get(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    def list_all(self) -> list[CronJob]:
        return list(self._jobs.values())

    def fire(self, job_id: str) -> str | None:
        """Mark a job as fired. Returns prompt if found, None otherwise."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        job.last_fired = time.time()
        job.fire_count += 1
        if not job.recurring:
            del self._jobs[job_id]
        return job.prompt


# Module-level shared instance
_scheduler = CronScheduler()


def get_cron_scheduler() -> CronScheduler:
    return _scheduler


# ── Tools ────────────────────────────────────────────────────────────

class CronCreateTool(BaseTool):
    name = "CronCreate"
    description = (
        "Schedule a prompt to run at a future time.\n\n"
        "Uses standard 5-field cron: minute hour day-of-month month day-of-week.\n"
        "Examples:\n"
        "  '*/5 * * * *' = every 5 minutes\n"
        "  '0 9 * * 1-5' = weekdays at 9am\n"
        "  '30 14 25 12 *' = Dec 25 at 2:30pm (one-shot)\n\n"
        "Set recurring=false for one-shot reminders (fire once then auto-delete).\n"
        "Jobs live only in this session — they are lost when the app exits.\n\n"
        "Tip: Avoid :00 and :30 minute marks when timing is approximate."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "cron": {
                "type": "string",
                "description": "5-field cron expression: 'M H DoM Mon DoW'",
            },
            "prompt": {
                "type": "string",
                "description": "The prompt to run when the cron fires",
            },
            "recurring": {
                "type": "boolean",
                "description": "true = fire repeatedly (default), false = fire once then delete",
                "default": True,
            },
        },
        "required": ["cron", "prompt"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        cron_expr = input_data["cron"].strip()
        prompt = input_data["prompt"].strip()
        recurring = input_data.get("recurring", True)

        if not prompt:
            return "Error: prompt must not be empty."

        # Validate cron expression (basic: 5 fields)
        fields = cron_expr.split()
        if len(fields) != 5:
            return f"Error: cron expression must have 5 fields (got {len(fields)}). Format: 'M H DoM Mon DoW'"

        scheduler = get_cron_scheduler()
        job = scheduler.create(cron_expr, prompt, recurring)

        mode = "recurring" if recurring else "one-shot"
        return (
            f"Cron job created: {job.id}\n"
            f"Schedule: {cron_expr} ({mode})\n"
            f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n"
            f"Note: Jobs live only in this session."
        )


class CronDeleteTool(BaseTool):
    name = "CronDelete"
    description = "Delete a scheduled cron job by its ID."
    input_schema = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "The cron job ID to delete (e.g., 'cron_1')",
            },
        },
        "required": ["id"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        job_id = input_data["id"].strip()
        scheduler = get_cron_scheduler()
        if scheduler.delete(job_id):
            return f"Cron job {job_id} deleted."
        return f"Error: cron job {job_id} not found."


class CronListTool(BaseTool):
    name = "CronList"
    description = "List all scheduled cron jobs in this session."
    input_schema = {
        "type": "object",
        "properties": {},
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        scheduler = get_cron_scheduler()
        jobs = scheduler.list_all()
        if not jobs:
            return "No cron jobs scheduled."

        lines = ["Scheduled cron jobs:"]
        for job in jobs:
            mode = "recurring" if job.recurring else "one-shot"
            fired = f", fired {job.fire_count}x" if job.fire_count > 0 else ""
            lines.append(
                f"  {job.id}: {job.cron} ({mode}{fired})\n"
                f"    Prompt: {job.prompt[:80]}{'...' if len(job.prompt) > 80 else ''}"
            )
        return "\n".join(lines)
