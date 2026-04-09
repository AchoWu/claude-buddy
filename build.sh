#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Claude Buddy — Build Script
# Packages BUDDY into a standalone executable using PyInstaller.
#
# Usage:
#   ./build.sh              # Directory mode (fast, for testing)
#   ./build.sh --onefile    # Single .exe (slow, for distribution)
#   ./build.sh --clean      # Clean artifacts before building
# ═══════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE="--onedir"
CLEAN=false

for arg in "$@"; do
    case "$arg" in
        --onefile) MODE="--onefile" ;;
        --clean)   CLEAN=true ;;
        --help|-h)
            echo "Usage: $0 [--onefile] [--clean]"
            echo "  --onefile   Package as single .exe (slower, for distribution)"
            echo "  --clean     Remove build/dist before building"
            exit 0
            ;;
    esac
done

# ── Clean ────────────────────────────────────────────────────
if $CLEAN; then
    echo "Cleaning build artifacts..."
    rm -rf build/ dist/ ClaudeBuddy.spec
fi

# ── Check PyInstaller ────────────────────────────────────────
if ! python -m PyInstaller --version >/dev/null 2>&1; then
    echo "Installing PyInstaller..."
    pip install pyinstaller
fi

echo "============================================================"
echo "Building ClaudeBuddy (${MODE#--})..."
echo "============================================================"

# ── Run PyInstaller ──────────────────────────────────────────
python -m PyInstaller \
    --name ClaudeBuddy \
    --windowed \
    --noconfirm \
    $MODE \
    --add-data "assets;assets" \
    --add-data "soul;soul" \
    --hidden-import PyQt6.QtCore \
    --hidden-import PyQt6.QtGui \
    --hidden-import PyQt6.QtWidgets \
    --hidden-import anthropic \
    --hidden-import openai \
    --hidden-import httpx \
    --hidden-import httpx._transports.default \
    --hidden-import httpcore \
    --hidden-import tiktoken \
    --hidden-import tiktoken_ext \
    --hidden-import tiktoken_ext.openai_public \
    --hidden-import html2text \
    --hidden-import PIL \
    --hidden-import PIL.Image \
    --hidden-import core \
    --hidden-import core.engine \
    --hidden-import core.conversation \
    --hidden-import core.commands \
    --hidden-import core.memory \
    --hidden-import core.settings \
    --hidden-import core.context_injection \
    --hidden-import core.normalization \
    --hidden-import core.token_estimation \
    --hidden-import core.evolution \
    --hidden-import core.dream \
    --hidden-import core.sandbox \
    --hidden-import core.watchdog \
    --hidden-import core.task_manager \
    --hidden-import core.task_budget \
    --hidden-import core.tool_pool \
    --hidden-import core.tool_registry \
    --hidden-import core.tool_summary \
    --hidden-import core.streaming_executor \
    --hidden-import core.providers \
    --hidden-import core.providers.base \
    --hidden-import core.providers.anthropic_provider \
    --hidden-import core.providers.openai_provider \
    --hidden-import core.providers.prompt_tool_provider \
    --hidden-import core.cron \
    --hidden-import core.cron.parser \
    --hidden-import core.cron.scheduler \
    --hidden-import core.bridge \
    --hidden-import core.bridge.server \
    --hidden-import core.bridge.handlers \
    --hidden-import core.bridge.protocol \
    --hidden-import core.bridge.auth \
    --hidden-import core.bridge.session_pointer \
    --hidden-import core.bridge.state_sync \
    --hidden-import core.services \
    --hidden-import core.services.hooks \
    --hidden-import core.services.plugins \
    --hidden-import core.services.mcp \
    --hidden-import core.services.mcp_approval \
    --hidden-import core.services.lsp \
    --hidden-import core.services.analytics \
    --hidden-import core.services.notifier \
    --hidden-import core.services.agent_summary \
    --hidden-import core.services.bundled_skills \
    --hidden-import core.services.session_memory \
    --hidden-import core.services.team_memory \
    --hidden-import prompts \
    --hidden-import prompts.system \
    --hidden-import prompts.compact \
    --hidden-import prompts.templates \
    --hidden-import tools \
    --hidden-import tools.base \
    --hidden-import tools.bash_tool \
    --hidden-import tools.file_read_tool \
    --hidden-import tools.file_write_tool \
    --hidden-import tools.file_edit_tool \
    --hidden-import tools.glob_tool \
    --hidden-import tools.grep_tool \
    --hidden-import tools.agent_tool \
    --hidden-import tools.ask_user_tool \
    --hidden-import tools.task_tool \
    --hidden-import tools.task_output_tool \
    --hidden-import tools.cron_tool \
    --hidden-import tools.plan_mode_tool \
    --hidden-import tools.web_search_tool \
    --hidden-import tools.web_fetch_tool \
    --hidden-import tools.web_browser_tool \
    --hidden-import tools.notebook_edit_tool \
    --hidden-import tools.mcp_tool \
    --hidden-import tools.mcp_resource_tools \
    --hidden-import tools.lsp_tool \
    --hidden-import tools.skill_tool \
    --hidden-import tools.workflow_tool \
    --hidden-import tools.soul_tools \
    --hidden-import tools.send_message_tool \
    --hidden-import tools.send_user_file_tool \
    --hidden-import tools.team_tool \
    --hidden-import tools.monitor_tool \
    --hidden-import tools.push_notification_tool \
    --hidden-import tools.subscribe_pr_tool \
    --hidden-import tools.terminal_capture_tool \
    --hidden-import tools.worktree_tool \
    --hidden-import tools.snip_tool \
    --hidden-import tools.ctx_inspect_tool \
    --hidden-import tools.config_tool \
    --hidden-import tools.extra_tools \
    --hidden-import tools.utility_tools \
    --hidden-import ui \
    --hidden-import ui.chat_dialog \
    --hidden-import ui.pet_window \
    --hidden-import ui.sprite_engine \
    --hidden-import ui.permission_dialog \
    --hidden-import ui.ask_user_dialog \
    --hidden-import ui.settings_dialog \
    --hidden-import ui.speech_bubble \
    --hidden-import ui.notification \
    --hidden-import ui.task_panel \
    --hidden-import ui.tray \
    --hidden-import ui.context_menu \
    --exclude-module matplotlib \
    --exclude-module numpy \
    --exclude-module scipy \
    --exclude-module pandas \
    --exclude-module tkinter \
    --exclude-module unittest \
    --exclude-module test \
    --exclude-module tests \
    --exclude-module pytest \
    --exclude-module setuptools \
    --exclude-module pip \
    main.py

# ── Report ───────────────────────────────────────────────────
echo ""
echo "============================================================"
if [ "$MODE" = "--onefile" ]; then
    EXE="dist/ClaudeBuddy.exe"
else
    EXE="dist/ClaudeBuddy/ClaudeBuddy.exe"
fi

if [ -f "$EXE" ]; then
    SIZE=$(du -sh "$EXE" | cut -f1)
    echo "Build successful!"
    echo "Output: $EXE"
    echo "Size:   $SIZE"
else
    echo "Build FAILED — executable not found."
    exit 1
fi
echo "============================================================"
