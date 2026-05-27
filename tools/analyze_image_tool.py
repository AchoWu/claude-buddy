"""
AnalyzeImage Tool — sends a pending image to the dedicated vision model.

The main agent calls this tool with a custom prompt to analyze user-attached images.
The vision model (hunyuan-turbos-vision-latest) is separate from the conversation model.

Flow:
  1. User attaches image in chat → stored as engine._pending_image
  2. Main agent sees "[User attached an image. Use AnalyzeImage tool...]"
  3. Agent calls AnalyzeImage with a specific prompt (e.g., "识别报错信息")
  4. This tool calls the vision model and returns the text description
  5. Agent uses the description to answer the user's question
"""

from tools.base import BaseTool


class AnalyzeImageTool(BaseTool):
    """Analyze a user-attached image using the dedicated vision model."""

    name = "AnalyzeImage"
    description = (
        "Analyze an image using a vision model. You MUST call this tool whenever "
        "the user's message contains '[Image #N]' markers, or when a FileRead "
        "returns image data (base64).\n\n"
        "How it works:\n"
        "- The image is already loaded in memory (from user upload or FileRead)\n"
        "- You provide a 'prompt' telling the vision model what to focus on\n"
        "- The vision model returns a text description of the image\n"
        "- You then use that description to answer the user's question\n\n"
        "IMPORTANT: Write the prompt based on what the user is asking:\n"
        "- User asks about an error → prompt: '识别图中的错误信息、错误类型和堆栈追踪'\n"
        "- User asks about UI/design → prompt: '描述界面布局、按钮、文字和配色'\n"
        "- User asks to read text → prompt: '提取图片中所有可见文字，按顺序排列'\n"
        "- User asks about location/position → prompt: '描述图中所有元素的位置，用行列或坐标表示'\n"
        "- General question → prompt: '详细描述图片的完整内容'\n\n"
        "Always call this tool BEFORE answering image-related questions. "
        "Do NOT guess what's in the image without calling this tool first."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "What to look for in the image. Be specific based on the user's question. "
                    "For example, if user asks about an error, use '识别图中的错误信息和堆栈追踪'. "
                    "If user asks about UI, use '描述这个界面的布局、按钮和文字内容'."
                ),
            },
        },
        "required": ["prompt"],
    }
    is_read_only = True
    is_destructive = False
    concurrency_safe = False  # uses engine._pending_image state

    def __init__(self):
        self._engine = None  # injected by ToolRegistry

    def execute(self, input_data: dict) -> str:
        prompt = input_data.get("prompt", "Please describe this image in detail.")

        if not self._engine:
            return "Error: Engine not configured for AnalyzeImage tool."

        return self._engine.call_vision_model(prompt)
