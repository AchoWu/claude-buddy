# CLAUDE.md

This file provides guidance to Claude Code when working with the BUDDY codebase.

## What This Is

**BUDDY** is a desktop AI pet application built with Python/PyQt6. It runs as a small animated character on the user's desktop, providing a chat interface to interact with Claude and other LLMs. The core engine is aligned with Anthropic's Claude Code CLI architecture (streaming, tool loops, retry logic, compaction).

## Scale

~150 Python files across 6 directories, ~28,000+ lines of code.

## Tech Stack

- **Language**: Python 3.11+
- **Desktop UI**: PyQt6 (frameless windows, translucent glass-morphism design)
- **API Clients**: Anthropic SDK (`anthropic`), OpenAI SDK (`openai`), Venus SDK (`venus_api_base`)
- **HTTP**: httpx (async-capable)
- **Image Processing**: Pillow (sprite sheets, avatar rendering)
- **HTML to Markdown**: html2text (WebFetch tool)
- **Token Counting**: tiktoken (cl100k_base), CJK-aware heuristic fallback

## Architecture Overview

### Entry Point

`main.py` -- `BuddyApp` class orchestrates everything:
1. Settings -> PetWindow -> LLMEngine -> ToolRegistry (53 tools) -> MemoryManager
2. Signal/slot wiring between engine (background thread) and UI (main thread)
3. Auto-save timer (30s), cron scheduler, dream manager
4. Screenshot overlay + Vision pipeline wiring
5. Qt event loop (`app.exec()`)

### Core Engine (`core/engine.py`, ~55KB)

`LLMEngine(QObject)` -- the heart of the system:
- Tool-call loop with MAX_TOOL_ROUNDS=25
- Streaming + sync fallback (CC-aligned: falls back on ANY mid-stream failure)
- Error classification (9 categories: rate_limit, overloaded, server_error, context_too_long, max_output_tokens, network, timeout, auth, invalid_request)
- Exponential backoff retry (500ms base, 10 max, +25% jitter; CC: withRetry.ts)
- 529 OVERLOADED separated from 429 RATE_LIMIT (CC: MAX_529_RETRIES=3)
- Context-too-long 2-stage recovery (collapse drain -> reactive compact)
- Max-output-tokens single-jump escalation (8k -> 64k; CC: ESCALATED_MAX_TOKENS=64000)
- Abort signal with conversation rollback (`_msg_count_at_query_start`)
- CC-aligned parallel tool execution with concurrency_safe batching
- Tool results >50KB get `<persisted-output>` tag with 2KB preview
- Auto memory extraction in background thread after each completed turn

### Provider System (`core/providers/`)

Three providers, all implementing `BaseProvider`:
- `AnthropicProvider` -- native tool_use, adaptive thinking, cache_control, effort, structured output, image content blocks in tool_result
- `OpenAIProvider` -- function calling format, streaming with tool_calls accumulation, image_url conversion for Vision models
- `PromptToolProvider` -- for models without native tool support; injects tool descriptions into system prompt, parses `<tool_call>` tags from output, DeepSeek-R1 reasoning_content handling

### Tool System (`tools/`, 53 tools)

Each tool in its own file inheriting `BaseTool`:
- **File ops**: FileRead, FileWrite, FileEdit, Glob, NotebookEdit
- **Code execution**: Bash, TerminalCapture, LSP
- **Search**: WebSearch (DuckDuckGo), WebFetch (URL to markdown)
- **AI coordination**: Agent (sub-agent), SendMessage, TeamCreate/TeamDelete, AskUser
- **Task management**: TaskCreate/Update/List/Get (CC V2: owner, blocks/blockedBy, metadata, deleted), TaskOutput, TaskStop
- **Scheduling**: CronCreate/Delete/List
- **Plan mode**: EnterPlanMode, ExitPlanMode
- **Memory/Soul**: SelfReflect, SelfModify, DiaryWrite
- **Vision**: Screenshot (cross-thread capture), AnalyzeImage (Venus API gemini-3-flash)
- **Other**: Skill, MCP tools, Workflow, Monitor, PushNotification, Worktree, CtxInspect, SnipTool

Each tool defines: `name`, `description`, `input_schema`, `is_read_only`, `concurrency_safe`, `execute()`.

### Conversation & Compaction (`core/conversation.py`, ~30KB)

`ConversationManager` -- 8-layer compaction pipeline:
- L0: Microcompact (fold repeated FileRead stubs, truncate old tool results)
- L1: Snip (remove oldest 8 messages, preserve recent 12)
- L2: Tool-result compress (truncate old outputs to 500 chars head+tail)
- L3: Message grouping (keep assistant+tool pairs intact, no orphaned tool messages)
- L4: Memory preserve (extract preferences via regex before dropping messages)
- L5: Mechanical summary (regex-based `[CONTEXT COMPACTED]` with file/tool lists)
- L6: LLM summary (structured 9-section summary via provider call, NO_TOOLS_PREAMBLE)
- L7: Reactive (force compact on context_too_long, feature-flag gated)
- Adaptive threshold: 8+ msgs in 2min -> offset -5 (compact sooner)
- CJK-aware token estimation: Chinese 1.5 chars/token, English 4 chars/token

### Memory System (`core/memory.py`)

CC-aligned v4 with four-category taxonomy (from CC's memoryTypes.ts):
- Categories: `user`, `feedback`, `project`, `reference`
- Storage: `~/.claude-buddy/memory/` -- MEMORY.md index + semantic topic files with frontmatter
- Frontmatter: `name`, `description`, `type` (CC mandatory fields)
- File naming: semantic snake_case (`user_prefers_chinese_aba3.md`) not hash-only
- MEMORY.md format: `- [Title](file.md) -- one-line hook` (<=200 lines, <=25KB)
- Auto-extraction: LLM-driven (4 categories) + regex fallback, every 3 turns / 60s cooldown
- Project-specific: `~/.claude-buddy/projects/<hash>/memory/`
- CLAUDE.md multi-level search: CWD -> parent dirs -> `~/.claude-buddy/CLAUDE.md`
- `@include` directive with circular reference prevention
- Legacy migration: v2 general.md -> v3 category_hash.md -> v4 semantic files (automatic)

### Command System (`core/commands.py`, ~50KB)

~50 slash commands registered in `CommandRegistry`:
- Core: /help, /clear, /exit, /version, /init
- Session: /context, /diff, /files, /cost, /session, /resume, /rewind
- Mode: /plan, /fast, /effort, /model
- Memory: /memory, /compact
- Tasks: /tasks (background tasks, NOT task list -- CC-aligned: task list is tools-only)
- Code: /review, /pr, /branch, /commit
- Diagnostics: /debug, /transitions, /flags
- Cron: /cron-create, /cron-list, /cron-delete
- Soul: /diary, /reflect, /evolve

### UI System (`ui/`, 11 files)

All PyQt6, frameless translucent windows:
- `PetWindow` -- animated sprite, drag, context menu, idle/working/celebrating states
- `ChatDialog` -- glass-morphism chat with streaming bubbles, tool call indicators, InterruptBubble (amber, centered), plan mode badge (blue), multi-image [Image #N] chips, file [filename] chips, drag & drop, forced repaint via unpolish/polish/processEvents
- `ScreenshotOverlay` -- full-screen region selection for Screenshot tool
- `SettingsDialog` -- API key, provider, model selection
- `PermissionDialog` -- tool permission prompts (allow/deny/always)
- `SpeechBubble` -- floating text near pet
- `TaskPanel` -- side panel task list
- `NotificationWidget` -- toast notifications

### Prompt System (`prompts/`)

- `system.py` (~30KB) -- 20-section system prompt builder (identity, rules, tool reference, safety, git workflow, etc.)
- `compact.py` -- compaction prompt templates (NO_TOOLS_PREAMBLE, 9-section structured summary)
- `templates.py` -- reusable prompt fragments

## Code Conventions

- **Tool pattern**: `class {Name}Tool(BaseTool)` in `tools/{name}_tool.py`
- **Command pattern**: `def _cmd_{name}(args, ctx)` registered via `R(name, description, handler)`
- **Signals**: Engine runs in background thread, communicates via `pyqtSignal` (thread-safe)
- **Provider pattern**: `class {Name}Provider(BaseProvider)` with `call_sync()`, `call_stream()`, `format_tools()`, `format_tool_results()`
- **Error handling**: Best-effort pattern -- extraction, memory save, self-reflection wrapped in try/except with silent failure
- **Qt stylesheet refresh**: After `setStyleSheet()` from signal slot, must call `unpolish/polish/repaint/processEvents` for immediate visual update

## Threading Model

- **Main thread**: Qt event loop, all UI rendering
- **Engine thread**: `threading.Thread(daemon=True)` for each `send_message()`
- **Cross-thread**: `pyqtSignal` for engine -> UI (response_text, tool_start, error, plan_mode_changed)
- **Abort**: `threading.Event`-based AbortSignal + 3s QTimer safety net (Python can't interrupt blocking `requests.post()` like JS AbortController)
- **Cancel flow**: rollback to `_msg_count_at_query_start` (both conversation and UI checkpoint), then insert `[Request interrupted by user]` as InterruptBubble

## Vision / Image Analysis

Auto-selects strategy based on model capability:

- **Vision-capable models** (Claude, GPT-4o): CC mode — images sent directly as content blocks in messages
- **Non-vision models** (DeepSeek, hy3): Fallback — agent calls `AnalyzeImage` tool → Venus API `gemini-3-flash`

Image input methods (all three insert `[Image #N]` or `[filename]` chips):
- Upload button (📎) — file picker for images and documents
- Ctrl+V — clipboard images or copied files from file manager
- Drag & drop — files/images onto chat dialog

File attachment (non-image): CC-aligned lazy load — stores path only, model uses `FileRead` tool on demand. Avoids bloating conversation context, enables prompt cache hits.

Key files: `core/vision.py` (capture + base64), `tools/analyze_image_tool.py`, `tools/screenshot_tool.py`, `ui/screenshot_overlay.py`

## Configuration (`config.py`)

- `DATA_DIR = ~/.claude-buddy/` -- all persistent data
- `CONVERSATIONS_DIR`, `TASKS_FILE`, `INPUT_HISTORY_FILE`
- UI constants: CLAUDE_ORANGE, CLAUDE_ORANGE_SHIMMER, BORDER_RADIUS
- `GLOBAL_QSS` -- application-wide Qt stylesheet with `#sendBtn`, `#closeBtn` etc.
- Vision config: `VISION_MODEL` (gemini-3-flash), `VISION_SECRET_ID/KEY`, `VISION_APP_GROUP_ID`
- `VISION_CAPABLE_MODELS` / `VISION_CAPABLE_PROVIDERS` -- auto-detect if model supports image blocks

## Key Files by Size/Importance

| File | Purpose |
|---|---|
| `main.py` (~25KB) | Entry point, BuddyApp controller, signal wiring |
| `core/engine.py` (~55KB) | LLM engine: tool loop, retry, streaming, abort |
| `core/conversation.py` (~30KB) | Conversation manager, 8-layer compaction |
| `core/commands.py` (~50KB) | ~50 slash commands |
| `prompts/system.py` (~30KB) | 20-section system prompt builder |
| `core/memory.py` (~15KB) | Memory system v4, 4-category taxonomy |
| `ui/chat_dialog.py` (~40KB) | Chat window, streaming, tool bubbles |
| `core/providers/anthropic_provider.py` | Anthropic API: thinking, effort, cache |
| `core/providers/openai_provider.py` | OpenAI API: function calling format |
| `core/providers/prompt_tool_provider.py` | PromptTool: system prompt injection, R1 reasoning handling |
| `core/vision.py` | Screen capture + base64 encoding for Vision |
| `core/tool_registry.py` | Tool registration, concurrency_safe marking |
| `core/task_manager.py` | Task CRUD with dependencies, high water mark IDs |

## Testing

```bash
# Run all tests
python run_all_tests.py

# Run specific suite
python tests/test_s1_engine.py       # Engine core
python tests/test_s2_compaction.py   # Compaction pipeline (14 tests)
python tests/test_s4_tools.py        # Tool system
python tests/test_s5_commands.py     # Commands
python tests/test_cap_engine.py      # CC-alignment capability tests

# Tests use QT_QPA_PLATFORM=offscreen for headless Qt
```

## Navigation Tips

- **To understand a tool**: `tools/{name}_tool.py` -- schema, permissions, execute() in one file
- **To understand a command**: Search `_cmd_{name}` in `core/commands.py`
- **To trace a message**: `main.py._on_user_message` -> `engine.send_message` -> `engine._tool_loop` -> `engine._call_with_retry` -> provider
- **To understand compaction**: `core/conversation.py` `compact_if_needed()` -> L0-L7 layers
- **To understand memory**: `core/memory.py` MemoryManager + `core/context_injection.py` CLAUDE.md search
- **Large files warning**: `engine.py` (~55KB), `commands.py` (~50KB), `chat_dialog.py` (~40KB) -- use targeted searches
