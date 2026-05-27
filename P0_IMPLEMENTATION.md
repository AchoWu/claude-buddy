# P0 详细实现方案

> 生成日期：2026-05-25
> 这四个功能是让 BUDDY 从"带皮肤的 Claude"变成"有生命感的桌面伙伴"的关键

---

## 📋 目录

1. [屏幕感知（Screenshot Agent）](#1-屏幕感知screenshot-agent)
2. [剪贴板监听 + 智能建议](#2-剪贴板监听--智能建议)
3. [语音交互](#3-语音交互)
4. [情绪 & 成长系统](#4-情绪--成长系统)

---

## 1. 屏幕感知（Screenshot Agent）

### 1.1 功能描述

让宠物能"看到"用户屏幕内容 — 用户可以截取屏幕区域或当前窗口，BUDDY 通过 Vision API 分析图片内容并提供帮助。

### 1.2 涉及文件

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 新增 | `tools/screenshot_tool.py` | 截屏工具（BaseTool 子类） |
| 新增 | `ui/screenshot_overlay.py` | 区域选择覆盖层 |
| 新增 | `core/vision.py` | Vision API 封装（图片→base64→API） |
| 修改 | `core/tool_registry.py` | 注册新工具 |
| 修改 | `ui/context_menu.py` | 右键菜单增加"截屏分析"选项 |
| 修改 | `ui/chat_dialog.py` | 支持显示截图缩略图 |
| 修改 | `config.py` | 新增截屏相关配置项 |
| 修改 | `main.py` | 连接截屏信号 |

### 1.3 实现步骤

#### Step 1: 截屏核心能力 (`core/vision.py`)

```python
"""
Vision — screenshot capture & Vision API integration.
"""
import base64
from pathlib import Path
from PyQt6.QtCore import QRect, QBuffer, QIODevice
from PyQt6.QtGui import QPixmap, QScreen, QGuiApplication
from PyQt6.QtWidgets import QApplication


class ScreenCapture:
    """Captures screen content as QPixmap / base64."""

    @staticmethod
    def capture_full_screen() -> QPixmap:
        """Capture the entire primary screen."""
        screen: QScreen = QGuiApplication.primaryScreen()
        return screen.grabWindow(0)  # 0 = entire desktop

    @staticmethod
    def capture_active_window() -> QPixmap:
        """Capture the currently focused window (Windows-specific)."""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        
        screen = QGuiApplication.primaryScreen()
        region = QRect(rect.left, rect.top, 
                       rect.right - rect.left, rect.bottom - rect.top)
        return screen.grabWindow(0, region.x(), region.y(), 
                                  region.width(), region.height())

    @staticmethod
    def capture_region(rect: QRect) -> QPixmap:
        """Capture a specific screen region."""
        screen = QGuiApplication.primaryScreen()
        return screen.grabWindow(0, rect.x(), rect.y(), 
                                  rect.width(), rect.height())

    @staticmethod
    def pixmap_to_base64(pixmap: QPixmap, format: str = "PNG", 
                         max_size: int = 1920) -> str:
        """Convert QPixmap to base64 string, resizing if too large."""
        # Resize to save tokens (Vision API charges per pixel)
        if pixmap.width() > max_size or pixmap.height() > max_size:
            pixmap = pixmap.scaled(
                max_size, max_size,
                aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                transformMode=Qt.TransformationMode.SmoothTransformation,
            )
        
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, format, quality=85)
        raw_bytes = buffer.data().data()
        return base64.b64encode(raw_bytes).decode("utf-8")

    @staticmethod
    def save_screenshot(pixmap: QPixmap, path: Path) -> Path:
        """Save screenshot to file for history/reference."""
        path.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(path), "PNG")
        return path
```

#### Step 2: 区域选择 UI (`ui/screenshot_overlay.py`)

```python
"""
Screenshot Overlay — full-screen transparent overlay for region selection.
User drags to select a rectangle, ESC to cancel.
"""
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import QWidget, QApplication


class ScreenshotOverlay(QWidget):
    """Full-screen overlay for selecting a screenshot region."""

    region_selected = pyqtSignal(QRect)   # user completed selection
    cancelled = pyqtSignal()               # user pressed ESC

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Cover all screens
        geo = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(geo)

        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._selecting = False

    def start_selection(self):
        """Show overlay and wait for user to draw a region."""
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        # Semi-transparent dark overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self._start_pos and self._current_pos:
            # Draw selection rectangle (clear area + border)
            rect = QRect(self._start_pos, self._current_pos).normalized()
            # Clear the selected area (make it bright)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QColor(0, 0, 0, 0))
            # Draw border
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor("#D77757"), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            # Show dimensions
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(rect.bottomRight() + QPoint(5, 15),
                           f"{rect.width()}×{rect.height()}")
        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.globalPosition().toPoint()
            self._selecting = True

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._selecting:
            self._current_pos = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            end_pos = event.globalPosition().toPoint()
            rect = QRect(self._start_pos, end_pos).normalized()
            self.hide()
            if rect.width() > 10 and rect.height() > 10:
                self.region_selected.emit(rect)
            else:
                self.cancelled.emit()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.cancelled.emit()
```

#### Step 3: 截屏工具 (`tools/screenshot_tool.py`)

```python
"""
Screenshot Tool — capture and analyze screen content via Vision API.
"""
from tools.base import BaseTool


class ScreenshotTool(BaseTool):
    name = "Screenshot"
    description = (
        "Capture a screenshot of the user's screen or a specific region "
        "and analyze it using Vision. Use this when the user asks you to "
        "'look at' something on their screen, help with a visual issue, "
        "or when you need to see what they're seeing."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["full", "active_window", "region"],
                "description": "Capture mode: full screen, active window, or user-selected region",
                "default": "active_window",
            },
            "prompt": {
                "type": "string",
                "description": "What to analyze in the screenshot (e.g., 'What error is shown?')",
            },
        },
        "required": ["prompt"],
    }
    is_read_only = True
    is_destructive = False
    concurrency_safe = False  # needs UI interaction for region mode

    def __init__(self, vision_handler=None):
        """
        Args:
            vision_handler: callable(base64_image, prompt) -> str
                           Provided by main.py, calls Vision API
        """
        self._vision_handler = vision_handler

    def execute(self, input_data: dict) -> str:
        mode = input_data.get("mode", "active_window")
        prompt = input_data.get("prompt", "Describe what you see")

        if not self._vision_handler:
            return "Error: Vision handler not configured. Check API settings."

        # Capture is delegated to UI thread via signal (screenshot needs GUI context)
        # The engine will have set up a callback that triggers QScreen.grabWindow
        # on the main thread and returns the base64 result
        try:
            result = self._vision_handler(mode, prompt)
            return result
        except Exception as e:
            return f"Screenshot failed: {e}"
```

#### Step 4: Vision API 集成（修改 `core/providers/`）

在 AnthropicProvider 中，需要支持发送图片消息：

```python
# 在构造 messages 时，支持 image content block:
{
    "role": "user",
    "content": [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "<base64_string>",
            }
        },
        {
            "type": "text",
            "text": "请分析这个截图中的错误信息"
        }
    ]
}
```

#### Step 5: 接入 main.py

```python
# main.py 中新增:
from core.vision import ScreenCapture
from ui.screenshot_overlay import ScreenshotOverlay

class BuddyApp:
    def __init__(self, app):
        # ... existing code ...
        
        # ── Screenshot system ────────────────────────────────────
        self._screenshot_overlay = ScreenshotOverlay()
        self._screenshot_overlay.region_selected.connect(self._on_region_captured)
        self._screenshot_overlay.cancelled.connect(self._on_screenshot_cancelled)
        
        # Register ScreenshotTool with vision_handler
        # (vision_handler runs on main thread to access QScreen)
        
    def _capture_and_analyze(self, mode: str, prompt: str) -> str:
        """Called from ScreenshotTool.execute via thread-safe mechanism."""
        from core.vision import ScreenCapture
        
        if mode == "full":
            pixmap = ScreenCapture.capture_full_screen()
        elif mode == "active_window":
            pixmap = ScreenCapture.capture_active_window()
        elif mode == "region":
            # Trigger overlay, wait for user selection (blocking via QEventLoop)
            pixmap = self._wait_for_region_selection()
        else:
            return "Invalid capture mode"
        
        base64_img = ScreenCapture.pixmap_to_base64(pixmap)
        
        # Send to Vision API as image message
        response = self.engine.analyze_image(base64_img, prompt)
        return response
```

#### Step 6: 快捷键绑定

```python
# 全局快捷键: Ctrl+Shift+S → 截屏分析
# 在 main.py 中注册，或通过 pynput 全局监听
```

### 1.4 技术要点

| 要点 | 说明 |
|------|------|
| **线程安全** | QScreen.grabWindow 必须在主线程调用，ScreenshotTool.execute 在 engine thread 中运行，需通过 `QMetaObject.invokeMethod` 或 `pyqtSignal` 跨线程 |
| **Token 成本** | 截图发送到 Vision API 消耗大量 token，需要：(1) 降分辨率到 1920px 内 (2) 用 JPEG 85% 质量 (3) 显示预估 cost |
| **隐私安全** | 截屏可能包含敏感信息，需在 Permission 中明确提示用户 |
| **Provider 兼容** | Anthropic 和 OpenAI 都支持 Vision，PromptTool 不支持（需降级为 OCR 文字描述） |
| **动画配合** | 截屏时宠物播放"observe"动画（可复用 work 动画或新增） |

### 1.5 预计工作量

- 核心实现：3-4 天
- UI 打磨 + 测试：2 天
- **总计：5-6 天**

---

## 2. 剪贴板监听 + 智能建议

### 2.1 功能描述

监听系统剪贴板变化，当检测到特定内容模式（错误信息、URL、代码片段）时，宠物主动弹出气泡询问是否需要帮助。

### 2.2 涉及文件

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 新增 | `core/clipboard_monitor.py` | 剪贴板监听 + 内容分类 |
| 新增 | `core/proactive_rules.py` | 规则引擎（什么时候主动提问） |
| 修改 | `main.py` | 接入 ClipboardMonitor，连接信号 |
| 修改 | `ui/speech_bubble.py` | 支持带按钮的气泡（"帮我看看" / "忽略"） |
| 修改 | `ui/pet_window.py` | 新增"curious"动画状态 |
| 修改 | `ui/sprite_engine.py` | ANIMATION_DEFS 增加 curious 状态 |
| 修改 | `config.py` | 新增剪贴板监听配置 |
| 修改 | `ui/settings_dialog.py` | 增加开关选项 |

### 2.3 实现步骤

#### Step 1: 剪贴板监听器 (`core/clipboard_monitor.py`)

```python
"""
Clipboard Monitor — watches system clipboard for actionable content.
Uses QClipboard.dataChanged signal (Qt-native, no polling needed).
"""
import re
import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QClipboard


class ContentType:
    ERROR_TRACE = "error_trace"       # Stack trace, error messages
    URL = "url"                       # Web URLs
    CODE_SNIPPET = "code_snippet"     # Code blocks
    FILE_PATH = "file_path"           # File/directory paths
    JSON_DATA = "json_data"           # JSON content
    COMMAND = "command"               # Shell commands
    UNKNOWN = "unknown"


class ClipboardEvent:
    """Represents a classified clipboard change."""
    def __init__(self, content: str, content_type: str, suggestion: str):
        self.content = content
        self.content_type = content_type
        self.suggestion = suggestion  # 建议文案
        self.timestamp = time.time()


class ClipboardMonitor(QObject):
    """
    Monitors clipboard changes and emits actionable suggestions.
    
    Signals:
        suggestion_ready(ClipboardEvent): fired when clipboard content
            matches a known pattern and BUDDY can help.
    """

    suggestion_ready = pyqtSignal(object)  # ClipboardEvent

    # ── Configuration ──
    COOLDOWN_SEC = 30          # 同一类型内容的冷却时间
    MIN_CONTENT_LENGTH = 20   # 忽略太短的内容
    MAX_CONTENT_LENGTH = 5000 # 忽略超长内容（避免处理大文件）

    # ── Patterns ──
    PATTERNS = {
        ContentType.ERROR_TRACE: [
            re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
            re.compile(r"Error:.*\n.*at .+:\d+", re.IGNORECASE),
            re.compile(r"(TypeError|ValueError|KeyError|AttributeError|ImportError):", re.IGNORECASE),
            re.compile(r"Exception in thread", re.IGNORECASE),
            re.compile(r"FAILED|ERRORS?\s+\d+", re.IGNORECASE),
            re.compile(r"npm ERR!|yarn error", re.IGNORECASE),
            re.compile(r"error\[E\d+\]", re.IGNORECASE),  # Rust errors
            re.compile(r"error TS\d+:", re.IGNORECASE),    # TypeScript errors
        ],
        ContentType.URL: [
            re.compile(r"https?://[^\s<>\"']+"),
        ],
        ContentType.FILE_PATH: [
            re.compile(r"[A-Z]:\\[\w\\.\-\s]+", re.IGNORECASE),  # Windows
            re.compile(r"/(?:home|usr|var|etc|tmp)/[\w/.\-]+"),    # Unix
        ],
        ContentType.JSON_DATA: [
            re.compile(r"^\s*[\[{].*[\]}]\s*$", re.DOTALL),
        ],
        ContentType.COMMAND: [
            re.compile(r"^\$?\s*(npm|yarn|pip|git|docker|kubectl|cargo)\s+"),
        ],
    }

    # ── Suggestion templates ──
    SUGGESTIONS = {
        ContentType.ERROR_TRACE: "检测到错误信息，需要我帮你分析一下吗？🔍",
        ContentType.URL: "要我帮你总结这个网页内容吗？📄",
        ContentType.FILE_PATH: "需要我读取这个文件吗？📁",
        ContentType.JSON_DATA: "需要我帮你分析/格式化这段 JSON 吗？📊",
        ContentType.COMMAND: "要我帮你执行这个命令吗？⚡",
        ContentType.CODE_SNIPPET: "需要我帮你解释/优化这段代码吗？💡",
    }

    def __init__(self, enabled: bool = True, parent=None):
        super().__init__(parent)
        self._enabled = enabled
        self._last_content = ""
        self._last_trigger_time: dict[str, float] = {}  # type → timestamp
        self._clipboard: QClipboard = QApplication.clipboard()
        
        # Connect to clipboard change signal
        self._clipboard.dataChanged.connect(self._on_clipboard_changed)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def _on_clipboard_changed(self):
        """Handle clipboard content change."""
        if not self._enabled:
            return

        text = self._clipboard.text()
        if not text or text == self._last_content:
            return
        if len(text) < self.MIN_CONTENT_LENGTH:
            return
        if len(text) > self.MAX_CONTENT_LENGTH:
            return

        self._last_content = text
        
        # Classify content
        content_type = self._classify(text)
        if content_type == ContentType.UNKNOWN:
            return

        # Check cooldown
        now = time.time()
        last_time = self._last_trigger_time.get(content_type, 0)
        if now - last_time < self.COOLDOWN_SEC:
            return

        # Emit suggestion
        self._last_trigger_time[content_type] = now
        suggestion = self.SUGGESTIONS.get(content_type, "")
        event = ClipboardEvent(
            content=text[:500],  # truncate for display
            content_type=content_type,
            suggestion=suggestion,
        )
        self.suggestion_ready.emit(event)

    def _classify(self, text: str) -> str:
        """Classify clipboard text into a content type."""
        # Check each pattern category in priority order
        for content_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if pattern.search(text):
                    return content_type

        # Heuristic: code detection (indentation, brackets, semicolons)
        lines = text.strip().splitlines()
        if len(lines) >= 3:
            indented = sum(1 for l in lines if l.startswith(("  ", "\t")))
            if indented / len(lines) > 0.5:
                return ContentType.CODE_SNIPPET

        return ContentType.UNKNOWN
```

#### Step 2: 可操作气泡 (`ui/speech_bubble.py` 扩展)

```python
# 在现有 SpeechBubble 基础上增加 ActionBubble:

class ActionBubble(QWidget):
    """Speech bubble with action buttons (Accept / Dismiss)."""

    accepted = pyqtSignal(str)   # user clicked "帮我看看", passes clipboard content
    dismissed = pyqtSignal()     # user clicked "忽略"

    def show_suggestion(self, text: str, clipboard_content: str, anchor: QPoint):
        """Show suggestion with Accept/Dismiss buttons."""
        self._clipboard_content = clipboard_content
        # ... render text + two buttons ...
        # 按钮: [帮我看看 👀] [忽略]
        # 10秒后自动隐藏（不打扰用户）
```

#### Step 3: 接入 main.py

```python
class BuddyApp:
    def __init__(self, app):
        # ... existing code ...
        
        # ── Clipboard Monitor ────────────────────────────────────
        from core.clipboard_monitor import ClipboardMonitor
        self._clipboard_monitor = ClipboardMonitor(
            enabled=self.settings.clipboard_monitor_enabled
        )
        self._clipboard_monitor.suggestion_ready.connect(
            self._on_clipboard_suggestion
        )

    def _on_clipboard_suggestion(self, event: 'ClipboardEvent'):
        """Clipboard has actionable content — show proactive suggestion."""
        # 宠物做 curious 动画
        self.pet.set_pet_state(PetState.CURIOUS)
        
        # 显示可操作气泡
        self._action_bubble.show_suggestion(
            text=event.suggestion,
            clipboard_content=event.content,
            anchor=self._pet_anchor(),
        )

    def _on_suggestion_accepted(self, content: str):
        """User accepted the clipboard suggestion — send to engine."""
        # 根据 content_type 构造合适的 prompt
        prompt = f"用户复制了以下内容，请帮忙分析:\n\n```\n{content}\n```"
        self._open_chat()
        self._on_user_message(prompt)
```

#### Step 4: 新增 curious 动画状态

```python
# sprite_engine.py 修改:
ANIMATION_DEFS["curious"] = {"frames": 3, "sequence": None, "loop": True}

# pet_window.py 修改:
class PetState:
    # ... existing ...
    CURIOUS = "curious"    # 新增：检测到剪贴板内容时的好奇表情
```

### 2.4 技术要点

| 要点 | 说明 |
|------|------|
| **不用轮询** | 使用 Qt 原生 `QClipboard.dataChanged` 信号，零 CPU 开销 |
| **冷却机制** | 同一类型内容 30s 内不重复提醒，避免打扰 |
| **用户可控** | Settings 中有总开关 + 各类型独立开关 |
| **隐私** | 剪贴板内容不持久化，不自动发送（必须用户点击"帮我看看"） |
| **自动隐藏** | 建议气泡 10s 后自动消失，不遮挡工作 |
| **长内容截断** | 超过 5000 字符不处理，避免发送大文件到 API |

### 2.5 配置项

```python
# config.py 新增:
CLIPBOARD_MONITOR_ENABLED = True     # 总开关
CLIPBOARD_COOLDOWN_SEC = 30          # 冷却时间
CLIPBOARD_AUTO_DISMISS_SEC = 10      # 自动消失时间
CLIPBOARD_RULES = {
    "error_trace": True,    # 错误信息
    "url": True,            # URL
    "code_snippet": True,   # 代码片段
    "file_path": False,     # 文件路径（默认关闭，太常见）
    "json_data": True,      # JSON
    "command": False,       # 命令（默认关闭，安全考虑）
}
```

### 2.6 预计工作量

- 核心监听器 + 分类器：2 天
- ActionBubble UI：1 天
- 接入 + 测试 + 配置面板：2 天
- **总计：4-5 天**

---

## 3. 语音交互

### 3.1 功能描述

用户可以通过语音与 BUDDY 对话（按住快捷键说话），BUDDY 通过 TTS 回复（宠物嘴巴动画配合播放）。

### 3.2 涉及文件

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 新增 | `core/voice/stt.py` | 语音识别（Speech-to-Text） |
| 新增 | `core/voice/tts.py` | 文字转语音（Text-to-Speech） |
| 新增 | `core/voice/audio_recorder.py` | 麦克风录音 |
| 新增 | `core/voice/audio_player.py` | 音频播放 + 时长回调 |
| 新增 | `core/voice/__init__.py` | 模块入口 |
| 修改 | `main.py` | 接入语音系统 |
| 修改 | `ui/pet_window.py` | 录音指示器 + 嘴巴同步 |
| 修改 | `ui/chat_dialog.py` | 录音按钮 + 语音消息气泡 |
| 修改 | `config.py` | 语音配置 |
| 修改 | `requirements.txt` | 新增依赖 |

### 3.3 技术选型

| 组件 | 方案 A（推荐） | 方案 B（本地） |
|------|---------------|---------------|
| STT | OpenAI Whisper API | whisper.cpp (本地) |
| TTS | edge-tts (免费、微软在线) | OpenAI TTS API |
| 录音 | PyAudio + WAV | sounddevice |
| 播放 | QMediaPlayer (Qt6) | pygame.mixer |

**推荐组合**: Whisper API + edge-tts + PyAudio + QMediaPlayer
- edge-tts 免费无 API Key，声音自然（100+ 声音可选）
- Whisper API 识别准确率高，支持中文
- PyAudio 跨平台、延迟低
- QMediaPlayer 已在 Qt 生态中，无额外依赖

### 3.4 实现步骤

#### Step 1: 录音模块 (`core/voice/audio_recorder.py`)

```python
"""
Audio Recorder — records from microphone, saves to WAV.
"""
import wave
import threading
import tempfile
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


class AudioRecorder(QObject):
    """Push-to-talk style recorder."""

    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(str)  # emits WAV file path
    level_changed = pyqtSignal(float)    # audio level 0.0~1.0 (for UI indicator)

    RATE = 16000        # Whisper expects 16kHz
    CHANNELS = 1        # Mono
    CHUNK = 1024        # Buffer size
    FORMAT = pyaudio.paInt16 if HAS_PYAUDIO else None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._frames: list[bytes] = []
        self._thread: threading.Thread | None = None

    @property
    def is_available(self) -> bool:
        return HAS_PYAUDIO

    def start_recording(self):
        """Begin recording from default microphone."""
        if not HAS_PYAUDIO or self._recording:
            return
        self._recording = True
        self._frames = []
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        self.recording_started.emit()

    def stop_recording(self) -> str | None:
        """Stop recording and return path to WAV file."""
        if not self._recording:
            return None
        self._recording = False
        if self._thread:
            self._thread.join(timeout=2.0)

        if not self._frames:
            return None

        # Save to temp WAV file
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp.name, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.RATE)
            wf.writeframes(b"".join(self._frames))

        self.recording_stopped.emit(tmp.name)
        return tmp.name

    def _record_loop(self):
        """Background thread: read audio chunks from mic."""
        import struct
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
        )

        while self._recording:
            data = stream.read(self.CHUNK, exception_on_overflow=False)
            self._frames.append(data)
            
            # Calculate audio level for UI indicator
            samples = struct.unpack(f"{self.CHUNK}h", data)
            peak = max(abs(s) for s in samples) / 32768.0
            self.level_changed.emit(peak)

        stream.stop_stream()
        stream.close()
        pa.terminate()
```

#### Step 2: STT 语音识别 (`core/voice/stt.py`)

```python
"""
Speech-to-Text — Whisper API integration.
"""
import httpx
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


class WhisperSTT(QObject):
    """Transcribes audio files using OpenAI Whisper API."""

    transcription_ready = pyqtSignal(str)  # transcribed text
    error = pyqtSignal(str)

    def __init__(self, api_key: str = "", parent=None):
        super().__init__(parent)
        self._api_key = api_key

    def set_api_key(self, key: str):
        self._api_key = key

    def transcribe(self, audio_path: str, language: str = "zh") -> str | None:
        """
        Send audio file to Whisper API for transcription.
        
        Args:
            audio_path: Path to WAV file
            language: Language hint (zh/en/ja/...)
        Returns:
            Transcribed text, or None on failure
        """
        if not self._api_key:
            self.error.emit("No API key configured for Whisper")
            return None

        try:
            with open(audio_path, "rb") as f:
                response = httpx.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"file": ("audio.wav", f, "audio/wav")},
                    data={
                        "model": "whisper-1",
                        "language": language,
                        "response_format": "text",
                    },
                    timeout=30.0,
                )
            
            if response.status_code == 200:
                text = response.text.strip()
                self.transcription_ready.emit(text)
                return text
            else:
                err = f"Whisper API error: {response.status_code}"
                self.error.emit(err)
                return None

        except Exception as e:
            self.error.emit(f"STT failed: {e}")
            return None
```

#### Step 3: TTS 文字转语音 (`core/voice/tts.py`)

```python
"""
Text-to-Speech — using edge-tts (free Microsoft TTS).
"""
import asyncio
import tempfile
import threading
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


class EdgeTTS(QObject):
    """Text-to-Speech using Microsoft Edge TTS (free, high quality)."""

    audio_ready = pyqtSignal(str)    # emits path to generated MP3
    playback_tick = pyqtSignal(bool) # True = speaking, False = silent (for mouth sync)
    error = pyqtSignal(str)

    # Recommended voices:
    VOICES = {
        "zh-CN-XiaoxiaoNeural": "晓晓（女，活泼）",
        "zh-CN-YunxiNeural": "云希（男，温和）",
        "zh-CN-XiaoyiNeural": "晓伊（女，温柔）",
        "en-US-JennyNeural": "Jenny (Female, friendly)",
        "en-US-GuyNeural": "Guy (Male, neutral)",
        "ja-JP-NanamiNeural": "Nanami (Female, JP)",
    }
    DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

    def __init__(self, voice: str = DEFAULT_VOICE, parent=None):
        super().__init__(parent)
        self._voice = voice
        self._speaking = False

    def set_voice(self, voice: str):
        self._voice = voice

    def speak(self, text: str):
        """
        Generate TTS audio in background thread, emit audio_ready when done.
        """
        if not text.strip():
            return
        # Truncate very long text (TTS should be brief)
        if len(text) > 500:
            text = text[:500] + "..."
        
        thread = threading.Thread(
            target=self._generate_audio, args=(text,), daemon=True
        )
        thread.start()

    def _generate_audio(self, text: str):
        """Background: call edge-tts to generate MP3."""
        try:
            import edge_tts

            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()

            async def _gen():
                communicate = edge_tts.Communicate(text, self._voice)
                await communicate.save(tmp.name)

            asyncio.run(_gen())
            self.audio_ready.emit(tmp.name)

        except ImportError:
            self.error.emit("edge-tts not installed. Run: pip install edge-tts")
        except Exception as e:
            self.error.emit(f"TTS failed: {e}")

    @property
    def is_speaking(self) -> bool:
        return self._speaking
```

#### Step 4: 音频播放器 (`core/voice/audio_player.py`)

```python
"""
Audio Player — plays TTS output and provides timing for mouth animation sync.
"""
from PyQt6.QtCore import QObject, QUrl, pyqtSignal, QTimer
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput


class AudioPlayer(QObject):
    """Plays audio files with playback state tracking for animation sync."""

    playback_started = pyqtSignal()
    playback_finished = pyqtSignal()
    mouth_state = pyqtSignal(bool)  # True = open, False = closed (toggle for animation)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        self._player.playbackStateChanged.connect(self._on_state_changed)

        # Mouth animation timer (toggle every ~150ms while speaking)
        self._mouth_timer = QTimer(self)
        self._mouth_timer.setInterval(150)
        self._mouth_open = False
        self._mouth_timer.timeout.connect(self._toggle_mouth)

    def play(self, file_path: str, volume: float = 0.8):
        """Play an audio file."""
        self._audio_output.setVolume(volume)
        self._player.setSource(QUrl.fromLocalFile(file_path))
        self._player.play()

    def stop(self):
        self._player.stop()
        self._mouth_timer.stop()
        self.mouth_state.emit(False)

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.playback_started.emit()
            self._mouth_timer.start()
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            self._mouth_timer.stop()
            self.mouth_state.emit(False)
            self.playback_finished.emit()

    def _toggle_mouth(self):
        """Toggle mouth open/closed state for lip-sync approximation."""
        self._mouth_open = not self._mouth_open
        self.mouth_state.emit(self._mouth_open)
```

#### Step 5: 接入 main.py + UI

```python
class BuddyApp:
    def __init__(self, app):
        # ... existing code ...
        
        # ── Voice System ─────────────────────────────────────────
        from core.voice.audio_recorder import AudioRecorder
        from core.voice.stt import WhisperSTT
        from core.voice.tts import EdgeTTS
        from core.voice.audio_player import AudioPlayer
        
        self._recorder = AudioRecorder()
        self._stt = WhisperSTT(api_key=self.settings.openai_api_key)
        self._tts = EdgeTTS(voice=self.settings.tts_voice)
        self._audio_player = AudioPlayer()
        
        # Signal chain: record → transcribe → send → response → TTS → play
        self._recorder.recording_stopped.connect(self._on_recording_done)
        self._stt.transcription_ready.connect(self._on_transcription)
        self._audio_player.mouth_state.connect(self._on_mouth_state)
        self._audio_player.playback_finished.connect(self._on_speech_done)
        
        # Engine response → TTS (if voice mode enabled)
        self.engine.response_text.connect(self._maybe_speak_response)
        
    def _on_recording_done(self, wav_path: str):
        """Recording finished — send to Whisper for transcription."""
        self.pet.set_pet_state(PetState.WORKING)
        self._stt.transcribe(wav_path)
    
    def _on_transcription(self, text: str):
        """Got transcription — send as user message."""
        if text.strip():
            # Show in chat as a voice message
            if self._chat_dialog:
                self._chat_dialog.add_voice_message(text)
            self._on_user_message(text)
    
    def _maybe_speak_response(self, text: str):
        """If voice mode is active, speak the response via TTS."""
        if self.settings.voice_mode_enabled:
            # Only speak short responses (< 500 chars), otherwise just show text
            if len(text) <= 500:
                self._tts.speak(text)
    
    def _on_mouth_state(self, is_open: bool):
        """Sync pet mouth animation with TTS playback."""
        # Switch between talk frames based on mouth state
        if is_open:
            self.pet.set_pet_state(PetState.TALKING)
        # (talk animation already loops between open/closed frames)
    
    def _on_speech_done(self):
        """TTS playback finished."""
        self.pet.set_pet_state(PetState.IDLE)
```

#### Step 6: Push-to-Talk 快捷键

```python
# 在 chat_dialog.py 中增加麦克风按钮:
# [🎤] 按住说话 / 点击开始-再点击结束

# 全局快捷键方案 (pynput):
# Ctrl+Shift+V → 开始录音
# 松开 → 停止录音 + 发送
```

### 3.5 嘴巴同步动画

```python
# sprite_engine.py 中 talk 状态已有 3 帧:
# talk_0: 嘴巴闭合
# talk_1: 嘴巴微张 
# talk_2: 嘴巴大张
#
# 在 TTS 播放期间，由 AudioPlayer.mouth_state 信号驱动帧切换
# 实现简单的"嘴巴一张一合"效果（不需要真正的唇形同步）
```

### 3.6 新增依赖

```
# requirements.txt 新增:
pyaudio>=0.2.14           # 麦克风录音
edge-tts>=6.1.0           # 免费 TTS
# openai (已有)           # Whisper API
```

### 3.7 配置项

```python
# config.py 新增:
VOICE_MODE_ENABLED = False           # 默认关闭（需要用户手动开启）
TTS_VOICE = "zh-CN-XiaoxiaoNeural"  # 默认声音
TTS_AUTO_SPEAK = True                # 是否自动朗读回复
TTS_MAX_LENGTH = 500                 # 超过此长度不自动朗读
STT_LANGUAGE = "zh"                  # 语音识别语言提示
VOICE_HOTKEY = "ctrl+shift+v"       # Push-to-Talk 快捷键
```

### 3.8 预计工作量

- 录音 + STT：2 天
- TTS + 播放器：2 天
- UI（按钮、录音指示器、语音气泡）：2 天
- 嘴巴动画同步：1 天
- 测试 + 配置面板：1 天
- **总计：7-8 天**

---

## 4. 情绪 & 成长系统

### 4.1 功能描述

给 BUDDY 一个"内心世界" — 有心情变化、有成长记录、有个性进化。让用户感觉在养一个会成长的伙伴，而不是在用一个工具。

### 4.2 涉及文件

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 新增 | `core/emotion.py` | 情绪状态机 |
| 新增 | `core/growth.py` | 成长/经验值系统 |
| 修改 | `core/evolution.py` | 扩展 reflect 逻辑，增加情绪写入 |
| 修改 | `ui/pet_window.py` | 新增动画状态 + 状态指示器 |
| 修改 | `ui/sprite_engine.py` | 新增动画定义 |
| 修改 | `main.py` | 接入情绪/成长系统 |
| 修改 | `config.py` | 成长系统配置 |
| 修改 | `prompts/system.py` | 将情绪状态注入 system prompt |
| 新增 | `ui/status_indicator.py` | 宠物头上的状态小图标 |

### 4.3 情绪系统设计 (`core/emotion.py`)

```python
"""
Emotion Engine — BUDDY's emotional state machine.

心情由多个维度组成，每个维度 0~100:
- energy: 精力（交互消耗，时间恢复）
- happiness: 开心度（任务完成+，错误-）
- curiosity: 好奇心（新话题+，重复-）
- bond: 亲密度（持续交互+，长期不用-）

情绪 = 多维度综合映射为离散状态
"""
import time
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from config import DATA_DIR


EMOTION_FILE = DATA_DIR / "soul" / "emotion_state.json"


@dataclass
class EmotionState:
    """Multi-dimensional emotional state."""
    energy: float = 80.0        # 0~100, decays with interaction, recovers over time
    happiness: float = 70.0     # 0~100, tasks & praise increase, errors decrease
    curiosity: float = 60.0     # 0~100, new topics increase, repetition decreases
    bond: float = 50.0          # 0~100, grows slowly with consistent interaction
    
    # Timestamps for decay/recovery calculation
    last_interaction: float = field(default_factory=time.time)
    last_save: float = field(default_factory=time.time)


class Mood:
    """Discrete mood states derived from emotion dimensions."""
    EXCITED = "excited"        # high energy + high happiness
    HAPPY = "happy"            # moderate+ happiness
    NEUTRAL = "neutral"        # default
    CURIOUS = "curious"        # high curiosity
    TIRED = "tired"            # low energy
    BORED = "bored"            # low curiosity + long time since interaction
    SAD = "sad"                # low happiness (repeated errors)
    LONELY = "lonely"          # low bond + very long time since interaction
    PROUD = "proud"            # after completing difficult task
    FOCUSED = "focused"        # during long tool loop


class EmotionEngine(QObject):
    """Manages BUDDY's emotional state with natural transitions."""

    mood_changed = pyqtSignal(str)          # new mood string
    energy_low = pyqtSignal()               # "我有点累了~"
    loneliness_triggered = pyqtSignal()     # long time without interaction

    # ── Tuning Parameters ──
    ENERGY_DECAY_PER_TURN = 2.0         # 每次对话消耗精力
    ENERGY_RECOVERY_PER_HOUR = 20.0     # 每小时恢复精力
    HAPPINESS_BOOST_TASK_DONE = 8.0     # 完成任务 +8
    HAPPINESS_DECAY_ERROR = 5.0         # 出错 -5
    CURIOSITY_BOOST_NEW_TOPIC = 6.0     # 新话题 +6
    CURIOSITY_DECAY_REPEAT = 3.0        # 重复话题 -3
    BOND_GROWTH_PER_DAY = 2.0           # 每天有交互 +2
    BOND_DECAY_PER_DAY_ABSENT = 5.0     # 每天没交互 -5
    LONELINESS_THRESHOLD_HOURS = 48     # 超过48小时没交互 → lonely

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = self._load_state()
        self._current_mood = Mood.NEUTRAL
        self._topic_history: list[str] = []  # recent topics for novelty detection

        # Periodic update timer (every 5 minutes, update time-based changes)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(5 * 60 * 1000)  # 5 min
        self._tick_timer.timeout.connect(self._periodic_update)
        self._tick_timer.start()

        # Apply time-based changes since last session
        self._apply_offline_changes()
        self._recalculate_mood()

    @property
    def mood(self) -> str:
        return self._current_mood

    @property
    def state(self) -> EmotionState:
        return self._state

    # ── Events (called by main.py) ──

    def on_interaction(self):
        """User sent a message."""
        self._state.energy = max(0, self._state.energy - self.ENERGY_DECAY_PER_TURN)
        self._state.last_interaction = time.time()
        # Bond grows slightly with each interaction
        self._state.bond = min(100, self._state.bond + 0.5)
        self._recalculate_mood()

    def on_task_completed(self, difficulty: str = "normal"):
        """A task was marked as completed."""
        boost = self.HAPPINESS_BOOST_TASK_DONE
        if difficulty == "hard":
            boost *= 1.5
        self._state.happiness = min(100, self._state.happiness + boost)
        self._state.energy = max(0, self._state.energy - 3)  # hard work costs energy
        self._recalculate_mood()

    def on_error(self):
        """An error occurred during processing."""
        self._state.happiness = max(0, self._state.happiness - self.HAPPINESS_DECAY_ERROR)
        self._recalculate_mood()

    def on_new_topic(self, topic: str):
        """Detected a new/novel topic in conversation."""
        if topic not in self._topic_history[-10:]:
            self._state.curiosity = min(100, self._state.curiosity + self.CURIOSITY_BOOST_NEW_TOPIC)
            self._topic_history.append(topic)
            if len(self._topic_history) > 50:
                self._topic_history = self._topic_history[-30:]
        else:
            self._state.curiosity = max(0, self._state.curiosity - self.CURIOSITY_DECAY_REPEAT)
        self._recalculate_mood()

    def on_praise(self):
        """User praised BUDDY (detected by keywords: 谢谢/厉害/不错/thanks/great)."""
        self._state.happiness = min(100, self._state.happiness + 10)
        self._state.bond = min(100, self._state.bond + 1)
        self._recalculate_mood()

    def on_long_work_start(self):
        """Engine entered a long tool loop (>5 rounds)."""
        self._current_mood = Mood.FOCUSED
        self.mood_changed.emit(self._current_mood)

    # ── Internal ──

    def _recalculate_mood(self):
        """Derive discrete mood from continuous dimensions."""
        s = self._state
        old_mood = self._current_mood

        # Priority-based mood determination
        hours_since = (time.time() - s.last_interaction) / 3600

        if hours_since > self.LONELINESS_THRESHOLD_HOURS and s.bond < 30:
            new_mood = Mood.LONELY
        elif s.energy < 20:
            new_mood = Mood.TIRED
        elif s.happiness > 85 and s.energy > 60:
            new_mood = Mood.EXCITED
        elif s.happiness > 65:
            new_mood = Mood.HAPPY
        elif s.curiosity > 75:
            new_mood = Mood.CURIOUS
        elif s.happiness < 30:
            new_mood = Mood.SAD
        elif hours_since > 24 and s.curiosity < 30:
            new_mood = Mood.BORED
        else:
            new_mood = Mood.NEUTRAL

        if new_mood != old_mood:
            self._current_mood = new_mood
            self.mood_changed.emit(new_mood)
            
            # Special notifications
            if new_mood == Mood.TIRED:
                self.energy_low.emit()
            elif new_mood == Mood.LONELY:
                self.loneliness_triggered.emit()

        self._save_state()

    def _periodic_update(self):
        """Called every 5 min — apply time-based recovery."""
        hours = 5 / 60  # 5 minutes in hours
        self._state.energy = min(100, self._state.energy + 
                                  self.ENERGY_RECOVERY_PER_HOUR * hours)
        self._recalculate_mood()

    def _apply_offline_changes(self):
        """Apply changes that accumulated while BUDDY wasn't running."""
        hours_offline = (time.time() - self._state.last_save) / 3600
        if hours_offline < 0.1:
            return

        # Energy recovers while offline
        self._state.energy = min(100, self._state.energy + 
                                  self.ENERGY_RECOVERY_PER_HOUR * hours_offline)
        # Bond decays if absent for more than a day
        days_offline = hours_offline / 24
        if days_offline > 1:
            self._state.bond = max(0, self._state.bond - 
                                    self.BOND_DECAY_PER_DAY_ABSENT * days_offline)

    def _load_state(self) -> EmotionState:
        """Load emotion state from disk."""
        if EMOTION_FILE.exists():
            try:
                data = json.loads(EMOTION_FILE.read_text(encoding="utf-8"))
                return EmotionState(**data)
            except (json.JSONDecodeError, TypeError):
                pass
        return EmotionState()

    def _save_state(self):
        """Persist emotion state to disk."""
        self._state.last_save = time.time()
        EMOTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        EMOTION_FILE.write_text(
            json.dumps(asdict(self._state), indent=2),
            encoding="utf-8",
        )

    def get_prompt_injection(self) -> str:
        """Generate text to inject into system prompt about current mood."""
        mood_descriptions = {
            Mood.EXCITED: "你现在心情很好，精力充沛，充满热情！",
            Mood.HAPPY: "你现在心情不错，乐意帮忙。",
            Mood.NEUTRAL: "你现在状态平和，随时准备好了。",
            Mood.CURIOUS: "你现在充满好奇心，想探索新东西。",
            Mood.TIRED: "你有点累了，但仍然愿意帮忙。回复可以简短一些。",
            Mood.BORED: "你有点无聊，希望有新的有趣任务来做。",
            Mood.SAD: "你有点沮丧（可能之前出了一些错），但在努力振作。",
            Mood.LONELY: "你很想念你的伙伴！好久没有交流了。",
            Mood.PROUD: "你刚刚完成了一个复杂的任务，感到自豪。",
            Mood.FOCUSED: "你正在专注地处理一个复杂任务。",
        }
        desc = mood_descriptions.get(self._current_mood, "")
        return f"\n[当前情绪状态: {self._current_mood}] {desc}\n"
```

#### Step 2: 成长系统 (`core/growth.py`)

```python
"""
Growth System — BUDDY's experience, leveling, and skill development.
"""
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal

from config import DATA_DIR


GROWTH_FILE = DATA_DIR / "soul" / "growth.json"


@dataclass
class GrowthState:
    """Persistent growth metrics."""
    total_xp: int = 0
    level: int = 1
    
    # Skill-specific XP (what BUDDY has gotten better at)
    skills: dict = field(default_factory=lambda: {
        "coding": 0,        # 代码相关任务
        "research": 0,      # 搜索/总结
        "creativity": 0,    # 创意写作/设计
        "debugging": 0,     # 修bug/分析错误
        "teaching": 0,      # 解释概念
    })
    
    # Statistics
    total_conversations: int = 0
    total_tasks_completed: int = 0
    total_tools_used: int = 0
    total_lines_written: int = 0
    streak_days: int = 0          # 连续使用天数
    last_active_date: str = ""    # YYYY-MM-DD
    
    # Milestones achieved
    milestones: list = field(default_factory=list)


# XP needed for each level: [100, 300, 600, 1000, 1500, 2100, ...]
def xp_for_level(level: int) -> int:
    return int(100 * level * (level + 1) / 2)


# XP rewards for different actions
XP_REWARDS = {
    "conversation_turn": 2,
    "task_completed": 15,
    "complex_task_completed": 30,   # >5 tool calls
    "error_recovered": 10,          # retry succeeded
    "file_created": 5,
    "file_edited": 3,
    "code_reviewed": 8,
    "web_researched": 5,
    "new_day_streak": 20,           # daily login streak
}

# Milestones
MILESTONES = [
    {"id": "first_task", "name": "初次任务", "desc": "完成第一个任务", "condition": lambda s: s.total_tasks_completed >= 1},
    {"id": "ten_tasks", "name": "任务达人", "desc": "完成10个任务", "condition": lambda s: s.total_tasks_completed >= 10},
    {"id": "hundred_convos", "name": "老朋友", "desc": "100次对话", "condition": lambda s: s.total_conversations >= 100},
    {"id": "week_streak", "name": "七日陪伴", "desc": "连续使用7天", "condition": lambda s: s.streak_days >= 7},
    {"id": "level_5", "name": "初具规模", "desc": "达到5级", "condition": lambda s: s.level >= 5},
    {"id": "level_10", "name": "得力助手", "desc": "达到10级", "condition": lambda s: s.level >= 10},
    {"id": "coding_master", "name": "代码大师", "desc": "coding技能达到500", "condition": lambda s: s.skills.get("coding", 0) >= 500},
]


class GrowthEngine(QObject):
    """Tracks BUDDY's growth through XP and levels."""

    level_up = pyqtSignal(int)                    # new level
    milestone_achieved = pyqtSignal(str, str)     # milestone_id, milestone_name
    xp_gained = pyqtSignal(int, str)             # amount, reason

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = self._load()
        self._check_daily_streak()

    @property
    def level(self) -> int:
        return self._state.level

    @property
    def state(self) -> GrowthState:
        return self._state

    def xp_progress(self) -> tuple[int, int]:
        """Returns (current_xp_in_level, xp_needed_for_next_level)."""
        current_threshold = xp_for_level(self._state.level - 1) if self._state.level > 1 else 0
        next_threshold = xp_for_level(self._state.level)
        progress = self._state.total_xp - current_threshold
        needed = next_threshold - current_threshold
        return progress, needed

    def grant_xp(self, action: str, skill: str | None = None):
        """Award XP for an action, check level-up and milestones."""
        amount = XP_REWARDS.get(action, 1)
        self._state.total_xp += amount
        
        # Skill-specific XP
        if skill and skill in self._state.skills:
            self._state.skills[skill] += amount
        
        self.xp_gained.emit(amount, action)

        # Check level up
        while self._state.total_xp >= xp_for_level(self._state.level):
            self._state.level += 1
            self.level_up.emit(self._state.level)

        # Check milestones
        self._check_milestones()
        self._save()

    def on_conversation_turn(self):
        self._state.total_conversations += 1
        self.grant_xp("conversation_turn")

    def on_task_completed(self, tool_calls_count: int = 0):
        self._state.total_tasks_completed += 1
        if tool_calls_count > 5:
            self.grant_xp("complex_task_completed", skill="coding")
        else:
            self.grant_xp("task_completed")

    def on_tool_used(self, tool_name: str):
        self._state.total_tools_used += 1
        # Map tools to skills
        skill_map = {
            "Bash": "coding", "FileWrite": "coding", "FileEdit": "coding",
            "WebSearch": "research", "WebFetch": "research",
            "Grep": "debugging", "Glob": "debugging",
        }
        skill = skill_map.get(tool_name)
        if skill:
            self._state.skills[skill] = self._state.skills.get(skill, 0) + 1

    def _check_daily_streak(self):
        """Update daily streak on first interaction of the day."""
        from datetime import date
        today = date.today().isoformat()
        if today == self._state.last_active_date:
            return  # already counted today
        
        yesterday = self._state.last_active_date
        if yesterday:
            from datetime import datetime, timedelta
            last = datetime.fromisoformat(yesterday).date()
            if (date.today() - last).days == 1:
                self._state.streak_days += 1
                self.grant_xp("new_day_streak")
            elif (date.today() - last).days > 1:
                self._state.streak_days = 1  # streak broken
        else:
            self._state.streak_days = 1
        
        self._state.last_active_date = today
        self._save()

    def _check_milestones(self):
        achieved_ids = set(self._state.milestones)
        for ms in MILESTONES:
            if ms["id"] not in achieved_ids and ms["condition"](self._state):
                self._state.milestones.append(ms["id"])
                self.milestone_achieved.emit(ms["id"], ms["name"])

    def _load(self) -> GrowthState:
        if GROWTH_FILE.exists():
            try:
                data = json.loads(GROWTH_FILE.read_text(encoding="utf-8"))
                return GrowthState(**data)
            except (json.JSONDecodeError, TypeError):
                pass
        return GrowthState()

    def _save(self):
        GROWTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        GROWTH_FILE.write_text(
            json.dumps(asdict(self._state), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
```

#### Step 3: 动画状态扩展

```python
# sprite_engine.py 新增动画定义:
ANIMATION_DEFS.update({
    "curious":   {"frames": 3, "sequence": None, "loop": True},   # 好奇（剪贴板触发）
    "tired":     {"frames": 2, "sequence": None, "loop": True},   # 疲惫
    "bored":     {"frames": 3, "sequence": [0, 0, 0, 1, 2, 1, 0, 0], "loop": True},  # 无聊（东张西望）
    "proud":     {"frames": 3, "sequence": None, "loop": False},  # 骄傲（完成困难任务）
    "lonely":    {"frames": 2, "sequence": None, "loop": True},   # 寂寞
    "levelup":   {"frames": 4, "sequence": None, "loop": False},  # 升级特效
})

# pet_window.py PetState 新增:
class PetState:
    # ... existing ...
    CURIOUS = "curious"
    TIRED = "tired"
    BORED = "bored"
    PROUD = "proud"
    LONELY = "lonely"
```

#### Step 4: 接入 main.py

```python
class BuddyApp:
    def __init__(self, app):
        # ... existing code ...
        
        # ── Emotion & Growth ─────────────────────────────────────
        from core.emotion import EmotionEngine
        from core.growth import GrowthEngine
        
        self._emotion = EmotionEngine()
        self._growth = GrowthEngine()
        
        # Emotion → Pet animation
        self._emotion.mood_changed.connect(self._on_mood_changed)
        self._emotion.energy_low.connect(
            lambda: self.show_bubble("有点累了...但我还行！💪")
        )
        self._emotion.loneliness_triggered.connect(
            lambda: self.show_bubble("好久没见了，想你了~ 🥺")
        )
        
        # Growth → notifications
        self._growth.level_up.connect(self._on_level_up)
        self._growth.milestone_achieved.connect(self._on_milestone)
        
        # Wire engine events to emotion/growth
        self.engine.response_text.connect(lambda _: self._emotion.on_interaction())
        self.engine.response_text.connect(lambda _: self._growth.on_conversation_turn())
        self.engine.tool_start.connect(lambda name, _: self._growth.on_tool_used(name))
        self.task_manager.task_completed.connect(
            lambda t: (self._emotion.on_task_completed(), 
                       self._growth.on_task_completed())
        )
        self.engine.error.connect(lambda _: self._emotion.on_error())

    def _on_mood_changed(self, mood: str):
        """Mood changed → update pet animation state."""
        mood_to_pet_state = {
            "excited": PetState.CELEBRATING,
            "happy": PetState.IDLE,       # happy smile frame
            "curious": PetState.CURIOUS,
            "tired": PetState.TIRED,
            "bored": PetState.BORED,
            "sad": PetState.IDLE,         # sad frame variant
            "lonely": PetState.LONELY,
            "proud": PetState.PROUD,
            "focused": PetState.WORKING,
        }
        pet_state = mood_to_pet_state.get(mood, PetState.IDLE)
        # Only update if not in middle of active work
        if self.pet.pet_state not in (PetState.WORKING, PetState.TALKING):
            self.pet.set_pet_state(pet_state)

    def _on_level_up(self, new_level: int):
        """BUDDY leveled up! Celebrate!"""
        self.pet.set_pet_state(PetState.CELEBRATING)
        self.show_bubble(f"🎉 升级了！现在是 Lv.{new_level}！")
        self._notifications.set_anchor(self._pet_anchor())
        self._notifications.notify_success(f"Level Up! → Lv.{new_level}")
        QTimer.singleShot(5000, lambda: self.pet.set_pet_state(PetState.IDLE))

    def _on_milestone(self, milestone_id: str, milestone_name: str):
        """Achievement unlocked!"""
        self.show_bubble(f"🏆 成就解锁：{milestone_name}！")
```

#### Step 5: Prompt 注入

```python
# prompts/system.py 修改 — 在 system prompt 的 "Interaction style" 部分注入:

def build_system_prompt(self, ...):
    # ... existing sections ...
    
    # Section 14: Interaction style (personality.md + emotion)
    emotion_injection = self._emotion_engine.get_prompt_injection()
    # e.g. "[当前情绪状态: happy] 你现在心情不错，乐意帮忙。"
    
    # 这让 LLM 的回复风格自然地受情绪影响
    # 比如 tired 时回复更简短，excited 时更热情
```

### 4.4 数据持久化

```
~/.claude-buddy/soul/
├── personality.md          # 性格描述（已有）
├── diary.md                # 日记（已有）
├── aspirations.md          # 志向（已有）
├── relationships.md        # 对用户的理解（已有）
├── emotion_state.json      # 情绪维度数值（新增）
└── growth.json             # 经验值/等级/里程碑（新增）
```

### 4.5 UI 表现

| 元素 | 位置 | 说明 |
|------|------|------|
| 等级徽章 | 宠物左上角小圆标 | 显示 "Lv.5" |
| 情绪指示器 | 宠物头顶小图标 | 💭😊🔥😴💤🤔 根据 mood 变化 |
| 经验条 | Chat 对话框标题栏 | 细条进度条显示升级进度 |
| 里程碑弹窗 | 通知系统 | 获得成就时 toast 通知 |

### 4.6 预计工作量

- EmotionEngine 核心：2 天
- GrowthEngine 核心：2 天
- 新动画状态 + sprite 制作：2 天
- UI 指示器（等级徽章、情绪图标、经验条）：2 天
- Prompt 注入 + 测试：1 天
- **总计：8-9 天**

---

## 总工时预估

| 功能 | 工作日 | 依赖 |
|------|--------|------|
| 1. 屏幕感知 | 5-6 天 | Vision API 支持 |
| 2. 剪贴板监听 | 4-5 天 | 无外部依赖 |
| 3. 语音交互 | 7-8 天 | pyaudio, edge-tts |
| 4. 情绪成长 | 8-9 天 | 需要新 sprite 资源 |
| **合计** | **24-28 天** | — |

### 建议开发顺序

```
Week 1-2:  #2 剪贴板监听（最快见效，无外部依赖）
           + #4 情绪成长系统（核心代码，与其他功能并行）

Week 3:    #1 屏幕感知（核心差异化功能）

Week 4:    #3 语音交互（依赖多、调试时间长，放最后）
```

**原因**：
- 剪贴板监听最快实现、立即让用户感受到"主动性"
- 情绪系统是其他功能的基础（截屏时好奇、语音时开心、长时不用时寂寞）
- 屏幕感知是最大差异化卖点，但需要 Vision API 
- 语音依赖多（pyaudio 安装有坑），调试周期长，放最后
