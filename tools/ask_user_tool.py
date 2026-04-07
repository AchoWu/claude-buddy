"""
Ask User Question Tool — present a question to the user and collect their answer.

Aligned with Claude Code's AskUserQuestionTool pattern:
- Formats a question with optional selectable options
- Supports single-select and multi-select modes
- Read-only: actual UI interaction is handled by the engine/UI layer
- The tool returns a formatted prompt; the engine intercepts it and
  shows a Qt dialog or inline widget, then feeds the user's answer back.
"""

from tools.base import BaseTool


class AskUserQuestionTool(BaseTool):
    name = "AskUser"
    description = (
        "Ask the user a question and wait for their response.\n\n"
        "Use this tool when you need clarification, confirmation, or a choice from "
        "the user before proceeding. Do NOT guess or assume — ask.\n\n"
        "When to use this tool:\n"
        "- You need to choose between multiple valid approaches\n"
        "- A requirement is ambiguous and you need clarification\n"
        "- You need confirmation before a destructive or irreversible action\n"
        "- You need a value (name, path, preference) that was not provided\n"
        "- You need information that isn't available in the codebase or context\n\n"
        "When NOT to use this tool:\n"
        "- The answer is clearly stated in the conversation or context\n"
        "- You can make a reasonable default choice and mention it\n"
        "- The question is trivial or would interrupt the user's flow unnecessarily\n"
        "- For rhetorical questions or status updates\n\n"
        "Tips:\n"
        "- Keep questions concise and specific\n"
        "- When providing options, include a short description for each so the user "
        "can make an informed choice\n"
        "- Prefer providing options over open-ended questions when the choices are known\n"
        "- For yes/no questions, you can omit the options list\n\n"
        "IMPORTANT: Only use this tool when you genuinely need user input to continue."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "The question to ask the user. Should be clear, concise, "
                    "and indicate what information you need to proceed."
                ),
            },
            "options": {
                "type": "array",
                "description": (
                    "Optional list of choices for the user to pick from. "
                    "If omitted, the user can respond with free-form text."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": (
                                "Short label for this option (shown as the "
                                "selectable item)"
                            ),
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "Optional longer description explaining what "
                                "this option means or does"
                            ),
                        },
                    },
                    "required": ["label"],
                },
            },
            "multiSelect": {
                "type": "boolean",
                "description": (
                    "If true, the user can select multiple options. "
                    "Only meaningful when 'options' is provided. Defaults to false."
                ),
                "default": False,
            },
        },
        "required": ["question"],
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        question = input_data.get("question", "").strip()
        if not question:
            return "Error: 'question' must be a non-empty string."

        options = input_data.get("options")
        multi_select = input_data.get("multiSelect", False)

        # ----- Build the formatted output -----
        # The engine/UI layer intercepts this output, displays it to the user
        # via a Qt dialog or inline widget, collects the user's response, and
        # feeds it back as the tool result.
        parts: list[str] = []
        parts.append(f"Question: {question}")

        if options:
            # Validate: must be a non-empty list of dicts with 'label'
            if not isinstance(options, list) or len(options) == 0:
                return (
                    "Error: 'options' must be a non-empty list of objects "
                    "with at least a 'label' field."
                )

            valid_options: list[dict] = []
            for i, opt in enumerate(options):
                if not isinstance(opt, dict) or "label" not in opt:
                    return (
                        f"Error: options[{i}] is invalid — each option must be "
                        f"an object with at least a 'label' field."
                    )
                label = opt["label"].strip()
                if not label:
                    return f"Error: options[{i}].label must not be empty."
                valid_options.append(opt)

            mode_label = "Multi-select" if multi_select else "Single-select"
            parts.append(
                f"\n{mode_label} — choose "
                f"{'one or more' if multi_select else 'one'}:"
            )
            for idx, opt in enumerate(valid_options, start=1):
                label = opt["label"].strip()
                desc = opt.get("description", "").strip()
                if desc:
                    parts.append(f"  {idx}. {label} — {desc}")
                else:
                    parts.append(f"  {idx}. {label}")
        else:
            parts.append("\n(Free-form response expected)")

        return "\n".join(parts)
