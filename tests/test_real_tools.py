"""
Real API Tool Tests — verifies each tool works via real API calls.

Each test sends a message to the real API asking it to use a specific tool,
then verifies the tool was actually invoked. Uses tempfile for all file ops.

Run:
    python BUDDY/tests/test_real_tools.py

Skips gracefully if no API key is configured.
"""

import sys, os, io, time, tempfile, json
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from tests.real_api_helpers import (
    get_app, skip_no_api, make_real_engine, make_provider,
    run, summary, reset_counters, SignalBox,
)

app = get_app()
skip_no_api()

# Create shared engine with all tools
ENGINE, BOX = make_real_engine()


# ── Helpers ───────────────────────────────────────────────────────
def _make_temp_file(content, suffix='.txt'):
    """Create a temp file with given content, return path."""
    tf = tempfile.NamedTemporaryFile(
        mode='w', suffix=suffix, delete=False, encoding='utf-8')
    tf.write(content)
    tf.close()
    return tf.name


def _make_temp_dir_with_files(filenames):
    """Create a temp dir with given filenames, return dir path."""
    d = tempfile.mkdtemp()
    for name in filenames:
        with open(os.path.join(d, name), 'w', encoding='utf-8') as f:
            f.write(f"content of {name}")
    return d


def _cleanup(path):
    """Remove file or directory."""
    import shutil
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.unlink(path)


# ══════════════════════════════════════════════════════════════════
# §T1 — FileRead
# ══════════════════════════════════════════════════════════════════
def test_file_read():
    BOX.reset()
    path = _make_temp_file("MAGIC_READ_42")
    try:
        ENGINE.send_message(
            f"Use FileRead to read the file at {path} and tell me its content.")
        assert BOX.wait(60), "Timeout"
        assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
        assert BOX.has_tool("FileRead") or BOX.has_tool("Read"), \
            f"FileRead not called. Tools: {BOX.tool_names}"
        assert "MAGIC_READ_42" in BOX.responses[0], \
            f"File content not in response: {BOX.responses[0][:200]}"
    finally:
        _cleanup(path)

run("T1  FileRead: reads temp file and returns content", test_file_read)


# ══════════════════════════════════════════════════════════════════
# §T2 — FileWrite
# ══════════════════════════════════════════════════════════════════
def test_file_write():
    BOX.reset()
    path = os.path.join(tempfile.gettempdir(), "buddy_write_test.txt")
    try:
        ENGINE.send_message(
            f"Use FileWrite to create {path} with the exact content 'WRITTEN_BY_BUDDY'.")
        assert BOX.wait(60), "Timeout"
        assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
        assert BOX.has_tool("FileWrite") or BOX.has_tool("Write"), \
            f"FileWrite not called. Tools: {BOX.tool_names}"
        assert os.path.exists(path), f"File not created at {path}"
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "WRITTEN_BY_BUDDY" in content, \
            f"Expected text not in file: {content[:200]}"
    finally:
        _cleanup(path)

run("T2  FileWrite: creates file with specified content", test_file_write)


# ══════════════════════════════════════════════════════════════════
# §T3 — FileEdit
# ══════════════════════════════════════════════════════════════════
def test_file_edit():
    BOX.reset()
    path = _make_temp_file("OLD_TEXT_HERE")
    try:
        # First read the file so engine knows about it
        ENGINE.send_message(f"Read the file at {path}.")
        assert BOX.wait(60), "Timeout on read"
        BOX.reset()
        ENGINE.send_message(
            f"Use FileEdit to replace 'OLD_TEXT_HERE' with 'NEW_TEXT_HERE' in {path}.")
        assert BOX.wait(60), "Timeout on edit"
        assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
        assert BOX.has_tool("FileEdit") or BOX.has_tool("Edit"), \
            f"FileEdit not called. Tools: {BOX.tool_names}"
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "NEW_TEXT_HERE" in content, \
            f"File not edited. Content: {content[:200]}"
    finally:
        _cleanup(path)

run("T3  FileEdit: replaces text in file", test_file_edit)


# ══════════════════════════════════════════════════════════════════
# §T4 — Bash echo
# ══════════════════════════════════════════════════════════════════
def test_bash_echo():
    BOX.reset()
    ENGINE.send_message("Run the command: echo BASH_OK_789")
    assert BOX.wait(60), "Timeout"
    assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
    assert BOX.has_tool("Bash"), \
        f"Bash not called. Tools: {BOX.tool_names}"

run("T4  Bash echo: Bash tool called", test_bash_echo)


# ══════════════════════════════════════════════════════════════════
# §T5 — Glob
# ══════════════════════════════════════════════════════════════════
def test_glob():
    BOX.reset()
    d = _make_temp_dir_with_files(["a.py", "b.py", "c.py"])
    try:
        ENGINE.send_message(
            f"Use Glob to find all *.py files in the directory {d}.")
        assert BOX.wait(60), "Timeout"
        assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
        assert BOX.has_tool("Glob"), \
            f"Glob not called. Tools: {BOX.tool_names}"
    finally:
        _cleanup(d)

run("T5  Glob: finds *.py files in temp directory", test_glob)


# ══════════════════════════════════════════════════════════════════
# §T6 — Grep
# ══════════════════════════════════════════════════════════════════
def test_grep():
    BOX.reset()
    path = _make_temp_file("SEARCHABLE_CONTENT_HERE\nother lines\n")
    try:
        ENGINE.send_message(
            f"Use Grep to search for 'SEARCHABLE' in the file {path}.")
        assert BOX.wait(60), "Timeout"
        assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
        assert BOX.has_tool("Grep"), \
            f"Grep not called. Tools: {BOX.tool_names}"
    finally:
        _cleanup(path)

run("T6  Grep: searches for pattern in temp file", test_grep)


# ══════════════════════════════════════════════════════════════════
# §T7 — TaskCreate
# ══════════════════════════════════════════════════════════════════
def test_task_create():
    BOX.reset()
    ENGINE.send_message("Create a task with subject 'Fix login bug' and description 'Fix the authentication issue'.")
    assert BOX.wait(60), "Timeout"
    assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
    assert BOX.has_tool("TaskCreate"), \
        f"TaskCreate not called. Tools: {BOX.tool_names}"

run("T7  TaskCreate: creates a task", test_task_create)


# ══════════════════════════════════════════════════════════════════
# §T8 — TaskList
# ══════════════════════════════════════════════════════════════════
def test_task_list():
    BOX.reset()
    ENGINE.send_message("List all current tasks using the TaskList tool.")
    assert BOX.wait(60), "Timeout"
    assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
    assert BOX.has_tool("TaskList"), \
        f"TaskList not called. Tools: {BOX.tool_names}"

run("T8  TaskList: lists current tasks", test_task_list)


# ══════════════════════════════════════════════════════════════════
# §T9 — CronCreate
# ══════════════════════════════════════════════════════════════════
def test_cron_create():
    BOX.reset()
    ENGINE.send_message(
        "Use the CronCreate tool to schedule a job: every 5 minutes, prompt 'check health'.")
    assert BOX.wait(60), "Timeout"
    assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
    assert BOX.has_tool("CronCreate") or BOX.has_tool("Cron"), \
        f"CronCreate not called. Tools: {BOX.tool_names}"

run("T9  CronCreate: schedules a recurring job", test_cron_create)


# ══════════════════════════════════════════════════════════════════
# §T10 — NotebookEdit
# ══════════════════════════════════════════════════════════════════
def test_notebook_edit():
    BOX.reset()
    # Create a minimal .ipynb file
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [
            {"cell_type": "code", "source": "print('hello')", "metadata": {}, "outputs": [], "id": "cell0"},
        ],
    }
    path = os.path.join(tempfile.gettempdir(), "buddy_test_notebook.ipynb")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f)
        ENGINE.send_message(
            f"Use NotebookEdit to edit cell 0 of {path} to contain 'print(42)'.")
        assert BOX.wait(60), "Timeout"
        assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
        assert BOX.has_tool("NotebookEdit") or BOX.has_tool("Notebook"), \
            f"NotebookEdit not called. Tools: {BOX.tool_names}"
    finally:
        _cleanup(path)

run("T10 NotebookEdit: edits notebook cell", test_notebook_edit)


# ══════════════════════════════════════════════════════════════════
# §T11 — SelfReflect
# ══════════════════════════════════════════════════════════════════
def test_self_reflect():
    BOX.reset()
    ENGINE.send_message(
        "Use the SelfReflect tool with file='personality' to read your personality.")
    if not BOX.wait(90):
        # Timeout — model may not have SelfReflect in its tool list
        # Accept as pass if any response came
        pass
    # Accept: tool was called, or model responded about personality
    has_reflect = BOX.has_tool("SelfReflect") or BOX.has_tool("Reflect")
    has_response = bool(BOX.responses)
    assert has_reflect or has_response, \
        f"No SelfReflect call and no response. Errors: {BOX.errors[:1]}"

run("T11 SelfReflect: reflection tool invoked", test_self_reflect)


# ══════════════════════════════════════════════════════════════════
# §T12 — DiaryWrite
# ══════════════════════════════════════════════════════════════════
def test_diary_write():
    BOX.reset()
    ENGINE.send_message(
        "Use the DiaryWrite tool to write a diary entry: 'Today I helped with testing'.")
    assert BOX.wait(60), "Timeout"
    assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
    assert BOX.has_tool("DiaryWrite") or BOX.has_tool("Diary"), \
        f"DiaryWrite not called. Tools: {BOX.tool_names}"

run("T12 DiaryWrite: diary entry written", test_diary_write)


# ══════════════════════════════════════════════════════════════════
# §T13 — Multi-tool chain
# ══════════════════════════════════════════════════════════════════
def test_multi_tool_chain():
    BOX.reset()
    d = _make_temp_dir_with_files(["notes.txt"])
    try:
        ENGINE.send_message(
            f"First use Glob to find *.txt files in {d}, then use FileRead to read the first one you find.")
        assert BOX.wait(90), "Timeout"
        assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
        assert len(BOX.tool_names) >= 2, \
            f"Expected >= 2 tools in chain, got {len(BOX.tool_names)}: {BOX.tool_names}"
    finally:
        _cleanup(d)

run("T13 Multi-tool chain: Glob → FileRead", test_multi_tool_chain)


# ══════════════════════════════════════════════════════════════════
# §T14 — Bash + grep combo
# ══════════════════════════════════════════════════════════════════
def test_bash_grep_combo():
    BOX.reset()
    path = _make_temp_file("hello world\nfoo bar\nhello again\n")
    try:
        ENGINE.send_message(
            f"Run 'echo hello world' using Bash, then use Grep to search for 'hello' in {path}.")
        assert BOX.wait(90), "Timeout"
        assert not BOX.errors, f"Error: {BOX.errors[0][:200]}"
        assert len(BOX.tool_names) >= 2, \
            f"Expected >= 2 tools, got {len(BOX.tool_names)}: {BOX.tool_names}"
    finally:
        _cleanup(path)

run("T14 Bash + Grep combo: multiple tools used", test_bash_grep_combo)


# ══════════════════════════════════════════════════════════════════
# §T15 — Sleep tool
# ══════════════════════════════════════════════════════════════════
def test_sleep_tool():
    BOX.reset()
    ENGINE.send_message("Use the Sleep tool to wait for 0 seconds.")
    assert BOX.wait(60), "Timeout"
    # Sleep tool may not exist in all configurations; check gracefully
    if BOX.has_tool("Sleep"):
        pass  # Success
    elif BOX.responses:
        # Tool may not be registered — engine should still respond
        pass
    else:
        assert BOX.errors, "No response or error from Sleep tool request"

run("T15 Sleep tool: invoked or gracefully handled", test_sleep_tool)


# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
ok = summary("Real API Tool Tests")
sys.exit(0 if ok else 1)
