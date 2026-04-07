"""
Test Soul Tools (4.13) and Soul Commands (5.11) and Prompt Injection (3.1b)
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

import core.evolution as evo_mod
evo_mod.SOUL_DIR = Path(TEMP_DIR) / 'soul'
evo_mod.EVOLUTION_DIR = Path(TEMP_DIR) / 'evolution'
evo_mod.BACKUPS_DIR = evo_mod.EVOLUTION_DIR / 'backups'
evo_mod.PROPOSALS_DIR = evo_mod.EVOLUTION_DIR / 'proposals'
evo_mod.REFLECTIONS_DIR = evo_mod.EVOLUTION_DIR / 'reflections'
evo_mod.CHANGELOG_FILE = evo_mod.EVOLUTION_DIR / 'changelog.md'

from core.evolution import EvolutionManager
from tools.soul_tools import SelfReflectTool, SelfModifyTool, DiaryWriteTool
from core.commands import CommandRegistry
from prompts.system import build_system_prompt

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
    buddy_root = evo_mod.BUDDY_ROOT

    # Create EvolutionManager (initializes soul files)
    evo = EvolutionManager()

    # ═══════════════════════════════════════════════════════════════
    # 4.13: Soul Tools
    # ═══════════════════════════════════════════════════════════════

    # ─── 4.13.1: SelfReflect ──────────────────────────────────────
    print('=== 4.13.1: SelfReflect tool ===')
    sr = SelfReflectTool()
    sr._evolution_mgr = evo

    result = sr.execute({'file': 'personality'})
    check('read personality', 'Communication Style' in result)

    result = sr.execute({'file': 'diary'})
    check('read diary', 'First entry' in result)

    result = sr.execute({'file': 'aspirations'})
    check('read aspirations', 'Aspirations' in result)

    result = sr.execute({'file': 'relationships'})
    check('read relationships', 'Partner' in result or 'partner' in result.lower())

    result = sr.execute({'file': 'all'})
    check('read all: has personality', 'personality.md' in result)
    check('read all: has diary', 'diary.md' in result)

    result = sr.execute({'file': 'status'})
    check('read status: has Personality', 'Personality' in result)
    check('read status: has Backups', 'Backups' in result)

    result = sr.execute({'file': 'changelog'})
    check('read changelog', 'changelog' in result.lower() or 'No changelog' in result)

    # SelfReflect is read-only
    check('SelfReflect.is_read_only = True', sr.is_read_only)

    # No EvolutionManager → error
    sr_no_evo = SelfReflectTool()
    result = sr_no_evo.execute({'file': 'personality'})
    check('no evo mgr: returns error', 'Error' in result)

    # ─── 4.13.2: SelfModify ──────────────────────────────────────
    print('=== 4.13.2: SelfModify tool ===')
    sm = SelfModifyTool()
    sm._evolution_mgr = evo

    # Modify personality (low risk)
    result = sm.execute({
        'file_path': 'soul/personality.md',
        'content': '# Updated Personality\n- Concise\n- Warm\n',
        'reason': 'user feedback: too verbose',
    })
    check('modify personality: success', 'risk=low' in result.lower() or 'low' in result.lower())
    content = (soul_dir / 'personality.md').read_text(encoding='utf-8')
    check('personality content updated', 'Concise' in content)

    # Modify with append mode
    result = sm.execute({
        'file_path': 'soul/personality.md',
        'content': '- Also curious\n',
        'reason': 'adding a trait',
        'operation': 'append',
    })
    content = (soul_dir / 'personality.md').read_text(encoding='utf-8')
    check('append mode: original preserved', 'Concise' in content)
    check('append mode: new content added', 'curious' in content)

    # Modify high-risk with valid code
    test_py = str(buddy_root / 'core' / '__test_sm.py')
    Path(test_py).write_text('a = 1\n', encoding='utf-8')
    result = sm.execute({
        'file_path': 'core/__test_sm.py',
        'content': 'a = 2\nb = 3\n',
        'reason': 'test high-risk modify',
    })
    check('high-risk valid: has risk indicator', 'high' in result.lower() or 'HIGH' in result)
    Path(test_py).unlink(missing_ok=True)

    # Modify high-risk with broken code
    test_py2 = str(buddy_root / 'core' / '__test_sm2.py')
    Path(test_py2).write_text('c = 1\n', encoding='utf-8')
    result = sm.execute({
        'file_path': 'core/__test_sm2.py',
        'content': 'def broken(\n',
        'reason': 'test rollback',
    })
    check('high-risk broken: ROLLED BACK', 'ROLLED BACK' in result)
    restored = Path(test_py2).read_text(encoding='utf-8')
    check('high-risk broken: file restored', 'c = 1' in restored)
    Path(test_py2).unlink(missing_ok=True)

    # SelfModify is NOT read-only
    check('SelfModify.is_read_only = False', not sm.is_read_only)

    # Empty content → error
    result = sm.execute({
        'file_path': 'soul/diary.md',
        'content': '',
        'reason': 'empty test',
    })
    check('empty content: error', 'Error' in result or 'error' in result.lower())

    # Empty file_path → error
    result = sm.execute({
        'file_path': '',
        'content': 'something',
        'reason': 'empty path test',
    })
    check('empty file_path: error', 'Error' in result or 'error' in result.lower())

    # ─── 4.13.3: DiaryWrite ──────────────────────────────────────
    print('=== 4.13.3: DiaryWrite tool ===')
    dw = DiaryWriteTool()
    dw._evolution_mgr = evo

    result = dw.execute({'entry': 'Today I learned that my partner prefers concise responses.'})
    check('diary write: success', 'Diary entry saved' in result)

    diary_content = (soul_dir / 'diary.md').read_text(encoding='utf-8')
    check('diary has new entry', 'concise responses' in diary_content)

    # Empty entry → error
    result = dw.execute({'entry': ''})
    check('empty entry: error', 'Error' in result or 'error' in result.lower())

    # DiaryWrite is NOT read-only
    check('DiaryWrite.is_read_only = False', not dw.is_read_only)

    # No EvolutionManager → error
    dw_no_evo = DiaryWriteTool()
    result = dw_no_evo.execute({'entry': 'test'})
    check('no evo mgr: returns error', 'Error' in result)

    # ═══════════════════════════════════════════════════════════════
    # 5.11: Soul Commands
    # ═══════════════════════════════════════════════════════════════

    print('=== 5.11.1: /soul command ===')
    cr = CommandRegistry()
    ctx = {'evolution_mgr': evo}

    result = cr.execute('/soul', ctx)
    check('/soul: has Personality', 'Personality' in result)
    check('/soul: has Diary', 'Diary' in result)

    result = cr.execute('/soul personality', ctx)
    check('/soul personality: has content', 'Concise' in result)

    result = cr.execute('/soul all', ctx)
    check('/soul all: has personality.md', 'personality.md' in result)

    print('=== 5.11.2: /diary command ===')
    result = cr.execute('/diary', ctx)
    check('/diary: has content', len(result) > 20)

    result = cr.execute('/diary last', ctx)
    check('/diary last: has ## header', '##' in result or 'concise' in result.lower())

    print('=== 5.11.3: /evolve command ===')
    result = cr.execute('/evolve', ctx)
    check('/evolve: has changelog content', len(result) > 20)

    result = cr.execute('/evolve 5', ctx)
    check('/evolve 5: returns something', len(result) > 10)

    print('=== 5.11.4: /rollback command ===')
    result = cr.execute('/rollback', ctx)
    check('/rollback (no args): shows usage', 'Usage' in result)

    result = cr.execute('/rollback soul/personality.md', ctx)
    check('/rollback personality: executed',
          'Rolled back' in result or 'No backups' in result or 'rollback' in result.lower())

    # ═══════════════════════════════════════════════════════════════
    # 3.1b: System Prompt Soul Injection
    # ═══════════════════════════════════════════════════════════════

    print('=== 3.1b: System prompt soul injection ===')
    prompt = build_system_prompt()
    check('prompt has # Soul section', '# Soul' in prompt)
    check('prompt has SelfReflect mention', 'SelfReflect' in prompt)
    check('prompt has SelfModify mention', 'SelfModify' in prompt)
    check('prompt has DiaryWrite mention', 'DiaryWrite' in prompt)
    check('prompt has safety guarantees', 'auto-rollback' in prompt.lower() or 'auto-backup' in prompt.lower())
    check('prompt has guiding principles', 'Guiding Principles' in prompt)

    # Check that personality content is injected
    check('prompt has personality content', 'Concise' in prompt or 'personality' in prompt.lower())

    # Check section ordering: Soul comes after Identity, before System Rules
    identity_pos = prompt.find('# Identity')
    soul_pos = prompt.find('# Soul')
    rules_pos = prompt.find('# System Rules')
    check('Soul section after Identity', soul_pos > identity_pos)
    check('Soul section before System Rules', soul_pos < rules_pos)

    # Check tool details include soul tools
    check('tool details has SelfReflect', '## SelfReflect' in prompt)
    check('tool details has SelfModify', '## SelfModify' in prompt)
    check('tool details has DiaryWrite', '## DiaryWrite' in prompt)

    # ═══════════════════════════════════════════════════════════════
    # E2E.8: Full soul view chain
    # ═══════════════════════════════════════════════════════════════

    print('=== E2E.8: Soul view full chain ===')
    soul_result = cr.execute('/soul', ctx)
    diary_result = cr.execute('/diary last', ctx)
    evolve_result = cr.execute('/evolve', ctx)
    check('soul view chain: /soul returns', len(soul_result) > 20)
    check('soul view chain: /diary returns', len(diary_result) > 10)
    check('soul view chain: /evolve returns', len(evolve_result) > 10)

    return passed, failed


if __name__ == '__main__':
    try:
        p, f = run_tests()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        # Cleanup any test files in BUDDY/core/
        for pat in ['__test_sm*.py']:
            for fp in Path(_buddy_root).glob(f'core/{pat}'):
                fp.unlink(missing_ok=True)
    print(f'\n=== TOTAL: {p} passed, {f} failed ===')
    sys.exit(1 if f > 0 else 0)
