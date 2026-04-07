"""
SendUserFileTool — CC-aligned file delivery.
CC: Kairos remote service. BUDDY workaround: copy to outbox + notification.
"""

import shutil
from pathlib import Path
from tools.base import BaseTool
from config import DATA_DIR


class SendUserFileTool(BaseTool):
    name = "SendUserFile"
    description = (
        "Deliver a file to the user. Copies the file to the outbox directory "
        "(~/.claude-buddy/outbox/) and shows a notification. "
        "The user can find delivered files there."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to deliver",
            },
            "message": {
                "type": "string",
                "description": "Optional message to include with the file",
            },
        },
        "required": ["file_path"],
    }
    is_read_only = True  # doesn't modify the source file

    def execute(self, input_data: dict) -> str:
        file_path = Path(input_data.get("file_path", ""))
        message = input_data.get("message", "")

        if not file_path.exists():
            return f"Error: File not found: {file_path}"

        outbox = DATA_DIR / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)

        dest = outbox / file_path.name
        # Avoid overwrite
        if dest.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            i = 1
            while dest.exists():
                dest = outbox / f"{stem}_{i}{suffix}"
                i += 1

        shutil.copy2(str(file_path), str(dest))

        result = f"File delivered to: {dest}"
        if message:
            result += f"\nMessage: {message}"

        # Try desktop notification
        try:
            from tools.push_notification_tool import PushNotificationTool
            notif = PushNotificationTool()
            notif.execute({"title": "File Ready", "message": f"{file_path.name}: {message or 'File delivered'}"})
        except Exception:
            pass

        return result
