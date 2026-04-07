"""
Web Search Tool — robust web search with multiple fallback strategies.
"""

import re
import json
from tools.base import BaseTool


class WebSearchTool(BaseTool):
    name = "WebSearch"
    description = (
        "Search the web for information using DuckDuckGo.\n\n"
        "Use for:\n"
        "- Current events and recent information\n"
        "- Documentation lookup\n"
        "- Any information beyond your training data\n\n"
        "Returns search results with titles, URLs, and snippets.\n\n"
        "IMPORTANT: After answering the user's question based on search results, "
        "you MUST include a 'Sources:' section at the end listing the URLs.\n"
        "Example:\n"
        "  Sources:\n"
        "  - [Title](https://example.com)\n\n"
        "REMINDER: Always include Sources with URLs when reporting web search results."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
        },
        "required": ["query"],
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        query = input_data["query"]

        try:
            import httpx
        except ImportError:
            return "Error: httpx not installed. Run: pip install httpx"

        # Strategy 1: DuckDuckGo Instant Answer API (JSON, most stable)
        result = self._try_ddg_api(httpx, query)
        if result:
            return result

        # Strategy 2: DuckDuckGo HTML search (fallback)
        result = self._try_ddg_html(httpx, query)
        if result:
            return result

        return f"No results found for: {query}"

    def _try_ddg_api(self, httpx, query: str) -> str | None:
        """DuckDuckGo Instant Answer API — stable JSON, good for facts."""
        try:
            resp = httpx.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                headers={"User-Agent": "ClaudeBuddy/1.0"},
                timeout=10,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            results = []

            # Abstract (main answer)
            if data.get("Abstract"):
                results.append(
                    f"**{data.get('Heading', 'Answer')}**\n"
                    f"{data['AbstractURL']}\n"
                    f"{data['Abstract']}\n"
                )

            # Related topics
            for topic in data.get("RelatedTopics", [])[:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    url = topic.get("FirstURL", "")
                    text = topic["Text"]
                    results.append(f"• {text}\n  {url}\n")

            if results:
                return "\n".join(results)
            return None

        except Exception:
            return None

    def _try_ddg_html(self, httpx, query: str) -> str | None:
        """DuckDuckGo HTML search — broader results, regex extraction."""
        try:
            resp = httpx.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=15,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return None

            html = resp.text
            results = []

            # Extract result blocks using multiple regex patterns for resilience
            # Pattern 1: result__a (title links)
            titles = self._extract_clean(
                r'class="result__a"[^>]*>(.*?)</a', html
            )
            # Pattern 2: result__snippet
            snippets = self._extract_clean(
                r'class="result__snippet"[^>]*>(.*?)</(?:a|span|td)', html
            )
            # Pattern 3: result__url
            urls = self._extract_clean(
                r'class="result__url"[^>]*>(.*?)</a', html
            )

            # Alternative patterns if primary ones fail
            if not titles:
                titles = self._extract_clean(
                    r'class="[^"]*result[^"]*title[^"]*"[^>]*>(.*?)</a', html
                )
            if not snippets:
                snippets = self._extract_clean(
                    r'class="[^"]*result[^"]*body[^"]*"[^>]*>(.*?)</(?:div|td|span)', html
                )

            for i in range(min(5, max(len(titles), len(snippets)))):
                title = titles[i] if i < len(titles) else ""
                snippet = snippets[i] if i < len(snippets) else ""
                url = urls[i] if i < len(urls) else ""
                if title or snippet:
                    results.append(f"**{title}**\n{url}\n{snippet}\n")

            return "\n".join(results) if results else None

        except Exception:
            return None

    @staticmethod
    def _extract_clean(pattern: str, html: str) -> list[str]:
        """Extract and clean HTML matches."""
        matches = re.findall(pattern, html, re.DOTALL)
        cleaned = []
        for m in matches:
            text = re.sub(r"<[^>]+>", "", m).strip()
            text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            text = text.replace("&quot;", '"').replace("&#39;", "'")
            if text:
                cleaned.append(text)
        return cleaned
