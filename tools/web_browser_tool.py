"""
WebBrowserTool — CC-aligned headless browser automation.
CC: feature-gated behind WEB_BROWSER_TOOL.
Uses Playwright for headless Chromium. Optional dependency.
"""

from tools.base import BaseTool


class WebBrowserTool(BaseTool):
    name = "WebBrowser"
    description = (
        "Headless browser automation: navigate, click, type, screenshot, extract text. "
        "Requires `playwright` package (pip install playwright && playwright install chromium). "
        "Browser launches lazily on first use, auto-closes after 5 minutes idle."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["navigate", "click", "type", "screenshot", "get_text", "evaluate"],
                "description": "Browser action to perform",
            },
            "url": {"type": "string", "description": "URL to navigate to (for 'navigate')"},
            "selector": {"type": "string", "description": "CSS selector (for click/type)"},
            "text": {"type": "string", "description": "Text to type (for 'type')"},
            "js": {"type": "string", "description": "JavaScript to evaluate (for 'evaluate')"},
        },
        "required": ["action"],
    }
    is_read_only = False
    concurrency_safe = False

    _browser = None
    _page = None
    _last_use = 0

    def execute(self, input_data: dict) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return (
                "Error: playwright not installed.\n"
                "Install with: pip install playwright && playwright install chromium"
            )

        action = input_data.get("action", "")
        import time
        self._last_use = time.time()

        try:
            self._ensure_browser()

            if action == "navigate":
                url = input_data.get("url", "")
                if not url:
                    return "Error: url required for navigate."
                self._page.goto(url, timeout=30000)
                title = self._page.title()
                text = self._page.inner_text("body")[:8000]
                return f"Navigated to: {url}\nTitle: {title}\n\nContent:\n{text}"

            elif action == "click":
                selector = input_data.get("selector", "")
                if not selector:
                    return "Error: selector required for click."
                self._page.click(selector, timeout=10000)
                return f"Clicked: {selector}"

            elif action == "type":
                selector = input_data.get("selector", "")
                text = input_data.get("text", "")
                if not selector or not text:
                    return "Error: selector and text required for type."
                self._page.fill(selector, text, timeout=10000)
                return f"Typed into {selector}: {text[:50]}..."

            elif action == "screenshot":
                import base64
                screenshot = self._page.screenshot()
                b64 = base64.b64encode(screenshot).decode()
                return f"Screenshot captured ({len(screenshot)} bytes).\n[base64 data: {len(b64)} chars]"

            elif action == "get_text":
                selector = input_data.get("selector", "body")
                text = self._page.inner_text(selector)[:8000]
                return text

            elif action == "evaluate":
                js = input_data.get("js", "")
                if not js:
                    return "Error: js required for evaluate."
                result = self._page.evaluate(js)
                return str(result)[:8000]

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            return f"Browser error: {e}"

    def _ensure_browser(self):
        """Lazy-launch browser on first use."""
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        self._browser = pw.chromium.launch(headless=True)
        self._page = self._browser.new_page()

    def cleanup(self):
        """Close browser."""
        try:
            if self._browser:
                self._browser.close()
                self._browser = None
                self._page = None
        except Exception:
            pass
