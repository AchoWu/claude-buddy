"""
Sprite Animation Engine — manages pixel art frame sequences and state transitions.
"""

from pathlib import Path
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont

from config import SPRITES_DIR, SPRITE_TICK_MS, PET_SIZE, CHARACTERS_DIR, DEFAULT_CHARACTER


# Idle sequence with blink (index -1 = blink frame, mapped to frame 0 with eyes closed)
IDLE_SEQUENCE = [0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0, 3, 0, 0]

ANIMATION_DEFS: dict[str, dict] = {
    "idle":      {"frames": 4, "sequence": IDLE_SEQUENCE, "loop": True},
    "walk":      {"frames": 4, "sequence": None, "loop": True},
    "sleep":     {"frames": 3, "sequence": None, "loop": True},
    "talk":      {"frames": 3, "sequence": None, "loop": True},
    "work":      {"frames": 4, "sequence": None, "loop": True},
    "celebrate": {"frames": 4, "sequence": None, "loop": False},
}


def _generate_placeholder_sprite(state: str, frame: int, size: int = PET_SIZE) -> QPixmap:
    """Generate a colored placeholder sprite with state/frame label."""
    palette = {
        "idle": "#D77757",
        "walk": "#4EBA65",
        "sleep": "#7B8EC9",
        "talk": "#EB9F7F",
        "work": "#FFC107",
        "celebrate": "#FF6B80",
    }
    color = palette.get(state, "#888888")

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # transparent

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Body (rounded rect)
    body_color = QColor(color)
    painter.setBrush(body_color)
    painter.setPen(QColor(0, 0, 0, 0))
    margin = 10
    painter.drawRoundedRect(margin, margin + 20, size - 2 * margin, size - 2 * margin - 20, 16, 16)

    # Eyes
    painter.setBrush(QColor("white"))
    eye_y = margin + 40 + (frame % 2) * 2  # slight bounce
    painter.drawEllipse(size // 2 - 22, eye_y, 16, 16)
    painter.drawEllipse(size // 2 + 6, eye_y, 16, 16)

    # Pupils
    painter.setBrush(QColor("#2D2D2D"))
    pupil_y = eye_y + 4
    painter.drawEllipse(size // 2 - 18, pupil_y, 8, 8)
    painter.drawEllipse(size // 2 + 10, pupil_y, 8, 8)

    # Mouth / expression per state
    painter.setPen(QColor("#2D2D2D"))
    painter.setPen(QColor("#2D2D2D"))
    mouth_y = eye_y + 24
    if state == "sleep":
        # Closed eyes (horizontal lines)
        painter.drawLine(size // 2 - 20, eye_y + 8, size // 2 - 8, eye_y + 8)
        painter.drawLine(size // 2 + 8, eye_y + 8, size // 2 + 20, eye_y + 8)
    elif state == "talk" and frame % 2 == 0:
        # Open mouth
        painter.setBrush(QColor("#2D2D2D"))
        painter.drawEllipse(size // 2 - 8, mouth_y, 16, 12)
    elif state == "celebrate":
        # Big smile
        from PyQt6.QtCore import QRect
        painter.drawArc(QRect(size // 2 - 12, mouth_y - 4, 24, 16), 0, -180 * 16)
    else:
        # Small smile
        from PyQt6.QtCore import QRect
        painter.drawArc(QRect(size // 2 - 8, mouth_y, 16, 8), 0, -180 * 16)

    painter.end()
    return pixmap


class SpriteEngine(QObject):
    """Manages sprite animation frames and state transitions."""

    frame_changed = pyqtSignal(QPixmap)  # emitted each tick with current frame

    def __init__(self, parent=None, character: str = DEFAULT_CHARACTER):
        super().__init__(parent)
        self._character = character
        self._states: dict[str, list[QPixmap]] = {}
        self._sequences: dict[str, list[int] | None] = {}
        self._loop: dict[str, bool] = {}

        self._current_state = "idle"
        self._frame_index = 0
        self._pending_state: str | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(SPRITE_TICK_MS)
        self._timer.timeout.connect(self._tick)

        self._load_sprites()

    def set_character(self, character: str):
        """Switch to a different character's sprites at runtime."""
        if character == self._character:
            return
        self._character = character
        self._load_sprites()
        self._frame_index = 0
        # Emit current frame immediately so pet updates
        frames = self._states.get(self._current_state, [])
        if frames:
            self.frame_changed.emit(frames[0])

    def _load_sprites(self):
        """Load sprite PNGs from character directory, falling back to generated placeholders."""
        char_dir = CHARACTERS_DIR / self._character
        for state, anim_def in ANIMATION_DEFS.items():
            frames: list[QPixmap] = []
            for i in range(anim_def["frames"]):
                # Try character-specific directory first
                path = char_dir / f"{state}_{i}.png"
                if not path.exists():
                    # Fallback: old top-level sprites dir (backward compat)
                    path = SPRITES_DIR / f"{state}_{i}.png"
                if path.exists():
                    px = QPixmap(str(path))
                    if not px.isNull():
                        frames.append(px)
                        continue
                # Generate placeholder
                frames.append(_generate_placeholder_sprite(state, i))

            self._states[state] = frames
            self._sequences[state] = anim_def.get("sequence")
            self._loop[state] = anim_def.get("loop", True)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    @property
    def current_state(self) -> str:
        return self._current_state

    def set_state(self, state: str):
        """Request state transition. Non-looping anims finish before switching."""
        if state == self._current_state:
            return
        if state not in self._states:
            return

        if self._loop.get(self._current_state, True):
            # Looping anim → switch immediately
            self._switch_state(state)
        else:
            # Non-looping → queue switch after current finishes
            self._pending_state = state

    def _switch_state(self, state: str):
        self._current_state = state
        self._frame_index = 0
        self._pending_state = None

    def _tick(self):
        frames = self._states.get(self._current_state, [])
        if not frames:
            return

        seq = self._sequences.get(self._current_state)
        if seq:
            # Use custom sequence
            idx = seq[self._frame_index % len(seq)]
            if idx == -1:
                # Blink: use frame 0 but could add a blink variant later
                idx = 0
            frame = frames[idx % len(frames)]
            self._frame_index += 1

            if self._frame_index >= len(seq):
                if self._loop.get(self._current_state, True):
                    self._frame_index = 0
                else:
                    self._on_anim_finished()
        else:
            # Simple sequential
            frame = frames[self._frame_index % len(frames)]
            self._frame_index += 1

            if self._frame_index >= len(frames):
                if self._loop.get(self._current_state, True):
                    self._frame_index = 0
                else:
                    self._on_anim_finished()

        self.frame_changed.emit(frame)

    def _on_anim_finished(self):
        if self._pending_state:
            self._switch_state(self._pending_state)
        else:
            self._switch_state("idle")

    def current_pixmap(self) -> QPixmap:
        """Get the current frame without advancing."""
        frames = self._states.get(self._current_state, [])
        if not frames:
            return QPixmap()
        seq = self._sequences.get(self._current_state)
        if seq:
            idx = seq[self._frame_index % len(seq)]
            if idx == -1:
                idx = 0
            return frames[idx % len(frames)]
        return frames[self._frame_index % len(frames)]
