"""
Task Output + Task Stop tools — manage background tasks.
Aligned with Claude Code's TaskOutputTool and TaskStopTool.
"""

from tools.base import BaseTool


class TaskOutputTool(BaseTool):
    name = "TaskOutput"
    description = (
        "Get the output of a background task by its ID.\n\n"
        "Background tasks are started by Bash with run_in_background=true.\n"
        "Use this to check if a task is still running and retrieve its output.\n\n"
        "Parameters:\n"
        "- task_id: The task ID returned when the background task was started\n"
        "- block: If true, wait for the task to complete (default: true)\n"
        "- timeout: Max wait time in seconds (default: 30)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The background task ID (e.g., 'bg_1')",
            },
            "block": {
                "type": "boolean",
                "description": "Wait for task to complete (default: true)",
                "default": True,
            },
            "timeout": {
                "type": "integer",
                "description": "Max wait time in seconds (default: 30)",
                "default": 30,
            },
        },
        "required": ["task_id"],
    }
    is_read_only = True

    def __init__(self):
        self._engine = None  # injected by ToolRegistry
        self._bash_tool = None  # injected by ToolRegistry

    def execute(self, input_data: dict) -> str:
        import time

        task_id = input_data.get("task_id", "").strip()
        block = input_data.get("block", True)
        timeout = min(input_data.get("timeout", 30), 300)

        if not task_id:
            return "Error: task_id is required."

        # Try engine's background tasks first
        record = None
        if self._engine:
            record = self._engine.get_background_task(task_id)

        # Try bash tool's background tasks
        if not record and self._bash_tool:
            record = self._bash_tool.get_background_task(task_id)

        if not record:
            return f"Error: Background task '{task_id}' not found."

        if record["status"] == "running" and block:
            start = time.time()
            while record["status"] == "running" and (time.time() - start) < timeout:
                time.sleep(0.5)
            if record["status"] == "running":
                return f"Task {task_id} is still running (timed out after {timeout}s)."

        status = record["status"]
        output = record.get("output", "(no output)")

        return f"Task {task_id} [{status}]:\n{output}"


class TaskStopTool(BaseTool):
    name = "TaskStop"
    description = (
        "Stop a running background task by its ID.\n\n"
        "Parameters:\n"
        "- task_id: The background task ID to stop"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The background task ID to stop",
            },
        },
        "required": ["task_id"],
    }
    is_read_only = False

    def __init__(self):
        self._engine = None

    def execute(self, input_data: dict) -> str:
        task_id = input_data.get("task_id", "").strip()
        if not task_id:
            return "Error: task_id is required."

        if not self._engine:
            return "Error: Engine not available."

        record = self._engine.get_background_task(task_id)
        if not record:
            return f"Error: Task '{task_id}' not found."

        if record["status"] != "running":
            return f"Task {task_id} is already {record['status']}."

        thread = record.get("thread")
        if thread and thread.is_alive():
            # Python threads can't be killed directly; mark as stopped
            record["status"] = "stopped"
            record["output"] = record.get("output", "") + "\n(stopped by user)"
            return f"Task {task_id} marked as stopped."

        record["status"] = "stopped"
        return f"Task {task_id} stopped."
