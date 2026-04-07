"""
Streaming Tool Executor — CC-aligned concurrent tool execution during streaming.
CC: StreamingToolExecutor.ts — executes tools while LLM is still streaming.

Key: tools are dispatched as soon as their tool_use JSON block is complete,
not after the entire response is finished. This roughly halves latency.
"""

import threading
import time
from enum import Enum
from typing import Any, Callable
from concurrent.futures import ThreadPoolExecutor, Future


class ToolStatus(Enum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    ERRORED = "errored"


class TrackedTool:
    """A tool call being tracked through the streaming executor."""
    def __init__(self, tool_use_id: str, tool_name: str, tool_input: dict):
        self.id = tool_use_id
        self.name = tool_name
        self.input = tool_input
        self.status = ToolStatus.QUEUED
        self.result: dict | None = None
        self.future: Future | None = None
        self.is_concurrency_safe: bool = False


class StreamingToolExecutor:
    """
    CC-aligned: execute tools while the LLM response is still streaming.
    Tools are dispatched immediately when their tool_use block completes.
    Results are buffered in stream order.
    """

    def __init__(
        self,
        executor_fn: Callable[[str, dict], dict],
        concurrency_safe_fn: Callable[[str], bool],
        max_workers: int = 10,
    ):
        """
        executor_fn: (tool_name, input) → result dict
        concurrency_safe_fn: (tool_name) → bool
        """
        self._executor_fn = executor_fn
        self._concurrency_safe_fn = concurrency_safe_fn
        self._max_workers = max_workers
        self._tracked: list[TrackedTool] = []
        self._pool: ThreadPoolExecutor | None = None
        self._discarded = False

    def add_tool(self, tool_use_id: str, tool_name: str, tool_input: dict):
        """
        CC: called when a tool_use block is fully received from the stream.
        Immediately dispatches if concurrency-safe, else queues.
        """
        if self._discarded:
            return

        tracked = TrackedTool(tool_use_id, tool_name, tool_input)
        tracked.is_concurrency_safe = self._concurrency_safe_fn(tool_name)
        self._tracked.append(tracked)

        # Dispatch immediately if safe
        if tracked.is_concurrency_safe:
            self._dispatch(tracked)

    def flush_sequential(self):
        """
        CC: called when all tool_use blocks are received.
        Dispatches any queued non-concurrent tools sequentially.
        """
        if self._discarded:
            return

        for tracked in self._tracked:
            if tracked.status == ToolStatus.QUEUED and not tracked.is_concurrency_safe:
                self._dispatch(tracked)
                # Wait for non-concurrent tool before dispatching next
                if tracked.future:
                    tracked.future.result()

    def wait_all(self, timeout: float = 300) -> list[dict]:
        """Wait for all tools to complete. Returns results in stream order."""
        deadline = time.time() + timeout
        results = []
        for tracked in self._tracked:
            if tracked.future:
                remaining = max(0, deadline - time.time())
                try:
                    tracked.future.result(timeout=remaining)
                except Exception:
                    if tracked.result is None:
                        tracked.result = {"output": f"Timeout waiting for {tracked.name}", "is_error": True}
                        tracked.status = ToolStatus.ERRORED

            results.append(tracked.result or {"output": "No result", "is_error": True})

        self._shutdown_pool()
        return results

    def discard(self):
        """CC: called on stream fallback — cancel queued tools, mark as discarded."""
        self._discarded = True
        for tracked in self._tracked:
            if tracked.status == ToolStatus.QUEUED:
                tracked.result = {"output": "Discarded (stream fallback)", "is_error": True}
                tracked.status = ToolStatus.ERRORED
        self._shutdown_pool()

    def get_status(self) -> list[dict]:
        """Get status of all tracked tools."""
        return [
            {"id": t.id, "name": t.name, "status": t.status.value}
            for t in self._tracked
        ]

    def _dispatch(self, tracked: TrackedTool):
        """Submit tool for execution."""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=self._max_workers)

        tracked.status = ToolStatus.EXECUTING

        def _run():
            try:
                result = self._executor_fn(tracked.name, tracked.input)
                tracked.result = result if isinstance(result, dict) else {"output": str(result)}
                tracked.status = ToolStatus.COMPLETED
            except Exception as e:
                tracked.result = {"output": f"Error: {e}", "is_error": True}
                tracked.status = ToolStatus.ERRORED

        tracked.future = self._pool.submit(_run)

    def _shutdown_pool(self):
        if self._pool:
            self._pool.shutdown(wait=False)
            self._pool = None
