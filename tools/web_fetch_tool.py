"""
Web Fetch Tool v2 — fetch and convert web page content.
Aligned with Claude Code's WebFetchTool:
  - 15-minute in-memory cache
  - Redirect detection and reporting
  - Prompt-based extraction parameter
  - HTTP status code tracking
  - Byte count in output
"""

import time
from urllib.parse import urlparse
from tools.base import BaseTool


# 15-minute self-cleaning cache
_fetch_cache: dict[str, dict] = {}
_CACHE_TTL = 900  # 15 minutes


def _cache_get(url: str) -> str | None:
    """Get cached response if fresh."""
    entry = _fetch_cache.get(url)
    if entry and (time.time() - entry["time"]) < _CACHE_TTL:
        return entry["content"]
    # Clean stale entry
    _fetch_cache.pop(url, None)
    return None


def _cache_set(url: str, content: str):
    """Store response in cache."""
    # Clean old entries (simple eviction: cap at 50)
    if len(_fetch_cache) > 50:
        oldest_key = min(_fetch_cache, key=lambda k: _fetch_cache[k]["time"])
        del _fetch_cache[oldest_key]
    _fetch_cache[url] = {"content": content, "time": time.time()}


class WebFetchTool(BaseTool):
    name = "WebFetch"
    description = (
        "Fetch content from a URL and convert HTML to readable text/markdown.\n\n"
        "Features:\n"
        "- HTML is converted to markdown via html2text\n"
        "- JSON responses are returned as-is\n"
        "- 15-minute cache for repeated requests to the same URL\n"
        "- Redirect detection: reports if URL redirected to a different host\n"
        "- Optional prompt parameter to extract specific information\n"
        "- Returns first 10,000 characters\n\n"
        "Parameters:\n"
        "- url: the URL to fetch (required)\n"
        "- prompt: what information to extract (optional, helps focus the output)\n\n"
        "NOTE: This tool WILL FAIL for authenticated/private URLs (Google Docs, Jira, etc.)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch",
            },
            "prompt": {
                "type": "string",
                "description": "Optional: what information to extract from the page",
            },
        },
        "required": ["url"],
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        url = input_data["url"]
        prompt = input_data.get("prompt", "")

        # Check cache first
        cached = _cache_get(url)
        if cached:
            result = f"(cached) {cached}"
            if prompt:
                result = f"[Extract: {prompt}]\n\n{result}"
            return result

        try:
            import httpx
        except ImportError:
            return "Error: httpx not installed. Run: pip install httpx"

        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Claude Buddy)"},
                timeout=20,
                follow_redirects=True,
            )

            # Check for redirect to different host
            redirect_info = ""
            original_host = urlparse(url).netloc
            final_host = urlparse(str(resp.url)).netloc
            if original_host != final_host:
                redirect_info = (
                    f"[Redirected from {original_host} to {final_host}]\n"
                    f"Final URL: {resp.url}\n\n"
                )

            if resp.status_code != 200:
                return f"Fetch failed: HTTP {resp.status_code} {resp.reason_phrase}"

            content_type = resp.headers.get("content-type", "")
            byte_count = len(resp.content)

            if "json" in content_type:
                content = resp.text[:10000]
            elif "html" in content_type:
                try:
                    import html2text
                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.ignore_images = True
                    h.body_width = 0
                    content = h.handle(resp.text)[:10000]
                except ImportError:
                    import re
                    text = re.sub(r"<[^>]+>", " ", resp.text)
                    text = re.sub(r"\s+", " ", text).strip()
                    content = text[:10000]
            else:
                content = resp.text[:10000]

            # Cache the result
            _cache_set(url, content)

            # Build output
            parts = []
            if redirect_info:
                parts.append(redirect_info)
            if prompt:
                parts.append(f"[Extract: {prompt}]\n")
            parts.append(content)
            parts.append(f"\n({byte_count:,} bytes fetched)")

            return "".join(parts)

        except ImportError:
            return "Error: httpx not installed. Run: pip install httpx"
        except Exception as e:
            return f"Fetch error: {e}"
