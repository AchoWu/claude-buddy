"""
Compact Prompts — LLM-based conversation summarization prompts.
Aligned with Claude Code's compact/prompt.ts:
  - NO_TOOLS_PREAMBLE (force text-only response)
  - <analysis> tag for structured thinking
  - 9-section summary structure
  - Post-compact file restoration hints
  - Partial compact variant (recent messages only)
"""

# ── NO TOOLS PREAMBLE ─────────────────────────────────────────────
# Prefixed to compact prompts to prevent model from calling tools
NO_TOOLS_PREAMBLE = """\
CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.
- Do NOT use FileRead, Bash, Grep, Glob, FileEdit, FileWrite, or ANY other tool.
- Tool calls will be REJECTED and will waste your only turn.
- Your entire response must be plain text: an <analysis> block followed by a <summary> block.
"""

# ── ANALYSIS INSTRUCTION ──────────────────────────────────────────
# Requires structured thinking before summarization
ANALYSIS_INSTRUCTION = """\
First, write your analysis inside <analysis> tags. In your analysis:
1. Review each message chronologically.
2. Identify: the user's requests, the approach taken, key decisions made, any errors encountered, and user feedback/corrections.
3. Pay special attention to the most recent messages — they represent the current state.
4. Double-check that your analysis captures everything important. If you miss something, the model will lose that context.
</analysis>
"""

# ── 9-SECTION SUMMARY STRUCTURE ──────────────────────────────────
SUMMARY_STRUCTURE = """\
Then write your summary inside <summary> tags with these sections:

1. **Primary Request and Intent**: What the user originally asked for and what they're trying to accomplish.

2. **Key Technical Concepts**: Important technical details, patterns, or domain knowledge from the conversation.

3. **Files and Code Sections**: List every file that was read, created, or modified, with a brief note on WHY each file was involved (not just that it was touched).

4. **Errors and Fixes**: Any errors encountered and how they were resolved. Include root causes.

5. **Problem Solving**: Key decisions, trade-offs considered, and approaches tried (including failed ones).

6. **User Messages**: Reproduce ALL user messages (non-tool-result) since they contain the ground truth of requirements.

7. **Pending Tasks**: Any tasks or follow-ups that were mentioned but not yet completed.

8. **Current Work**: What was being worked on right before this compaction, and what the natural next step would be.

9. **Key Facts**: Any specific values, names, versions, URLs, or configuration details that would be hard to re-derive.
</summary>
"""

# ── FULL COMPACT PROMPT ───────────────────────────────────────────
# Used when compacting the entire conversation
FULL_COMPACT_PROMPT = f"""\
{NO_TOOLS_PREAMBLE}

You are a conversation summarizer. Your job is to create a detailed, accurate summary of the conversation so far. This summary will REPLACE the old messages, so it must capture EVERYTHING important.

{ANALYSIS_INSTRUCTION}

{SUMMARY_STRUCTURE}

Guidelines:
- Be thorough. It's better to include too much than to lose critical context.
- Use exact file paths and line numbers where relevant.
- Preserve the user's original wording for requirements (don't paraphrase requirements).
- If the conversation references specific versions, URLs, or values, include them.
- Note any user preferences or corrections (these inform future behavior).
"""

# ── PARTIAL COMPACT PROMPT ────────────────────────────────────────
# Used when only compacting older messages (recent ones preserved)
PARTIAL_COMPACT_PROMPT = f"""\
{NO_TOOLS_PREAMBLE}

You are summarizing the OLDER portion of a conversation. The most recent messages will be preserved separately, so focus on context that supports understanding those recent messages.

{ANALYSIS_INSTRUCTION}

{SUMMARY_STRUCTURE}

Additional guidelines for partial compaction:
- Focus on context needed to understand the recent messages.
- You can be briefer on resolved topics that won't affect current work.
- Be thorough on: file paths, user preferences, error patterns, architectural decisions.
"""

# ── POST-COMPACT MARKER ──────────────────────────────────────────
# Injected as the first message after compaction
POST_COMPACT_MARKER = """\
[CONTEXT COMPACTED]
The conversation above was summarized to save context space.
The original messages have been replaced by a summary.

IMPORTANT:
- Files mentioned in the summary may have changed. Re-read them with FileRead before editing.
- The summary preserves key facts, but nuances may be lost.
- If you're unsure about something, verify it rather than assuming.

{file_hint}
"""

# ── FILE HINT TEMPLATE ────────────────────────────────────────────
FILE_HINT_TEMPLATE = """\
Files you were working on (re-read before editing):
{file_list}
"""


def build_compact_prompt(
    partial: bool = False,
    preserve_recent_count: int = 0,
) -> str:
    """Build the appropriate compact prompt."""
    if partial:
        return PARTIAL_COMPACT_PROMPT
    return FULL_COMPACT_PROMPT


def build_post_compact_marker(active_files: list[str] | None = None) -> str:
    """Build the post-compaction marker message."""
    file_hint = ""
    if active_files:
        file_list = "\n".join(f"  - {f}" for f in active_files[:20])
        file_hint = FILE_HINT_TEMPLATE.format(file_list=file_list)
    return POST_COMPACT_MARKER.format(file_hint=file_hint)
