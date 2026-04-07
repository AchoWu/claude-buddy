"""
LLM Engine v3 — fully aligned with Claude Code's QueryEngine.ts.

Key patterns implemented:
  - Multi-layer auto-compaction (snip → compress → summarize → reactive)
  - Token tracking with per-model context window awareness
  - Max-output-token recovery circuit (3 attempts)
  - Reactive compaction (on prompt-too-long API error)
  - Proper error categorization (retryable vs fatal)
  - Transition state machine for debugging
  - Abort signal support (cancel mid-loop)
  - Smart tool result truncation (head+tail)
  - Dynamic context injection per turn
  - Per-model cost tracking
  - Parallel-safe tool execution
  - Memory system integration
  - Post-tool hooks (file-read tracking, CWD updates)
"""

import time
import hashlib
import threading
import traceback
import random
import json as _json
from typing import Any, Callable
from enum import Enum
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from core.providers.base import BaseProvider, ToolCall, ToolDef, AbortSignal, LLMCallParams
from core.conversation import ConversationManager
from core.context_injection import collect_context, invalidate_cache
from core.normalization import normalize_messages
from core.tool_summary import generate_tool_summary_async
from prompts.system import build_system_prompt
from config import MAX_TOOL_ROUNDS


# ── Error Classification ─────────────────────────────────────────────

class ErrorCategory(Enum):
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"       # CC: 529 separate from 429
    SERVER_ERROR = "server_error"
    CONTEXT_TOO_LONG = "context_too_long"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


def categorize_error(e: Exception) -> ErrorCategory:
    """Classify an API error into a structured category."""
    msg = str(e).lower()
    # CC: 529 is OVERLOADED (separate from 429 rate_limit)
    if any(kw in msg for kw in ["529", "overloaded_error"]):
        return ErrorCategory.OVERLOADED
    if any(kw in msg for kw in ["rate limit", "429", "too many requests"]):
        return ErrorCategory.RATE_LIMIT
    if any(kw in msg for kw in ["context_length", "context length", "too many tokens",
                                 "prompt is too long", "request too large", "context window"]):
        return ErrorCategory.CONTEXT_TOO_LONG
    if any(kw in msg for kw in ["max_tokens", "max output", "maximum output",
                                 "output token", "length limit"]):
        return ErrorCategory.MAX_OUTPUT_TOKENS
    if any(kw in msg for kw in ["timeout", "timed out", "deadline"]):
        return ErrorCategory.TIMEOUT
    if any(kw in msg for kw in ["connection", "network", "dns", "socket",
                                 "econnreset", "epipe", "broken pipe"]):
        return ErrorCategory.NETWORK_ERROR
    if any(kw in msg for kw in ["500", "502", "503", "504", "overloaded",
                                 "server error", "internal error", "bad gateway",
                                 "service unavailable"]):
        return ErrorCategory.SERVER_ERROR
    if any(kw in msg for kw in ["401", "403", "unauthorized", "forbidden",
                                 "authentication", "invalid api key"]):
        return ErrorCategory.AUTH_ERROR
    if any(kw in msg for kw in ["400", "invalid", "malformed", "validation"]):
        return ErrorCategory.INVALID_REQUEST
    return ErrorCategory.UNKNOWN


def is_retryable(cat: ErrorCategory) -> bool:
    """Check if an error category is retryable. CC: AUTH_ERROR is retryable (reinit client)."""
    return cat in {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.OVERLOADED,
        ErrorCategory.SERVER_ERROR,
        ErrorCategory.NETWORK_ERROR,
        ErrorCategory.TIMEOUT,
        ErrorCategory.AUTH_ERROR,  # CC: retryable — reinit client on each attempt
    }


# ── Transition Types ─────────────────────────────────────────────────

class TransitionType(Enum):
    COMPACTION = "compaction"
    TOKEN_COMPACTION = "token_compaction"
    CONTEXT_RECOVERY = "context_recovery"
    MAX_OUTPUT_RECOVERY = "max_output_recovery"
    TOOL_RESULTS = "tool_results"
    TERMINAL = "terminal"
    MAX_ROUNDS = "max_rounds"
    ABORTED = "aborted"
    ERROR = "error"


# ── Cost Tracking ────────────────────────────────────────────────────

class SessionCost:
    """Track token usage and cost per session."""

    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_api_calls = 0
        self.total_tool_calls = 0
        self.cache_read_tokens = 0       # CC-aligned: prompt cache hits
        self.cache_creation_tokens = 0   # CC-aligned: prompt cache misses
        self.model_usage: dict[str, dict] = {}  # model → {input, output, calls}

    def add_call(self, model: str, input_tokens: int = 0, output_tokens: int = 0):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_api_calls += 1
        if model not in self.model_usage:
            self.model_usage[model] = {"input": 0, "output": 0, "calls": 0}
        self.model_usage[model]["input"] += input_tokens
        self.model_usage[model]["output"] += output_tokens
        self.model_usage[model]["calls"] += 1

    def add_tool_call(self):
        self.total_tool_calls += 1

    def summary(self) -> str:
        parts = [
            f"API calls: {self.total_api_calls}",
            f"Tool calls: {self.total_tool_calls}",
            f"Input tokens: {self.total_input_tokens:,}",
            f"Output tokens: {self.total_output_tokens:,}",
        ]
        if self.cache_read_tokens or self.cache_creation_tokens:
            parts.append(f"Cache read tokens: {self.cache_read_tokens:,}")
            parts.append(f"Cache creation tokens: {self.cache_creation_tokens:,}")
        # CC-aligned: show cost estimate
        cost = self.cost_usd
        if cost > 0:
            parts.append(f"Estimated cost: ${cost:.4f}")
        if self.model_usage:
            parts.append("By model:")
            for model, usage in self.model_usage.items():
                parts.append(f"  {model}: {usage['calls']} calls, {usage['input']:,}+{usage['output']:,} tokens")
        return "\n".join(parts)

    @property
    def cost_usd(self) -> float:
        """CC-aligned: calculate cost in USD based on model pricing."""
        try:
            from config import MODEL_PRICING
        except ImportError:
            return 0.0

        total = 0.0
        for model, usage in self.model_usage.items():
            pricing = MODEL_PRICING.get(model)
            if not pricing:
                # Try partial match
                for key, val in MODEL_PRICING.items():
                    if key in model or model in key:
                        pricing = val
                        break
            if pricing:
                total += usage["input"] * pricing.get("input", 0) / 1_000_000
                total += usage["output"] * pricing.get("output", 0) / 1_000_000

        # Add cache costs
        if self.cache_read_tokens or self.cache_creation_tokens:
            # Use first model's pricing for cache
            for model in self.model_usage:
                pricing = MODEL_PRICING.get(model, {})
                total += self.cache_read_tokens * pricing.get("cache_read", 0) / 1_000_000
                total += self.cache_creation_tokens * pricing.get("cache_create", 0) / 1_000_000
                break

        return total


# ═══════════════════════════════════════════════════════════════════════

class LLMEngine(QObject):
    """
    Core AI engine. Runs the LLM tool-call loop in a background thread.
    Communicates with the UI via Qt signals (thread-safe).
    """

    # ── Signals ───────────────────────────────────────────────────────
    response_text = pyqtSignal(str)       # final text reply
    response_chunk = pyqtSignal(str)      # streaming text fragment
    intermediate_text = pyqtSignal(str)   # mid-loop text (shown alongside tool calls)
    tool_start = pyqtSignal(str, dict)    # tool name, input
    tool_result = pyqtSignal(str, str)    # tool name, output
    state_changed = pyqtSignal(str)       # pet state: idle/working/etc.
    error = pyqtSignal(str)               # error message
    cost_updated = pyqtSignal(str)        # cost summary string
    plan_mode_changed = pyqtSignal(bool)  # plan mode toggled
    ask_user = pyqtSignal(str, object, bool)  # question, options(list), multiSelect

    # ── Retry config (CC: withRetry.ts BASE_DELAY_MS=500, max 10 retries) ──
    MAX_RETRIES = 10
    RETRY_BASE_DELAY = 0.5      # CC: 500ms
    RETRY_MAX_DELAY = 32.0      # CC: normal mode caps at 32s
    RETRY_JITTER_FACTOR = 0.25  # CC: uniform random 0-25% of base delay
    MAX_529_RETRIES = 3         # CC: separate 529 retry limit before model fallback

    # ── Recovery limits (circuit breakers) ────────────────────────────
    MAX_OUTPUT_TOKEN_RECOVERY_LIMIT = 3
    MAX_REACTIVE_COMPACT_ATTEMPTS = 2

    # ── Max-output escalation (CC: 8k→64k single jump, NOT progressive) ─
    CAPPED_DEFAULT_MAX_TOKENS = 8000     # CC: context.ts L24
    ESCALATED_MAX_TOKENS = 64000         # CC: context.ts L25

    # ── Token budget ──────────────────────────────────────────────────
    DEFAULT_CONTEXT_WINDOW = 32000
    OUTPUT_RESERVE = 4000
    COMPACTION_BUFFER = 8000

    # ── Tool result limits (CC: DEFAULT_MAX_RESULT_SIZE_CHARS=50000) ─
    MAX_TOOL_RESULT_CHARS = 50000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider: BaseProvider | None = None
        self._provider_model: str = ""
        self._tools: list[ToolDef] = []
        self._tool_executors: dict[str, Callable] = {}
        self._tool_read_only: dict[str, bool] = {}
        self._tool_concurrency_safe: dict[str, bool] = {}  # CC: isConcurrencySafe per tool
        self._conversation = ConversationManager()
        self._permission_callback: Callable[[str, dict], bool] | None = None
        self._is_running = False
        self._abort_signal = AbortSignal()
        self._context_window = self.DEFAULT_CONTEXT_WINDOW

        # CC-aligned: AskUser blocking mechanism
        self._ask_user_event = threading.Event()
        self._ask_user_answer: str = ""

        # Session tracking
        self._session_cost = SessionCost()
        self._last_transitions: list[dict] = []
        self._memory_content: str | None = None
        self._denied_tools: list[dict] = []  # CC-aligned: wrappedCanUseTool denial tracking

        # Plan mode state (injected by ToolRegistry)
        self._plan_mode_state = None  # PlanModeState | None

        # Background tasks registry {task_id: {thread, output, status, buffer}}
        self._background_tasks: dict[str, dict] = {}
        self._next_task_id = 1
        self._streaming_enabled = True  # can be toggled via settings

        # Max-output escalation state (CC-aligned)
        self._max_output_override: int | None = None

        # Memory manager (injected by main.py)
        self._memory_mgr = None

        # Team memory store (shared across agents)
        self._team_memory = None  # TeamMemoryStore, injected

        # Evolution manager (injected by main.py)
        self._evolution_mgr = None  # EvolutionManager, for self-reflection

        # Hook registry (CC-aligned lifecycle hooks)
        self._hook_registry = None  # HookRegistry, injected

        # #53 CC-aligned: session lineage (parent→child tracking)
        self._parent_session_id: str | None = None

        # #66 CC-aligned: message fingerprint for cache consistency
        self._last_msg_fingerprint: str = ""

        # #13 CC-aligned: 529 overloaded counter (separate from 429)
        self._consecutive_529 = 0

        # #30 CC-aligned: tool result disk persistence threshold
        self._tool_result_persist_dir = Path.home() / ".claude-buddy" / "tool_results"

        # #55 CC-aligned: analytics event pre-queue (buffer before sink attached)
        self._analytics_queue: list[dict] = []
        self._analytics_sink: Callable[[dict], None] | None = None

        # #11 CC-aligned: cache break detection (tool-set hash tracking)
        self._tool_set_hash: str = ""

        # #65 CC-aligned: API response iterations field
        self._last_api_iterations: int = 0

        # #67 CC-aligned: cached microcompact detection
        self._last_compact_msg_count: int = 0

    # ── Configuration ─────────────────────────────────────────────────

    def set_provider(self, provider: BaseProvider, model: str = ""):
        self._provider = provider
        self._provider_model = model
        invalidate_cache()
        # #18 CC-aligned: API preconnect — warm up connection pool
        self._preconnect(provider)

    def _preconnect(self, provider: BaseProvider):
        """#18 CC-aligned: preconnect to API (HTTP HEAD to warm TCP+TLS)."""
        def _warmup():
            try:
                import urllib.request
                # Determine base URL from provider
                base_url = getattr(provider, '_base_url', None)
                if not base_url and hasattr(provider, '_client'):
                    base_url = getattr(provider._client, 'base_url', None)
                    if base_url:
                        base_url = str(base_url)
                if not base_url:
                    base_url = "https://api.anthropic.com"
                # CC: fetch(baseUrl, {method: "HEAD", signal: AbortSignal.timeout(10_000)})
                req = urllib.request.Request(base_url, method="HEAD")
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass  # preconnect is best-effort, swallow all errors
        t = threading.Thread(target=_warmup, daemon=True)
        t.start()

    def set_context_window(self, tokens: int):
        self._context_window = tokens

    def set_memory(self, content: str | None):
        """Set memory content to inject into system prompt."""
        self._memory_content = content

    def set_memory_manager(self, mgr):
        """Inject MemoryManager for auto-extraction."""
        self._memory_mgr = mgr

    def set_team_memory(self, store):
        """Inject TeamMemoryStore for agent memory sharing."""
        self._team_memory = store

    def set_evolution_manager(self, mgr):
        """Inject EvolutionManager for self-reflection."""
        self._evolution_mgr = mgr

    def set_hook_registry(self, registry):
        """Inject HookRegistry for lifecycle event hooks."""
        self._hook_registry = registry

    def set_analytics_sink(self, sink: Callable[[dict], None]):
        """#55 CC-aligned: attach analytics sink, flush queued events."""
        self._analytics_sink = sink
        # Flush pre-queued events
        for event in self._analytics_queue:
            try:
                sink(event)
            except Exception:
                pass
        self._analytics_queue.clear()

    def _emit_analytics(self, event_type: str, data: dict | None = None):
        """#55 CC-aligned: emit analytics event (buffered if no sink)."""
        event = {"type": event_type, "time": time.time(), **(data or {})}
        if self._analytics_sink:
            try:
                self._analytics_sink(event)
            except Exception:
                pass
        else:
            self._analytics_queue.append(event)

    def register_tool(
        self,
        tool_def: ToolDef,
        executor: Callable[[dict], Any],
        is_read_only: bool = False,
        concurrency_safe: bool = False,
    ):
        self._tools.append(tool_def)
        self._tool_executors[tool_def.name] = executor
        self._tool_read_only[tool_def.name] = is_read_only
        self._tool_concurrency_safe[tool_def.name] = concurrency_safe
        # #11 CC-aligned: update tool-set hash for cache break detection
        self._update_tool_set_hash()

    def set_permission_callback(self, callback: Callable[[str, dict], bool]):
        self._permission_callback = callback

    def resolve_ask_user(self, answer: str):
        """Called from UI thread when user answers an AskUser question."""
        self._ask_user_answer = answer
        self._ask_user_event.set()

    @property
    def conversation(self) -> ConversationManager:
        return self._conversation

    @property
    def transitions(self) -> list[dict]:
        return self._last_transitions

    @property
    def session_cost(self) -> SessionCost:
        return self._session_cost

    # ── Message Sending ───────────────────────────────────────────────

    def send_message(self, user_text: str):
        """Send a user message — runs the tool loop in a background thread."""
        if self._is_running:
            self.error.emit("Already processing a message.")
            return
        if not self._provider:
            self.error.emit("No AI provider configured. Open Settings to add an API key.")
            return

        self._is_running = True
        self._abort_signal.reset()
        self._msg_count_before_send = len(self._conversation._messages)
        self._conversation.add_user_message(user_text)
        self.state_changed.emit("work")

        self._msg_count_at_query_start = len(self._conversation._messages)
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()

    def send_prompt(self, prompt: str, display_text: str = ""):
        """Send a prompt to the LLM without adding it as a visible user message.
        Used by __LLM_PROMPT__ commands (/init, /review, /pr).
        The prompt goes to the model, but conversation stores display_text for UI."""
        if self._is_running:
            self.error.emit("Already processing a message.")
            return
        if not self._provider:
            self.error.emit("No AI provider configured. Open Settings to add an API key.")
            return

        self._is_running = True
        self._abort_signal.reset()
        self._msg_count_before_send = len(self._conversation._messages)
        # Store display_text in conversation (shown on reload),
        # but put full prompt as content for the API call
        self._conversation._messages.append({
            "role": "user",
            "content": prompt,
            "_display": display_text or prompt,
            "timestamp": __import__("time").time(),
        })
        self._conversation._dirty = True
        self.state_changed.emit("work")

        self._msg_count_at_query_start = len(self._conversation._messages)
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()

    def abort(self):
        """Request the current operation to abort immediately."""
        self._abort_signal.abort("user_cancel")

    def _run_loop(self):
        try:
            self._tool_loop()
        except Exception as e:
            if self._abort_signal.aborted:
                self._persist_abort()
                self.error.emit("Operation cancelled.")
            else:
                tb = traceback.format_exc()
                self.error.emit(f"Engine error: {e}\n{tb}")
        finally:
            self._is_running = False
            self._abort_signal.reset()
            self.state_changed.emit("idle")
            self.cost_updated.emit(self._session_cost.summary())
            # #51 CC-aligned: persist cost to settings.local.json
            self.persist_cost()

    def _persist_abort(self):
        """
        Persist cancelled operation — CC-aligned.
        CC uses createUserInterruptionMessage() which returns role="user".

        Rollback: remove ALL assistant/tool messages added since query start
        (not just the current round), then append the interrupt marker.
        Uses _msg_count_at_query_start which is set once at send_message time
        and never updated during the tool loop — immune to round-boundary races.
        """
        # Rollback all messages added during the entire query
        rollback_point = getattr(self, '_msg_count_at_query_start', None)
        if rollback_point is not None and rollback_point < len(self._conversation._messages):
            self._conversation._messages = self._conversation._messages[:rollback_point]

        # CC-aligned: interruption marker as user message
        self._conversation._messages.append({
            "role": "user",
            "content": "[Request interrupted by user]",
            "timestamp": time.time(),
        })
        self._conversation._dirty = True
        # Save immediately so it persists across restarts
        self._conversation.save()

    # ── Retry with Error Classification ───────────────────────────────

    def _call_with_retry(self, messages, system, tools):
        """
        Call provider with exponential backoff retry.
        Uses streaming when available, falls back to sync.
        Builds CC-aligned LLMCallParams from engine state.
        Returns (raw_content, tool_calls, text).
        Raises on fatal or exhausted retries.
        """
        # Build CC-aligned call parameters
        params = LLMCallParams(
            thinking=getattr(self, '_thinking_config', None),
            effort=getattr(self, '_effort_level', None),
            cache_control=getattr(self, '_cache_control_enabled', False),
            temperature=getattr(self, '_temperature', None),
            session_id=self._conversation._conversation_id if self._conversation else None,
            output_schema=getattr(self, '_output_schema', None),
        )
        # Don't set temperature when thinking is enabled (CC: claude.ts line 1693-1695)
        if params.thinking:
            params.temperature = None

        last_error = None
        for attempt in range(1 + self.MAX_RETRIES):
            if self._abort_signal.aborted:
                raise InterruptedError("Aborted by user")

            try:
                # Use streaming if provider supports it AND streaming is enabled
                if self._streaming_enabled and self._provider.supports_streaming:
                    result = self._call_streaming(messages, system, tools, params)
                else:
                    result = self._provider.call_sync(
                        messages=messages,
                        system=system,
                        tools=tools,
                        abort_signal=self._abort_signal,
                        params=params,
                    )

                # Track cost — use real usage from API if available and plausible
                raw = result[0]
                usage = raw.get("_usage") if isinstance(raw, dict) else None
                if usage and usage.get("input_tokens", 0) > 10:
                    # Real usage from API (sanity check: input > 10 means it's real)
                    est_input = usage["input_tokens"]
                    est_output = usage["output_tokens"]
                    # CC-aligned: track cache tokens separately
                    cache_read = usage.get("cache_read_input_tokens", 0)
                    cache_creation = usage.get("cache_creation_input_tokens", 0)
                    self._session_cost.add_call(
                        self._provider_model or "unknown",
                        input_tokens=est_input,
                        output_tokens=est_output,
                    )
                    # Track cache tokens if present
                    if cache_read or cache_creation:
                        self._session_cost.cache_read_tokens += cache_read
                        self._session_cost.cache_creation_tokens += cache_creation
                else:
                    # Fallback to estimation (streaming may not return accurate usage)
                    est_input = self._conversation.estimated_tokens
                    est_output = len(str(result[2] or "")) // 3
                    self._session_cost.add_call(
                        self._provider_model or "unknown",
                        input_tokens=est_input,
                        output_tokens=est_output,
                    )

                # Chain request ID for next call (CC: streaming correlation)
                if isinstance(raw, dict):
                    req_id = raw.get("_request_id")
                    if req_id:
                        params.request_id = req_id
                    # #65 CC-aligned: read iterations field from API response
                    iterations = raw.get("_iterations", 0)
                    if iterations:
                        self._last_api_iterations = iterations

                # Reset 529 counter on success
                self._consecutive_529 = 0

                return result

            except Exception as e:
                last_error = e
                cat = categorize_error(e)

                # CC: AUTH_ERROR — reinit client on EVERY auth error (no counter)
                if cat == ErrorCategory.AUTH_ERROR:
                    if hasattr(self, '_provider_factory') and self._provider_factory:
                        try:
                            self._provider = self._provider_factory()
                        except Exception:
                            pass
                    # CC: auth errors are retryable (reinit happened above)

                # CC: 529 OVERLOADED — separate limit (MAX_529_RETRIES=3)
                if cat == ErrorCategory.OVERLOADED:
                    consecutive_529 = getattr(self, '_consecutive_529', 0) + 1
                    self._consecutive_529 = consecutive_529
                    if consecutive_529 >= self.MAX_529_RETRIES:
                        # CC: trigger model fallback or raise CannotRetryError
                        raise RuntimeError(
                            f"Repeated 529 overloaded errors ({consecutive_529} consecutive). "
                            "The API is overloaded. Try a different model or wait."
                        ) from e

                # Non-retryable or exhausted
                if not is_retryable(cat) or attempt == self.MAX_RETRIES:
                    raise

                # CC: respect retry-after header if present (NO cap — direct use)
                retry_after = getattr(e, 'retry_after', None)
                if retry_after and isinstance(retry_after, (int, float)):
                    delay = float(retry_after)  # CC: no maxDelay cap on retry-after
                else:
                    # CC: BASE_DELAY * 2^(attempt-1), capped at maxDelay
                    # attempt=0 → delay=500ms*1=500ms (CC: first retry = 500ms)
                    delay = min(
                        self.RETRY_BASE_DELAY * (2 ** max(0, attempt)),
                        self.RETRY_MAX_DELAY,
                    )
                    # CC-aligned: add 0-25% jitter to avoid thundering herd
                    jitter = random.random() * self.RETRY_JITTER_FACTOR * delay
                    delay += jitter

                self.error.emit(
                    f"API error ({cat.value}, attempt {attempt + 1}/{1 + self.MAX_RETRIES}), "
                    f"retrying in {delay:.0f}s: {self._short_error(e)}"
                )
                # Interruptible sleep with CC-aligned heartbeat every 30s
                slept = 0.0
                heartbeat_interval = 30.0
                next_heartbeat = heartbeat_interval
                while slept < delay:
                    if self._abort_signal.aborted:
                        raise InterruptedError("Aborted during retry wait")
                    time.sleep(min(0.5, delay - slept))
                    slept += 0.5
                    # CC-aligned: heartbeat during long waits
                    if slept >= next_heartbeat:
                        remaining = delay - slept
                        self.error.emit(f"Still waiting... retrying in {remaining:.0f}s")
                        next_heartbeat += heartbeat_interval

        raise last_error  # type: ignore

    def _call_streaming(self, messages, system, tools, params=None):
        """
        Call provider with streaming. Emits response_chunk for each text delta.
        CC-aligned: falls back to sync on ANY streaming failure (not just no-data).
        The sync fallback has its own call (provider.call_sync), matching CC's
        separate executeNonStreamingRequest with retry.
        """
        from core.providers.base import StreamChunk

        try:
            gen = self._provider.call_stream(
                messages=messages,
                system=system,
                tools=tools,
                abort_signal=self._abort_signal,
                params=params,
            )
            # Force generator to start (may raise immediately for non-generator errors)
            first_chunk = next(gen)
        except StopIteration:
            # Generator was empty — treat as empty response
            return {"role": "assistant", "content": ""}, [], ""
        except Exception:
            # CC-aligned: streaming fallback to sync on failure
            return self._provider.call_sync(
                messages=messages,
                system=system,
                tools=tools,
                abort_signal=self._abort_signal,
                params=params,
            )

        raw_content = None
        tool_calls = []
        text = ""

        try:
            # Process first chunk
            chunk = first_chunk
            while True:
                if self._abort_signal.aborted:
                    raise InterruptedError("Aborted by user")

                if chunk.type == "text_delta" and chunk.text:
                    self.response_chunk.emit(chunk.text)
                    text += chunk.text
                elif chunk.type == "tool_call_start":
                    # CC-aligned: do NOT emit tool_start here.
                    # CC only notifies UI at execution time, not at stream-parse time.
                    # tool_start.emit happens in _execute_one_tool / _execute_tools_parallel.
                    pass
                elif chunk.type == "done":
                    try:
                        next(gen)
                    except StopIteration as si:
                        if si.value:
                            raw_content, tool_calls, text = si.value
                    break

                # Get next chunk
                try:
                    chunk = next(gen)
                except StopIteration as si:
                    if si.value:
                        raw_content, tool_calls, text = si.value
                    break
        except InterruptedError:
            raise  # re-raise abort
        except Exception as stream_err:
            # CC-aligned: fallback on ANY mid-stream failure (not just no-data)
            # CC falls back even when partial data exists — the sync call replaces
            try:
                return self._provider.call_sync(
                    messages=messages, system=system, tools=tools,
                    abort_signal=self._abort_signal, params=params,
                )
            except Exception:
                # If sync also fails AND we have partial data, use what we have
                if text or tool_calls:
                    if raw_content is None:
                        raw_content = {"role": "assistant", "content": text}
                    return raw_content, tool_calls, text
                raise stream_err  # re-raise original if nothing to salvage

        if raw_content is None:
            raw_content = {"role": "assistant", "content": text}

        return raw_content, tool_calls, text

    @staticmethod
    def _short_error(e: Exception) -> str:
        msg = str(e)
        return msg[:150] + "..." if len(msg) > 150 else msg

    # ── Main Tool Loop ────────────────────────────────────────────────

    def _tool_loop(self):
        """
        Synchronous tool-call loop — aligned with Claude Code's QueryEngine.

        CC-aligned architecture:
          1. Check abort signal
          2. **Proactive** multi-layer compaction (BEFORE API call, not reactive)
          3. Token budget pre-flight check
          4. Call LLM API (with retry + error recovery)
             - Context-too-long: 2-stage (collapse drain → reactive compact)
             - Max-output-tokens: escalating cap (8k→16k→32k→64k)
          5. Add assistant message
          6. Emit intermediate text for UI
          7. If no tool calls → terminal (done)
          8. Execute tools (with permission checks + denial tracking)
          9. Format results and add to conversation
          10. Continue loop
        """
        # Collect dynamic context
        context = collect_context()
        system = build_system_prompt(
            context=context,
            memory_content=self._memory_content,
        )
        formatted_tools = self._provider.format_tools(self._tools) if self._tools else []

        self._last_transitions = []
        self._denied_tools = []  # Reset denial tracking per query (CC: wrappedCanUseTool)
        max_output_recovery_count = 0
        reactive_compact_count = 0
        self._max_output_override = None  # Reset escalation state

        # Wire compact subsystem: give conversation access to provider + memory + warning signal
        self._conversation._provider_call_fn = self._provider.call_sync if self._provider else None
        self._conversation._memory_mgr = self._memory_mgr
        self._conversation._on_compact_warning = lambda msg: self.error.emit(f"[Compact] {msg}")

        # Initialize rollback point (after user message, before any API call)
        # Used by _persist_abort to rollback all messages added during this query.
        self._msg_count_at_query_start = len(self._conversation._messages)
        self._msg_count_before_round = self._msg_count_at_query_start

        for round_num in range(MAX_TOOL_ROUNDS):
            # ── Step 1: Abort check ───────────────────────────────
            if self._abort_signal.aborted:
                self._record_transition(round_num, TransitionType.ABORTED, "user abort")
                raise InterruptedError("Aborted by user")

            # Record position AFTER abort check — rollback will return to here
            self._msg_count_before_round = len(self._conversation._messages)

            # ── Step 2: Proactive multi-layer compaction ─────────
            # CC-aligned: compact BEFORE API call, not just on error.
            # This prevents context-too-long errors proactively.
            # #67 CC-aligned: skip if message count unchanged since last compact
            if not self._should_skip_compact():
                compaction_result = self._conversation.compact_if_needed()
                if compaction_result:
                    self._record_transition(round_num, TransitionType.COMPACTION, compaction_result)
                    self._last_compact_msg_count = len(self._conversation.messages)

            # ── Step 3: Token budget pre-flight ───────────────────
            est_tokens = self._conversation.estimated_tokens
            compact_threshold = self._context_window - self.OUTPUT_RESERVE - self.COMPACTION_BUFFER
            if est_tokens > compact_threshold:
                extra = self._conversation.compact_if_needed()
                if extra:
                    self._record_transition(
                        round_num, TransitionType.TOKEN_COMPACTION,
                        f"tokens ~{est_tokens} > threshold {compact_threshold}: {extra}"
                    )

            # ── Step 4: Call LLM API ──────────────────────────────
            # CC-aligned: normalize messages before API call
            normalized_msgs = normalize_messages(self._conversation.messages)
            # #66 BUDDY-original: compute message fingerprint before call
            self._last_msg_fingerprint = self._compute_msg_fingerprint()
            # Determine max_tokens (may be overridden by escalation)
            effective_max_tokens = self._max_output_override or 4096

            try:
                raw_content, tool_calls, text = self._call_with_retry(
                    messages=normalized_msgs,
                    system=system,
                    tools=formatted_tools,
                )
            except Exception as e:
                cat = categorize_error(e)

                # Recovery: context too long → 2-stage (CC-aligned)
                # Stage 1: Collapse drain (force compact current messages)
                # Stage 2: Reactive compact (full compaction + retry)
                if cat == ErrorCategory.CONTEXT_TOO_LONG:
                    # Check feature flag before reactive compact
                    reactive_enabled = True
                    try:
                        from core.services.analytics import get_feature_flags
                        reactive_enabled = get_feature_flags().is_enabled("reactive_compact")
                    except Exception:
                        reactive_enabled = True  # default: enabled

                    if reactive_enabled and reactive_compact_count < self.MAX_REACTIVE_COMPACT_ATTEMPTS:
                        reactive_compact_count += 1
                        self._record_transition(
                            round_num, TransitionType.CONTEXT_RECOVERY,
                            f"stage {reactive_compact_count}: collapse drain + compact: {self._short_error(e)}"
                        )
                        # Stage 1: collapse drain — snip oldest aggressively
                        self._conversation._snip_oldest()
                        # Stage 2: full compact
                        self._conversation._full_compact()
                        try:
                            raw_content, tool_calls, text = self._call_with_retry(
                                messages=self._conversation.messages,
                                system=system,
                                tools=formatted_tools,
                            )
                        except Exception:
                            raise
                    else:
                        raise

                # Recovery: max output tokens → escalating cap (CC-aligned)
                # CC: escalate 8k→16k→32k→64k + add continuation message
                elif cat == ErrorCategory.MAX_OUTPUT_TOKENS:
                    if max_output_recovery_count < self.MAX_OUTPUT_TOKEN_RECOVERY_LIMIT:
                        max_output_recovery_count += 1
                        # Escalate the token cap (CC-aligned)
                        self._max_output_override = self._escalate_token_cap(
                            self._max_output_override
                        )
                        # CC-aligned: add continuation message (exact CC text)
                        self._conversation._messages.append({
                            "role": "user",
                            "content": (
                                "Output token limit hit. Resume directly — no apology, "
                                "no recap of what you were doing. Pick up mid-thought if "
                                "that is where the cut happened. Break remaining work into "
                                "smaller pieces."
                            ),
                            "timestamp": time.time(),
                        })
                        self._record_transition(
                            round_num, TransitionType.MAX_OUTPUT_RECOVERY,
                            f"attempt {max_output_recovery_count}, "
                            f"escalated cap to {self._max_output_override}"
                        )
                        continue  # retry the same round with higher cap
                    else:
                        raise
                else:
                    raise

            # ── Step 4b: Stop reason handling (CC-aligned) ────────
            # CC: query.ts checks stop_reason for max_tokens vs end_turn vs tool_use
            stop_reason = ""
            if isinstance(raw_content, dict):
                stop_reason = raw_content.get("_stop_reason", "end_turn")

            # CC-aligned: response withholding on max_tokens stop
            # If model stopped due to output limit (not an error, just truncated),
            # DON'T show partial text to user — silently escalate + continue
            if stop_reason == "max_tokens" and not tool_calls:
                if max_output_recovery_count < self.MAX_OUTPUT_TOKEN_RECOVERY_LIMIT:
                    max_output_recovery_count += 1
                    self._max_output_override = self._escalate_token_cap(
                        self._max_output_override
                    )
                    # CC-aligned: preserve partial assistant response in messages
                    # (already added in Step 5 below, so add it now before continuing)
                    if isinstance(raw_content, dict) and "role" in raw_content:
                        self._conversation._messages.append(raw_content)
                    else:
                        self._conversation.add_assistant_message(raw_content)
                    # Add continuation prompt
                    self._conversation._messages.append({
                        "role": "user",
                        "content": (
                            "Output token limit hit. Resume directly — no apology, "
                            "no recap of what you were doing. Pick up mid-thought if "
                            "that is where the cut happened. Break remaining work into "
                            "smaller pieces."
                        ),
                        "timestamp": time.time(),
                    })
                    self._record_transition(
                        round_num, TransitionType.MAX_OUTPUT_RECOVERY,
                        f"withhold+escalate attempt {max_output_recovery_count}, "
                        f"cap → {self._max_output_override}"
                    )
                    continue  # retry — DON'T emit partial text to user

            # ── Step 5: Add assistant message ─────────────────────
            if isinstance(raw_content, dict) and "role" in raw_content:
                self._conversation._messages.append(raw_content)
            else:
                self._conversation.add_assistant_message(raw_content)

            # ── Step 6: Emit intermediate text ──────────────────
            # If the model returned text alongside tool calls (e.g. "I'll search for..."),
            # show it immediately so user sees progress, not just tool indicators.
            if text and tool_calls:
                self.intermediate_text.emit(text)
                # Brief yield to let the main thread process the signal and update UI
                time.sleep(0.05)

            # ── Step 7: No tool calls → terminal ──────────────────
            if not tool_calls:
                if text:
                    self.response_text.emit(text)
                self._record_transition(round_num, TransitionType.TERMINAL, "end_turn")

                # Reset max-output escalation on successful terminal
                max_output_recovery_count = 0
                self._max_output_override = None

                # Auto-extract memories in background (non-blocking)
                self._try_auto_extract()

                # Self-reflection in background (non-blocking)
                self._try_self_reflect()

                return

            # ── Step 8: Execute tool calls ────────────────────────
            # CC-aligned: parallel execution when multiple tools (ThreadPoolExecutor)
            results = []
            tool_names_used = []
            if len(tool_calls) > 1:
                results, tool_names_used = self._execute_tools_parallel(
                    tool_calls, round_num
                )
            else:
                results, tool_names_used = self._execute_tools_sequential(
                    tool_calls, round_num
                )
            # Track transition
            self._record_transition(
                round_num, TransitionType.TOOL_RESULTS,
                f"{len(tool_calls)} tools: {', '.join(tool_names_used)}"
            )

            # ── Step 9: Format and add tool results ───────────────
            tool_result_msg = self._provider.format_tool_results(tool_calls, results)
            if isinstance(tool_result_msg, dict) and "_multi_messages" in tool_result_msg:
                for msg in tool_result_msg["_multi_messages"]:
                    self._conversation._messages.append(msg)
            else:
                self._conversation._messages.append(tool_result_msg)

            # ── Step 10: Tool use summary (CC: toolUseSummaryGenerator) ─
            # CC: after ≥2 tool calls, fire-and-forget summary generation
            if len(tool_calls) >= 2 and self._provider:
                tool_infos = []
                for tc, res in zip(tool_calls, results):
                    tool_infos.append({
                        "name": tc.name,
                        "input": tc.input,
                        "output": res.get("output", "")[:300] if res else "",
                    })
                generate_tool_summary_async(
                    tool_infos=tool_infos,
                    provider_call_fn=self._provider.call_sync if self._provider else None,
                    last_assistant_text=text or "",
                )

            # ── Step 11: Continue loop ────────────────────────────

        # Exceeded max rounds
        self._record_transition(MAX_TOOL_ROUNDS, TransitionType.MAX_ROUNDS,
                                f"exceeded {MAX_TOOL_ROUNDS} rounds")
        self.error.emit(
            f"Tool loop exceeded {MAX_TOOL_ROUNDS} rounds. Stopping to prevent infinite loops."
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _record_transition(self, round_num: int, ttype: TransitionType, detail: str):
        self._last_transitions.append({
            "round": round_num,
            "type": ttype.value,
            "detail": detail,
            "time": time.time(),
        })

    def _escalate_token_cap(self, current: int | None) -> int:
        """
        CC-aligned: single jump from capped default to escalated max.
        CC: context.ts — CAPPED_DEFAULT_MAX_TOKENS=8000, ESCALATED_MAX_TOKENS=64000.
        NOT progressive (no 16k/32k intermediate steps).
        """
        return self.ESCALATED_MAX_TOKENS

    # ── #11 CC-aligned: Cache Break Detection ────────────────────────

    def _update_tool_set_hash(self):
        """CC-aligned: hash full tool schemas (not just names) for cache break detection."""
        # CC: computes toolsHash from all tool schemas (descriptions + input_schemas)
        parts = []
        for t in sorted(self._tools, key=lambda x: x.name):
            parts.append(f"{t.name}|{t.description}|{_json.dumps(t.input_schema, sort_keys=True)}")
        h = hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]
        if self._tool_set_hash and h != self._tool_set_hash:
            # Tool set changed → cache is stale
            self._emit_analytics("cache_break", {"reason": "tool_set_change",
                                                   "old_hash": self._tool_set_hash, "new_hash": h})
        self._tool_set_hash = h

    # ── #66 BUDDY-original: Message fingerprint (lightweight change detection) ──

    def _compute_msg_fingerprint(self) -> str:
        """BUDDY-original lightweight fingerprint. NOTE: CC uses cache_read_tokens
        drop detection (promptCacheBreakDetection.ts), not message hashing."""
        n = len(self._conversation.messages)
        if n == 0:
            return ""
        # Hash: message count + last message role + last content prefix
        last = self._conversation.messages[-1]
        content = str(last.get("content", ""))[:200]
        raw = f"{n}|{last.get('role', '')}|{content}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    # ── #30 CC-aligned: Tool Result Disk Persistence ─────────────────

    TOOL_RESULT_PERSIST_THRESHOLD = 50_000  # CC: DEFAULT_MAX_RESULT_SIZE_CHARS=50000
    TOOL_RESULT_PREVIEW_SIZE = 2000         # CC: PREVIEW_SIZE_BYTES=2000

    def _persist_large_result(self, tool_name: str, output_str: str) -> str:
        """CC-aligned: persist large tool result to disk, return <persisted-output> reference."""
        try:
            self._tool_result_persist_dir.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256(output_str.encode()).hexdigest()[:16]
            filename = f"{tool_name}_{h}.txt"
            filepath = self._tool_result_persist_dir / filename
            filepath.write_text(output_str, encoding="utf-8")
            # CC: <persisted-output> tag with preview
            preview = output_str[:self.TOOL_RESULT_PREVIEW_SIZE]
            return (
                f"<persisted-output>\n"
                f"file_path: {filepath}\n"
                f"total_chars: {len(output_str)}\n"
                f"preview:\n{preview}\n"
                f"</persisted-output>"
            )
        except Exception:
            return output_str  # fallback: return original

    # ── #51 CC-aligned: Cost Persistence ─────────────────────────────

    def persist_cost(self):
        """Serialize session cost to settings.local.json for cross-session tracking."""
        try:
            from config import DATA_DIR
            path = DATA_DIR / "settings.local.json"
            data = {}
            if path.exists():
                try:
                    data = _json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data["last_session_cost"] = {
                "input_tokens": self._session_cost.total_input_tokens,
                "output_tokens": self._session_cost.total_output_tokens,
                "api_calls": self._session_cost.total_api_calls,
                "tool_calls": self._session_cost.total_tool_calls,
                "cache_read_tokens": self._session_cost.cache_read_tokens,
                "cache_creation_tokens": self._session_cost.cache_creation_tokens,
                "cost_usd": self._session_cost.cost_usd,
                "timestamp": time.time(),
            }
            # Accumulate total cost
            prev = data.get("total_cost_usd", 0.0)
            data["total_cost_usd"] = prev + self._session_cost.cost_usd
            path.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass  # best-effort

    # ── #53 CC-aligned: Session Lineage ──────────────────────────────

    def _propagate_session_lineage(self, sub_agent_engine) -> None:
        """Propagate parent session ID to sub-agent for lineage tracking."""
        session_id = self._conversation._conversation_id if self._conversation else None
        if session_id:
            sub_agent_engine._parent_session_id = session_id

    # ── #58 BUDDY-original: MEMORY.md index management ────────────────

    def update_memory_index(self) -> str | None:
        """
        CC-aligned: manage MEMORY.md index file.
        Scans project for CLAUDE.md-type files and maintains an index.
        Returns updated index content, or None.
        """
        try:
            import os
            project_dir = os.getcwd()
            memory_files = []
            for root, dirs, files in os.walk(project_dir):
                # Skip hidden dirs and common non-project dirs
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', '.git', 'venv')]
                for f in files:
                    if f in ("CLAUDE.md", "MEMORY.md", ".claude-buddy-memory"):
                        memory_files.append(os.path.relpath(os.path.join(root, f), project_dir))

            if not memory_files:
                return None

            index = "# Memory Index\n\n"
            for mf in sorted(memory_files):
                index += f"- `{mf}`\n"

            # Write index to .claude-buddy/memory_index.md
            from config import DATA_DIR
            index_path = DATA_DIR / "memory_index.md"
            index_path.write_text(index, encoding="utf-8")
            return index
        except Exception:
            return None

    # ── #64 BUDDY-original: Parallel tool result dedup ─────────────

    def _dedup_parallel_results(self, results: list[dict]) -> list[dict]:
        """
        BUDDY-original: deduplicate identical tool results in parallel calls.
        NOTE: CC does NOT do this — this is a BUDDY optimization.
        """
        seen: dict[str, int] = {}
        for i, r in enumerate(results):
            output = r.get("output", "")
            if len(output) > 500:  # only dedup large outputs
                h = hashlib.md5(output.encode()).hexdigest()
                if h in seen:
                    first_idx = seen[h]
                    results[i] = {
                        "output": f"[Same as tool result #{first_idx + 1} — deduplicated]",
                        "is_error": r.get("is_error", False),
                    }
                else:
                    seen[h] = i
        return results

    # ── #67 CC-aligned: Cached Microcompact Detection ────────────────

    def _should_skip_compact(self) -> bool:
        """
        CC-aligned: skip compaction if message count hasn't changed since last compact.
        Prevents redundant compaction cycles.
        """
        current = len(self._conversation.messages)
        if current == self._last_compact_msg_count:
            return True
        return False

    # ── Tool Execution Helpers ─────────────────────────────────────

    def _execute_one_tool(self, tc: ToolCall, round_num: int) -> dict:
        """Execute a single tool call with permission/plan checks. Returns result dict."""
        # Abort check
        if self._abort_signal.aborted:
            return {"output": "Operation cancelled by user.", "is_error": True}

        self.tool_start.emit(tc.name, tc.input)
        time.sleep(0.05)
        self._session_cost.add_tool_call()

        # CC-aligned: fire pre_tool_use hook (can block)
        if self._hook_registry:
            hook_results = self._hook_registry.fire("pre_tool_use", {
                "tool": tc.name, "input": tc.input, "round": round_num,
            })
            for hr in hook_results:
                if hr.block:
                    self.tool_result.emit(tc.name, f"Blocked by hook: {hr.output}")
                    return {"output": f"Blocked by pre_tool_use hook: {hr.output}", "is_error": True}

        # Plan mode check
        if self._plan_mode_state and self._plan_mode_state.active:
            if not self._tool_read_only.get(tc.name, False):
                if tc.name not in ("EnterPlanMode", "ExitPlanMode"):
                    self.tool_result.emit(tc.name, "Blocked by plan mode")
                    return {
                        "output": (
                            f"Plan mode is active. {tc.name} is blocked because it is not read-only. "
                            "Use ExitPlanMode first to restore full tool access, "
                            "or use read-only tools (FileRead, Glob, Grep, etc.) to investigate."
                        ),
                        "is_error": True,
                    }

        # Permission check
        if not self._tool_read_only.get(tc.name, False):
            if self._permission_callback:
                try:
                    perm_result = self._permission_callback(tc.name, tc.input)
                except Exception:
                    perm_result = False
                if isinstance(perm_result, dict):
                    approved = perm_result.get("approved", False)
                    action = perm_result.get("action", "deny")
                else:
                    approved = bool(perm_result)
                    action = "allow" if approved else "deny"

                if not approved:
                    self._denied_tools.append({
                        "tool": tc.name, "action": action, "round": round_num,
                    })
                    self.tool_result.emit(tc.name, "Permission denied")
                    return {
                        "output": (
                            f"User denied permission for {tc.name} (action={action}). "
                            "You cannot run this tool without user approval. "
                            "Try an alternative approach or use AskUser to explain why you need it."
                        ),
                        "is_error": True,
                    }

        # Find executor
        executor = self._tool_executors.get(tc.name)
        if not executor:
            available = ", ".join(sorted(self._tool_executors.keys()))
            return {"output": f"Unknown tool: {tc.name}. Available tools: {available}", "is_error": True}

        # ── AskUser special handling: block engine thread, wait for UI answer ──
        if tc.name == "AskUser":
            question = tc.input.get("question", "").strip()
            options = tc.input.get("options") or []  # ensure list, never None
            multi_select = bool(tc.input.get("multiSelect", False))
            if not question:
                return {"output": "Error: 'question' must be a non-empty string.", "is_error": True}

            # Emit signal → main thread shows dialog
            self._ask_user_event.clear()
            self._ask_user_answer = ""
            # Must use list() to ensure a real list (not None) for pyqtSignal(list)
            self.ask_user.emit(question, list(options), multi_select)

            # Block until user responds (5 min timeout)
            answered = self._ask_user_event.wait(timeout=300)
            if self._abort_signal.aborted:
                return {"output": "Operation cancelled by user.", "is_error": True}
            if not answered:
                output_str = "[User did not respond within 5 minutes]"
            else:
                output_str = self._ask_user_answer or "[No answer provided]"
            self.tool_result.emit(tc.name, output_str[:300])
            return {"output": output_str}

        # Execute
        try:
            output = executor(tc.input)
            output_str = str(output) if output is not None else ""

            # #30 CC-aligned: persist large results to disk
            if len(output_str) > self.TOOL_RESULT_PERSIST_THRESHOLD:
                persisted_ref = self._persist_large_result(tc.name, output_str)
                # Still truncate for message context, but note the disk path
                head_size = self.MAX_TOOL_RESULT_CHARS * 2 // 3
                tail_size = self.MAX_TOOL_RESULT_CHARS // 3
                truncated = len(output_str) - head_size - tail_size
                output_str = (
                    output_str[:head_size]
                    + f"\n\n... [{truncated:,} chars truncated, full result: {persisted_ref}] ...\n\n"
                    + output_str[-tail_size:]
                )
            elif len(output_str) > self.MAX_TOOL_RESULT_CHARS:
                head_size = self.MAX_TOOL_RESULT_CHARS * 2 // 3
                tail_size = self.MAX_TOOL_RESULT_CHARS // 3
                truncated = len(output_str) - head_size - tail_size
                output_str = (
                    output_str[:head_size]
                    + f"\n\n... [{truncated:,} chars truncated] ...\n\n"
                    + output_str[-tail_size:]
                )
            self.tool_result.emit(tc.name, output_str[:300])
            # CC-aligned: fire post_tool_use hook (non-blocking)
            if self._hook_registry:
                self._hook_registry.fire_async("post_tool_use", {
                    "tool": tc.name, "input": tc.input, "output": output_str[:500],
                })
            return {"output": output_str}
        except Exception as e:
            error_msg = f"Error executing {tc.name}: {e}"
            self.tool_result.emit(tc.name, error_msg[:300])
            # CC-aligned: fire on_error hook
            if self._hook_registry:
                self._hook_registry.fire_async("on_error", {
                    "tool": tc.name, "error": str(e),
                })
            return {"output": error_msg, "is_error": True}

    def _execute_tools_sequential(self, tool_calls: list, round_num: int) -> tuple[list, list]:
        """Execute tool calls one by one."""
        results = []
        names = []
        for tc in tool_calls:
            names.append(tc.name)
            results.append(self._execute_one_tool(tc, round_num))
        return results, names

    def _execute_tools_parallel(self, tool_calls: list, round_num: int) -> tuple[list, list]:
        """
        CC-aligned: partition tool calls by concurrency safety, then execute.
        CC: toolOrchestration.ts — consecutive safe tools → one parallel batch;
        unsafe tool → alone in sequential batch. This prevents unsafe tools
        (FileWrite, Bash with mutations) from racing.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        names = [tc.name for tc in tool_calls]

        # Emit tool_start for all tools
        for tc in tool_calls:
            self.tool_start.emit(tc.name, tc.input)
        time.sleep(0.05)

        # CC: partition into batches — consecutive safe → parallel, unsafe → alone
        batches: list[list[tuple[int, Any]]] = []  # list of [(original_idx, tc)]
        current_batch: list[tuple[int, Any]] = []
        current_batch_safe = True

        for i, tc in enumerate(tool_calls):
            is_safe = self._tool_concurrency_safe.get(tc.name, False)
            if is_safe and current_batch_safe:
                current_batch.append((i, tc))
            else:
                if current_batch:
                    batches.append(current_batch)
                if is_safe:
                    current_batch = [(i, tc)]
                    current_batch_safe = True
                else:
                    # Unsafe tool: alone in its own batch
                    batches.append([(i, tc)])
                    current_batch = []
                    current_batch_safe = True
        if current_batch:
            batches.append(current_batch)

        # Execute batches: parallel for safe, sequential for unsafe (single-item)
        results = [None] * len(tool_calls)
        for batch in batches:
            if len(batch) == 1:
                idx, tc = batch[0]
                results[idx] = self._execute_one_tool(tc, round_num)
            else:
                # Parallel batch (all concurrency-safe)
                with ThreadPoolExecutor(max_workers=min(10, len(batch))) as pool:
                    future_to_idx = {}
                    for idx, tc in batch:
                        future = pool.submit(self._execute_one_tool, tc, round_num)
                        future_to_idx[future] = idx
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            results[idx] = future.result()
                        except Exception as e:
                            results[idx] = {"output": f"Error: {e}", "is_error": True}

        # BUDDY-original: deduplicate identical parallel results
        results = self._dedup_parallel_results(results)

        return results, names

    def clear_conversation(self):
        self._conversation.clear()
        invalidate_cache()

    def save_conversation(self):
        self._conversation.save()

    def load_conversation(self, conversation_id: str):
        self._conversation.load(conversation_id)

    def get_cost_summary(self) -> str:
        return self._session_cost.summary()

    def set_plan_mode_state(self, state):
        """Inject PlanModeState from ToolRegistry."""
        self._plan_mode_state = state
        if state is not None:
            state.on_change(lambda active: self.plan_mode_changed.emit(active))

    def verify_api_key(self) -> tuple[bool, str]:
        """
        CC-aligned: verify API key with a minimal request.
        CC: verifyApiKey() in claude.ts does temperature=1 test.
        Returns (success: bool, message: str).
        """
        if not self._provider:
            return False, "No provider configured."
        try:
            params = LLMCallParams(temperature=1.0)
            self._provider.call_sync(
                messages=[{"role": "user", "content": "Hi"}],
                system="Respond with OK.",
                tools=[],
                max_tokens=10,
                params=params,
            )
            return True, "API key is valid."
        except Exception as e:
            cat = categorize_error(e)
            if cat == ErrorCategory.AUTH_ERROR:
                return False, f"Invalid API key: {self._short_error(e)}"
            elif cat == ErrorCategory.RATE_LIMIT:
                return True, "API key valid (rate limited)."
            else:
                return False, f"API error: {self._short_error(e)}"

    def _try_auto_extract(self):
        """
        Attempt auto memory extraction after a completed turn.
        Runs in a background thread to avoid blocking the response.
        """
        if not self._memory_mgr:
            return
        if not self._memory_mgr.should_extract():
            return

        # Run extraction in background thread
        def _extract():
            try:
                recent = self._conversation.messages[-10:]
                provider_fn = None
                if self._provider:
                    provider_fn = self._provider.call_sync
                memories = self._memory_mgr.auto_extract(
                    recent_messages=recent,
                    provider_call_fn=provider_fn,
                )
                # If memories were found, update the in-memory content
                if memories and self._memory_mgr:
                    import os
                    updated = self._memory_mgr.load_memory(project_path=os.getcwd())
                    if updated:
                        self._memory_content = updated
            except Exception:
                pass  # extraction is best-effort

        t = threading.Thread(target=_extract, daemon=True)
        t.start()

    def _try_self_reflect(self):
        """
        Attempt self-reflection after a completed turn.
        Runs in a background thread to avoid blocking the response.
        Triggers every REFLECT_INTERVAL turns (default: 5).
        """
        if not self._evolution_mgr:
            return
        if not self._evolution_mgr.should_reflect():
            return

        def _reflect():
            try:
                recent = self._conversation.messages[-10:]
                provider_fn = None
                if self._provider:
                    provider_fn = self._provider.call_sync
                self._evolution_mgr.reflect(
                    recent_messages=recent,
                    provider_call_fn=provider_fn,
                )
            except Exception:
                pass  # reflection is best-effort

        t = threading.Thread(target=_reflect, daemon=True)
        t.start()

    # ── Sub-Agent Execution (for AgentTool) ───────────────────────

    def run_sub_agent(self, system_prompt: str, user_prompt: str,
                      agent_id: str = "", team: str = "",
                      model_override: str | None = None) -> str:
        """
        Run a sub-agent in an isolated conversation context.
        Called by AgentTool.execute() — runs synchronously in the caller's thread.

        CC-aligned sub-agent architecture:
          - Shares the same provider
          - Gets a FRESH message history (not forked from parent)
          - Has access to all tools (with own permission checks)
          - Limited to 15 rounds (half of main agent)
          - Inherits team memory from parent
          - Parent context forked as last-20 messages (CC: filterMessagesForContext)
          - Returns the final text response
        """
        if not self._provider:
            return "Error: No provider configured."

        SUB_AGENT_MAX_ROUNDS = 15
        sub_tools = self._provider.format_tools(self._tools) if self._tools else []

        # CC-aligned: model override — use a different model for sub-agent
        sub_provider = self._provider
        sub_model = self._provider_model
        if model_override:
            # Map short names to full model names
            _MODEL_MAP = {
                "sonnet": "claude-sonnet-4-20250514",
                "opus": "claude-opus-4-20250514",
                "haiku": "claude-3-5-haiku-20241022",
            }
            full_model = _MODEL_MAP.get(model_override, model_override)
            # Try to create a provider with the overridden model
            try:
                if hasattr(self, '_provider_factory_with_model'):
                    sub_provider = self._provider_factory_with_model(full_model)
                    sub_model = full_model
                elif hasattr(sub_provider, '_model'):
                    # Shallow override: just change model name on same provider
                    import copy
                    sub_provider = copy.copy(self._provider)
                    sub_provider._model = full_model
                    sub_model = full_model
            except Exception:
                pass  # fallback to main provider

        # #53 CC-aligned: propagate session lineage to sub-agent context
        lineage_info = ""
        parent_sid = self._conversation._conversation_id if self._conversation else None
        if parent_sid:
            lineage_info = f"\n\n[Session lineage: parent={parent_sid}]"

        # Inject team memory context into the sub-agent's system prompt
        enhanced_system = system_prompt
        if self._team_memory:
            mem_context = self._team_memory.get_context_for_agent(
                agent_id=agent_id, team=team,
            )
            if mem_context:
                enhanced_system += f"\n\n{mem_context}"

        # CC-aligned: fork parent context (last 20 messages) for sub-agent awareness
        # This gives the sub-agent awareness of what the parent was working on
        parent_context = ""
        parent_msgs = self._conversation.messages[-20:]
        if parent_msgs:
            context_parts = []
            for m in parent_msgs:
                role = m.get("role", "")
                content = m.get("content", "")
                if isinstance(content, str) and content.strip():
                    context_parts.append(f"[{role}]: {content[:200]}")
            if context_parts:
                parent_context = (
                    "\n\n## Parent conversation context (for awareness):\n"
                    + "\n".join(context_parts[-10:])  # last 10 for brevity
                )
                enhanced_system += parent_context

        # #53 CC-aligned: add lineage info
        if lineage_info:
            enhanced_system += lineage_info

        messages: list[dict] = [{"role": "user", "content": user_prompt}]

        for round_num in range(SUB_AGENT_MAX_ROUNDS):
            if self._abort_signal.aborted:
                return "(Sub-agent aborted by user)"

            try:
                raw_content, tool_calls, text = sub_provider.call_sync(
                    messages=messages,
                    system=enhanced_system,
                    tools=sub_tools,
                )
            except Exception as e:
                return f"Sub-agent API error: {self._short_error(e)}"

            # Track cost
            est_input = sum(len(str(m.get("content", ""))) // 3 for m in messages)
            est_output = len(str(text or "")) // 3
            self._session_cost.add_call(
                sub_model or "unknown",
                input_tokens=est_input,
                output_tokens=est_output,
            )

            # Add assistant response
            if isinstance(raw_content, dict) and "role" in raw_content:
                messages.append(raw_content)
            else:
                messages.append({"role": "assistant", "content": raw_content})

            # No tool calls → return text
            if not tool_calls:
                # Merge sub-agent memories back to parent
                if self._team_memory and agent_id:
                    self._team_memory.merge_from_agent(agent_id)
                return text or "(sub-agent returned empty)"

            # Execute tools
            results = []
            for tc in tool_calls:
                self._session_cost.add_tool_call()
                executor = self._tool_executors.get(tc.name)
                if not executor:
                    results.append({"output": f"Unknown tool: {tc.name}", "is_error": True})
                    continue

                # Permission check (sub-agent still needs permission)
                if not self._tool_read_only.get(tc.name, False):
                    if self._permission_callback:
                        try:
                            approved = self._permission_callback(tc.name, tc.input)
                        except Exception:
                            approved = False
                        if not approved:
                            results.append({"output": "Permission denied.", "is_error": True})
                            continue

                try:
                    output = executor(tc.input)
                    output_str = str(output) if output is not None else ""
                    if len(output_str) > 8000:
                        output_str = output_str[:5000] + "\n...[truncated]...\n" + output_str[-2000:]
                    results.append({"output": output_str})
                except Exception as e:
                    results.append({"output": f"Error: {e}", "is_error": True})

            # Add tool results to sub-conversation
            tool_result_msg = self._provider.format_tool_results(tool_calls, results)
            if isinstance(tool_result_msg, dict) and "_multi_messages" in tool_result_msg:
                messages.extend(tool_result_msg["_multi_messages"])
            else:
                messages.append(tool_result_msg)

        return "(Sub-agent exceeded max rounds)"

    # ── Background Task Support (CC-aligned: TaskOutput with buffering) ─

    # Max memory for background task output buffering (CC: 8MB default)
    _BG_TASK_MAX_BUFFER = 8 * 1024 * 1024  # 8MB

    def start_background_task(self, executor: Callable, input_data: dict) -> str:
        """
        Start a tool execution in the background.
        Returns a task_id that can be used to check status later.

        CC-aligned: TaskOutput pattern with memory buffering.
        """
        task_id = str(self._next_task_id)
        self._next_task_id += 1

        task_record = {
            "status": "running",
            "output": None,
            "thread": None,
            "buffer": [],       # CC-aligned: circular buffer for recent lines
            "total_bytes": 0,   # CC-aligned: track output size
        }
        self._background_tasks[task_id] = task_record

        def _run():
            try:
                output = executor(input_data)
                output_str = str(output) if output is not None else ""
                # CC-aligned: cap buffer at 8MB, keep tail if exceeded
                if len(output_str) > self._BG_TASK_MAX_BUFFER:
                    output_str = (
                        f"[Output truncated: {len(output_str):,} bytes, showing last "
                        f"{self._BG_TASK_MAX_BUFFER // 1024}KB]\n"
                        + output_str[-self._BG_TASK_MAX_BUFFER:]
                    )
                task_record["output"] = output_str
                task_record["total_bytes"] = len(output_str)
                task_record["status"] = "completed"
            except Exception as e:
                task_record["output"] = f"Error: {e}"
                task_record["status"] = "error"

        t = threading.Thread(target=_run, daemon=True)
        task_record["thread"] = t
        t.start()
        return task_id

    def get_background_task(self, task_id: str) -> dict | None:
        """Get status and output of a background task."""
        return self._background_tasks.get(task_id)
