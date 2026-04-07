"""
Base Tool — abstract base class for all tools.
"""

from dataclasses import dataclass, field
from typing import Any
from core.providers.base import ToolDef


@dataclass
class ToolResult:
    output: str
    is_error: bool = False


class BaseTool:
    """Abstract base class for all buddy tools."""

    name: str = ""
    description: str = ""
    input_schema: dict = field(default_factory=dict)  # JSON Schema
    is_read_only: bool = False
    is_destructive: bool = False
    concurrency_safe: bool = False  # CC: isConcurrencySafe — safe to run in parallel

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def execute(self, input_data: dict) -> str:
        """Execute the tool and return output string."""
        raise NotImplementedError

    def to_tool_def(self) -> ToolDef:
        """Convert to ToolDef for provider formatting."""
        return ToolDef(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )
