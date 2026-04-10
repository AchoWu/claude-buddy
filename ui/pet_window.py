"""
Pet Main Window — frameless transparent window hosting the pixel pet sprite.
Child windows (speech bubble, chat dialog, etc.) follow the pet when dragged.
"""

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QMouseEvent
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout

from config import PET_SIZE, IDLE_TIMEOUT_SEC, DEFAULT_CHARACTER
from ui.sprite_engine import SpriteEngine


class PetState:
    IDLE = "idle"
    TALKING = "talk"
    WORKING = "work"
    SLEEPING = "sleep"
    WALKING = "walk"
    CELEBRATING = "celebrate"


class PetWindow(QWidget):
    """Frameless, transparent, always-on-top pet window."""

    clicked = pyqtSignal()           # single click → speech bubble
    double_clicked = pyqtSignal()    # double click → chat dialog
    right_clicked = pyqtSignal(QPoint)  # right click → context menu
    pet_moved = pyqtSignal(QPoint)   # emitted during drag — followers reposition

    def __init__(self, character: str = DEFAULT_CHARACTER, parent=None):
        super().__init__(parent)
        self._character = character

        # Window flags: frameless, always on top, tool window (no taskbar entry)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(PET_SIZE, PET_SIZE)

        # Position near bottom-right of screen
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width() - PET_SIZE - 60, geo.height() - PET_SIZE - 60)

        # Sprite display
        self._sprite_label = QLabel(self)
        self._sprite_label.setFixedSize(PET_SIZE, PET_SIZE)
        self._sprite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sprite_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._sprite_label.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._sprite_label)

        # Sprite engine
        self._sprite_engine = SpriteEngine(self, character=self._character)
        self._sprite_engine.frame_changed.connect(self._on_frame)
        self._sprite_engine.start()

        # Drag state
        self._drag_pos: QPoint | None = None
        self._is_dragging = False

        # Idle timeout → sleep
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(IDLE_TIMEOUT_SEC * 1000)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._idle_timer.start()

        # Current logical state
        self._pet_state = PetState.IDLE

    # ── Properties ───────────────────────────────────────────────────────
    @property
    def sprite_engine(self) -> SpriteEngine:
        return self._sprite_engine

    @property
    def pet_state(self) -> str:
        return self._pet_state

    def set_pet_state(self, state: str):
        """Change pet state and update sprite animation."""
        self._pet_state = state
        self._sprite_engine.set_state(state)
        if state != PetState.SLEEPING:
            self._reset_idle_timer()

    def set_character(self, character: str):
        """Switch to a different character's sprites."""
        self._character = character
        self._sprite_engine.set_character(character)

    def anchor_point(self) -> QPoint:
        """Global position of pet's top-center (for anchoring bubbles above)."""
        return QPoint(self.pos().x() + PET_SIZE // 2, self.pos().y())

    # ── Frame update ─────────────────────────────────────────────────────
    def _on_frame(self, pixmap: QPixmap):
        self._sprite_label.setPixmap(pixmap)

    # ── Idle timer ───────────────────────────────────────────────────────
    def _reset_idle_timer(self):
        self._idle_timer.stop()
        self._idle_timer.start()

    def _on_idle_timeout(self):
        if self._pet_state == PetState.IDLE:
            self.set_pet_state(PetState.SLEEPING)

    # ── Mouse events ─────────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            self._is_dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            distance = (new_pos - self.pos()).manhattanLength()
            if distance > 5:
                self._is_dragging = True
                self.move(new_pos)
                # Notify followers (bubble, chat, notifications) to reposition
                self.pet_moved.emit(self.anchor_point())

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_dragging:
                self.clicked.emit()
            self._drag_pos = None
            self._is_dragging = False
            self._reset_idle_timer()

            # Wake up if sleeping
            if self._pet_state == PetState.SLEEPING:
                self.set_pet_state(PetState.IDLE)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            self._reset_idle_timer()
            if self._pet_state == PetState.SLEEPING:
                self.set_pet_state(PetState.IDLE)
