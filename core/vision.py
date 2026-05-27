"""
Vision — Screen capture & image processing for Screenshot tool.

Provides three capture modes:
  - Full screen: entire desktop
  - Active window: currently focused window (Windows-specific)
  - Region: user-selected rectangle (delegated to ScreenshotOverlay)

Image processing:
  - Downsample large images to save API tokens
  - JPEG compression with configurable quality
  - Base64 encoding for Anthropic Vision API
"""

import base64
import io
import platform
from PyQt6.QtCore import Qt, QRect, QBuffer, QIODevice
from PyQt6.QtGui import QPixmap, QGuiApplication

from config import (
    SCREENSHOT_MAX_SIZE,
    SCREENSHOT_QUALITY,
)


class ScreenCapture:
    """Captures screen content and converts to base64 for Vision API."""

    @staticmethod
    def capture_full_screen() -> QPixmap:
        """Capture the entire primary screen."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return QPixmap()
        return screen.grabWindow(0)

    @staticmethod
    def capture_active_window() -> QPixmap:
        """
        Capture the currently focused/active window.
        Windows-specific: uses Win32 API to get foreground window rect.
        Falls back to full screen on other platforms or failure.
        """
        if platform.system() == "Windows":
            try:
                return ScreenCapture._capture_active_window_win32()
            except Exception:
                pass
        # Fallback: full screen
        return ScreenCapture.capture_full_screen()

    @staticmethod
    def _capture_active_window_win32() -> QPixmap:
        """Windows-specific: capture foreground window using Win32 API."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # Get the foreground window handle
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ScreenCapture.capture_full_screen()

        # Get the window rectangle (including borders/title bar)
        rect = wintypes.RECT()
        # Use DwmGetWindowAttribute for accurate bounds (excludes shadow)
        try:
            dwmapi = ctypes.windll.dwmapi
            DWMWA_EXTENDED_FRAME_BOUNDS = 9
            dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
        except (AttributeError, OSError):
            # Fallback to GetWindowRect (includes shadows on Win10+)
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

        # Convert to QRect
        x = rect.left
        y = rect.top
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        if w <= 0 or h <= 0:
            return ScreenCapture.capture_full_screen()

        # Grab that region of the screen
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return QPixmap()
        return screen.grabWindow(0, x, y, w, h)

    @staticmethod
    def capture_region(rect: QRect) -> QPixmap:
        """Capture a specific screen region defined by QRect."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return QPixmap()
        return screen.grabWindow(
            0, rect.x(), rect.y(), rect.width(), rect.height()
        )

    @staticmethod
    def pixmap_to_base64(
        pixmap: QPixmap,
        max_size: int = SCREENSHOT_MAX_SIZE,
        quality: int = SCREENSHOT_QUALITY,
    ) -> str:
        """
        Convert QPixmap to base64-encoded JPEG string.

        Resizes if larger than max_size on either dimension (saves API tokens).
        Uses JPEG format with configurable quality for smaller payload.

        Args:
            pixmap: The screenshot pixmap
            max_size: Maximum pixel dimension (width or height)
            quality: JPEG quality (1-100)

        Returns:
            Base64-encoded JPEG string
        """
        if pixmap.isNull():
            return ""

        # Resize if too large
        if pixmap.width() > max_size or pixmap.height() > max_size:
            pixmap = pixmap.scaled(
                max_size,
                max_size,
                aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                transformMode=Qt.TransformationMode.SmoothTransformation,
            )

        # Encode to JPEG in memory
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "JPEG", quality)
        raw_bytes = buffer.data().data()
        buffer.close()

        return base64.b64encode(raw_bytes).decode("utf-8")

    @staticmethod
    def estimate_tokens(base64_data: str) -> int:
        """
        Estimate token cost of an image.
        Anthropic: ~0.125 tokens per base64 character (rough heuristic from CC).
        """
        return int(len(base64_data) * 0.125)
