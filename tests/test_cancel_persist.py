"""
Test: Cancel persistence — simulate the full UI flow of cancel + reopen chat.
Verifies that [Request interrupted by user] survives across chat close/reopen.
"""
import sys, os, tempfile, json, time
_buddy_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _buddy_root)
os.chdir(_buddy_root)
if sys.platform == 'win32':
    sys.stdout.reconfigure(errors='replace')

from pathlib import Path

# Patch to temp dir
import config
TEMP_DIR = tempfile.mkdtemp(prefix='buddy_cancel_')
config.DATA_DIR = Path(TEMP_DIR)
config.CONVERSATIONS_DIR = Path(TEMP_DIR) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
config.INPUT_HISTORY_FILE = Path(TEMP_DIR) / "input_history.json"

from core.providers.base import BaseProvider, ToolCall, ToolDef, AbortSignal
from core.engine import LLMEngine
from core.conversation import ConversationManager

passed = 0
failed = 0

def check(name, condition, detail=''):
    global passed, failed
    if condition:
        passed += 1
        print(f'  PASS: {name}')
    else:
        failed += 1
        print(f'  FAIL: {name} -- {detail}')


class SlowMockProvider(BaseProvider):
    """Mock provider that simulates a slow streaming response."""

    def __init__(self):
        self.chunks = []  # list of strings to yield as chunks

    def call_sync(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        # Simulate slow sync call that checks abort
        for i in range(10):
            if abort_signal and abort_signal.aborted:
                raise InterruptedError("Aborted")
            time.sleep(0.05)
        return (
            {"role": "assistant", "content": "full response"},
            [],
            "full response",
        )

    def call_stream(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        from core.providers.base import StreamChunk
        for chunk_text in self.chunks:
            if abort_signal and abort_signal.aborted:
                raise InterruptedError("Aborted during stream")
            yield StreamChunk(type="text_delta", text=chunk_text)
            time.sleep(0.05)
        yield StreamChunk(type="done")
        full = "".join(self.chunks)
        return ({"role": "assistant", "content": full}, [], full)

    @property
    def supports_streaming(self):
        return True

    def format_tools(self, tools):
        return []

    def format_tool_results(self, tool_calls, results):
        return {"role": "user", "content": []}


def run_tests():
    global passed, failed

    # ================================================================
    # Test 1: Normal flow — send message, get response, save, reload
    # ================================================================
    print("=== Test 1: Normal flow (baseline) ===")
    engine = LLMEngine()
    provider = SlowMockProvider()
    provider.chunks = ["Hello ", "world!"]
    engine.set_provider(provider, "mock")
    engine._streaming_enabled = True

    # Simulate: user sends message, engine runs to completion
    engine._is_running = True
    engine._abort_signal.reset()
    engine._conversation.add_user_message("Hi there")
    engine._tool_loop()
    engine._is_running = False

    check("normal: 3 messages (user + assistant + none extra)",
          len(engine.conversation.messages) >= 2,
          f"got {len(engine.conversation.messages)}")

    engine.save_conversation()

    # Simulate reopen: new ConversationManager loads from disk
    conv2 = ConversationManager()
    loaded = conv2.load_last()
    check("normal: load_last succeeds", loaded)
    check("normal: messages preserved",
          conv2.message_count >= 2,
          f"got {conv2.message_count}")

    last_msg = conv2.messages[-1]
    check("normal: last message is assistant",
          last_msg.get("role") == "assistant",
          f"got role={last_msg.get('role')}")

    # ================================================================
    # Test 2: Cancel during streaming — engine path
    # ================================================================
    print("\n=== Test 2: Cancel during streaming (engine._persist_abort) ===")
    engine2 = LLMEngine()
    provider2 = SlowMockProvider()
    # Make it slow enough that we can abort mid-stream
    provider2.chunks = [f"chunk{i} " for i in range(20)]
    engine2.set_provider(provider2, "mock")
    engine2._streaming_enabled = True

    # Simulate send
    engine2._conversation.add_user_message("Tell me a long story")
    engine2._is_running = True
    engine2._abort_signal.reset()

    # Run in thread, abort after a short delay
    import threading
    def run_and_abort():
        time.sleep(0.2)  # let a few chunks through
        engine2.abort()

    abort_thread = threading.Thread(target=run_and_abort)
    abort_thread.start()

    try:
        engine2._tool_loop()
    except Exception:
        pass

    # _run_loop would call _persist_abort on abort, simulate that
    if engine2._abort_signal.aborted:
        engine2._persist_abort()

    abort_thread.join()
    engine2._is_running = False

    # Check conversation has the interrupt marker
    msgs = engine2.conversation.messages
    check("cancel: has messages", len(msgs) >= 2, f"got {len(msgs)}")

    last = msgs[-1]
    check("cancel: last message is interrupt marker",
          last.get("content") == "[Request interrupted by user]",
          f"got content='{last.get('content', '')[:50]}'")
    check("cancel: interrupt marker is user role (CC-aligned)",
          last.get("role") == "user",
          f"got role='{last.get('role')}'")

    # Check it was saved to disk
    session_file = config.CONVERSATIONS_DIR / f"{engine2.conversation._conversation_id}.json"
    check("cancel: session file exists", session_file.exists())

    # ================================================================
    # Test 3: Reopen after cancel — the KEY test
    # ================================================================
    print("\n=== Test 3: Reopen after cancel (load from disk) ===")

    # Simulate closing chat and reopening: create fresh ConversationManager
    conv3 = ConversationManager()
    loaded3 = conv3.load_last()
    check("reopen: load_last succeeds", loaded3)
    check("reopen: has messages", conv3.message_count >= 2,
          f"got {conv3.message_count}")

    # Find the interrupt marker
    has_interrupt = False
    interrupt_role = None
    for m in conv3.messages:
        if m.get("content") == "[Request interrupted by user]":
            has_interrupt = True
            interrupt_role = m.get("role")
    check("reopen: interrupt marker found in loaded messages", has_interrupt)
    check("reopen: interrupt marker is user role (CC-aligned)",
          interrupt_role == "user",
          f"got role='{interrupt_role}'")

    # Simulate what load_history would show in the chat UI
    print("\n  [Simulating chat UI load_history:]")
    for m in conv3.messages:
        role = m.get("role", "?")
        content = str(m.get("content", ""))[:60]
        side = ">>>" if role == "user" else "<<<"
        print(f"    {side} [{role}] {content}")

    # ================================================================
    # Test 4: Multiple cancel cycles don't corrupt conversation
    # ================================================================
    print("\n=== Test 4: Multiple cancel cycles ===")
    engine4 = LLMEngine()
    provider4 = SlowMockProvider()
    provider4.chunks = [f"c{i} " for i in range(20)]
    engine4.set_provider(provider4, "mock")
    engine4._streaming_enabled = True

    for cycle in range(3):
        engine4._conversation.add_user_message(f"Question {cycle+1}")
        engine4._abort_signal.reset()
        engine4._is_running = True

        # Abort quickly
        def quick_abort():
            time.sleep(0.1)
            engine4.abort()
        t = threading.Thread(target=quick_abort)
        t.start()
        try:
            engine4._tool_loop()
        except Exception:
            pass
        if engine4._abort_signal.aborted:
            engine4._persist_abort()
        t.join()
        engine4._is_running = False

    msgs4 = engine4.conversation.messages
    interrupt_count = sum(1 for m in msgs4 if m.get("content") == "[Request interrupted by user]")
    check(f"multi-cancel: 3 interrupt markers (got {interrupt_count})",
          interrupt_count == 3)

    # Reload from disk
    conv4 = ConversationManager()
    conv4.load_last()
    interrupt_count_disk = sum(1 for m in conv4.messages if m.get("content") == "[Request interrupted by user]")
    check(f"multi-cancel: all 3 markers persisted to disk (got {interrupt_count_disk})",
          interrupt_count_disk == 3)

    # ================================================================
    # Test 5: Simulate full app flow: send → cancel → close chat → reopen
    # ================================================================
    print("\n=== Test 5: Full app flow (send → cancel → close → reopen) ===")
    engine5 = LLMEngine()
    provider5 = SlowMockProvider()
    provider5.chunks = [f"word{i} " for i in range(30)]
    engine5.set_provider(provider5, "mock")
    engine5._streaming_enabled = True

    # Step 1: User sends message
    print("  [User sends: 'What is AI?']")
    engine5._conversation.add_user_message("What is AI?")
    engine5._is_running = True
    engine5._abort_signal.reset()

    # Step 2: Abort after brief streaming
    collected_errors = []
    engine5.error.connect(lambda e: collected_errors.append(e))

    def delayed_abort5():
        time.sleep(0.15)
        engine5.abort()
    t5 = threading.Thread(target=delayed_abort5)
    t5.start()

    # Step 3: Run the engine (simulates _run_loop)
    try:
        engine5._tool_loop()
    except Exception as e:
        if engine5._abort_signal.aborted:
            engine5._persist_abort()
            collected_errors.append("Operation cancelled.")
    t5.join()
    engine5._is_running = False

    # Verify engine memory has the marker
    mem_msgs = engine5.conversation.messages
    mem_interrupt = [m for m in mem_msgs if m.get("content") == "[Request interrupted by user]"]
    check("app-flow: interrupt in engine memory", len(mem_interrupt) == 1,
          f"found {len(mem_interrupt)}")

    # Step 4: Simulate closing the chat dialog (just hide, not destroy)
    print("  [User closes chat dialog]")

    # Step 5: Simulate reopening — this is what _open_chat does
    print("  [User reopens chat dialog]")
    # _open_chat calls: load_history(self.engine.conversation.messages)
    reopen_msgs = engine5.conversation.messages
    rendered = []
    for msg in reopen_msgs:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            text = content.strip()
            if not text.startswith("[Tool Result"):
                rendered.append((role, text[:60]))

    print("  [Chat UI would render:]")
    for role, text in rendered:
        side = ">>>" if role == "user" else "<<<"
        print(f"    {side} [{role}] {text}")

    has_interrupt_in_ui = any(text == "[Request interrupted by user]" and role == "user"
                              for role, text in rendered)
    check("app-flow: interrupt marker rendered in UI", has_interrupt_in_ui)

    # Step 6: Also verify disk persistence
    conv5 = ConversationManager()
    loaded5 = conv5.load_last()
    disk_interrupt = [m for m in conv5.messages if m.get("content") == "[Request interrupted by user]"]
    check("app-flow: interrupt persisted to disk", len(disk_interrupt) == 1,
          f"found {len(disk_interrupt)} on disk")

    return passed, failed


if __name__ == '__main__':
    import shutil
    try:
        p, f = run_tests()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f'\n=== TOTAL: {p} passed, {f} failed ===')
    sys.exit(1 if f > 0 else 0)
