"""
SnipTool — CC-aligned history snipping.
CC: feature-gated behind HISTORY_SNIP.
Saves/retrieves named code snippets to disk.
"""

from pathlib import Path
from tools.base import BaseTool
from config import DATA_DIR


_SNIPPETS_DIR = DATA_DIR / "snippets"


class SnipTool(BaseTool):
    name = "Snip"
    description = (
        "Save, retrieve, list, and delete named code snippets. "
        "Useful for storing reusable code fragments, templates, or notes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "get", "list", "delete"],
                "description": "Action to perform",
            },
            "name": {
                "type": "string",
                "description": "Snippet name (required for save/get/delete)",
            },
            "content": {
                "type": "string",
                "description": "Snippet content (required for save)",
            },
            "language": {
                "type": "string",
                "description": "Programming language (for save, used as file extension)",
            },
        },
        "required": ["action"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        action = input_data.get("action", "list")
        name = input_data.get("name", "")

        _SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)

        if action == "save":
            content = input_data.get("content", "")
            lang = input_data.get("language", "txt")
            if not name or not content:
                return "Error: name and content required."
            safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
            path = _SNIPPETS_DIR / f"{safe_name}.{lang}"
            path.write_text(content, encoding="utf-8")
            return f"Snippet '{name}' saved ({len(content)} chars) → {path}"

        elif action == "get":
            if not name:
                return "Error: name required."
            safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
            for p in _SNIPPETS_DIR.glob(f"{safe_name}.*"):
                return f"```\n{p.read_text(encoding='utf-8')}\n```"
            return f"Snippet '{name}' not found."

        elif action == "list":
            snippets = list(_SNIPPETS_DIR.glob("*"))
            if not snippets:
                return "No snippets saved."
            lines = ["Saved Snippets:"]
            for p in sorted(snippets):
                size = p.stat().st_size
                lines.append(f"  {p.stem} ({p.suffix[1:]}, {size} bytes)")
            return "\n".join(lines)

        elif action == "delete":
            if not name:
                return "Error: name required."
            safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
            deleted = False
            for p in _SNIPPETS_DIR.glob(f"{safe_name}.*"):
                p.unlink()
                deleted = True
            return f"Snippet '{name}' deleted." if deleted else f"Snippet '{name}' not found."

        return f"Unknown action: {action}"
