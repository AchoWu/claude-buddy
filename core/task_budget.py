"""
Task Budget — CC-aligned per-task token budget enforcement.
CC: output_config.task_budget = {total, remaining}
Prevents runaway agents from consuming unlimited tokens.
"""

from dataclasses import dataclass


@dataclass
class TaskBudget:
    """Track token budget for a single task/query."""
    total: int = 0           # Total token budget for this task
    remaining: int = 0       # Remaining tokens
    enabled: bool = False    # Whether budget enforcement is active

    @property
    def is_exhausted(self) -> bool:
        return self.enabled and self.remaining <= 0

    @property
    def percentage_used(self) -> float:
        if not self.enabled or self.total <= 0:
            return 0.0
        return (1.0 - self.remaining / self.total) * 100

    def deduct(self, output_tokens: int):
        """Deduct tokens from remaining budget."""
        if self.enabled:
            self.remaining = max(0, self.remaining - output_tokens)

    def to_output_config(self) -> dict | None:
        """Convert to output_config.task_budget for API call."""
        if not self.enabled:
            return None
        return {"total": self.total, "remaining": self.remaining}

    @classmethod
    def from_config(cls, config: dict | None) -> "TaskBudget":
        """Create from output_config.task_budget response."""
        if not config:
            return cls()
        return cls(
            total=config.get("total", 0),
            remaining=config.get("remaining", config.get("total", 0)),
            enabled=True,
        )

    def get_wrap_up_message(self) -> str:
        """CC: message injected when budget is near exhaustion."""
        return (
            "Token budget is nearly exhausted. Wrap up your current work: "
            "finish the immediate task, save any important state, and provide "
            "a brief summary of what was accomplished and what remains."
        )
