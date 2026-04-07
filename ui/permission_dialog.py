"""
Permission Dialog — tool permission approval UI.
"""

import json
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QPlainTextEdit,
)

from config import (
    BG_DARK, BG_BUBBLE, TEXT_PRIMARY, TEXT_DIM,
    CLAUDE_ORANGE, PERMISSION_BLUE, ERROR_RED,
    BORDER_RADIUS, SUCCESS_GREEN,
)


class PermissionDialog(QDialog):
    """Modal dialog for approving tool executions."""

    def __init__(self, tool_name: str, input_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Permission Request")
        self.setWindowFlags(
            Qt.WindowType.Dialog
        )
        self.setFixedWidth(420)
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG_DARK};
                border: 1px solid {PERMISSION_BLUE};
                border-radius: {BORDER_RADIUS}px;
            }}
        """)

        self._result = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel(f"🔒 <b style='color:{PERMISSION_BLUE}'>Permission Request</b>")
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setStyleSheet(f"font-size: 15px; color: {TEXT_PRIMARY};")
        layout.addWidget(header)

        # Tool name
        tool_label = QLabel(f"<b>{tool_name}</b> wants to execute:")
        tool_label.setTextFormat(Qt.TextFormat.RichText)
        tool_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px;")
        layout.addWidget(tool_label)

        # Input details
        detail_text = json.dumps(input_data, indent=2, ensure_ascii=False)
        detail = QPlainTextEdit(detail_text)
        detail.setReadOnly(True)
        detail.setMaximumHeight(200)
        detail.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {BG_BUBBLE};
                color: {TEXT_DIM};
                border: 1px solid #555;
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }}
        """)
        layout.addWidget(detail)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        deny_btn = QPushButton("Deny")
        deny_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ERROR_RED};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #FF8599; }}
        """)
        deny_btn.clicked.connect(self._on_deny)

        allow_btn = QPushButton("Allow")
        allow_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SUCCESS_GREEN};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #5ECF75; }}
        """)
        allow_btn.clicked.connect(self._on_allow)

        always_btn = QPushButton("Always Allow")
        always_btn.setStyleSheet(f"""
            QPushButton {{
                background: {PERMISSION_BLUE};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #C5CBF9; }}
        """)
        always_btn.clicked.connect(self._on_always)

        btn_layout.addWidget(deny_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(allow_btn)
        btn_layout.addWidget(always_btn)

        layout.addLayout(btn_layout)

        self._always = False

    @property
    def approved(self) -> bool:
        return self._result

    @property
    def always_allow(self) -> bool:
        return self._always

    def _on_deny(self):
        self._result = False
        self.accept()

    def _on_allow(self):
        self._result = True
        self.accept()

    def _on_always(self):
        self._result = True
        self._always = True
        self.accept()


class PermissionManager(QObject):
    """
    Manages tool permissions with multi-source decisions.
    Aligned with Claude Code's permission system:
      - Always-allow rules (persistent, per-tool and per-pattern)
      - Always-deny rules (persistent)
      - Denial tracking (count consecutive denials)
      - Pattern-based matching (e.g., "Bash(git *)")
    """

    _permission_request = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._always_allowed: set[str] = set()        # tool names
        self._allow_patterns: list[str] = []           # "Bash(git *)" patterns
        self._always_denied: set[str] = set()          # tool names
        self._denial_count: dict[str, int] = {}        # tool → consecutive denials
        self._pending_event = threading.Event()
        self._pending_result = False
        self._load_permissions()

    def check_permission(self, tool_name: str, input_data: dict) -> bool:
        """
        Check if a tool call is permitted. May show a dialog.
        Thread-safe — can be called from the engine thread.
        """
        # 1. Check always-denied
        if tool_name in self._always_denied:
            self._track_denial(tool_name)
            return False

        # 2. Check always-allowed (exact tool name)
        if tool_name in self._always_allowed:
            return True

        # 3. Check pattern-based rules (e.g., "Bash(git *)")
        if self._matches_allow_pattern(tool_name, input_data):
            return True

        # 4. Show dialog on main thread
        self._pending_event.clear()
        self._pending_result = False

        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
        QMetaObject.invokeMethod(
            self,
            "_show_dialog",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, tool_name),
            Q_ARG(str, json.dumps(input_data)),
        )

        self._pending_event.wait(timeout=300)

        if not self._pending_result:
            self._track_denial(tool_name)
        else:
            self._denial_count.pop(tool_name, None)

        return self._pending_result

    def _matches_allow_pattern(self, tool_name: str, input_data: dict) -> bool:
        """Check if tool+input matches any allow pattern like 'Bash(git *)'."""
        import fnmatch
        for pattern in self._allow_patterns:
            if "(" in pattern:
                # Pattern format: "ToolName(command_pattern)"
                pat_tool, _, pat_arg = pattern.partition("(")
                pat_arg = pat_arg.rstrip(")")
                if pat_tool.strip() == tool_name:
                    # Match against command (for Bash) or file_path (for file tools)
                    cmd = input_data.get("command", input_data.get("file_path", ""))
                    if fnmatch.fnmatch(str(cmd), pat_arg.strip()):
                        return True
            else:
                if pattern.strip() == tool_name:
                    return True
        return False

    def _track_denial(self, tool_name: str):
        """Track consecutive denials for a tool."""
        self._denial_count[tool_name] = self._denial_count.get(tool_name, 0) + 1

    def get_denial_count(self, tool_name: str) -> int:
        return self._denial_count.get(tool_name, 0)

    def add_allow_pattern(self, pattern: str):
        """Add a pattern-based allow rule (e.g., 'Bash(git *)')."""
        if pattern not in self._allow_patterns:
            self._allow_patterns.append(pattern)
            self._save_permissions()

    def _show_dialog(self, tool_name: str, input_json: str):
        """Show permission dialog (runs on main thread via signal)."""
        input_data = json.loads(input_json)
        dialog = PermissionDialog(tool_name, input_data)
        dialog.exec()

        if dialog.always_allow:
            self._always_allowed.add(tool_name)
            self._save_permissions()

        self._pending_result = dialog.approved
        self._pending_event.set()

    # ── Persistence ──────────────────────────────────────────────────

    _PERM_FILE = "permissions.json"

    def _save_permissions(self):
        """Save permission rules to disk."""
        try:
            from config import DATA_DIR
            path = DATA_DIR / self._PERM_FILE
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "always_allowed": sorted(self._always_allowed),
                "allow_patterns": self._allow_patterns,
                "always_denied": sorted(self._always_denied),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_permissions(self):
        """Load persisted permission rules."""
        try:
            from config import DATA_DIR
            path = DATA_DIR / self._PERM_FILE
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    # Legacy format: just a list of allowed tools
                    self._always_allowed = set(data)
                elif isinstance(data, dict):
                    self._always_allowed = set(data.get("always_allowed", []))
                    self._allow_patterns = data.get("allow_patterns", [])
                    self._always_denied = set(data.get("always_denied", []))
        except Exception:
            pass

    def reset_permissions(self):
        """Clear all always-allowed permissions (for settings UI)."""
        self._always_allowed.clear()
        self._save_permissions()
