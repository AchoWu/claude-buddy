"""UI tests for PetWindow (ui/pet_window.py)."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
from ui.pet_window import PetWindow, PetState

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def test_initial_state_is_idle():
    pet = PetWindow()
    assert pet.pet_state == "idle", f"Expected 'idle', got '{pet.pet_state}'"

def test_set_pet_state_work():
    pet = PetWindow()
    pet.set_pet_state("work")
    assert pet.pet_state == "work", f"Expected 'work', got '{pet.pet_state}'"

def test_single_click_emits_clicked():
    pet = PetWindow()
    pet.show()
    captured = []
    pet.clicked.connect(lambda: captured.append(True))
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert len(captured) >= 1, f"clicked signal not emitted, captured={captured}"

def test_double_click_emits_double_clicked():
    pet = PetWindow()
    pet.show()
    captured = []
    pet.double_clicked.connect(lambda: captured.append(True))
    QTest.mouseDClick(pet, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert len(captured) >= 1, f"double_clicked signal not emitted, captured={captured}"

def test_right_click_emits_right_clicked():
    pet = PetWindow()
    pet.show()
    captured = []
    pet.right_clicked.connect(lambda pt: captured.append(pt))
    QTest.mouseClick(pet, Qt.MouseButton.RightButton)
    app.processEvents()
    assert len(captured) >= 1, f"right_clicked signal not emitted, captured={captured}"

def test_window_has_frameless_hint():
    pet = PetWindow()
    flags = pet.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint, "Missing FramelessWindowHint"

def test_window_has_translucent_background():
    pet = PetWindow()
    assert pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), "Missing WA_TranslucentBackground"

def test_sprite_engine_connected():
    pet = PetWindow()
    assert pet._sprite_engine is not None, "_sprite_engine is None"
    assert hasattr(pet._sprite_engine, 'frame_changed'), "SpriteEngine missing frame_changed signal"

def test_set_pet_state_sleep():
    pet = PetWindow()
    pet.set_pet_state("sleep")
    assert pet.pet_state == "sleep", f"Expected 'sleep', got '{pet.pet_state}'"

def test_anchor_point_returns_qpoint():
    pet = PetWindow()
    anchor = pet.anchor_point()
    assert isinstance(anchor, QPoint), f"Expected QPoint, got {type(anchor)}"

def test_pet_state_property_starts_idle():
    pet = PetWindow()
    assert pet.pet_state == PetState.IDLE, f"Expected PetState.IDLE, got '{pet.pet_state}'"

def test_cycle_all_states():
    pet = PetWindow()
    all_states = [PetState.IDLE, PetState.TALKING, PetState.WORKING,
                  PetState.SLEEPING, PetState.WALKING, PetState.CELEBRATING]
    for state in all_states:
        pet.set_pet_state(state)
        assert pet.pet_state == state, f"Expected '{state}', got '{pet.pet_state}'"


if __name__ == "__main__":
    print("=== test_ui_pet_window ===")
    run("initial_state_is_idle", test_initial_state_is_idle)
    run("set_pet_state_work", test_set_pet_state_work)
    run("single_click_emits_clicked", test_single_click_emits_clicked)
    run("double_click_emits_double_clicked", test_double_click_emits_double_clicked)
    run("right_click_emits_right_clicked", test_right_click_emits_right_clicked)
    run("window_has_frameless_hint", test_window_has_frameless_hint)
    run("window_has_translucent_background", test_window_has_translucent_background)
    run("sprite_engine_connected", test_sprite_engine_connected)
    run("set_pet_state_sleep", test_set_pet_state_sleep)
    run("anchor_point_returns_qpoint", test_anchor_point_returns_qpoint)
    run("pet_state_property_starts_idle", test_pet_state_property_starts_idle)
    run("cycle_all_states", test_cycle_all_states)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
