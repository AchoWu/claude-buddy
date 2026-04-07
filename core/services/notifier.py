"""
Notifier Service — CC-aligned system notification on task events.
CC: notifier service sends toast/sound on task completion.
Wraps PushNotificationTool as an engine-level automatic service.
"""


class NotifierService:
    """Auto-notify user on significant engine events."""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._notify_fn = None

    def set_notify_fn(self, fn):
        """Set the notification function (e.g., PushNotificationTool.execute)."""
        self._notify_fn = fn

    def on_task_complete(self, task_name: str, duration_s: float = 0):
        """Notify when a background task completes."""
        if not self._enabled or not self._notify_fn:
            return
        msg = f"Task '{task_name}' completed"
        if duration_s > 0:
            msg += f" ({duration_s:.1f}s)"
        self._safe_notify("Task Complete", msg)

    def on_error(self, error_msg: str):
        """Notify on significant errors."""
        if not self._enabled or not self._notify_fn:
            return
        self._safe_notify("Error", error_msg[:200])

    def on_agent_done(self, agent_id: str, summary: str = ""):
        """Notify when a sub-agent finishes."""
        if not self._enabled or not self._notify_fn:
            return
        msg = f"Agent '{agent_id}' finished"
        if summary:
            msg += f": {summary[:100]}"
        self._safe_notify("Agent Done", msg)

    def _safe_notify(self, title: str, message: str):
        try:
            self._notify_fn({"title": f"BUDDY: {title}", "message": message})
        except Exception:
            pass  # notifications are best-effort
