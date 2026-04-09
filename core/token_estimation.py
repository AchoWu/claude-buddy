"""
Token Estimation — CC-aligned accurate token counting.
CC: src/utils/tokens.ts uses tiktoken for accurate counts.

Strategy: try tiktoken (pip install tiktoken), fall back to char-based heuristic.
"""

import json
from typing import Any

# Try to load tiktoken at module level (one-time cost)
_encoder = None
_tiktoken_available = False

try:
    import tiktoken
    
    # For PyInstaller bundled apps, use pre-loaded cache
    import sys
    if getattr(sys, 'frozen', False):
        # Running as bundled executable
        import os
        cache_dir = os.path.join(os.path.dirname(sys.executable), 'tiktoken_cache')
        if os.path.exists(cache_dir):
            # Set cache directory for tiktoken
            import tiktoken.core
            tiktoken.core.data_gym_cache = cache_dir
    
    _encoder = tiktoken.get_encoding("cl100k_base")  # Claude/GPT-4 encoding
    _tiktoken_available = True
except ImportError:
    pass


def count_tokens(text: str) -> int:
    """Count tokens in a string. Uses tiktoken if available, else heuristic."""
    if not text:
        return 0
    if _tiktoken_available and _encoder:
        try:
            return len(_encoder.encode(text, disallowed_special=()))
        except Exception:
            return _heuristic_count(text)
    return _heuristic_count(text)


def count_message_tokens(content: Any) -> int:
    """Count tokens in a message content (str, list, or dict)."""
    if isinstance(content, str):
        return count_tokens(content)
    elif isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                for v in block.values():
                    if isinstance(v, str):
                        total += count_tokens(v)
                    elif isinstance(v, dict):
                        total += count_tokens(json.dumps(v, ensure_ascii=False))
        return total
    elif isinstance(content, dict):
        return count_tokens(json.dumps(content, ensure_ascii=False))
    return 0


def is_tiktoken_available() -> bool:
    """Check if tiktoken is installed for accurate counting."""
    return _tiktoken_available


def _heuristic_count(text: str) -> int:
    """Fallback: CJK-aware character heuristic (~±15% accuracy)."""
    if not text:
        return 0
    sample = text[:500]
    cjk = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
    ratio = cjk / max(len(sample), 1)
    chars_per_token = 1.5 * ratio + 4.0 * (1 - ratio)
    if any(c in sample for c in '{}();=<>[]'):
        chars_per_token = min(chars_per_token, 3.5)
    return max(1, int(len(text) / chars_per_token))
