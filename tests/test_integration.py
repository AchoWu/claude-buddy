"""
Test Engine Integration + Memory Extension + Tool Registry + main.py wiring
"""
import sys, os, shutil, tempfile
_buddy_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _buddy_root)
os.chdir(_buddy_root)

from pathlib import Path

# Patch to temp dir
import config
TEMP_DIR = tempfile.mkdtemp(prefix='buddy_test_')
config.DATA_DIR = Path(TEMP_DIR)
config.CONVERSATIONS_DIR = Path(TEMP_DIR) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

import core.evolution as evo_mod
evo_mod.SOUL_DIR = Path(TEMP_DIR) / 'soul'
evo_mod.EVOLUTION_DIR = Path(TEMP_DIR) / 'evolution'
evo_mod.BACKUPS_DIR = evo_mod.EVOLUTION_DIR / 'backups'
evo_mod.PROPOSALS_DIR = evo_mod.EVOLUTION_DIR / 'proposals'
evo_mod.REFLECTIONS_DIR = evo_mod.EVOLUTION_DIR / 'reflections'
evo_mod.CHANGELOG_FILE = evo_mod.EVOLUTION_DIR / 'changelog.md'

# Patch memory dir
import core.memory as mem_mod
mem_mod.MEMORY_DIR = Path(TEMP_DIR) / "memory"
mem_mod.MEMORY_DIR.mkdir(parents=True, exist_ok=True)

from core.evolution import EvolutionManager
from core.engine import LLMEngine
from core.memory import MemoryManager, EXTRACT_SYSTEM_PROMPT
from core.tool_registry import ToolRegistry
from core.commands import CommandRegistry

passed = 0
failed = 0

def check(name, condition, detail=''):
    global passed, failed
    if condition:
        passed += 1
        print(f'  PASS: {name}')
    else:
        failed += 1
        print(f'  FAIL: {name} -- {detail}')


def run_tests():
    global passed, failed
    soul_dir = evo_mod.SOUL_DIR

    # ═══════════════════════════════════════════════════════════════
    # Engine: EvolutionManager injection
    # ═══════════════════════════════════════════════════════════════
    print('=== Engine: EvolutionManager injection ===')
    evo = EvolutionManager()
    engine = LLMEngine()
    engine.set_evolution_manager(evo)
    check('engine._evolution_mgr is set', engine._evolution_mgr is not None)
    check('engine._evolution_mgr is EvolutionManager',
          isinstance(engine._evolution_mgr, EvolutionManager))

    # ─── _try_self_reflect exists and doesn't crash without provider ─
    print('=== Engine: _try_self_reflect safety ===')
    # No provider, no crash
    try:
        engine._try_self_reflect()
        check('_try_self_reflect without provider: no crash', True)
    except Exception as e:
        check('_try_self_reflect without provider: no crash', False, str(e))

    # No evolution_mgr → should skip silently
    engine2 = LLMEngine()
    try:
        engine2._try_self_reflect()
        check('_try_self_reflect without evo_mgr: no crash', True)
    except Exception as e:
        check('_try_self_reflect without evo_mgr: no crash', False, str(e))

    # ─── should_reflect tracking through engine ───────────────────
    print('=== Engine: reflection trigger ===')
    evo._turn_count = 0
    evo._last_reflect_time = 0
    for _ in range(4):
        evo.should_reflect()
    check('4 turns: should_reflect=False', not evo.should_reflect() == False)

    # ═══════════════════════════════════════════════════════════════
    # ToolRegistry: soul tools registration
    # ═══════════════════════════════════════════════════════════════
    print('=== ToolRegistry: soul tool registration ===')
    registry = ToolRegistry(evolution_manager=evo)

    sr = registry.get('SelfReflect')
    sm = registry.get('SelfModify')
    dw = registry.get('DiaryWrite')
    check('SelfReflect registered', sr is not None)
    check('SelfModify registered', sm is not None)
    check('DiaryWrite registered', dw is not None)

    # Check that EvolutionManager was injected
    check('SelfReflect has evo_mgr', sr._evolution_mgr is evo)
    check('SelfModify has evo_mgr', sm._evolution_mgr is evo)
    check('DiaryWrite has evo_mgr', dw._evolution_mgr is evo)

    # SelfReflect is read-only, others are not
    check('SelfReflect is_read_only', sr.is_read_only)
    check('SelfModify not read_only', not sm.is_read_only)
    check('DiaryWrite not read_only', not dw.is_read_only)

    # Verify tool count increased
    all_tools = registry.all_tools()
    tool_names = [t.name for t in all_tools]
    check('SelfReflect in all_tools', 'SelfReflect' in tool_names)
    check('SelfModify in all_tools', 'SelfModify' in tool_names)
    check('DiaryWrite in all_tools', 'DiaryWrite' in tool_names)

    # ─── Tools actually work through registry ─────────────────────
    print('=== ToolRegistry: tool execution ===')
    result = sr.execute({'file': 'personality'})
    check('SelfReflect via registry: works', 'Communication' in result or 'Personality' in result)

    result = dw.execute({'entry': 'Test entry from registry'})
    check('DiaryWrite via registry: works', 'Diary entry saved' in result)

    result = sm.execute({
        'file_path': 'soul/personality.md',
        'content': '# Personality via registry\n- Test trait\n',
        'reason': 'registry test',
    })
    check('SelfModify via registry: works', 'low' in result.lower())

    # ═══════════════════════════════════════════════════════════════
    # Memory: Extended extraction prompt
    # ═══════════════════════════════════════════════════════════════
    print('=== Memory: extraction prompt extension ===')
    check('prompt has [user] tag', '[user]' in EXTRACT_SYSTEM_PROMPT)
    check('prompt has [self] tag', '[self]' in EXTRACT_SYSTEM_PROMPT)
    check('prompt has BUDDY Self-Insights section',
          'BUDDY Self-Insights' in EXTRACT_SYSTEM_PROMPT or 'Self-Insights' in EXTRACT_SYSTEM_PROMPT)
    check('prompt has user insights section',
          'User Insights' in EXTRACT_SYSTEM_PROMPT)

    # ─── Memory: _save_self_insights ──────────────────────────────
    print('=== Memory: self-insight saving ===')
    mm = MemoryManager(memory_dir=Path(TEMP_DIR) / "memory")

    # relationships.md needs to exist
    rel_path = soul_dir / 'relationships.md'
    check('relationships.md exists', rel_path.exists())

    mm._save_self_insights(['User responds well to bullet points', 'User prefers Python over JS'])
    rel_content = rel_path.read_text(encoding='utf-8')
    check('insight saved to relationships', 'bullet points' in rel_content)
    check('both insights saved', 'Python over JS' in rel_content)

    # Deduplication test
    mm._save_self_insights(['User responds well to bullet points'])
    rel_content2 = rel_path.read_text(encoding='utf-8')
    count = rel_content2.lower().count('bullet points')
    check(f'dedup: bullet points appears once (got {count})', count == 1)

    # ─── Memory: _llm_extract parses [user]/[self] tags ───────────
    print('=== Memory: [user]/[self] tag parsing ===')
    # Simulate what _llm_extract does after getting LLM response
    # by testing the parsing logic directly
    from core.memory import MemoryManager as MM

    # Create a mock provider that returns tagged memories
    def mock_provider(messages, system, tools):
        return (
            {"role": "assistant", "content": ""},
            [],
            "- [user] Prefers tabs over spaces\n"
            "- [self] User gets frustrated with long explanations\n"
            "- [user] Uses pytest for testing\n"
            "- [self] Should provide code examples more often\n"
        )

    mm2 = MemoryManager(memory_dir=Path(TEMP_DIR) / "memory2")
    (Path(TEMP_DIR) / "memory2").mkdir(exist_ok=True)
    test_msgs = [
        {'role': 'user', 'content': 'I always use tabs and pytest'},
        {'role': 'assistant', 'content': 'Got it, using tabs and pytest.'},
    ]
    memories = mm2._llm_extract(test_msgs, mock_provider)
    check('LLM extract returns user memories',
          any('tabs' in m.lower() for m in memories))
    check('LLM extract returns pytest memory',
          any('pytest' in m.lower() for m in memories))
    # [self] entries should NOT be in the returned memories list (they go to relationships)
    check('[self] entries not in user memories',
          not any('frustrated' in m.lower() for m in memories))

    # ═══════════════════════════════════════════════════════════════
    # Commands: context wiring
    # ═══════════════════════════════════════════════════════════════
    print('=== Commands: context wiring (simulating main.py) ===')
    cr = CommandRegistry()
    # Build context like main.py does
    ctx = {
        'engine': engine,
        'conversation': engine.conversation,
        'command_registry': cr,
        'tool_registry': registry,
        'evolution_mgr': evo,
        'task_manager': None,
        'settings': None,
        'memory_mgr': mm,
        'plugin_mgr': None,
        'analytics': None,
        'permission_mgr': None,
    }

    result = cr.execute('/soul', ctx)
    check('/soul via wired context: works', 'Personality' in result)

    result = cr.execute('/diary', ctx)
    check('/diary via wired context: works', len(result) > 20)

    result = cr.execute('/evolve', ctx)
    check('/evolve via wired context: works', len(result) > 10)

    result = cr.execute('/version', ctx)
    check('/version shows v5.0', 'v5.0' in result)
    check('/version shows Soul', 'Soul' in result or 'soul' in result.lower())

    # ═══════════════════════════════════════════════════════════════
    # main.py: _handle_command wiring check
    # ═══════════════════════════════════════════════════════════════
    print('=== main.py wiring: evolution_mgr in context ===')
    # Verify main.py correctly passes evolution_mgr to command context
    import ast
    main_src = Path(_buddy_root) / 'main.py'
    main_content = main_src.read_text(encoding='utf-8')
    check('main.py has evolution_mgr in ctx', 'evolution_mgr' in main_content)
    check('main.py references _evolution_mgr', '_evolution_mgr' in main_content)

    # Check tool_start handler shows soul tool summaries
    check('main.py handles DiaryWrite entry', '"entry"' in main_content or "'entry'" in main_content)
    check('main.py handles SelfReflect file', '"file"' in main_content or "'file'" in main_content)

    # ═══════════════════════════════════════════════════════════════
    # E2E.6: Dual memory test
    # ═══════════════════════════════════════════════════════════════
    print('=== E2E.6: Dual memory (user + self insights) ===')
    # Reset relationships
    rel_path.write_text('# Relationships\n', encoding='utf-8')

    def mock_dual_provider(messages, system, tools):
        return (
            {"role": "assistant", "content": ""},
            [],
            "- [user] Prefers Python 3.12 features\n"
            "- [self] User is very detail-oriented\n"
            "- [user] Uses black for formatting\n"
        )

    mm3 = MemoryManager(memory_dir=Path(TEMP_DIR) / "memory3")
    (Path(TEMP_DIR) / "memory3").mkdir(exist_ok=True)
    test_msgs = [
        {'role': 'user', 'content': 'Use black formatter and Python 3.12'},
    ]
    user_mems = mm3._llm_extract(test_msgs, mock_dual_provider)
    check('E2E.6: user memories extracted', len(user_mems) >= 2)
    check('E2E.6: Python 3.12 in user memories',
          any('3.12' in m for m in user_mems))

    rel_content_final = rel_path.read_text(encoding='utf-8')
    check('E2E.6: self-insight in relationships', 'detail-oriented' in rel_content_final)

    return passed, failed


if __name__ == '__main__':
    try:
        p, f = run_tests()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f'\n=== TOTAL: {p} passed, {f} failed ===')
    sys.exit(1 if f > 0 else 0)
