"""
File Write Tool — write content to a file with staleness protection.
Aligned with Claude Code's FileWriteTool:
- Warns when overwriting existing files
- Updates file-read state after write
"""

import hashlib
from pathlib import Path
from tools.base import BaseTool


class FileWriteTool(BaseTool):
    name = "FileWrite"
    description = (
        "Write content to a file, creating it if it doesn't exist.\n\n"
        "WARNING: This OVERWRITES the entire file. For modifying part of a file, "
        "use FileEdit instead.\n\n"
        "Features:\n"
        "- Creates parent directories automatically\n"
        "- Use absolute paths\n"
        "- Best for: creating new files, complete file rewrites\n\n"
        "When to use FileWrite vs FileEdit:\n"
        "- FileWrite: creating a NEW file, or completely rewriting an existing file\n"
        "- FileEdit: changing specific parts of an existing file\n\n"
        "IMPORTANT: If the file already exists, you MUST read it with FileRead first.\n"
        "REMINDER: For modifying existing files, prefer FileEdit (it only changes the diff)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    }
    is_read_only = False
    is_destructive = True

    def __init__(self):
        self._file_read_state = None  # injected by ToolRegistry

    def execute(self, input_data: dict) -> str:
        file_path = Path(input_data["file_path"])
        content = input_data["content"]

        # Read-before-overwrite enforcement for existing files
        if file_path.exists() and self._file_read_state:
            if not self._file_read_state.has_read(str(file_path)):
                return (
                    f"Warning: {file_path} already exists but you haven't read it. "
                    f"FileWrite will OVERWRITE the entire file. "
                    f"Use FileRead first to see current content, or if you're sure, "
                    f"re-submit this FileWrite call."
                )

        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            is_new = not file_path.exists()
            file_path.write_text(content, encoding="utf-8")
            lines = content.count("\n") + 1

            # Update file-read state
            if self._file_read_state:
                new_mtime = file_path.stat().st_mtime
                new_hash = hashlib.md5(content.encode()).hexdigest()[:12]
                self._file_read_state.record_read(
                    str(file_path), mtime=new_mtime, content_hash=new_hash
                )

            action = "Created" if is_new else "Overwrote"
            return f"{action} {file_path} ({lines} lines)"

        except Exception as e:
            return f"Error writing file: {e}"
