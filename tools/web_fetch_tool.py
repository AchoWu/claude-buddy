"""
Web Fetch Tool v3 — fetch and convert web page content.
Aligned with Claude Code's WebFetchTool:
  - 15-minute in-memory cache
  - Redirect detection and reporting
  - Prompt-based extraction via LLM (CC: applyPromptToMarkdown)
  - 100K character buffer (CC-aligned: MAX_MARKDOWN_LENGTH)
  - HTTP status code tracking
  - Byte count in output
"""

import time
from urllib.parse import urlparse
from tools.base import BaseTool


# CC-aligned: 100K character limit (CC uses 100_000)
MAX_CONTENT_LENGTH = 100_000

# Threshold above which LLM extraction is used when a prompt is provided
_EXTRACTION_THRESHOLD = 20_000

# 15-minute self-cleaning cache (stores raw content before extraction)
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


def _extract_with_llm(content: str, prompt: str, provider_call_fn, abort_signal=None) -> str:
    """
    CC-aligned: applyPromptToMarkdown — use LLM to extract relevant
    information from fetched content based on the user's prompt.

    This is the key differentiator vs naive truncation: instead of cutting
    off content at a character limit, we ask the model to extract what's
    relevant to the user's question.

    Returns:
        Extracted text prefixed with [LLM-extracted] marker.
    """
    if not provider_call_fn:
        # No provider available — fall back to truncation
        return content[:MAX_CONTENT_LENGTH]

    # Truncate to MAX_CONTENT_LENGTH before sending to model (CC does this too)
    if len(content) > MAX_CONTENT_LENGTH:
        truncated = content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated due to length...]"
    else:
        truncated = content

    extraction_prompt = (
        f"Below is the content fetched from a web page. "
        f"Extract and summarize the information relevant to this request: {prompt}\n\n"
        f"Rules:\n"
        f"- Return the relevant content faithfully — do not invent information\n"
        f"- Preserve important details, code snippets, numbers, and quotes\n"
        f"- If the entire content is relevant, return it as-is (shortened if needed)\n"
        f"- If only parts are relevant, extract those parts with context\n"
        f"- Keep the output under 15000 characters\n"
        f"- Use markdown formatting\n\n"
        f"---\n\n{truncated}"
    )

    try:
        raw, _, text = provider_call_fn(
            messages=[{"role": "user", "content": extraction_prompt}],
            system="You are a content extraction assistant. Extract relevant information faithfully.",
            tools=[],
            max_tokens=4096,
            abort_signal=abort_signal,
        )
        # Validate extraction succeeded (model returned meaningful content)
        if text and len(text.strip()) > 100:
            return (
                f"[LLM-extracted from {len(content):,} chars, prompt: \"{prompt}\"]\n\n"
                f"{text.strip()}"
            )
    except Exception:
        pass

    # Fallback: return truncated content if extraction fails
    return content[:MAX_CONTENT_LENGTH]


class WebFetchTool(BaseTool):
    name = "WebFetch"
    description = (
        "Fetch content from a URL and convert HTML to readable text/markdown.\n\n"
        "Features:\n"
        "- HTML is converted to markdown via html2text\n"
        "- JSON responses are returned as-is\n"
        "- 15-minute cache for repeated requests to the same URL\n"
        "- Redirect detection: reports if URL redirected to a different host\n"
        "- When a prompt is provided and content is long, uses LLM to extract relevant info\n"
        "- Returns up to 100,000 characters (summarized if longer)\n\n"
        "Parameters:\n"
        "- url: the URL to fetch (required)\n"
        "- prompt: what information to extract (optional but recommended for large pages)\n\n"
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

    def __init__(self):
        self._engine = None  # injected by ToolRegistry

    def _get_provider_call_fn(self):
        """Get the provider's call_sync function if available."""
        if self._engine and self._engine._provider:
            return self._engine._provider.call_sync
        return None

    def _get_abort_signal(self):
        """Get the engine's abort signal if available."""
        if self._engine:
            return self._engine._abort_signal
        return None

    def execute(self, input_data: dict) -> str:
        url = input_data["url"]
        prompt = input_data.get("prompt", "")

        # Check cache first — cache stores raw content, extraction runs on each call
        cached = _cache_get(url)
        if cached:
            # If cached content is long and prompt provided, still do LLM extraction
            if len(cached) > _EXTRACTION_THRESHOLD and prompt:
                content = _extract_with_llm(
                    cached, prompt,
                    self._get_provider_call_fn(),
                    self._get_abort_signal(),
                )
                return f"(cached) {content}\n({len(cached):,} chars cached)"
            # Short content or no prompt — return as-is
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

            # ── Convert to readable text ──────────────────────────────
            if "json" in content_type:
                content = resp.text[:MAX_CONTENT_LENGTH]
            elif "html" in content_type:
                try:
                    import html2text
                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.ignore_images = True
                    h.body_width = 0
                    content = h.handle(resp.text)
                except ImportError:
                    import re
                    text = re.sub(r"<[^>]+>", " ", resp.text)
                    text = re.sub(r"\s+", " ", text).strip()
                    content = text
            else:
                content = resp.text

            # Cache raw content (before extraction) so different prompts can reuse it
            _cache_set(url, content)

            # ── CC-aligned: intelligent extraction vs naive truncation ──
            used_extraction = False
            if len(content) > _EXTRACTION_THRESHOLD and prompt:
                content = _extract_with_llm(
                    content, prompt,
                    self._get_provider_call_fn(),
                    self._get_abort_signal(),
                )
                used_extraction = True
            elif len(content) > MAX_CONTENT_LENGTH:
                content = content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated due to length...]"

            # Build output
            parts = []
            if redirect_info:
                parts.append(redirect_info)
            if prompt and not used_extraction:
                parts.append(f"[Extract: {prompt}]\n")
            parts.append(content)
            parts.append(f"\n({byte_count:,} bytes fetched)")

            return "".join(parts)

        except ImportError:
            return "Error: httpx not installed. Run: pip install httpx"
        except Exception as e:
            return f"Fetch error: {e}"
