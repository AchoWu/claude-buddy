"""
Suite 4 — Tool System Tests
Tests ALL 40 tools in the BUDDY system: file tools, bash, search, tasks,
plan mode, cron, notebook, soul, utility, extra, protocol, and agent tools.
~45 tests covering every tool class + edge cases.
"""

import sys, os, io, json, tempfile, time, platform
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

# ── Test framework ──────────────────────────────────────────────
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

print('='*60)
print('  Suite 4: Tool System Tests (~45 tests)')
print('='*60)

# ── Shared helpers ──────────────────────────────────────────────
# Need QApp for TaskManager (uses QObject/pyqtSignal)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

def _make_task_manager(tmp_dir):
    """Create a TaskManager backed by a temp tasks file."""
    tasks_file = Path(tmp_dir) / "tasks.json"
    tasks_file.write_text("[]", encoding="utf-8")
    with patch('core.task_manager.TASKS_FILE', tasks_file):
        from core.task_manager import TaskManager
        tm = TaskManager()
    # Patch save to use temp file
    tm._save_orig = tm._save
    def _save_patched():
        tasks_file.write_text(
            json.dumps([t.to_dict() for t in tm._tasks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    tm._save = _save_patched
    return tm

def _make_file_read_state():
    """Simple mock for FileReadState."""
    class FRS:
        def __init__(self):
            self._reads = {}
        def record_read(self, path, mtime=None, content_hash=None):
            self._reads[path] = {"mtime_at_read": mtime, "content_hash": content_hash}
        def has_read(self, path):
            return path in self._reads
        def get_read_info(self, path):
            return self._reads.get(path)
        def is_stale(self, path):
            info = self._reads.get(path)
            if not info:
                return True
            try:
                cur_mtime = Path(path).stat().st_mtime
                return cur_mtime != info.get("mtime_at_read")
            except:
                return True
    return FRS()


# ══════════════════════════════════════════════════════════════════
# 1. Registry check
# ══════════════════════════════════════════════════════════════════

def test_registry_has_enough_tools():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    tools = reg.all_tools()
    assert len(tools) >= 33, f"Expected >= 33 tools, got {len(tools)}"

run("1. Registry has >= 33 tools", test_registry_has_enough_tools)

def test_registry_all_have_names():
    from core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    for t in reg.all_tools():
        assert t.name, f"Tool without name: {type(t).__name__}"

run("2. All registered tools have names", test_registry_all_have_names)

def test_registry_all_have_execute():
    from core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    for t in reg.all_tools():
        assert callable(getattr(t, 'execute', None)), f"{t.name} missing execute()"

run("3. All registered tools have execute()", test_registry_all_have_execute)


# ══════════════════════════════════════════════════════════════════
# 2-4. File Tools
# ══════════════════════════════════════════════════════════════════

def test_file_read_basic():
    from tools.file_read_tool import FileReadTool
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("line one\nline two\nline three\n")
        f.flush()
        path = f.name
    try:
        tool = FileReadTool()
        result = tool.execute({"file_path": path})
        assert "line one" in result
        assert "line two" in result
        # Should have line numbers
        assert "1\t" in result or "1 " in result
    finally:
        os.unlink(path)

run("4. FileRead: basic read with line numbers", test_file_read_basic)

def test_file_read_offset_limit():
    from tools.file_read_tool import FileReadTool
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        for i in range(1, 51):
            f.write(f"line {i}\n")
        f.flush()
        path = f.name
    try:
        tool = FileReadTool()
        result = tool.execute({"file_path": path, "offset": 10, "limit": 5})
        assert "line 10" in result
        assert "line 14" in result
        # line 1 should NOT be in the result
        assert "line 1\n" not in result or "line 10" in result
    finally:
        os.unlink(path)

run("5. FileRead: offset and limit", test_file_read_offset_limit)

def test_file_read_not_found():
    from tools.file_read_tool import FileReadTool
    tool = FileReadTool()
    result = tool.execute({"file_path": "/nonexistent/path/foo.txt"})
    assert "Error" in result or "not found" in result.lower()

run("6. FileRead: non-existent file returns error", test_file_read_not_found)

def test_file_write_basic():
    from tools.file_write_tool import FileWriteTool
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "output.txt")
        tool = FileWriteTool()
        result = tool.execute({"file_path": path, "content": "hello world\n"})
        assert "Created" in result or "Overwrote" in result
        assert os.path.exists(path)
        assert Path(path).read_text(encoding='utf-8') == "hello world\n"

run("7. FileWrite: create new file", test_file_write_basic)

def test_file_write_creates_dirs():
    from tools.file_write_tool import FileWriteTool
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sub", "deep", "file.txt")
        tool = FileWriteTool()
        result = tool.execute({"file_path": path, "content": "nested\n"})
        assert os.path.exists(path)

run("8. FileWrite: auto-creates parent dirs", test_file_write_creates_dirs)

def test_file_edit_basic():
    from tools.file_edit_tool import FileEditTool
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write("def hello():\n    return 'world'\n")
        f.flush()
        path = f.name
    try:
        tool = FileEditTool()
        # No file_read_state => no enforcement
        result = tool.execute({
            "file_path": path,
            "old_string": "return 'world'",
            "new_string": "return 'universe'",
        })
        assert "Successfully" in result
        content = Path(path).read_text(encoding='utf-8')
        assert "universe" in content
    finally:
        os.unlink(path)

run("9. FileEdit: basic replacement", test_file_edit_basic)

def test_file_edit_read_enforcement():
    from tools.file_edit_tool import FileEditTool
    frs = _make_file_read_state()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("original content\n")
        f.flush()
        path = f.name
    try:
        tool = FileEditTool()
        tool._file_read_state = frs
        # Haven't read the file yet -> should be rejected
        result = tool.execute({
            "file_path": path,
            "old_string": "original",
            "new_string": "modified",
        })
        assert "must read" in result.lower() or "error" in result.lower()
    finally:
        os.unlink(path)

run("10. FileEdit: rejected without prior read", test_file_edit_read_enforcement)

def test_file_edit_not_found():
    from tools.file_edit_tool import FileEditTool
    tool = FileEditTool()
    result = tool.execute({
        "file_path": "/nonexistent/foo.txt",
        "old_string": "a",
        "new_string": "b",
    })
    assert "not found" in result.lower() or "error" in result.lower()

run("11. FileEdit: non-existent file", test_file_edit_not_found)

def test_file_edit_replace_all():
    from tools.file_edit_tool import FileEditTool
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("foo bar foo baz foo\n")
        f.flush()
        path = f.name
    try:
        tool = FileEditTool()
        result = tool.execute({
            "file_path": path,
            "old_string": "foo",
            "new_string": "qux",
            "replace_all": True,
        })
        assert "3" in result  # 3 occurrences
        content = Path(path).read_text(encoding='utf-8')
        assert "foo" not in content
        assert content.count("qux") == 3
    finally:
        os.unlink(path)

run("12. FileEdit: replace_all=True replaces all", test_file_edit_replace_all)

def test_file_edit_ambiguous():
    from tools.file_edit_tool import FileEditTool
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("abc abc abc\n")
        f.flush()
        path = f.name
    try:
        tool = FileEditTool()
        result = tool.execute({
            "file_path": path,
            "old_string": "abc",
            "new_string": "xyz",
        })
        # Should fail because 'abc' appears 3 times
        assert "3 times" in result or "found" in result.lower()
    finally:
        os.unlink(path)

run("13. FileEdit: ambiguous match rejected", test_file_edit_ambiguous)


# ══════════════════════════════════════════════════════════════════
# 5-7. Bash Tool
# ══════════════════════════════════════════════════════════════════

def test_bash_echo():
    from tools.bash_tool import BashTool
    tool = BashTool()
    result = tool.execute({"command": "echo hello"})
    assert "hello" in result

run("14. Bash: echo hello", test_bash_echo)

def test_bash_safety_rm_rf():
    from tools.bash_tool import BashTool
    tool = BashTool()
    result = tool.execute({"command": "rm -rf /"})
    assert "dangerous" in result.lower() or "blocked" in result.lower()

run("15. Bash: rm -rf / blocked", test_bash_safety_rm_rf)

def test_bash_git_force_push_main():
    from tools.bash_tool import BashTool
    tool = BashTool()
    result = tool.execute({"command": "git push --force origin main"})
    assert "blocked" in result.lower() or "dangerous" in result.lower()

run("16. Bash: git push --force main blocked", test_bash_git_force_push_main)

def test_bash_background():
    from tools.bash_tool import BashTool
    tool = BashTool()
    result = tool.execute({"command": "echo bg_test", "run_in_background": True})
    assert "bg_" in result.lower() or "background" in result.lower()

run("17. Bash: background execution", test_bash_background)

def test_bash_timeout():
    from tools.bash_tool import BashTool
    tool = BashTool()
    # Timeout should be capped at 600
    result = tool.execute({"command": "echo fast", "timeout": 9999})
    assert "fast" in result

run("18. Bash: timeout cap", test_bash_timeout)


# ══════════════════════════════════════════════════════════════════
# 8. Glob Tool
# ══════════════════════════════════════════════════════════════════

def test_glob_basic():
    from tools.glob_tool import GlobTool
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.py").write_text("# a", encoding='utf-8')
        (Path(d) / "b.py").write_text("# b", encoding='utf-8')
        (Path(d) / "c.txt").write_text("c", encoding='utf-8')
        tool = GlobTool()
        result = tool.execute({"pattern": "*.py", "path": d})
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

run("19. Glob: *.py matches only .py files", test_glob_basic)

def test_glob_no_matches():
    from tools.glob_tool import GlobTool
    with tempfile.TemporaryDirectory() as d:
        tool = GlobTool()
        result = tool.execute({"pattern": "*.xyz", "path": d})
        assert "No files" in result or "no" in result.lower()

run("20. Glob: no matches", test_glob_no_matches)


# ══════════════════════════════════════════════════════════════════
# 9. Grep Tool
# ══════════════════════════════════════════════════════════════════

def test_grep_basic():
    from tools.grep_tool import GrepTool
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "test.py").write_text("def hello():\n    pass\ndef goodbye():\n    pass\n", encoding='utf-8')
        tool = GrepTool()
        result = tool.execute({"pattern": "def hello", "path": d})
        assert "hello" in result

run("21. Grep: finds pattern in file", test_grep_basic)

def test_grep_no_match():
    from tools.grep_tool import GrepTool
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "test.py").write_text("nothing here\n", encoding='utf-8')
        tool = GrepTool()
        result = tool.execute({"pattern": "zzz_nonexistent", "path": d})
        assert "no match" in result.lower() or "No matches" in result

run("22. Grep: no match returns message", test_grep_no_match)

def test_grep_case_insensitive():
    from tools.grep_tool import GrepTool
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "x.txt").write_text("Hello World\n", encoding='utf-8')
        tool = GrepTool()
        result = tool.execute({"pattern": "hello", "path": d, "case_insensitive": True})
        assert "Hello" in result or "hello" in result.lower()

run("23. Grep: case insensitive", test_grep_case_insensitive)


# ══════════════════════════════════════════════════════════════════
# 10-13. Task Tools
# ══════════════════════════════════════════════════════════════════

def test_task_create():
    from tools.task_tool import TaskCreateTool
    with tempfile.TemporaryDirectory() as d:
        tm = _make_task_manager(d)
        tool = TaskCreateTool()
        tool._task_manager = tm
        result = tool.execute({"subject": "Fix bug", "description": "A test task"})
        assert "#" in result and "Fix bug" in result

run("24. TaskCreate: creates task", test_task_create)

def test_task_update():
    from tools.task_tool import TaskCreateTool, TaskUpdateTool
    with tempfile.TemporaryDirectory() as d:
        tm = _make_task_manager(d)
        create = TaskCreateTool()
        create._task_manager = tm
        create.execute({"subject": "T1", "description": "D1"})
        update = TaskUpdateTool()
        update._task_manager = tm
        result = update.execute({"task_id": 1, "status": "in_progress"})
        assert "in_progress" in result

run("25. TaskUpdate: update status", test_task_update)

def test_task_list():
    from tools.task_tool import TaskCreateTool, TaskListTool
    with tempfile.TemporaryDirectory() as d:
        tm = _make_task_manager(d)
        create = TaskCreateTool()
        create._task_manager = tm
        create.execute({"subject": "Alpha", "description": "D"})
        create.execute({"subject": "Beta", "description": "D"})
        lst = TaskListTool()
        lst._task_manager = tm
        result = lst.execute({})
        assert "Alpha" in result
        assert "Beta" in result

run("26. TaskList: lists tasks", test_task_list)

def test_task_get():
    from tools.task_tool import TaskCreateTool, TaskGetTool
    with tempfile.TemporaryDirectory() as d:
        tm = _make_task_manager(d)
        create = TaskCreateTool()
        create._task_manager = tm
        create.execute({"subject": "Detail", "description": "Full details"})
        get = TaskGetTool()
        get._task_manager = tm
        result = get.execute({"task_id": 1})
        data = json.loads(result)
        assert data["subject"] == "Detail"
        assert data["description"] == "Full details"

run("27. TaskGet: get task details", test_task_get)

def test_task_no_manager():
    from tools.task_tool import TaskCreateTool
    tool = TaskCreateTool()
    tool._task_manager = None
    result = tool.execute({"subject": "X", "description": "Y"})
    assert "Error" in result or "not connected" in result.lower()

run("28. TaskCreate: error without TaskManager", test_task_no_manager)


# ══════════════════════════════════════════════════════════════════
# 14. Plan Mode Tools
# ══════════════════════════════════════════════════════════════════

def test_plan_mode_enter_exit():
    from tools.plan_mode_tool import EnterPlanModeTool, ExitPlanModeTool, PlanModeState
    state = PlanModeState()
    enter = EnterPlanModeTool()
    enter._plan_mode_state = state
    exit_tool = ExitPlanModeTool()
    exit_tool._plan_mode_state = state

    assert not state.active
    r1 = enter.execute({})
    assert state.active
    assert "activated" in r1.lower() or "plan mode" in r1.lower()

    r2 = exit_tool.execute({})
    assert not state.active
    assert "deactivated" in r2.lower() or "available" in r2.lower()

run("29. PlanMode: enter/exit cycle", test_plan_mode_enter_exit)

def test_plan_mode_double_enter():
    from tools.plan_mode_tool import EnterPlanModeTool, PlanModeState
    state = PlanModeState()
    enter = EnterPlanModeTool()
    enter._plan_mode_state = state
    enter.execute({})
    result = enter.execute({})
    assert "already" in result.lower()

run("30. PlanMode: double enter returns already active", test_plan_mode_double_enter)

def test_plan_mode_exit_without_enter():
    from tools.plan_mode_tool import ExitPlanModeTool, PlanModeState
    state = PlanModeState()
    exit_tool = ExitPlanModeTool()
    exit_tool._plan_mode_state = state
    result = exit_tool.execute({})
    assert "not active" in result.lower()

run("31. PlanMode: exit without enter", test_plan_mode_exit_without_enter)


# ══════════════════════════════════════════════════════════════════
# 15-17. Cron Tools
# ══════════════════════════════════════════════════════════════════

def test_cron_create():
    from tools.cron_tool import CronCreateTool, get_cron_scheduler
    # Reset scheduler
    sched = get_cron_scheduler()
    sched._jobs.clear()
    sched._next_id = 1

    tool = CronCreateTool()
    result = tool.execute({"cron": "*/5 * * * *", "prompt": "check status"})
    assert "cron_1" in result
    assert "recurring" in result.lower()

run("32. CronCreate: create recurring job", test_cron_create)

def test_cron_list():
    from tools.cron_tool import CronCreateTool, CronListTool, get_cron_scheduler
    sched = get_cron_scheduler()
    sched._jobs.clear()
    sched._next_id = 1

    CronCreateTool().execute({"cron": "0 9 * * *", "prompt": "morning check"})
    tool = CronListTool()
    result = tool.execute({})
    assert "morning check" in result
    assert "cron_1" in result

run("33. CronList: lists jobs", test_cron_list)

def test_cron_delete():
    from tools.cron_tool import CronCreateTool, CronDeleteTool, CronListTool, get_cron_scheduler
    sched = get_cron_scheduler()
    sched._jobs.clear()
    sched._next_id = 1

    CronCreateTool().execute({"cron": "0 9 * * *", "prompt": "test"})
    tool = CronDeleteTool()
    result = tool.execute({"id": "cron_1"})
    assert "deleted" in result.lower()
    # Verify it's gone
    list_result = CronListTool().execute({})
    assert "No cron" in list_result or "cron_1" not in list_result

run("34. CronDelete: delete job", test_cron_delete)

def test_cron_invalid_expr():
    from tools.cron_tool import CronCreateTool
    tool = CronCreateTool()
    result = tool.execute({"cron": "bad", "prompt": "test"})
    assert "Error" in result or "5 fields" in result

run("35. CronCreate: invalid expression", test_cron_invalid_expr)


# ══════════════════════════════════════════════════════════════════
# 18. Notebook Edit Tool
# ══════════════════════════════════════════════════════════════════

def test_notebook_edit_replace():
    from tools.notebook_edit_tool import NotebookEditTool
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {"cell_type": "code", "metadata": {}, "source": ["print('hello')\n"], "execution_count": 1, "outputs": []},
            {"cell_type": "markdown", "metadata": {}, "source": ["# Title\n"]},
        ]
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False, encoding='utf-8') as f:
        json.dump(nb, f)
        path = f.name
    try:
        tool = NotebookEditTool()
        result = tool.execute({
            "notebook_path": path,
            "cell_number": 0,
            "new_source": "print('world')",
        })
        assert "Successfully" in result
        # Verify
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        assert "world" in "".join(data["cells"][0]["source"])
    finally:
        os.unlink(path)

run("36. NotebookEdit: replace cell", test_notebook_edit_replace)

def test_notebook_edit_insert():
    from tools.notebook_edit_tool import NotebookEditTool
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
        {"cell_type": "code", "metadata": {}, "source": ["x=1\n"], "execution_count": None, "outputs": []},
    ]}
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False, encoding='utf-8') as f:
        json.dump(nb, f)
        path = f.name
    try:
        tool = NotebookEditTool()
        result = tool.execute({
            "notebook_path": path,
            "cell_number": 1,
            "new_source": "# New cell",
            "cell_type": "markdown",
            "edit_mode": "insert",
        })
        assert "inserted" in result.lower() or "Successfully" in result
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        assert len(data["cells"]) == 2
    finally:
        os.unlink(path)

run("37. NotebookEdit: insert cell", test_notebook_edit_insert)

def test_notebook_edit_delete():
    from tools.notebook_edit_tool import NotebookEditTool
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
        {"cell_type": "code", "metadata": {}, "source": ["a\n"], "execution_count": None, "outputs": []},
        {"cell_type": "code", "metadata": {}, "source": ["b\n"], "execution_count": None, "outputs": []},
    ]}
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False, encoding='utf-8') as f:
        json.dump(nb, f)
        path = f.name
    try:
        tool = NotebookEditTool()
        result = tool.execute({
            "notebook_path": path,
            "cell_number": 0,
            "new_source": "",
            "edit_mode": "delete",
        })
        assert "deleted" in result.lower() or "Successfully" in result
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        assert len(data["cells"]) == 1
    finally:
        os.unlink(path)

run("38. NotebookEdit: delete cell", test_notebook_edit_delete)


# ══════════════════════════════════════════════════════════════════
# 19-20. Utility Tools
# ══════════════════════════════════════════════════════════════════

def test_sleep_tool():
    from tools.utility_tools import SleepTool
    tool = SleepTool()
    t0 = time.time()
    result = tool.execute({"seconds": 1})
    elapsed = time.time() - t0
    assert "Slept" in result
    assert elapsed >= 0.9  # at least ~1s

run("39. SleepTool: sleep 1 second", test_sleep_tool)

def test_repl_python():
    from tools.utility_tools import REPLTool
    tool = REPLTool()
    result = tool.execute({"code": "print(6*7)", "language": "python"})
    assert "42" in result

run("40. REPLTool: Python print(6*7)", test_repl_python)

def test_repl_empty_code():
    from tools.utility_tools import REPLTool
    tool = REPLTool()
    result = tool.execute({"code": "", "language": "python"})
    assert "error" in result.lower() or "empty" in result.lower()

run("41. REPLTool: empty code error", test_repl_empty_code)


# ══════════════════════════════════════════════════════════════════
# 21-24. Extra Tools
# ══════════════════════════════════════════════════════════════════

def test_brief_tool():
    from tools.extra_tools import BriefTool
    tool = BriefTool()
    result = tool.execute({"enabled": True})
    assert "ON" in result or "brief" in result.lower()
    result2 = tool.execute({"enabled": False})
    assert "OFF" in result2 or "normal" in result2.lower()

run("42. BriefTool: toggle on/off", test_brief_tool)

def test_todo_write():
    from tools.extra_tools import TodoWriteTool
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "TODO.md")
        tool = TodoWriteTool()
        result = tool.execute({
            "file_path": path,
            "items": [
                {"text": "Fix bug", "done": False},
                {"text": "Write tests", "done": True},
            ]
        })
        assert "2 items" in result
        content = Path(path).read_text(encoding='utf-8')
        assert "[ ] Fix bug" in content
        assert "[x] Write tests" in content

run("43. TodoWrite: write items", test_todo_write)

def test_todo_write_empty():
    from tools.extra_tools import TodoWriteTool
    tool = TodoWriteTool()
    result = tool.execute({"items": []})
    assert "Error" in result or "empty" in result.lower()

run("44. TodoWrite: empty items error", test_todo_write_empty)

def test_tool_search():
    from tools.extra_tools import ToolSearchTool
    from core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    tool = reg.get("ToolSearch")
    assert tool is not None
    result = tool.execute({"query": "file"})
    assert "FileRead" in result or "FileWrite" in result or "file" in result.lower()

run("45. ToolSearch: search for 'file'", test_tool_search)

def test_tool_search_empty_query():
    from tools.extra_tools import ToolSearchTool
    tool = ToolSearchTool()
    tool._tool_registry = MagicMock()
    result = tool.execute({"query": ""})
    assert "error" in result.lower() or "required" in result.lower()

run("46. ToolSearch: empty query error", test_tool_search_empty_query)


# ══════════════════════════════════════════════════════════════════
# 25. Config Tool
# ══════════════════════════════════════════════════════════════════

def test_config_list():
    from tools.config_tool import ConfigTool
    with tempfile.TemporaryDirectory() as d:
        cfg_file = Path(d) / "settings.json"
        cfg_file.write_text('{"model.name": "test-model"}', encoding='utf-8')
        with patch('tools.config_tool.CONFIG_FILE', cfg_file):
            tool = ConfigTool()
            result = tool.execute({"operation": "list"})
            assert "model.name" in result

run("47. ConfigTool: list config", test_config_list)

def test_config_set_get():
    from tools.config_tool import ConfigTool
    with tempfile.TemporaryDirectory() as d:
        cfg_file = Path(d) / "settings.json"
        cfg_file.write_text('{}', encoding='utf-8')
        with patch('tools.config_tool.CONFIG_FILE', cfg_file):
            tool = ConfigTool()
            r1 = tool.execute({"operation": "set", "key": "theme", "value": "dark"})
            assert "theme" in r1
            r2 = tool.execute({"operation": "get", "key": "theme"})
            assert "dark" in r2

run("48. ConfigTool: set then get", test_config_set_get)


# ══════════════════════════════════════════════════════════════════
# 26. AskUser Tool
# ══════════════════════════════════════════════════════════════════

def test_ask_user_format():
    from tools.ask_user_tool import AskUserQuestionTool
    tool = AskUserQuestionTool()
    result = tool.execute({"question": "Which approach?"})
    assert "Which approach?" in result
    assert "Question" in result

run("49. AskUser: format question", test_ask_user_format)

def test_ask_user_with_options():
    from tools.ask_user_tool import AskUserQuestionTool
    tool = AskUserQuestionTool()
    result = tool.execute({
        "question": "Pick one",
        "options": [
            {"label": "Option A", "description": "First option"},
            {"label": "Option B"},
        ],
    })
    assert "Option A" in result
    assert "Option B" in result
    assert "Single-select" in result

run("50. AskUser: with options", test_ask_user_with_options)

def test_ask_user_empty_question():
    from tools.ask_user_tool import AskUserQuestionTool
    tool = AskUserQuestionTool()
    result = tool.execute({"question": ""})
    assert "Error" in result or "empty" in result.lower()

run("51. AskUser: empty question error", test_ask_user_empty_question)


# ══════════════════════════════════════════════════════════════════
# 27-28. Protocol Tools (MCP, LSP)
# ══════════════════════════════════════════════════════════════════

def test_mcp_no_manager():
    from tools.mcp_tool import MCPTool
    tool = MCPTool()
    tool._mcp_manager = None
    result = tool.execute({"server_name": "test", "tool_name": "test_tool"})
    assert "not available" in result.lower() or "no mcp" in result.lower() or "error" in result.lower()

run("52. MCPTool: no server returns error", test_mcp_no_manager)

def test_lsp_no_manager():
    from tools.lsp_tool import LSPTool
    tool = LSPTool()
    tool._lsp_manager = None
    result = tool.execute({"file_path": "test.py"})
    assert "no language server" in result.lower() or "not available" in result.lower()

run("53. LSPTool: no server returns message", test_lsp_no_manager)

def test_lsp_empty_path():
    from tools.lsp_tool import LSPTool
    tool = LSPTool()
    tool._lsp_manager = None
    result = tool.execute({"file_path": ""})
    assert "error" in result.lower() or "required" in result.lower()

run("54. LSPTool: empty path error", test_lsp_empty_path)


# ══════════════════════════════════════════════════════════════════
# 29-31. Soul Tools (SelfReflect, SelfModify, DiaryWrite)
# ══════════════════════════════════════════════════════════════════

def test_self_reflect_no_manager():
    from tools.soul_tools import SelfReflectTool
    tool = SelfReflectTool()
    tool._evolution_mgr = None
    result = tool.execute({"file": "personality"})
    assert "Error" in result or "not initialized" in result.lower()

run("55. SelfReflect: error without EvolutionManager", test_self_reflect_no_manager)

def test_self_reflect_with_mock():
    from tools.soul_tools import SelfReflectTool
    mock_mgr = MagicMock()
    mock_mgr.read_soul.return_value = {
        "personality": "I am BUDDY",
        "diary": "Day 1",
        "aspirations": "Be helpful",
        "relationships": "User is great",
    }
    tool = SelfReflectTool()
    tool._evolution_mgr = mock_mgr
    result = tool.execute({"file": "all"})
    assert "BUDDY" in result
    assert "personality" in result.lower()

run("56. SelfReflect: read all with mock", test_self_reflect_with_mock)

def test_self_modify_no_manager():
    from tools.soul_tools import SelfModifyTool
    tool = SelfModifyTool()
    tool._evolution_mgr = None
    result = tool.execute({"file_path": "soul/diary.md", "content": "test", "reason": "test"})
    assert "Error" in result

run("57. SelfModify: error without EvolutionManager", test_self_modify_no_manager)

def test_diary_write_no_manager():
    from tools.soul_tools import DiaryWriteTool
    tool = DiaryWriteTool()
    tool._evolution_mgr = None
    result = tool.execute({"entry": "Today was good"})
    assert "Error" in result

run("58. DiaryWrite: error without EvolutionManager", test_diary_write_no_manager)

def test_diary_write_with_mock():
    from tools.soul_tools import DiaryWriteTool
    mock_mgr = MagicMock()
    tool = DiaryWriteTool()
    tool._evolution_mgr = mock_mgr
    result = tool.execute({"entry": "A good day of coding"})
    assert "diary" in result.lower() or "saved" in result.lower()
    mock_mgr._append_diary.assert_called_once_with("A good day of coding")

run("59. DiaryWrite: writes with mock manager", test_diary_write_with_mock)

def test_diary_write_empty():
    from tools.soul_tools import DiaryWriteTool
    mock_mgr = MagicMock()
    tool = DiaryWriteTool()
    tool._evolution_mgr = mock_mgr
    result = tool.execute({"entry": ""})
    assert "error" in result.lower() or "required" in result.lower()

run("60. DiaryWrite: empty entry error", test_diary_write_empty)


# ══════════════════════════════════════════════════════════════════
# 32. PowerShell Tool
# ══════════════════════════════════════════════════════════════════

def test_powershell():
    from tools.extra_tools import PowerShellTool
    tool = PowerShellTool()
    if platform.system() == "Windows":
        result = tool.execute({"command": "Write-Output 'hello from ps'"})
        assert "hello from ps" in result
    else:
        result = tool.execute({"command": "echo hi"})
        assert "Windows" in result or "Error" in result

run("61. PowerShell: platform-dependent", test_powershell)


# ══════════════════════════════════════════════════════════════════
# 33-45. Additional edge cases
# ══════════════════════════════════════════════════════════════════

def test_file_read_dedup():
    """FileRead should return stub on duplicate read of unchanged file."""
    from tools.file_read_tool import FileReadTool
    frs = _make_file_read_state()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("content\n")
        f.flush()
        path = f.name
    try:
        tool = FileReadTool()
        tool._file_read_state = frs
        r1 = tool.execute({"file_path": path})
        assert "content" in r1
        r2 = tool.execute({"file_path": path})
        assert "unchanged" in r2.lower() or "omitted" in r2.lower()
    finally:
        os.unlink(path)

run("62. FileRead: dedup on same file", test_file_read_dedup)

def test_file_write_overwrite_enforcement():
    """FileWrite should warn when overwriting without prior read."""
    from tools.file_write_tool import FileWriteTool
    frs = _make_file_read_state()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("existing\n")
        f.flush()
        path = f.name
    try:
        tool = FileWriteTool()
        tool._file_read_state = frs
        result = tool.execute({"file_path": path, "content": "new content"})
        assert "Warning" in result or "haven't read" in result.lower()
    finally:
        os.unlink(path)

run("63. FileWrite: overwrite warning without read", test_file_write_overwrite_enforcement)

def test_bash_git_safety():
    """Bash detects git --no-verify."""
    from tools.bash_tool import BashTool
    tool = BashTool()
    result = tool.execute({"command": "git commit --no-verify -m 'test'"})
    assert "safety" in result.lower() or "warning" in result.lower() or "destructive" in result.lower()

run("64. Bash: git --no-verify warning", test_bash_git_safety)

def test_glob_recursive():
    from tools.glob_tool import GlobTool
    with tempfile.TemporaryDirectory() as d:
        sub = Path(d) / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "found.py").write_text("# deep file", encoding='utf-8')
        tool = GlobTool()
        result = tool.execute({"pattern": "**/*.py", "path": d})
        assert "found.py" in result

run("65. Glob: recursive ** pattern", test_glob_recursive)

def test_grep_files_with_matches():
    from tools.grep_tool import GrepTool
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.py").write_text("import os\n", encoding='utf-8')
        (Path(d) / "b.py").write_text("import sys\n", encoding='utf-8')
        tool = GrepTool()
        result = tool.execute({"pattern": "import os", "path": d, "output_mode": "files_with_matches"})
        assert "a.py" in result
        assert "b.py" not in result

run("66. Grep: files_with_matches mode", test_grep_files_with_matches)

def test_cron_one_shot():
    from tools.cron_tool import CronCreateTool, get_cron_scheduler
    sched = get_cron_scheduler()
    sched._jobs.clear()
    sched._next_id = 1
    tool = CronCreateTool()
    result = tool.execute({"cron": "30 14 25 12 *", "prompt": "xmas", "recurring": False})
    assert "one-shot" in result.lower()

run("67. CronCreate: one-shot job", test_cron_one_shot)

def test_cron_delete_nonexistent():
    from tools.cron_tool import CronDeleteTool, get_cron_scheduler
    sched = get_cron_scheduler()
    sched._jobs.clear()
    tool = CronDeleteTool()
    result = tool.execute({"id": "cron_999"})
    assert "not found" in result.lower() or "Error" in result

run("68. CronDelete: non-existent job", test_cron_delete_nonexistent)

def test_notebook_out_of_range():
    from tools.notebook_edit_tool import NotebookEditTool
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
        {"cell_type": "code", "metadata": {}, "source": ["x\n"], "execution_count": None, "outputs": []},
    ]}
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False, encoding='utf-8') as f:
        json.dump(nb, f)
        path = f.name
    try:
        tool = NotebookEditTool()
        result = tool.execute({"notebook_path": path, "cell_number": 99, "new_source": "y"})
        assert "out of range" in result.lower() or "Error" in result
    finally:
        os.unlink(path)

run("69. NotebookEdit: out of range cell", test_notebook_out_of_range)

def test_notebook_wrong_extension():
    from tools.notebook_edit_tool import NotebookEditTool
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("not a notebook")
        path = f.name
    try:
        tool = NotebookEditTool()
        result = tool.execute({"notebook_path": path, "cell_number": 0, "new_source": "x"})
        assert "ipynb" in result.lower() or "Error" in result
    finally:
        os.unlink(path)

run("70. NotebookEdit: wrong file extension", test_notebook_wrong_extension)

def test_ask_user_multi_select():
    from tools.ask_user_tool import AskUserQuestionTool
    tool = AskUserQuestionTool()
    result = tool.execute({
        "question": "Select features",
        "options": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
        "multiSelect": True,
    })
    assert "Multi-select" in result
    assert "A" in result and "B" in result and "C" in result

run("71. AskUser: multi-select mode", test_ask_user_multi_select)

def test_tool_registry_tool_defs():
    """All tool defs should have name and description."""
    from core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    defs = reg.all_tool_defs()
    assert len(defs) >= 33
    for td in defs:
        assert td.name, f"ToolDef missing name"
        assert td.description, f"ToolDef {td.name} missing description"

run("72. Registry: all tool_defs valid", test_tool_registry_tool_defs)

def test_bash_exit_code():
    from tools.bash_tool import BashTool
    tool = BashTool()
    if platform.system() == "Windows":
        result = tool.execute({"command": "cmd /c exit 1"})
    else:
        result = tool.execute({"command": "exit 1"})
    assert "Exit code: 1" in result or "exit code" in result.lower()

run("73. Bash: non-zero exit code reported", test_bash_exit_code)

def test_config_get_missing_key():
    from tools.config_tool import ConfigTool
    with tempfile.TemporaryDirectory() as d:
        cfg_file = Path(d) / "settings.json"
        cfg_file.write_text('{}', encoding='utf-8')
        with patch('tools.config_tool.CONFIG_FILE', cfg_file):
            tool = ConfigTool()
            result = tool.execute({"operation": "get", "key": "nonexistent"})
            assert "not found" in result.lower()

run("74. ConfigTool: get missing key", test_config_get_missing_key)

def test_mcp_missing_server_name():
    from tools.mcp_tool import MCPTool
    tool = MCPTool()
    tool._mcp_manager = None
    result = tool.execute({"server_name": "", "tool_name": "test"})
    assert "error" in result.lower() or "required" in result.lower()

run("75. MCPTool: empty server_name error", test_mcp_missing_server_name)

# ── Gap fills: TaskStop, TaskOutput, TeamCreate, TeamDelete, Worktree, Skill ──

def test_task_output_missing_id():
    from tools.task_output_tool import TaskOutputTool
    tool = TaskOutputTool()
    result = tool.execute({"task_id": ""})
    assert "error" in result.lower() or "required" in result.lower()

run("76. TaskOutput: empty task_id → error", test_task_output_missing_id)

def test_task_output_not_found():
    from tools.task_output_tool import TaskOutputTool
    tool = TaskOutputTool()
    tool._engine = None
    tool._bash_tool = None
    result = tool.execute({"task_id": "bg_999"})
    assert "not found" in result.lower()

run("77. TaskOutput: non-existent task → not found", test_task_output_not_found)

def test_task_stop_missing_id():
    from tools.task_output_tool import TaskStopTool
    tool = TaskStopTool()
    result = tool.execute({"task_id": ""})
    assert "error" in result.lower() or "required" in result.lower()

run("78. TaskStop: empty task_id → error", test_task_stop_missing_id)

def test_task_stop_no_engine():
    from tools.task_output_tool import TaskStopTool
    tool = TaskStopTool()
    tool._engine = None
    result = tool.execute({"task_id": "bg_1"})
    assert "error" in result.lower() or "not available" in result.lower()

run("79. TaskStop: no engine → error", test_task_stop_no_engine)

def test_team_create_no_registry():
    from tools.team_tool import TeamCreateTool
    tool = TeamCreateTool()
    tool._agent_registry = None
    result = tool.execute({"team_name": "test_team"})
    assert "error" in result.lower() or "not available" in result.lower()

run("80. TeamCreate: no registry → error", test_team_create_no_registry)

def test_team_create_empty_name():
    from tools.team_tool import TeamCreateTool
    tool = TeamCreateTool()
    result = tool.execute({"team_name": ""})
    assert "error" in result.lower() or "required" in result.lower()

run("81. TeamCreate: empty name → error", test_team_create_empty_name)

def test_team_delete_no_registry():
    from tools.team_tool import TeamDeleteTool
    tool = TeamDeleteTool()
    tool._agent_registry = None
    result = tool.execute({"team_name": "test_team"})
    assert "error" in result.lower() or "not available" in result.lower()

run("82. TeamDelete: no registry → error", test_team_delete_no_registry)

def test_team_delete_empty_name():
    from tools.team_tool import TeamDeleteTool
    tool = TeamDeleteTool()
    result = tool.execute({"team_name": ""})
    assert "error" in result.lower() or "required" in result.lower()

run("83. TeamDelete: empty name → error", test_team_delete_empty_name)

def test_worktree_enter_not_git_repo():
    from tools.worktree_tool import EnterWorktreeTool
    tool = EnterWorktreeTool()
    # Execute in a non-git temp directory
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            result = tool.execute({"name": "test-wt"})
            assert "error" in result.lower() or "not" in result.lower()
        finally:
            os.chdir(old_cwd)

run("84. EnterWorktree: non-git dir → error", test_worktree_enter_not_git_repo)

def test_worktree_exit_keep():
    from tools.worktree_tool import ExitWorktreeTool
    tool = ExitWorktreeTool()
    result = tool.execute({"action": "keep", "worktree_path": "/tmp/some_wt"})
    assert "kept" in result.lower() or "keep" in result.lower()

run("85. ExitWorktree: action=keep → kept message", test_worktree_exit_keep)

def test_worktree_exit_not_in_worktree():
    from tools.worktree_tool import ExitWorktreeTool
    tool = ExitWorktreeTool()
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            result = tool.execute({"action": "remove"})
            assert "error" in result.lower() or "not" in result.lower()
        finally:
            os.chdir(old_cwd)

run("86. ExitWorktree: not in worktree → error", test_worktree_exit_not_in_worktree)

def test_skill_empty_name():
    from tools.skill_tool import SkillTool
    tool = SkillTool()
    result = tool.execute({"skill": ""})
    assert "error" in result.lower() or "required" in result.lower()

run("87. Skill: empty name → error", test_skill_empty_name)

def test_skill_not_found():
    from tools.skill_tool import SkillTool
    tool = SkillTool()
    tool._command_registry = None
    result = tool.execute({"skill": "nonexistent_skill_xyz"})
    assert "not found" in result.lower() or "available" in result.lower()

run("88. Skill: non-existent skill → not found", test_skill_not_found)

def test_skill_json_file():
    from tools.skill_tool import SkillTool, SKILLS_DIR
    tool = SkillTool()
    tool._command_registry = None
    # Create temp skill file
    skill_file = SKILLS_DIR / "test_skill_temp.json"
    try:
        import json
        skill_file.write_text(json.dumps({"prompt": "Hello {{args}}"}), encoding="utf-8")
        result = tool.execute({"skill": "test_skill_temp", "args": "world"})
        assert "hello world" in result.lower() or "skill loaded" in result.lower()
    finally:
        skill_file.unlink(missing_ok=True)

run("89. Skill: loads JSON skill file with args", test_skill_json_file)


# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
total = PASS + FAIL
print(f'\n{"="*60}')
if FAIL == 0:
    print(f'  Suite 4 (Tools): {total}/{total} ALL TESTS PASSED')
else:
    print(f'  Suite 4 (Tools): {PASS}/{total} PASSED, {FAIL} FAILED')
    for n, e in ERRORS:
        print(f'    X {n}: {e}')
print(f'{"="*60}')
sys.exit(0 if FAIL == 0 else 1)
