"""
Screenshot Tool — capture and analyze screen content via Vision API.

CC-aligned: follows the same cross-thread pattern as AskUserTool.
The tool itself is a schema definition; actual capture logic is handled
by the engine's special-case branch (like AskUser) which delegates to
the main Qt thread for screen capture.
"""

from tools.base import BaseTool


class ScreenshotTool(BaseTool):
    """Capture a screenshot and analyze it using Vision."""

    name = "Screenshot"
    description = (
        "Capture a screenshot of the user's screen and analyze it using Vision.\n\n"
        "Use this when the user asks you to 'look at' something on their screen, "
        "help with a visual issue, analyze a UI, read an error dialog, or when "
        "you need to see what they're currently seeing.\n\n"
        "Modes:\n"
        "- active_window: Capture the currently focused window (default, recommended)\n"
        "- full: Capture the entire screen\n"
        "- region: Let the user select a specific area to capture\n\n"
        "The screenshot will be sent as an image for you to analyze. "
        "Describe what you see and provide relevant help based on the prompt."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["active_window", "full", "region"],
                "description": (
                    "Capture mode. 'active_window' captures the currently focused window "
                    "(best for analyzing specific apps). 'full' captures the entire desktop. "
                    "'region' lets the user draw a rectangle to select what to capture."
                ),
                "default": "active_window",
            },
            "prompt": {
                "type": "string",
                "description": (
                    "What to analyze in the screenshot. Be specific about what you're "
                    "looking for (e.g., 'What error is shown?', 'Describe this UI layout', "
                    "'Read the text in this dialog')."
                ),
            },
        },
        "required": ["prompt"],
    }
    is_read_only = True
    is_destructive = False
    concurrency_safe = False  # Needs UI interaction (especially for region mode)

    def execute(self, input_data: dict) -> str:
        """
        This method is NOT called directly by the engine.
        The engine has special-case handling for 'Screenshot' (like AskUser)
        that emits a signal to the main thread for capture.
        This is kept as a fallback / documentation.
        """
        return (
            "Screenshot tool requires GUI context. "
            "This should be handled by the engine's special Screenshot branch."
        )
