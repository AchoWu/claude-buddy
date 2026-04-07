"""
Claude Code Buddy — Global Configuration & Constants
Color palette extracted from Claude Code's design system.
"""

import os
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────
APP_NAME = "Claude Buddy"
APP_DIR = Path(__file__).parent
ASSETS_DIR = APP_DIR / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"
CHARACTERS_DIR = SPRITES_DIR / "characters"
DEFAULT_CHARACTER = "cute_girl"
DATA_DIR = Path.home() / ".claude-buddy"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
TASKS_FILE = DATA_DIR / "tasks.json"
INPUT_HISTORY_FILE = DATA_DIR / "input_history.json"

# Ensure data dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

# ── Claude Code Color Palette ────────────────────────────────────────────
CLAUDE_ORANGE = "#D77757"
CLAUDE_ORANGE_SHIMMER = "#EB9F7F"
PERMISSION_BLUE = "#B1B9F9"
BG_DARK = "#2D2D2D"
BG_BUBBLE = "#373737"
BG_INPUT = "#1E1E1E"
TEXT_PRIMARY = "#FFFFFF"
TEXT_DIM = "#999999"
SUCCESS_GREEN = "#4EBA65"
ERROR_RED = "#FF6B80"
WARNING_AMBER = "#FFC107"
BORDER_RADIUS = 12  # px

# ── Pet Behavior ─────────────────────────────────────────────────────────
PET_SIZE = 128  # sprite dimension (px)
SPRITE_TICK_MS = 150  # animation frame interval
IDLE_TIMEOUT_SEC = 300  # 5 min → sleep
BUBBLE_SHOW_SEC = 10  # speech bubble visible duration
BUBBLE_FADE_SEC = 3  # fade-out at the end
NOTIFICATION_SHOW_SEC = 8
MAX_TOOL_ROUNDS = 200  # prevent infinite tool loops

# ── Default Model Config ─────────────────────────────────────────────────
DEFAULT_PROVIDER = "taiji"
DEFAULT_MODEL = "DeepSeek-V3_1-Online-32k"

# ── Model Pricing (CC-aligned: per-million tokens in USD) ───────────────
MODEL_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_create": 3.75},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_create": 3.75},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 18.75},
    "claude-opus-4": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 18.75},
    "claude-haiku-3.5": {"input": 0.8, "output": 4.0, "cache_read": 0.08, "cache_create": 1.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "DeepSeek-V3_1-Online-32k": {"input": 0.14, "output": 0.28},
}

# ── Qt StyleSheet (global dark theme) ────────────────────────────────────
GLOBAL_QSS = f"""
QWidget {{
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "SF Pro", "Consolas", monospace;
    font-size: 13px;
}}
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {BG_INPUT};
    border: 1px solid #555;
    border-radius: 6px;
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {CLAUDE_ORANGE};
}}
QPushButton {{
    background: {CLAUDE_ORANGE};
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
}}
QPushButton:hover {{
    background: {CLAUDE_ORANGE_SHIMMER};
}}
QPushButton:pressed {{
    background: #C06A4A;
}}
QPushButton[flat="true"] {{
    background: transparent;
    color: {TEXT_DIM};
}}
QPushButton#closeBtn {{
    background: #CC4444;
    color: white;
    padding: 0px;
    font-size: 16px;
    font-weight: bold;
    font-family: Arial, sans-serif;
}}
QPushButton#closeBtn:hover {{
    background: #FF5555;
}}
QPushButton#miniBtn {{
    background: rgba(255,255,255,20);
    color: white;
    padding: 0px;
    font-size: 16px;
    font-weight: bold;
    font-family: Arial, sans-serif;
}}
QPushButton#miniBtn:hover {{
    background: rgba(255,255,255,50);
}}
QPushButton#settingsBtn {{
    background: rgba(255,255,255,15);
    color: {CLAUDE_ORANGE};
    padding: 0px;
    font-size: 16px;
    font-weight: bold;
    font-family: Arial, sans-serif;
}}
QPushButton#settingsBtn:hover {{
    background: {CLAUDE_ORANGE};
    color: white;
}}
QPushButton#sendBtn {{
    background: {CLAUDE_ORANGE};
    color: white;
    padding: 0px;
    font-size: 18px;
    font-weight: bold;
    font-family: Arial, sans-serif;
}}
QPushButton#sendBtn:hover {{
    background: {CLAUDE_ORANGE_SHIMMER};
}}
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #555;
    border-radius: 4px;
    min-height: 30px;
}}
"""
