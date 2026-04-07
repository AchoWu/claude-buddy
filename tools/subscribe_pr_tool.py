"""
SubscribePRTool — CC-aligned PR webhook subscription.
CC: Kairos GitHub webhooks. BUDDY workaround: polling via gh CLI.
"""

import subprocess
import json
from pathlib import Path
from tools.base import BaseTool
from config import DATA_DIR


class SubscribePRTool(BaseTool):
    name = "SubscribePR"
    description = (
        "Watch a GitHub PR for updates. Checks the PR state via `gh pr view` "
        "and reports changes (new comments, reviews, status). "
        "Use action='check' to get current state, 'subscribe' to set up monitoring."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["check", "subscribe", "unsubscribe", "list"],
                "description": "Action to perform",
            },
            "pr_url": {
                "type": "string",
                "description": "GitHub PR URL (required for check/subscribe)",
            },
        },
        "required": ["action"],
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        action = input_data.get("action", "check")
        pr_url = input_data.get("pr_url", "")

        watches_dir = DATA_DIR / "pr_watches"
        watches_dir.mkdir(parents=True, exist_ok=True)

        if action == "check":
            if not pr_url:
                return "Error: pr_url required."
            return self._check_pr(pr_url)

        elif action == "subscribe":
            if not pr_url:
                return "Error: pr_url required."
            state = self._check_pr(pr_url)
            # Save current state
            safe_name = pr_url.replace("/", "_").replace(":", "_")[-60:]
            state_file = watches_dir / f"{safe_name}.json"
            state_file.write_text(json.dumps({
                "url": pr_url,
                "last_check": state,
            }), encoding="utf-8")
            return f"Subscribed to PR updates: {pr_url}\nCurrent state:\n{state}"

        elif action == "unsubscribe":
            if not pr_url:
                return "Error: pr_url required."
            safe_name = pr_url.replace("/", "_").replace(":", "_")[-60:]
            state_file = watches_dir / f"{safe_name}.json"
            if state_file.exists():
                state_file.unlink()
                return f"Unsubscribed from: {pr_url}"
            return "Not subscribed to this PR."

        elif action == "list":
            watched = list(watches_dir.glob("*.json"))
            if not watched:
                return "No PR subscriptions."
            lines = ["Watched PRs:"]
            for f in watched:
                try:
                    data = json.loads(f.read_text())
                    lines.append(f"  {data.get('url', f.stem)}")
                except Exception:
                    pass
            return "\n".join(lines)

        return f"Unknown action: {action}"

    def _check_pr(self, pr_url: str) -> str:
        """Check PR state via gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "pr", "view", pr_url, "--json",
                 "state,title,author,comments,reviews,statusCheckRollup"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return f"Error checking PR: {result.stderr.strip()}"

            data = json.loads(result.stdout)
            lines = [
                f"PR: {data.get('title', '?')}",
                f"State: {data.get('state', '?')}",
                f"Author: {data.get('author', {}).get('login', '?')}",
                f"Comments: {len(data.get('comments', []))}",
                f"Reviews: {len(data.get('reviews', []))}",
            ]

            checks = data.get("statusCheckRollup", [])
            if checks:
                passed = sum(1 for c in checks if c.get("conclusion") == "SUCCESS")
                failed = sum(1 for c in checks if c.get("conclusion") == "FAILURE")
                lines.append(f"Checks: {passed} passed, {failed} failed, {len(checks)} total")

            return "\n".join(lines)
        except FileNotFoundError:
            return "Error: `gh` CLI not found. Install GitHub CLI: https://cli.github.com"
        except subprocess.TimeoutExpired:
            return "Error: PR check timed out."
        except Exception as e:
            return f"Error: {e}"
