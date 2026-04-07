"""
SendMessage Tool — inter-agent communication.
Aligned with Claude Code's SendMessageTool.

Agents spawned by AgentTool get a unique ID. SendMessage allows
sending a message to a running or completed agent to continue its work.
"""

from tools.base import BaseTool


class SendMessageTool(BaseTool):
    name = "SendMessage"
    description = (
        "Send a message to another agent (sub-agent) by ID or name.\n\n"
        "Use this tool to continue a previously spawned agent's work, "
        "or to coordinate between multiple agents.\n\n"
        "The target agent resumes with its full conversation context preserved.\n"
        "The message you send becomes a new user turn in that agent's conversation.\n\n"
        "When to use:\n"
        "- To follow up on a sub-agent's work\n"
        "- To provide additional instructions to a running agent\n"
        "- To ask a completed agent to do more work\n\n"
        "Parameters:\n"
        "- to: Agent ID or name to send the message to\n"
        "- message: The message content to send"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Agent ID or name to send the message to",
            },
            "message": {
                "type": "string",
                "description": "The message content to send to the agent",
            },
        },
        "required": ["to", "message"],
    }
    is_read_only = False

    def __init__(self):
        self._engine = None  # injected by ToolRegistry
        self._agent_registry = None  # shared agent registry

    def execute(self, input_data: dict) -> str:
        target = input_data.get("to", "").strip()
        message = input_data.get("message", "").strip()

        if not target:
            return "Error: 'to' (agent ID or name) is required."
        if not message:
            return "Error: 'message' must not be empty."

        if not self._engine:
            return "Error: SendMessage requires engine connection (not available)."

        # Look up agent in the agent registry
        if self._agent_registry:
            agent_record = self._agent_registry.get(target)
            if agent_record:
                return self._send_to_agent(agent_record, message)

        return (
            f"Error: Agent '{target}' not found. "
            f"Make sure the agent was spawned with the Agent tool "
            f"and use the correct ID or name."
        )

    def _send_to_agent(self, agent_record: dict, message: str) -> str:
        """Send a message to an agent, continuing its conversation."""
        if not self._engine:
            return "Error: No engine available."

        # The agent_record contains the agent's conversation state
        agent_messages = agent_record.get("messages", [])
        agent_system = agent_record.get("system_prompt", "")

        # Add the new message
        agent_messages.append({"role": "user", "content": message})

        # Run the agent for one more turn
        try:
            result = self._engine.run_sub_agent(
                system_prompt=agent_system,
                user_prompt=message,
            )
            return f"Agent responded:\n{result}"
        except Exception as e:
            return f"Error sending message to agent: {e}"


class AgentRegistry:
    """
    Registry tracking spawned agents and their conversation state.
    Shared between AgentTool and SendMessageTool.
    """

    def __init__(self):
        self._agents: dict[str, dict] = {}
        self._next_id = 1

    def register(self, name: str | None = None, **metadata) -> str:
        """Register a new agent. Returns the agent ID."""
        agent_id = f"agent_{self._next_id}"
        self._next_id += 1
        record = {
            "id": agent_id,
            "name": name or agent_id,
            "status": "running",
            "messages": [],
            "system_prompt": "",
            **metadata,
        }
        self._agents[agent_id] = record
        if name:
            self._agents[name] = record  # also index by name
        return agent_id

    def get(self, id_or_name: str) -> dict | None:
        return self._agents.get(id_or_name)

    def update(self, agent_id: str, **updates):
        record = self._agents.get(agent_id)
        if record:
            record.update(updates)

    def list_agents(self) -> list[dict]:
        seen = set()
        result = []
        for record in self._agents.values():
            aid = record["id"]
            if aid not in seen:
                seen.add(aid)
                result.append(record)
        return result
