"""
LSP Tool — query language server for diagnostics.
Aligned with Claude Code's LSPTool.
"""

from tools.base import BaseTool


class LSPTool(BaseTool):
    name = "LSP"
    description = (
        "Query language server diagnostics (errors, warnings) for a file.\n\n"
        "Returns compiler errors, type errors, lint warnings, etc. from the\n"
        "language server for the specified file.\n\n"
        "This requires a language server to be running (pyright, tsserver, etc.).\n"
        "Use /doctor to check if language servers are available.\n\n"
        "Parameters:\n"
        "- file_path: Path to the file to check diagnostics for\n"
        "- severity: Filter by severity ('error', 'warning', 'info', 'all')"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to check",
            },
            "severity": {
                "type": "string",
                "enum": ["error", "warning", "info", "all"],
                "description": "Filter diagnostics by severity (default: all)",
                "default": "all",
            },
        },
        "required": ["file_path"],
    }
    is_read_only = True

    def __init__(self):
        self._lsp_manager = None  # injected by ToolRegistry

    def execute(self, input_data: dict) -> str:
        file_path = input_data.get("file_path", "").strip()
        severity = input_data.get("severity", "all")

        if not file_path:
            return "Error: file_path is required."

        if not self._lsp_manager:
            return (
                "No language server available. "
                "Install a language server (pyright, tsserver, rust-analyzer, gopls) "
                "and it will be auto-detected."
            )

        diagnostics = self._lsp_manager.get_diagnostics(file_path)
        if severity != "all":
            diagnostics = [d for d in diagnostics if d.severity == severity]

        if not diagnostics:
            return f"No {severity} diagnostics for {file_path}."

        lines = [f"Diagnostics for {file_path} ({len(diagnostics)} issues):"]
        for d in diagnostics:
            lines.append(f"  {d.line}:{d.col} [{d.severity}] {d.message}")
        return "\n".join(lines)
