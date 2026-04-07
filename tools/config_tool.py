"""
Config Tool — view and modify BUDDY configuration.
Aligned with Claude Code's ConfigTool.
"""

import json
from pathlib import Path
from tools.base import BaseTool
from config import DATA_DIR


CONFIG_FILE = DATA_DIR / "settings.json"


class ConfigTool(BaseTool):
    name = "Config"
    description = (
        "View or modify BUDDY configuration settings.\n\n"
        "Operations:\n"
        "- get: Read a config value by key\n"
        "- set: Write a config value\n"
        "- list: Show all settings\n\n"
        "Parameters:\n"
        "- operation: 'get', 'set', or 'list'\n"
        "- key: Config key (for get/set)\n"
        "- value: New value (for set)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["get", "set", "list"],
                "description": "Operation: get, set, or list",
            },
            "key": {
                "type": "string",
                "description": "Config key (dot-notation, e.g., 'model.name')",
            },
            "value": {
                "type": "string",
                "description": "New value for set operation",
            },
        },
        "required": ["operation"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        op = input_data.get("operation", "list")
        key = input_data.get("key", "").strip()
        value = input_data.get("value")

        config = self._load_config()

        if op == "list":
            if not config:
                return "No configuration set. Use Config(operation='set', key='...', value='...') to add."
            lines = ["Configuration:"]
            for k, v in sorted(config.items()):
                lines.append(f"  {k} = {json.dumps(v)}")
            return "\n".join(lines)

        if op == "get":
            if not key:
                return "Error: key is required for get operation."
            val = config.get(key)
            if val is None:
                return f"Config key '{key}' not found."
            return f"{key} = {json.dumps(val)}"

        if op == "set":
            if not key:
                return "Error: key is required for set operation."
            if value is None:
                return "Error: value is required for set operation."
            # Try to parse as JSON for non-string types
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                parsed = value
            config[key] = parsed
            self._save_config(config)
            return f"Set {key} = {json.dumps(parsed)}"

        return f"Error: Unknown operation '{op}'. Use get, set, or list."

    @staticmethod
    def _load_config() -> dict:
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    @staticmethod
    def _save_config(config: dict):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
