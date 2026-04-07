"""§3 Prompt System – verify build_system_prompt() sections.

Tests correspond to capability-matrix rows 3.1 – 3.21 plus two
structural checks. Independently runnable:

    python tests/test_s3_prompts.py
"""
import sys, os

# ── Bootstrap ───────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import run, summary, reset

# ── Import the function under test ──────────────────────────────
from prompts.system import build_system_prompt


# ═══════════════════════════════════════════════════════════════
#  Assertion helpers
# ═══════════════════════════════════════════════════════════════

def _assert_in(needle, haystack):
    """Assert *needle* is a substring of *haystack*."""
    assert needle in haystack, f"expected {needle!r} in prompt (len={len(haystack)})"


def _assert_any_in(needles, haystack):
    """Assert at least one of *needles* appears in *haystack*."""
    assert any(n in haystack for n in needles), (
        f"expected one of {needles!r} in prompt (len={len(haystack)})"
    )


def _assert_all_in(needles, haystack):
    """Assert every item in *needles* appears in *haystack*."""
    for n in needles:
        assert n in haystack, f"expected {n!r} in prompt (len={len(haystack)})"


# ── Helpers ─────────────────────────────────────────────────────
def _prompt(**kw):
    """Build a system prompt with the given keyword arguments."""
    return build_system_prompt(**kw)


def _ci(**kw):
    """Build a system prompt and return it lowercased for case-insensitive checks."""
    return build_system_prompt(**kw).lower()


# ── Tests ───────────────────────────────────────────────────────
print("§3  Prompt System")
print("-" * 60)
reset()

# 3.1 – Identity
def test_3_1():
    _assert_in("Claude Buddy", _prompt())

run("3.1  identity contains 'Claude Buddy'", test_3_1)

# 3.1b – Soul / SelfModify
def test_3_1b():
    p = _ci()
    _assert_all_in(["soul", "selfmodify"], p)

run("3.1b soul section mentions Soul and SelfModify", test_3_1b)

# 3.2 – System rules: never fabricate
def test_3_2():
    _assert_any_in(["NEVER fabricate", "never fabricate"], _prompt())

run("3.2  system rules: never fabricate", test_3_2)

# 3.3 – Doing tasks: read file / FileRead
def test_3_3():
    _assert_any_in(["read the file", "FileRead"], _prompt())

run("3.3  doing tasks mentions file reading", test_3_3)

# 3.4 – Code quality: comment / style
def test_3_4():
    _assert_any_in(["comment", "style"], _ci())

run("3.4  code quality mentions comment or style", test_3_4)

# 3.5 – Action safety: SAFE and DANGEROUS
def test_3_5():
    p = _prompt()
    _assert_all_in(["SAFE", "DANGEROUS"], p)

run("3.5  action safety SAFE & DANGEROUS", test_3_5)

# 3.6 – Sandbox: OFF LIMITS / System
def test_3_6():
    _assert_any_in(["OFF LIMITS", "System"], _prompt())

run("3.6  sandbox section", test_3_6)

# 3.7 – AUTO mode prompt when permission_mode="auto"
def test_3_7():
    _assert_in("AUTO mode", _prompt(permission_mode="auto"))

run("3.7  AUTO mode prompt", test_3_7)

# 3.8 – Tool-selection table
def test_3_8():
    p = _prompt()
    _assert_in("Task", p)
    _assert_in("NEVER use Bash", p)

run("3.8  tool selection table", test_3_8)

# 3.9 – Tool details: FileRead
def test_3_9():
    _assert_any_in(["## FileRead", "FileRead"], _prompt())

run("3.9  tool details mention FileRead", test_3_9)

# 3.10 – Parallel tools
def test_3_10():
    _assert_any_in(["parallel", "independent"], _ci())

run("3.10 parallel / INDEPENDENT tools", test_3_10)

# 3.11 – Agent guidance
def test_3_11():
    p = _ci()
    _assert_in("agent", p)
    _assert_any_in(["sub-agent", "spawn"], p)

run("3.11 agent guidance", test_3_11)

# 3.12 – Background tasks
def test_3_12():
    _assert_in("run_in_background", _prompt())

run("3.12 background tasks", test_3_12)

# 3.13 – Git workflow
def test_3_13():
    _assert_any_in(["pre-commit", "never amend", "commit"], _ci())

run("3.13 git workflow", test_3_13)

# 3.14 – Error recovery
def test_3_14():
    _assert_any_in(["old_string not found", "Re-read"], _prompt())

run("3.14 error recovery", test_3_14)

# 3.15 – Cyber risk
def test_3_15():
    _assert_any_in(["NEVER generate", "fabricate", "URLs"], _prompt())

run("3.15 cyber risk: no fabricated URLs", test_3_15)

# 3.17 – Faithful reporting
def test_3_17():
    _assert_any_in(["claim", "fabricat"], _ci())

run("3.17 faithful reporting", test_3_17)

# 3.18 – Communication
def test_3_18():
    _assert_any_in(["stepped away", "expertise"], _ci())

run("3.18 communication: stepped away / expertise", test_3_18)

# 3.19 – Output format
def test_3_19():
    _assert_any_in(["fenced code", "markdown"], _ci())

run("3.19 output format: fenced code / markdown", test_3_19)

# 3.20 – Memory content injection
_MEMORY_SENTINEL = "XYZZY_TEST_MEMORY_42"
def test_3_20():
    _assert_in(_MEMORY_SENTINEL, _prompt(memory_content=_MEMORY_SENTINEL))

run("3.20 memory_content appears in prompt", test_3_20)

# 3.21 – Environment info
def test_3_21():
    _assert_any_in(["Working directory", "Platform"], _prompt())

run("3.21 environment: Working directory / Platform", test_3_21)

# ── Structural checks ──────────────────────────────────────────
def test_struct_nonempty():
    p = _prompt()
    assert isinstance(p, str), "prompt must be a string"
    assert len(p) > 1000, f"prompt too short: {len(p)} chars"

run("STRUCT  prompt is non-empty string > 1000 chars", test_struct_nonempty)

def test_struct_modes_differ():
    default = _prompt()
    auto = _prompt(permission_mode="auto")
    assert default != auto, "default and auto mode prompts should differ"

run("STRUCT  default vs auto mode prompts differ", test_struct_modes_differ)

# ── Report ──────────────────────────────────────────────────────
ok = summary("§3 Prompt System")
sys.exit(0 if ok else 1)
