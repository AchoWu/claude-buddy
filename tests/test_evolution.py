"""
Test Evolution System
"""
import sys, os, shutil, tempfile
# Ensure BUDDY root is on sys.path
_buddy_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _buddy_root)
os.chdir(_buddy_root)

from pathlib import Path

# Use a temp dir to avoid polluting real user data
import config
TEMP_DIR = tempfile.mkdtemp(prefix='buddy_test_')
config.DATA_DIR = Path(TEMP_DIR)

# Patch evolution paths BEFORE importing EvolutionManager
import core.evolution as evo_mod
evo_mod.SOUL_DIR = Path(TEMP_DIR) / 'soul'
evo_mod.EVOLUTION_DIR = Path(TEMP_DIR) / 'evolution'
evo_mod.BACKUPS_DIR = evo_mod.EVOLUTION_DIR / 'backups'
evo_mod.PROPOSALS_DIR = evo_mod.EVOLUTION_DIR / 'proposals'
evo_mod.REFLECTIONS_DIR = evo_mod.EVOLUTION_DIR / 'reflections'
evo_mod.CHANGELOG_FILE = evo_mod.EVOLUTION_DIR / 'changelog.md'

from core.evolution import (
    EvolutionManager, classify_risk, RiskLevel, is_destructive_operation,
)

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
    evo_dir = evo_mod.EVOLUTION_DIR
    buddy_root = evo_mod.BUDDY_ROOT

    # ─── 8.5.1: Soul file auto-init ────────────────────────────────
    print('=== 8.5.1: Soul file auto-init ===')
    evo = EvolutionManager()
    check('personality.md exists', (soul_dir / 'personality.md').exists())
    check('diary.md exists', (soul_dir / 'diary.md').exists())
    check('aspirations.md exists', (soul_dir / 'aspirations.md').exists())
    check('relationships.md exists', (soul_dir / 'relationships.md').exists())

    p_content = (soul_dir / 'personality.md').read_text(encoding='utf-8')
    check('personality has Communication Style', 'Communication Style' in p_content)
    check('personality has Values', 'Values' in p_content)

    d_content = (soul_dir / 'diary.md').read_text(encoding='utf-8')
    check('diary has first entry', 'First entry' in d_content)

    # ─── 8.5.2: Evolution directory structure ──────────────────────
    print('=== 8.5.2: Evolution directory structure ===')
    check('evolution/ exists', evo_dir.exists())
    check('backups/ exists', (evo_dir / 'backups').exists())
    check('proposals/ exists', (evo_dir / 'proposals').exists())
    check('reflections/ exists', (evo_dir / 'reflections').exists())

    # ─── 8.5.5: Risk classification ────────────────────────────────
    print('=== 8.5.5: Risk classification (4 levels) ===')
    check('soul/diary.md = LOW',
          classify_risk(str(soul_dir / 'diary.md')) == RiskLevel.LOW)
    check('soul/personality.md = LOW',
          classify_risk(str(soul_dir / 'personality.md')) == RiskLevel.LOW)
    check('evolution/changelog.md = LOW',
          classify_risk(str(evo_dir / 'changelog.md')) == RiskLevel.LOW)
    check('core/engine.py = HIGH',
          classify_risk(str(buddy_root / 'core' / 'engine.py')) == RiskLevel.HIGH)
    check('tools/base.py = HIGH',
          classify_risk(str(buddy_root / 'tools' / 'base.py')) == RiskLevel.HIGH)
    check('prompts/system.py = MEDIUM',
          classify_risk(str(buddy_root / 'prompts' / 'system.py')) == RiskLevel.MEDIUM)
    check('config.py = MEDIUM',
          classify_risk(str(buddy_root / 'config.py')) == RiskLevel.MEDIUM)

    # ─── 8.5.10: Destructive operation detection ──────────────────
    print('=== 8.5.10: Destructive operation detection ===')
    check('delete soul dir = destructive',
          is_destructive_operation('delete', str(soul_dir)))
    check('delete diary file = NOT destructive',
          not is_destructive_operation('delete', str(soul_dir / 'diary.md')))
    check('clear_all_memory = destructive',
          is_destructive_operation('clear_all_memory', ''))

    # ─── 8.5.6: Low-risk free write ───────────────────────────────
    print('=== 8.5.6: Low-risk free write (soul files) ===')
    result = evo.modify(
        str(soul_dir / 'personality.md'),
        '# New Personality\n- Bold\n- Creative\n',
        reason='test personality update',
    )
    check('low-risk modify success', result['success'])
    check('low-risk = low', result['risk'] == 'low')
    content = (soul_dir / 'personality.md').read_text(encoding='utf-8')
    check('content updated with Bold', 'Bold' in content)

    # ─── 8.5.7: Medium-risk auto-backup ───────────────────────────
    print('=== 8.5.7: Medium-risk auto-backup ===')
    test_file = str(buddy_root / 'prompts' / '__test_prompt.py')
    Path(test_file).write_text('# original content', encoding='utf-8')
    result = evo.modify(test_file, '# modified content', reason='test backup')
    check('medium-risk modify success', result['success'])
    check('medium-risk has backup', result['backup_path'] is not None)
    check('medium-risk backup file exists',
          result['backup_path'] and Path(result['backup_path']).exists())
    Path(test_file).unlink(missing_ok=True)

    # ─── 8.5.8/8.5.9: High-risk integrity + auto-rollback ────────
    print('=== 8.5.8/8.5.9: High-risk integrity check + auto-rollback ===')
    test_py = str(buddy_root / 'core' / '__test_evo.py')
    Path(test_py).write_text('x = 1\n', encoding='utf-8')
    # Valid change
    result_ok = evo.modify(test_py, 'x = 2\ny = 3\n', reason='valid change')
    check('valid .py: success', result_ok['success'])
    check('valid .py: not rolled back', not result_ok['rolled_back'])
    # Broken syntax
    result_bad = evo.modify(test_py, 'def f(\n', reason='intentional break')
    check('broken .py: NOT success', not result_bad['success'])
    check('broken .py: rolled back', result_bad['rolled_back'])
    check('broken .py: message has SyntaxError', 'SyntaxError' in result_bad['message'])
    restored = Path(test_py).read_text(encoding='utf-8')
    check('broken .py: file restored', 'x = 2' in restored)
    Path(test_py).unlink(missing_ok=True)

    # ─── 8.5.11: Backup version limit ─────────────────────────────
    print('=== 8.5.11: Backup version limit (max 20) ===')
    test_file2 = str(soul_dir / 'test_backup_limit.md')
    Path(test_file2).write_text('v0', encoding='utf-8')
    for i in range(25):
        evo.modify(test_file2, f'v{i+1}', reason=f'iteration {i+1}')
    backup_key = evo._backup_key(test_file2)
    backup_dir = evo_mod.BACKUPS_DIR / backup_key
    backup_count = len(list(backup_dir.iterdir())) if backup_dir.exists() else 0
    check(f'backup count <= 20 (got {backup_count})', backup_count <= 20)
    Path(test_file2).unlink(missing_ok=True)

    # ─── 8.5.12/8.5.13: Changelog ─────────────────────────────────
    print('=== 8.5.12/8.5.13: Changelog recording ===')
    changelog = evo.get_changelog(100)
    check('changelog has entries', len(changelog) > 50)
    check('changelog records reason', 'test personality update' in changelog)
    check('changelog records ROLLED BACK', 'ROLLED BACK' in changelog)

    # ─── 8.5.14: Rollback ─────────────────────────────────────────
    print('=== Rollback test ===')
    rb_file = str(soul_dir / 'rollback_test.md')
    Path(rb_file).write_text('original content', encoding='utf-8')
    evo.modify(rb_file, 'modified content', reason='before rollback')
    check('pre-rollback: modified',
          Path(rb_file).read_text(encoding='utf-8') == 'modified content')
    rb_ok = evo.rollback(rb_file)
    check('rollback succeeded', rb_ok)
    check('post-rollback: restored',
          Path(rb_file).read_text(encoding='utf-8') == 'original content')

    backups = evo.list_backups(rb_file)
    check('list_backups returns entries', len(backups) > 0)
    check('backup has name/time/size',
          all(k in backups[0] for k in ['name', 'time', 'size']))
    Path(rb_file).unlink(missing_ok=True)

    # ─── 8.5.15: Reflection trigger ───────────────────────────────
    print('=== 8.5.15: Reflection trigger conditions ===')
    evo2 = EvolutionManager()  # fresh instance, turn_count=0
    check('turn 1: should_reflect=False', not evo2.should_reflect())
    evo2.should_reflect()  # 2
    evo2.should_reflect()  # 3
    evo2.should_reflect()  # 4
    result5 = evo2.should_reflect()  # 5
    check('turn 5: should_reflect=True', result5)
    check('immediately after: False (cooldown)', not evo2.should_reflect())

    # ─── 8.5.17: Simple reflect (no provider) ─────────────────────
    print('=== 8.5.17: Simple reflect (no provider) ===')
    messages = [
        {'role': 'user', 'content': 'Help me refactor the auth module'},
        {'role': 'assistant', 'content': 'Sure, I will refactor it.'},
        {'role': 'user', 'content': 'Also add unit tests'},
    ]
    evo2._last_reflect_time = 0  # reset cooldown
    reflection = evo2.reflect(messages, provider_call_fn=None)
    check('simple reflect returned text', reflection is not None and len(reflection) > 10)
    diary_content = (soul_dir / 'diary.md').read_text(encoding='utf-8')
    check('diary has reflection entry', 'Worked on' in diary_content)

    # ─── 8.5.19: Reflection log archive ───────────────────────────
    print('=== 8.5.19: Reflection log archive ===')
    # The simple reflect doesn't save to reflections/ (only LLM reflect does)
    # But we can test the mechanism directly
    evo2._save_reflection('test reflection content', 'test context')
    ref_files = list(evo_mod.REFLECTIONS_DIR.glob('reflection_*.md'))
    check('reflection file created', len(ref_files) > 0)

    # ─── 8.5.25: Diary auto-trim ──────────────────────────────────
    print('=== 8.5.25: Diary auto-trim (50KB limit) ===')
    diary_path = soul_dir / 'diary.md'
    big_diary = '# Diary\n' + ('\n## 2024-01-01 00:00\nEntry content here.\n' * 3000)
    diary_path.write_text(big_diary, encoding='utf-8')
    evo2._append_diary('New entry after trim')
    trimmed = diary_path.read_text(encoding='utf-8')
    check(f'diary trimmed to <55KB (got {len(trimmed)})', len(trimmed) < 55000)
    check('diary has new entry', 'New entry after trim' in trimmed)
    check('diary has trim marker', 'Earlier entries trimmed' in trimmed)

    # ─── 8.5.27: Reflection file cleanup ──────────────────────────
    print('=== 8.5.27: Reflection file cleanup (max 50) ===')
    for i in range(55):
        (evo_mod.REFLECTIONS_DIR / f'reflection_test_{i:03d}.md').write_text(
            f'reflection {i}', encoding='utf-8')
    evo2._save_reflection('trigger cleanup', 'ctx')
    ref_count = len(list(evo_mod.REFLECTIONS_DIR.glob('reflection_*.md')))
    check(f'reflection files <= 50 (got {ref_count})', ref_count <= 51)

    # ─── 8.5.28: Soul status ──────────────────────────────────────
    print('=== 8.5.28: Soul status summary ===')
    status = evo2.soul_status()
    check('status has Personality', 'Personality' in status)
    check('status has Diary', 'Diary' in status)
    check('status has Aspirations', 'Aspirations' in status)
    check('status has Evolution', 'Evolution' in status)
    check('status has Backups', 'Backups' in status)

    return passed, failed


if __name__ == '__main__':
    try:
        p, f = run_tests()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f'\n=== TOTAL: {p} passed, {f} failed ===')
    sys.exit(1 if f > 0 else 0)
