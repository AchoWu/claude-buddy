#!/usr/bin/env python3
"""
BUDDY Test Runner — discovers and runs all test_*.py files in BUDDY/tests/.
Supports filtering by section, UI-only, or non-UI tests.

Usage:
    python run_all_tests.py                  # run all tests
    python run_all_tests.py --ui-only        # run only test_ui_*.py files
    python run_all_tests.py --no-ui          # run only non-UI test files
    python run_all_tests.py --section ui     # run tests matching *ui* in filename
    python run_all_tests.py --section s1     # run tests matching *s1* in filename
"""

import sys
import os
import io
import subprocess
import time
import argparse
from pathlib import Path

# Ensure UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Force offscreen rendering for Qt tests
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

BUDDY_DIR = Path(__file__).parent
TESTS_DIR = BUDDY_DIR / "tests"
TIMEOUT_SEC = 600  # 10 min for real API tests


def discover_tests(section=None, ui_only=False, no_ui=False):
    """Find test files matching criteria."""
    test_files = sorted(TESTS_DIR.glob("test_*.py"))

    if ui_only:
        test_files = [f for f in test_files if f.name.startswith("test_ui")]
    elif no_ui:
        test_files = [f for f in test_files if not f.name.startswith("test_ui")]

    if section:
        test_files = [f for f in test_files if section.lower() in f.name.lower()]

    return test_files


def run_test(test_path: Path):
    """Run a single test file, return (success, elapsed, output)."""
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    env['PYTHONIOENCODING'] = 'utf-8'

    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(test_path)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=TIMEOUT_SEC,
            cwd=str(BUDDY_DIR),
            env=env,
        )
        elapsed = time.time() - start
        output = (result.stdout or "") + (result.stderr or "")
        success = result.returncode == 0
        return success, elapsed, output
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return False, elapsed, f"TIMEOUT after {TIMEOUT_SEC}s"
    except Exception as e:
        elapsed = time.time() - start
        return False, elapsed, f"ERROR: {e}"


def main():
    parser = argparse.ArgumentParser(description="BUDDY Test Runner")
    parser.add_argument('--section', type=str, default=None,
                        help='Filter tests by section name (e.g. "ui", "s1", "integration")')
    parser.add_argument('--ui-only', action='store_true',
                        help='Run only UI test files (test_ui_*.py)')
    parser.add_argument('--no-ui', action='store_true',
                        help='Run only non-UI test files')
    args = parser.parse_args()

    if args.ui_only and args.no_ui:
        print("ERROR: Cannot use --ui-only and --no-ui together")
        sys.exit(2)

    test_files = discover_tests(
        section=args.section,
        ui_only=args.ui_only,
        no_ui=args.no_ui,
    )

    if not test_files:
        print("No test files found matching criteria.")
        sys.exit(2)

    print(f"\n{'='*60}")
    print(f"  BUDDY Test Runner — {len(test_files)} test file(s)")
    print(f"{'='*60}\n")

    results = []
    total_pass = 0
    total_fail = 0

    for test_path in test_files:
        name = test_path.name
        print(f"  Running {name}...", end=" ", flush=True)

        success, elapsed, output = run_test(test_path)
        status = "✅" if success else "❌"
        results.append((name, success, elapsed, output))

        if success:
            total_pass += 1
        else:
            total_fail += 1

        print(f"{status}  ({elapsed:.1f}s)")

    # Summary table
    print(f"\n{'='*60}")
    print(f"  {'Test File':<40} {'Status':<8} {'Time':>6}")
    print(f"  {'-'*40} {'-'*8} {'-'*6}")
    for name, success, elapsed, output in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {name:<40} {status:<8} {elapsed:>5.1f}s")

    print(f"\n  {'='*50}")
    print(f"  Total: {total_pass} passed, {total_fail} failed, {len(results)} total")
    print(f"  {'='*50}\n")

    # Print failures detail
    if total_fail > 0:
        print("  Failed test output:")
        print(f"  {'-'*50}")
        for name, success, elapsed, output in results:
            if not success:
                print(f"\n  --- {name} ---")
                for line in output.strip().split('\n'):
                    print(f"    {line}")
        print()

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
