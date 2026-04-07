<p align="center">
  <img src="assets/sprites/characters/cute_girl/idle_0.png" width="96" />
</p>

<h1 align="center">Claude Buddy</h1>

<p align="center">
  <b>Your Desktop AI Pet — Claude Code's brain in a pixel body</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/UI-PyQt6-41CD52?logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/LLM-Claude%20%7C%20GPT%20%7C%20Any-orange" />
  <img src="https://img.shields.io/badge/tools-37-blueviolet" />
  <img src="https://img.shields.io/badge/lines-38K+-lightgrey" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
</p>

---

A tiny animated character that lives on your desktop, backed by the full power of a Claude Code-grade AI engine. **Think of it as Claude Code, but instead of a terminal — it's a little buddy on your screen who reads files, writes code, runs shell commands, browses the web, manages tasks, and chats with you through a slick glass-morphism UI.**

> **tl;dr** — It's a desktop pet that can `grep` your codebase, edit your files, run your tests, and remember your preferences. Yes, really.

<p align="center">
  <img src="assets/sprites/characters/cute_girl/idle_0.png" width="48" />
  <img src="assets/sprites/characters/cute_girl/idle_1.png" width="48" />
  <img src="assets/sprites/characters/cute_girl/idle_2.png" width="48" />
  <img src="assets/sprites/characters/cute_girl/idle_3.png" width="48" />
  &nbsp;&nbsp;
  <img src="assets/sprites/characters/cute_girl/celebrate_0.png" width="48" />
  <img src="assets/sprites/characters/cute_girl/celebrate_1.png" width="48" />
  <img src="assets/sprites/characters/cute_girl/celebrate_2.png" width="48" />
  <img src="assets/sprites/characters/cute_girl/celebrate_3.png" width="48" />
</p>

---

## Features

### The Engine (Claude Code-aligned)

| Feature | Description |
|---------|-------------|
| **Tool Loop** | 25-round tool execution loop with streaming, abort, retry |
| **37 Tools** | File R/W/Edit, Bash, Glob, Grep, Web Search/Fetch, Agent, MCP, LSP, Cron, Tasks... |
| **3 Providers** | Anthropic (native tool_use), OpenAI (function calling), PromptTool (any model via XML) |
| **8-Layer Compaction** | Microcompact → Snip → Tool-compress → Group → Memory-preserve → Mechanical → LLM → Reactive |
| **Smart Retry** | Exponential backoff, 529/429 separation, context-too-long recovery, max-output escalation |
| **Memory System** | 4-category taxonomy (user/feedback/project/reference), semantic files, auto-extraction |
| **Sub-Agents** | Spawn child agents, team management, inter-agent messaging |
| **Cron & Dreams** | Scheduled tasks, proactive "dream" background tasks |
| **Plan Mode** | Read-only exploration mode — investigate before modifying |

### The Pet

| Feature | Description |
|---------|-------------|
| **Animated Sprite** | Idle, working, celebrating, sleeping states with smooth transitions |
| **Glass Chat UI** | Translucent glass-morphism chat window with streaming markdown |
| **Inline AskUser** | Interactive option chips right in the chat flow — no popups |
| **Draggable** | Lives anywhere on your desktop, remembers position |
| **50+ Slash Commands** | `/init`, `/diff`, `/review`, `/memory`, `/plan`, `/cost`, `/rewind`... |
| **Permission System** | Tool approval dialog — you control what Buddy can do |

---

## Quick Start

```bash
# Clone
git clone https://github.com/AchoWu/claude-buddy.git
cd claude-buddy

# Install dependencies
pip install -r requirements.txt

# Set your API key (pick one)
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export OPENAI_API_KEY="sk-..."

# Run
python main.py
```

Buddy appears on your desktop. Click on it to open the chat. That's it.

---

## Architecture

```
main.py                    # Entry point — wires everything together
├── core/
│   ├── engine.py          # LLM engine (55KB) — tool loop, streaming, retry
│   ├── conversation.py    # 8-layer compaction pipeline
│   ├── commands.py        # 50+ slash commands
│   ├── memory.py          # 4-category memory system
│   ├── providers/         # Anthropic, OpenAI, PromptTool
│   ├── task_manager.py    # CC V2 task system (dependencies, metadata)
│   ├── cron/              # Cron scheduler
│   ├── bridge/            # IDE bridge (VS Code / JetBrains)
│   └── services/          # MCP, LSP, analytics, hooks, plugins...
├── tools/                 # 37 tools, one file each
├── ui/
│   ├── chat_dialog.py     # Glass-morphism chat with streaming bubbles
│   ├── pet_window.py      # Animated desktop sprite
│   ├── permission_dialog.py
│   └── ...
├── prompts/               # System prompt builder, compaction templates
├── assets/sprites/        # Character animations
└── tests/                 # Unit + capability tests
```

### How a Message Flows

```
You type "fix the bug in auth.py"
  → main.py receives signal
    → engine.send_message() [background thread]
      → system prompt assembled (20 sections)
      → provider.call_stream() [Anthropic/OpenAI/PromptTool]
        → model streams back: "I'll read the file first"
          → [tool_use: FileRead auth.py]
            → permission check → execute → result
          → [tool_use: FileEdit auth.py]
            → permission check → execute → result
        → "I've fixed the bug. The issue was..."
      → response_text signal → UI updates
    → auto-extract memories in background
    → compact_if_needed() if context is getting full
```

---

## Tools (37)

<details>
<summary><b>Click to expand full tool list</b></summary>

| Category | Tools |
|----------|-------|
| **File System** | `FileRead`, `FileWrite`, `FileEdit`, `Glob`, `NotebookEdit` |
| **Code** | `Bash`, `Grep`, `TerminalCapture`, `LSP` |
| **Search** | `WebSearch` (DuckDuckGo), `WebFetch` (URL→markdown), `WebBrowser` |
| **AI Agents** | `Agent` (sub-agent), `SendMessage`, `TeamCreate`, `TeamDelete` |
| **Tasks** | `TaskCreate`, `TaskUpdate`, `TaskList`, `TaskGet`, `TaskOutput`, `TaskStop` |
| **Scheduling** | `CronCreate`, `CronDelete`, `CronList` |
| **Planning** | `EnterPlanMode`, `ExitPlanMode`, `AskUser` |
| **Memory** | `SelfReflect`, `SelfModify`, `DiaryWrite` |
| **MCP** | `MCPTool`, `ListMcpResources`, `ReadMcpResource` |
| **Other** | `Skill`, `Workflow`, `Monitor`, `PushNotification`, `Worktree`, `CtxInspect`, `SnipTool`, `SendUserFile`, `SubscribePR` |

</details>

---

## Slash Commands (50+)

<details>
<summary><b>Click to expand</b></summary>

| Command | What it does |
|---------|-------------|
| `/init` | Analyze codebase, generate CLAUDE.md |
| `/diff` | Show all file changes this session |
| `/review` | AI code review of recent changes |
| `/plan` | Toggle plan mode (read-only investigation) |
| `/memory` | View/edit/search memories |
| `/compact` | Force conversation compaction |
| `/cost` | Show token usage & cost |
| `/rewind` | Undo last N conversation turns |
| `/context` | Inspect current context (tokens, files, tools) |
| `/session` | Session management (list, switch, archive) |
| `/model` | Switch model mid-conversation |
| `/effort` | Set thinking effort level |
| `/tasks` | Show background tasks |
| `/cron-create` | Schedule recurring tasks |
| `/debug` | Debug info dump |
| `/transitions` | Show engine state transitions |
| ... | and ~35 more |

</details>

---

## Memory System

Buddy remembers things about you across sessions:

```
~/.claude-buddy/memory/
├── MEMORY.md                          # Index: [Title](file) — hook
├── user_prefers_chinese_aba3.md       # "User prefers Chinese responses"
├── project_uses_pyqt6_signals_f1e2.md # "Project uses pyqtSignal for cross-thread"
└── feedback_always_check_cc_d4a1.md   # "Always check CC source for alignment"
```

Four categories (aligned with Claude Code's `memoryTypes.ts`):
- **user** — personal preferences, language, style
- **feedback** — corrections, "don't do X", "always do Y"
- **project** — tech stack, patterns, conventions
- **reference** — facts, links, documentation

Memories are auto-extracted from conversations and manually editable via `/memory`.

---

## Configuration

Buddy reads `CLAUDE.md` files (just like Claude Code):

```
Project root/CLAUDE.md     → project instructions
Parent dirs/CLAUDE.md      → inherited context
~/.claude-buddy/CLAUDE.md  → global user instructions
```

Supports `@include path/to/file.md` directives with circular reference prevention.

---

## Provider Support

| Provider | How it works |
|----------|-------------|
| **Anthropic** | Native `tool_use` blocks, adaptive thinking, `cache_control`, effort levels |
| **OpenAI** | `function` calling format, streaming `tool_calls` accumulation |
| **PromptTool** | For any model — injects tool descriptions into system prompt, parses `<tool_call>` XML from output |

Set your API key in Settings (click the ⚙ gear icon) or via environment variable.

---

## How It Compares to Claude Code

Claude Buddy is architecturally aligned with Claude Code's source:

| Aspect | Claude Code | Claude Buddy |
|--------|------------|-------------|
| Runtime | Bun + React/Ink (terminal) | Python + PyQt6 (desktop GUI) |
| Engine | QueryEngine.ts (46KB) | engine.py (55KB) |
| Tools | ~40 tools | 37 tools |
| Compaction | 11-variant system | 8-layer pipeline |
| Memory | 4-category + MEMORY.md | Same (v4 aligned) |
| Task System | V2 (owner, blocks/blockedBy) | Same (V2 aligned) |
| Providers | Anthropic only | Anthropic + OpenAI + any (PromptTool) |
| UI | Terminal (React/Ink) | Desktop pet + glass chat |
| Personality | Professional CLI | Animated pixel buddy |

---

## Development

```bash
# Run tests
python run_all_tests.py

# Run specific test suite
python tests/test_s1_engine.py       # Engine core
python tests/test_s2_compaction.py   # Compaction pipeline
python tests/test_s4_tools.py        # Tool system
python tests/test_s5_commands.py     # Commands
python tests/test_cap_engine.py      # CC-alignment tests
```

### Project Stats

- **148 Python files**
- **~38,000 lines of code**
- **37 tools**, **50+ commands**
- **8-layer compaction pipeline**
- **3 LLM providers**

---

## Contributing

> **This project is a work in progress!** Some features are still rough around the edges — bugs, incomplete implementations, and quirky edge cases are expected. Contributions are very welcome!

### Known Issues & Areas for Improvement

- **Some tools are stubs** — tools like `WebBrowser`, `Workflow`, `Monitor`, `SubscribePR` have definitions but may not be fully functional yet
- **Streaming edge cases** — the streaming + abort + rollback flow has been extensively debugged but corner cases may still exist
- **Compaction robustness** — the 8-layer pipeline works but hasn't been stress-tested with extremely long conversations
- **Provider compatibility** — Anthropic provider is the most polished; OpenAI and PromptTool providers may have format edge cases
- **UI polish** — glass-morphism rendering, scrollbar behavior, and high-DPI scaling could use more love
- **Cross-platform** — primarily developed on Windows; macOS/Linux may need tweaks (especially the tray icon and sprite rendering)
- **Test coverage** — test files exist but many are capability tests rather than unit tests; more coverage is needed

### How to Contribute

1. **Fork** the repo
2. **Pick an issue** or find something that bugs you
3. **Fix it** and open a PR
4. Or just **open an issue** describing what went wrong — that helps too!

Whether it's a one-line typo fix, a new tool implementation, a UI improvement, or a bug report — all contributions are appreciated.

---

## License

MIT

---

<p align="center">
  <img src="assets/sprites/characters/cute_girl/celebrate_0.png" width="64" />
  <br/>
  <i>Built with love, aligned with Claude Code, powered by vibes.</i>
</p>
