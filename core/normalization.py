"""
Message Normalization — CC-aligned message preprocessing pipeline.
CC: normalizeMessagesForAPI() in src/utils/messages.ts

Transforms messages before sending to the API:
1. Strip virtual/display-only messages
2. Merge consecutive user messages (Bedrock requirement, good practice)
3. Remove orphaned tool_result blocks (no matching tool_use)
4. Strip empty messages
"""

from typing import Any


def normalize_messages(messages: list[dict]) -> list[dict]:
    """
    CC-aligned: normalize messages for API consumption.
    Returns a new list (does not mutate input).
    """
    if not messages:
        return messages

    result = []

    # Pass 1: filter out virtual and empty messages
    for msg in messages:
        # Skip virtual/display-only messages
        if msg.get("virtual") or msg.get("is_virtual"):
            continue
        # Skip empty content
        content = msg.get("content")
        if content is None or content == "" or content == []:
            continue
        result.append(dict(msg))  # shallow copy

    # Pass 2: collect tool_use IDs from assistant messages
    tool_use_ids: set[str] = set()
    for msg in result:
        if msg.get("role") == "assistant":
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_ids.add(block.get("id", ""))

    # Pass 3: remove orphaned tool_result blocks
    cleaned = []
    for msg in result:
        content = msg.get("content")
        if isinstance(content, list):
            filtered_blocks = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tid = block.get("tool_use_id", "")
                    if tid and tid not in tool_use_ids:
                        continue  # orphaned — skip
                filtered_blocks.append(block)
            if not filtered_blocks:
                continue  # all blocks removed
            msg = dict(msg)
            msg["content"] = filtered_blocks
        cleaned.append(msg)

    # Pass 4: merge consecutive user messages
    merged = []
    for msg in cleaned:
        if merged and merged[-1].get("role") == "user" and msg.get("role") == "user":
            prev = merged[-1]
            prev_content = prev.get("content", "")
            curr_content = msg.get("content", "")
            # Both strings: concatenate
            if isinstance(prev_content, str) and isinstance(curr_content, str):
                prev["content"] = prev_content + "\n" + curr_content
            # Both lists: extend
            elif isinstance(prev_content, list) and isinstance(curr_content, list):
                prev["content"] = prev_content + curr_content
            # Mixed: convert to list
            else:
                prev_list = prev_content if isinstance(prev_content, list) else [{"type": "text", "text": str(prev_content)}]
                curr_list = curr_content if isinstance(curr_content, list) else [{"type": "text", "text": str(curr_content)}]
                prev["content"] = prev_list + curr_list
        else:
            merged.append(msg)

    return merged
