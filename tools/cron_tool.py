"""
Cron Scheduling Tools — CronCreateTool, CronDeleteTool, CronListTool.
Aligned with Claude Code's ScheduleCronTool pattern.

Uses the single CronScheduler from core/cron/scheduler.py (QTimer-driven,
durable, CC-aligned). Tools obtain the shared instance via get_cron_scheduler().
"""

from __future__ import annotations
from tools.base import BaseTool


_fallback_scheduler = None


def get_cron_scheduler():
    """Get the shared CronScheduler instance from the main app, or create a local one."""
    global _fallback_scheduler
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_buddy') and hasattr(app._buddy, '_cron_scheduler'):
            return app._buddy._cron_scheduler
    except (ImportError, AttributeError):
        pass

    # Fallback: reuse cached local scheduler for command-line use
    if _fallback_scheduler is not None:
        return _fallback_scheduler

    try:
        from core.cron.scheduler import CronScheduler
        from pathlib import Path
        data_dir = Path.home() / ".claude-buddy"
        _fallback_scheduler = CronScheduler(data_dir, lambda job_id, prompt: print(f"⏰ Cron reminder: {prompt}"))
        return _fallback_scheduler
    except Exception:
        pass

    return None


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
        "Set durable=true to persist across restarts.\n\n"
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
            "durable": {
                "type": "boolean",
                "description": "true = persist to disk and survive restarts, false = session-only (default)",
                "default": False,
            },
        },
        "required": ["cron", "prompt"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        cron_expr = input_data["cron"].strip()
        prompt = input_data["prompt"].strip()
        recurring = input_data.get("recurring", True)
        durable = input_data.get("durable", False)

        if not prompt:
            return "Error: prompt must not be empty."

        # Validate cron expression (basic: 5 fields)
        fields = cron_expr.split()
        if len(fields) != 5:
            return f"Error: cron expression must have 5 fields (got {len(fields)}). Format: 'M H DoM Mon DoW'"

        scheduler = get_cron_scheduler()
        if not scheduler:
            return "Error: Cron scheduler not available."

        try:
            job = scheduler.create(cron_expr, prompt, recurring, durable=durable)
            mode = "recurring" if recurring else "one-shot"
            persist = " (durable — survives restarts)" if durable else " (session-only)"
            return (
                f"Cron job created: {job.id}\n"
                f"Schedule: {cron_expr} ({mode}){persist}\n"
                f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            )
        except Exception as e:
            return f"Error creating cron job: {e}"


class CronDeleteTool(BaseTool):
    name = "CronDelete"
    description = "Delete a scheduled cron job by its ID."
    input_schema = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "The cron job ID to delete",
            },
        },
        "required": ["id"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        job_id = input_data["id"].strip()
        scheduler = get_cron_scheduler()
        if not scheduler:
            return "Error: Cron scheduler not available."
        if scheduler.delete(job_id):
            return f"Cron job {job_id} deleted."
        return f"Error: cron job {job_id} not found."


class CronListTool(BaseTool):
    name = "CronList"
    description = "List all scheduled cron jobs."
    input_schema = {
        "type": "object",
        "properties": {},
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        scheduler = get_cron_scheduler()
        if not scheduler:
            return "Error: Cron scheduler not available."

        jobs = scheduler.list_jobs()
        if not jobs:
            return "No cron jobs scheduled."

        lines = ["Scheduled cron jobs:"]
        for j in jobs:
            mode = "recurring" if j["recurring"] else "one-shot"
            durable_tag = " [durable]" if j.get("durable") else ""
            lines.append(
                f"  {j['id']}: {j['cron']} ({mode}{durable_tag})\n"
                f"    Prompt: {j['prompt'][:80]}{'...' if len(j['prompt']) > 80 else ''}"
            )
        return "\n".join(lines)
