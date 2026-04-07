"""
Team Tools — create and manage multi-agent teams.
Aligned with Claude Code's TeamCreateTool / TeamDeleteTool.
"""

from tools.base import BaseTool


class TeamCreateTool(BaseTool):
    name = "TeamCreate"
    description = (
        "Create a team of agents that can work together on a task.\n\n"
        "A team is a named group of agents that share memory and can\n"
        "communicate via SendMessage.\n\n"
        "Parameters:\n"
        "- team_name: Name for the team\n"
        "- description: What the team will work on\n"
        "- agent_count: Number of agents to spawn (default: 2)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "team_name": {
                "type": "string",
                "description": "Name for the agent team",
            },
            "description": {
                "type": "string",
                "description": "Description of the team's task",
            },
            "agent_count": {
                "type": "integer",
                "description": "Number of agents (default: 2, max: 5)",
                "default": 2,
            },
        },
        "required": ["team_name"],
    }
    is_read_only = False

    def __init__(self):
        self._agent_registry = None

    def execute(self, input_data: dict) -> str:
        team_name = input_data.get("team_name", "").strip()
        description = input_data.get("description", "")
        count = min(input_data.get("agent_count", 2), 5)

        if not team_name:
            return "Error: team_name is required."

        if not self._agent_registry:
            return "Error: Agent registry not available."

        agent_ids = []
        for i in range(count):
            aid = self._agent_registry.register(
                name=f"{team_name}_agent_{i+1}",
                team=team_name,
                description=description,
            )
            agent_ids.append(aid)

        return (
            f"Team '{team_name}' created with {count} agents:\n"
            + "\n".join(f"  - {aid}" for aid in agent_ids)
            + f"\n\nUse SendMessage to communicate with agents."
        )


class TeamDeleteTool(BaseTool):
    name = "TeamDelete"
    description = (
        "Delete an agent team and all its agents.\n\n"
        "Parameters:\n"
        "- team_name: Name of the team to delete"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "team_name": {
                "type": "string",
                "description": "Name of the team to delete",
            },
        },
        "required": ["team_name"],
    }
    is_read_only = False

    def __init__(self):
        self._agent_registry = None

    def execute(self, input_data: dict) -> str:
        team_name = input_data.get("team_name", "").strip()
        if not team_name:
            return "Error: team_name is required."

        if not self._agent_registry:
            return "Error: Agent registry not available."

        # Find and remove agents in this team
        agents = self._agent_registry.list_agents()
        removed = 0
        for agent in agents:
            if agent.get("team") == team_name:
                self._agent_registry._agents.pop(agent["id"], None)
                if agent.get("name"):
                    self._agent_registry._agents.pop(agent["name"], None)
                removed += 1

        if removed == 0:
            return f"Team '{team_name}' not found or already deleted."
        return f"Team '{team_name}' deleted ({removed} agents removed)."
