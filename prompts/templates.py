"""
Prompt templates — notification templates, task templates, tool descriptions.
Aligned with Claude Code's template patterns.
"""

# ── Notification Templates ────────────────────────────────────────────
TASK_CREATED_TEMPLATE = "Task created: **{subject}**"
TASK_COMPLETED_TEMPLATE = "Task done: **{subject}**"
TASK_FAILED_TEMPLATE = "Task failed: **{subject}** - {reason}"
TOOL_EXECUTING_TEMPLATE = "Running **{tool_name}**..."
TOOL_RESULT_TEMPLATE = "{tool_name} completed"
PERMISSION_REQUEST_TEMPLATE = "**{tool_name}** wants to:\n```\n{detail}\n```\nAllow?"
ERROR_TEMPLATE = "Error: {message}"
GREETING_TEMPLATE = "Hi! I'm Claude Buddy. How can I help you today?"

# ── System Reminder Templates (injected into conversation) ────────────
CONTEXT_COMPACTED_TEMPLATE = """\
[CONTEXT COMPACTED]
Previous conversation was compacted to save context space.
{summary}

Files you were working on (re-read with FileRead before editing):
{files}

[End of compacted context. Continue from the messages below.]"""

TOOL_ERROR_REMINDER = """\
The tool {tool_name} returned an error. Try to recover:
- If file not found: use Glob to search for the correct path.
- If string not found in FileEdit: re-read the file with FileRead.
- If command failed: read the error message and try an alternative."""

POST_COMPACT_FILE_HINT = """\
After context compaction, the following files were being worked on.
Re-read them with FileRead before making any edits:
{files}"""

# ── Permission Mode Descriptions ──────────────────────────────────────
PERMISSION_MODE_DESC = {
    "default": "Ask before running non-read-only tools",
    "auto": "Auto-approve safe operations, ask for risky ones",
    "bypass": "Auto-approve all operations (use with caution)",
}

# ── Tool Safety Classifications ───────────────────────────────────────
SAFE_TOOLS = {"FileRead", "Glob", "Grep", "WebSearch", "WebFetch", "TaskList", "TaskGet"}
WRITE_TOOLS = {"FileWrite", "FileEdit", "TaskCreate", "TaskUpdate"}
DANGEROUS_TOOLS = {"Bash"}

# ── Commit Message Template ───────────────────────────────────────────
COMMIT_MSG_TEMPLATE = """\
{summary}

{body}"""

PR_BODY_TEMPLATE = """\
## Summary
{summary}

## Test plan
{test_plan}"""
