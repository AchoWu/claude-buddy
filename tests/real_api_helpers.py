"""
Real API test shared helpers — engine factory, signal management, wait logic.
"""

import sys
import os
import io
import time
import tempfile

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication

_app = None

def get_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication(sys.argv)
    return _app


# ── Test framework ────────────────────────────────────────────────
PASS = 0
FAIL = 0
ERRORS = []


def run(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f'  OK  {name}')
    except Exception as e:
        FAIL += 1
        ERRORS.append((name, str(e)))
        print(f'  FAIL {name}: {e}')


def summary(suite_name):
    total = PASS + FAIL
    print(f'\n{"=" * 60}')
    if FAIL == 0:
        print(f'  {suite_name}: {total}/{total} ALL PASSED')
    else:
        print(f'  {suite_name}: {PASS}/{total} PASSED, {FAIL} FAILED')
        for n, e in ERRORS:
            print(f'    X {n}: {e}')
    print(f'{"=" * 60}')
    return FAIL == 0


def reset_counters():
    global PASS, FAIL, ERRORS
    PASS = 0
    FAIL = 0
    ERRORS = []


# ── API availability check ────────────────────────────────────────
from core.settings import Settings

_settings = Settings()


def has_api_key():
    return bool(_settings.api_key)


def skip_no_api():
    if not has_api_key():
        print("=" * 60)
        print("  SKIP: No API key configured.")
        print("=" * 60)
        sys.exit(0)


# ── Engine factory ────────────────────────────────────────────────
from core.engine import LLMEngine
from core.tool_registry import ToolRegistry
from core.task_manager import TaskManager


def make_provider():
    s = _settings
    if s.provider == "anthropic":
        from core.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=s.api_key, model=s.model)
    else:
        from core.providers.prompt_tool_provider import PromptToolProvider
        return PromptToolProvider(
            api_key=s.api_key, model=s.model, base_url=s.base_url)


def make_real_engine(with_tools=True, with_evolution=False, data_dir=None):
    """
    Create a fully-wired engine with real provider.
    Returns (engine, signal_box).
    """
    app = get_app()
    engine = LLMEngine()
    provider = make_provider()
    engine.set_provider(provider)

    if with_tools:
        frs = engine.conversation.file_read_state
        tm = TaskManager()
        registry = ToolRegistry(
            task_manager=tm, file_read_state=frs, engine=engine)
        registry.register_all_to_engine(engine)

    if with_evolution:
        from core.evolution import EvolutionManager
        if data_dir:
            import core.evolution as evo_mod
            from pathlib import Path
            evo_mod.SOUL_DIR = Path(data_dir) / "soul"
            evo_mod.EVOLUTION_DIR = Path(data_dir) / "evolution"
            evo_mod.BACKUPS_DIR = evo_mod.EVOLUTION_DIR / "backups"
            evo_mod.PROPOSALS_DIR = evo_mod.EVOLUTION_DIR / "proposals"
            evo_mod.REFLECTIONS_DIR = evo_mod.EVOLUTION_DIR / "reflections"
        evo = EvolutionManager()
        engine.set_evolution_manager(evo)

    box = SignalBox(engine)
    return engine, box


class SignalBox:
    """Collects all engine signals for test assertions."""

    def __init__(self, engine: LLMEngine):
        self.responses = []
        self.errors = []
        self.tool_starts = []
        self.tool_results = []
        self.chunks = []
        self.states = []
        self.costs = []
        self._app = get_app()
        self._engine = engine

        engine.response_text.connect(lambda t: self.responses.append(t))
        engine.error.connect(lambda e: self.errors.append(e))
        engine.tool_start.connect(lambda n, d: self.tool_starts.append((n, d)))
        engine.tool_result.connect(lambda n, o: self.tool_results.append((n, o)))
        engine.response_chunk.connect(lambda c: self.chunks.append(c))
        engine.state_changed.connect(lambda s: self.states.append(s))
        engine.cost_updated.connect(lambda c: self.costs.append(c))

    def wait(self, timeout=45):
        for _ in range(timeout * 10):
            self._app.processEvents()
            time.sleep(0.1)
            if self.responses or self.errors:
                return True
        return False

    def reset(self):
        self.responses.clear()
        self.errors.clear()
        self.tool_starts.clear()
        self.tool_results.clear()
        self.chunks.clear()
        self.states.clear()
        self.costs.clear()
        # Wait for engine to be idle before next test
        self._wait_idle()

    def _wait_idle(self, timeout=15):
        """Wait for the engine to stop running."""
        for _ in range(timeout * 10):
            self._app.processEvents()
            if not getattr(self._engine, '_is_running', False):
                return
            time.sleep(0.1)
        # Force reset if still stuck
        self._engine._is_running = False
        self._engine._abort_requested = False

    @property
    def tool_names(self):
        return [n for n, _ in self.tool_starts]

    def has_tool(self, name):
        return any(name in n for n in self.tool_names)
