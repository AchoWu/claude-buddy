"""
PushNotificationTool — CC-aligned desktop notifications.
CC: feature-gated behind KAIROS / KAIROS_PUSH_NOTIFICATION.
BUDDY: uses cross-platform desktop notification via plyer or OS fallbacks.
"""

import platform
import subprocess
from tools.base import BaseTool


class PushNotificationTool(BaseTool):
    name = "PushNotification"
    description = (
        "Send a desktop notification to the user. "
        "Useful for alerting on task completion, errors, or important events "
        "during background/long-running operations."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Notification title",
            },
            "message": {
                "type": "string",
                "description": "Notification body text",
            },
            "timeout": {
                "type": "integer",
                "description": "Display duration in seconds (default: 10)",
            },
        },
        "required": ["title", "message"],
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        title = input_data.get("title", "BUDDY")
        message = input_data.get("message", "")
        timeout = input_data.get("timeout", 10)

        if not message:
            return "Error: message is required."

        try:
            return self._notify(title, message, timeout)
        except Exception as e:
            return f"Notification failed: {e}"

    def _notify(self, title: str, message: str, timeout: int) -> str:
        # Try plyer first (cross-platform)
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                timeout=timeout,
                app_name="Claude Buddy",
            )
            return f"Notification sent: {title}"
        except ImportError:
            pass

        # Platform-specific fallbacks
        system = platform.system()
        if system == "Darwin":  # macOS
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return f"Notification sent (macOS): {title}"
        elif system == "Linux":
            subprocess.run(
                ["notify-send", title, message, f"--expire-time={timeout * 1000}"],
                capture_output=True, timeout=5,
            )
            return f"Notification sent (Linux): {title}"
        elif system == "Windows":
            # Windows toast via PowerShell
            ps_cmd = (
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                f"ContentType = WindowsRuntime] > $null; "
                f"$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(0); "
                f"$text = $xml.GetElementsByTagName('text'); "
                f"$text[0].AppendChild($xml.CreateTextNode('{title}')); "
                f"$text[1].AppendChild($xml.CreateTextNode('{message}')); "
                f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Buddy')"
                f".Show([Windows.UI.Notifications.ToastNotification]::new($xml))"
            )
            try:
                subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=10)
                return f"Notification sent (Windows): {title}"
            except Exception:
                pass

        return f"Notification displayed in log: [{title}] {message}"
