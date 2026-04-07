"""
WorkflowTool — CC-aligned workflow state machine.
CC: feature-gated behind WORKFLOW_SCRIPTS.
Manages multi-step named workflows for self-organization.
"""

from tools.base import BaseTool


# In-memory workflow store
_workflows: dict[str, dict] = {}


class WorkflowTool(BaseTool):
    name = "Workflow"
    description = (
        "Manage multi-step workflows. Create named workflows with steps, "
        "advance through them, and track progress. Useful for organizing "
        "complex multi-step tasks."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "advance", "status", "list", "delete"],
                "description": "Workflow action to perform",
            },
            "name": {
                "type": "string",
                "description": "Workflow name (required for create/advance/status/delete)",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Step descriptions (required for create)",
            },
        },
        "required": ["action"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        action = input_data.get("action", "list")
        name = input_data.get("name", "")

        if action == "create":
            steps = input_data.get("steps", [])
            if not name or not steps:
                return "Error: name and steps required for create."
            _workflows[name] = {"steps": steps, "current": 0, "completed": []}
            return f"Workflow '{name}' created with {len(steps)} steps.\nNext: {steps[0]}"

        elif action == "advance":
            if name not in _workflows:
                return f"Workflow '{name}' not found."
            wf = _workflows[name]
            if wf["current"] >= len(wf["steps"]):
                return f"Workflow '{name}' already completed."
            wf["completed"].append(wf["steps"][wf["current"]])
            wf["current"] += 1
            if wf["current"] >= len(wf["steps"]):
                return f"Workflow '{name}' completed! All {len(wf['steps'])} steps done."
            return f"Step {wf['current']}/{len(wf['steps'])} completed.\nNext: {wf['steps'][wf['current']]}"

        elif action == "status":
            if name not in _workflows:
                return f"Workflow '{name}' not found."
            wf = _workflows[name]
            lines = [f"Workflow: {name} ({wf['current']}/{len(wf['steps'])} steps)"]
            for i, step in enumerate(wf["steps"]):
                mark = "✅" if i < wf["current"] else ("▶" if i == wf["current"] else "⬜")
                lines.append(f"  {mark} {i+1}. {step}")
            return "\n".join(lines)

        elif action == "list":
            if not _workflows:
                return "No active workflows."
            lines = ["Active Workflows:"]
            for n, wf in _workflows.items():
                lines.append(f"  {n}: {wf['current']}/{len(wf['steps'])} steps")
            return "\n".join(lines)

        elif action == "delete":
            if _workflows.pop(name, None):
                return f"Workflow '{name}' deleted."
            return f"Workflow '{name}' not found."

        return f"Unknown action: {action}"
