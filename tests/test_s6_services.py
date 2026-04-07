"""
Suite 6 — Service Modules
Tests: Bridge Protocol, Bridge Auth, Team Memory, Analytics, Plugins, Memory
~18 tests covering all service layers.
"""
import sys, os, io, json, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.helpers import run, summary, reset, temp_data_dir
from unittest.mock import patch, MagicMock
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# Bridge Protocol (3 tests)
# ═══════════════════════════════════════════════════════════════════

def test_rpc_request_serialization():
    """RPCRequest serialization and round-trip parsing."""
    from core.bridge.protocol import RPCRequest
    req = RPCRequest(method="echo", params={"msg": "hello"}, id=42)
    raw = req.to_json()
    data = json.loads(raw)
    assert data["jsonrpc"] == "2.0", f"Missing jsonrpc field: {data}"
    assert data["method"] == "echo", f"Wrong method: {data['method']}"
    assert data["params"]["msg"] == "hello", "Params not preserved"
    assert data["id"] == 42, f"ID not preserved: {data.get('id')}"
    # Notification (no id) should omit id key
    notif = RPCRequest(method="ping", params={})
    notif_data = json.loads(notif.to_json())
    assert "id" not in notif_data, f"Notification should not have id: {notif_data}"

def test_rpc_router_dispatch():
    """RPCRouter: register handler and dispatch call."""
    from core.bridge.protocol import RPCRouter
    router = RPCRouter()
    router.register("add", lambda params: params["a"] + params["b"])
    req_json = json.dumps({"jsonrpc": "2.0", "method": "add", "params": {"a": 3, "b": 7}, "id": 1})
    resp_raw = router.handle(req_json)
    assert resp_raw is not None, "Expected response for request with id"
    resp = json.loads(resp_raw)
    assert resp["result"] == 10, f"Expected 10, got {resp.get('result')}"
    assert resp["id"] == 1, f"Response id mismatch: {resp.get('id')}"
    assert "error" not in resp, f"Unexpected error: {resp.get('error')}"

def test_rpc_router_method_not_found():
    """RPCRouter: method not found returns standard error."""
    from core.bridge.protocol import RPCRouter, ERR_METHOD_NOT_FOUND
    router = RPCRouter()
    req_json = json.dumps({"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": 99})
    resp_raw = router.handle(req_json)
    resp = json.loads(resp_raw)
    assert resp["error"] is not None, "Expected error for unknown method"
    assert resp["error"]["code"] == -32601, f"Wrong error code: {resp['error']['code']}"
    assert resp["id"] == 99, f"Response id mismatch"

# ═══════════════════════════════════════════════════════════════════
# Bridge Auth (2 tests)
# ═══════════════════════════════════════════════════════════════════

def test_bridge_auth_generate_validate():
    """BridgeAuth: generate_token then validate_token round-trip."""
    from core.bridge.auth import BridgeAuth
    auth = BridgeAuth(secret="test-secret-key-1234", token_ttl=3600)
    token = auth.generate_token(device_id="my-laptop")
    assert isinstance(token, str) and "." in token, f"Token format invalid: {token}"
    payload = auth.validate_token(token)
    assert payload is not None, "Valid token rejected"
    assert payload["device"] == "my-laptop", f"Device mismatch: {payload.get('device')}"
    assert "exp" in payload and "iat" in payload, "Missing timing fields"

def test_bridge_auth_invalid_token():
    """BridgeAuth: tampered or garbage tokens are rejected."""
    from core.bridge.auth import BridgeAuth
    auth = BridgeAuth(secret="secret-abc")
    token = auth.generate_token(device_id="dev1")
    # Tamper with signature
    parts = token.split(".")
    tampered = parts[0] + ".aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    result = auth.validate_token(tampered)
    assert result is None, f"Tampered token should be rejected, got: {result}"
    # Completely garbage
    assert auth.validate_token("garbage.token.xyz") is None, "Garbage token accepted"
    assert auth.validate_token("") is None, "Empty token accepted"

# ═══════════════════════════════════════════════════════════════════
# Team Memory (4 tests)
# ═══════════════════════════════════════════════════════════════════

def test_team_memory_basic_crud():
    """TeamMemoryStore: set, get, has, delete operations."""
    with temp_data_dir():
        from core.services.team_memory import TeamMemoryStore
        store = TeamMemoryStore(persist_dir=Path(tempfile.mkdtemp()))
        store.set("lang", "Python")
        assert store.has("lang"), "has() should return True"
        assert store.get("lang") == "Python", f"get() returned: {store.get('lang')}"
        assert store.get("missing") is None, "get() for missing key should return None"
        deleted = store.delete("lang")
        assert deleted is True, "delete() should return True for existing key"
        assert not store.has("lang"), "has() should return False after delete"
        assert store.delete("missing") is False, "delete() for missing key should return False"

def test_team_memory_scope_filtering():
    """TeamMemoryStore: scope filtering — session/project/global."""
    with temp_data_dir():
        from core.services.team_memory import TeamMemoryStore
        store = TeamMemoryStore(persist_dir=Path(tempfile.mkdtemp()))
        store.set("s1", "session-val", scope="session", team="alpha")
        store.set("p1", "project-val", scope="project")
        store.set("g1", "global-val", scope="global")
        store.set("s2", "session-other", scope="session", team="beta")
        entries = store.all_entries()
        assert len(entries) == 4, f"Expected 4 entries, got {len(entries)}"
        # Team filtering
        alpha_entries = store.get_team_entries("alpha")
        alpha_keys = {e.key for e in alpha_entries}
        assert "s1" in alpha_keys, "alpha team should include s1"
        assert "p1" in alpha_keys, "alpha team should include teamless p1"
        # s2 belongs to beta so should NOT appear in alpha (unless no team restriction)
        # get_team_entries includes entries with no team OR matching team
        beta_entries = store.get_team_entries("beta")
        beta_keys = {e.key for e in beta_entries}
        assert "s2" in beta_keys, "beta team should include s2"

def test_team_memory_context_for_agent():
    """TeamMemoryStore: get_context_for_agent builds context string."""
    with temp_data_dir():
        from core.services.team_memory import TeamMemoryStore
        store = TeamMemoryStore(persist_dir=Path(tempfile.mkdtemp()))
        store.set("stack", "React + TS", scope="project")
        store.set("api_url", "https://api.test.com", scope="global", agent_id="agent_2")
        store.set("temp", "session-only", scope="session", team="research")
        ctx = store.get_context_for_agent(agent_id="agent_3", team="research")
        assert "## Shared Team Memory" in ctx, f"Missing header in context: {ctx[:100]}"
        assert "stack" in ctx, "Project-scoped entry missing from context"
        assert "api_url" in ctx, "Global-scoped entry missing from context"
        assert "(from agent_2)" in ctx, "Agent attribution missing"
        # Empty store should return empty string
        empty_store = TeamMemoryStore(persist_dir=Path(tempfile.mkdtemp()))
        assert empty_store.get_context_for_agent() == "", "Empty store context should be ''"

def test_team_memory_persistence():
    """TeamMemoryStore: save and load to/from temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persist_path = Path(tmpdir)
        # Save
        with temp_data_dir():
            from core.services.team_memory import TeamMemoryStore
            store1 = TeamMemoryStore(persist_dir=persist_path)
            store1.set("key1", "value1", scope="project")
            store1.set("key2", "value2", scope="global", agent_id="sub1")
            store1.save("test_save")
            saved_file = persist_path / "test_save.json"
            assert saved_file.exists(), "Save file not created"
        # Load into fresh store
        with temp_data_dir():
            from core.services.team_memory import TeamMemoryStore
            store2 = TeamMemoryStore(persist_dir=persist_path)
            loaded = store2.load("test_save")
            assert loaded is True, "load() should return True"
            assert store2.get("key1") == "value1", f"key1 not restored: {store2.get('key1')}"
            assert store2.get("key2") == "value2", f"key2 not restored: {store2.get('key2')}"

# ═══════════════════════════════════════════════════════════════════
# Analytics (3 tests)
# ═══════════════════════════════════════════════════════════════════

def test_feature_flags_defaults():
    """FeatureFlags: defaults are loaded when no config file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_config = Path(tmpdir) / "features.json"
        # Don't create the file — should use defaults
        with temp_data_dir():
            from core.services.analytics import FeatureFlags, _DEFAULT_FLAGS
            ff = FeatureFlags(config_path=fake_config)
            assert ff.is_enabled("streaming_enabled") is True, "streaming_enabled default should be True"
            assert ff.is_enabled("bridge_enabled") is False, "bridge_enabled default should be False"
            assert ff.get_int("max_tool_rounds") == 30, f"max_tool_rounds default: {ff.get_int('max_tool_rounds')}"
            assert ff.get("prompt_version") == "v4", f"prompt_version: {ff.get('prompt_version')}"
            # Check all defaults present
            for key in _DEFAULT_FLAGS:
                assert ff.get(key) is not None, f"Default flag '{key}' missing"

def test_feature_flags_set_get():
    """FeatureFlags: set and get custom values, persisted to file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "features.json"
        with temp_data_dir():
            from core.services.analytics import FeatureFlags
            ff = FeatureFlags(config_path=config_path)
            ff.set("bridge_enabled", True)
            ff.set("custom_flag", "hello")
            assert ff.is_enabled("bridge_enabled") is True, "Set flag not reflected"
            assert ff.get("custom_flag") == "hello", "Custom flag not stored"
            # Verify persisted to disk
            assert config_path.exists(), "Config file not written"
            with open(config_path, "r") as f:
                saved = json.load(f)
            assert saved.get("bridge_enabled") is True, "bridge_enabled not persisted"
            assert saved.get("custom_flag") == "hello", "custom_flag not persisted"

def test_analytics_tracker_recording():
    """Analytics: record_api_call and record_tool_call counters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with temp_data_dir():
            from core.services.analytics import Analytics
            tracker = Analytics(analytics_dir=Path(tmpdir))
            assert tracker.total_api_calls == 0, "Should start at 0"
            tracker.record_api_call(model="claude-3", input_tokens=100, output_tokens=50)
            tracker.record_api_call(model="claude-3", input_tokens=200, output_tokens=100)
            assert tracker.total_api_calls == 2, f"API calls: {tracker.total_api_calls}"
            tracker.record_tool_call("FileRead")
            tracker.record_tool_call("Bash")
            tracker.record_tool_call("FileRead")
            assert tracker.total_tool_calls == 3, f"Tool calls: {tracker.total_tool_calls}"
            top = tracker.top_tools(2)
            assert top[0][0] == "FileRead" and top[0][1] == 2, f"Top tool: {top}"
            # Error rate
            tracker.record_error("timeout")
            assert tracker.total_errors == 1, f"Errors: {tracker.total_errors}"
            assert tracker.error_rate > 0, "Error rate should be > 0"
            # Report format
            report = tracker.format_report()
            assert "API calls:" in report, f"Report missing API calls section"

# ═══════════════════════════════════════════════════════════════════
# Plugin Manager (3 tests)
# ═══════════════════════════════════════════════════════════════════

def test_plugin_discover():
    """PluginManager: discover plugins in temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugins_dir = Path(tmpdir)
        # Create a directory plugin
        (plugins_dir / "my_plugin").mkdir()
        (plugins_dir / "my_plugin" / "__init__.py").write_text(
            'PLUGIN_NAME = "my_plugin"\nPLUGIN_DESCRIPTION = "Test"\n'
            'PLUGIN_TOOLS = []\nPLUGIN_COMMANDS = []\n',
            encoding="utf-8"
        )
        # Create a single-file plugin
        (plugins_dir / "simple.py").write_text(
            'PLUGIN_NAME = "simple"\nPLUGIN_DESCRIPTION = "Simple"\n'
            'PLUGIN_TOOLS = []\nPLUGIN_COMMANDS = []\n',
            encoding="utf-8"
        )
        # Create a non-plugin file (should be ignored)
        (plugins_dir / "readme.txt").write_text("not a plugin", encoding="utf-8")

        with temp_data_dir():
            from core.services.plugins import PluginManager
            pm = PluginManager(plugins_dir=plugins_dir)
            discovered = pm.discover()
            names = {p.name for p in discovered}
            assert "my_plugin" in names, f"Directory plugin not found. Got: {names}"
            assert "simple" in names, f"Single-file plugin not found. Got: {names}"
            assert len(discovered) == 2, f"Expected 2 plugins, got {len(discovered)}"

def test_plugin_load_single_file():
    """PluginManager: load a single-file plugin and read its metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugins_dir = Path(tmpdir)
        (plugins_dir / "greeter.py").write_text(
            'PLUGIN_NAME = "greeter"\n'
            'PLUGIN_DESCRIPTION = "A greeting plugin"\n'
            'PLUGIN_VERSION = "1.2.3"\n'
            'PLUGIN_TOOLS = []\n'
            'PLUGIN_COMMANDS = []\n'
            'def on_load(config): pass\n',
            encoding="utf-8"
        )
        with temp_data_dir():
            from core.services.plugins import PluginManager
            pm = PluginManager(plugins_dir=plugins_dir)
            results = pm.load_all()
            assert len(results) == 1, f"Expected 1 plugin, got {len(results)}"
            info = results[0]
            assert info.name == "greeter", f"Name: {info.name}"
            assert info.status == "loaded", f"Status: {info.status}"
            assert info.version == "1.2.3", f"Version: {info.version}"
            assert info.description == "A greeting plugin", f"Desc: {info.description}"

def test_plugin_broken_isolation():
    """PluginManager: broken plugin doesn't crash manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugins_dir = Path(tmpdir)
        # Good plugin
        (plugins_dir / "good.py").write_text(
            'PLUGIN_NAME = "good"\nPLUGIN_DESCRIPTION = "Works"\n'
            'PLUGIN_TOOLS = []\nPLUGIN_COMMANDS = []\n',
            encoding="utf-8"
        )
        # Broken plugin (syntax error)
        (plugins_dir / "broken.py").write_text(
            'PLUGIN_NAME = "broken"\n'
            'this is not valid python!!!!\n',
            encoding="utf-8"
        )
        with temp_data_dir():
            from core.services.plugins import PluginManager
            pm = PluginManager(plugins_dir=plugins_dir)
            results = pm.load_all()
            assert len(results) == 2, f"Expected 2 entries, got {len(results)}"
            statuses = {r.name: r.status for r in results}
            assert statuses.get("good") == "loaded", f"Good plugin status: {statuses.get('good')}"
            assert statuses.get("broken") == "error", f"Broken plugin status: {statuses.get('broken')}"
            # Manager still works
            assert pm.loaded_count == 1, f"Loaded count: {pm.loaded_count}"
            assert pm.total_count == 2, f"Total count: {pm.total_count}"

# ═══════════════════════════════════════════════════════════════════
# Memory Manager (3 tests)
# ═══════════════════════════════════════════════════════════════════

def test_memory_save_load():
    """MemoryManager: save_memory and load_memory round-trip with temp dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with temp_data_dir():
            from core.memory import MemoryManager
            mm = MemoryManager(memory_dir=Path(tmpdir))
            # Save general memory
            mm.save_memory("- User prefers tabs over spaces")
            mm.save_memory("- Project uses PostgreSQL")
            loaded = mm.load_memory()
            assert loaded is not None, "load_memory returned None"
            assert "tabs over spaces" in loaded, f"Memory content missing: {loaded[:200]}"
            assert "PostgreSQL" in loaded, f"PostgreSQL missing: {loaded[:200]}"
            # Save project-specific memory
            mm.save_memory("- Uses React 18", project_path="/home/user/myproject")
            proj_loaded = mm.load_memory(project_path="/home/user/myproject")
            assert proj_loaded is not None, "Project memory is None"
            assert "React 18" in proj_loaded, f"Project memory missing: {proj_loaded[:200]}"
            # Deduplication: saving same content again should not duplicate
            mm.save_memory("- User prefers tabs over spaces")
            loaded2 = mm.load_memory()
            count = loaded2.count("tabs over spaces")
            assert count == 1, f"Duplicate not prevented, found {count} occurrences"

def test_memory_extraction_prompt_format():
    """MemoryManager: extraction prompt contains required directives."""
    from core.memory import EXTRACT_SYSTEM_PROMPT, EXTRACT_USER_TEMPLATE
    assert "Do NOT call any tools" in EXTRACT_SYSTEM_PROMPT, \
        "System prompt missing no-tools directive"
    assert "[user]" in EXTRACT_SYSTEM_PROMPT, "Missing [user] prefix instruction"
    assert "[self]" in EXTRACT_SYSTEM_PROMPT, "Missing [self] prefix instruction"
    assert "{messages_text}" in EXTRACT_USER_TEMPLATE, "Template missing messages_text placeholder"

def test_memory_should_extract_timing():
    """MemoryManager: should_extract respects cooldown and turn interval."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with temp_data_dir():
            from core.memory import MemoryManager
            mm = MemoryManager(memory_dir=Path(tmpdir))
            mm._extract_cooldown = 0.01  # very short for testing
            mm._extract_interval = 2     # extract every 2 turns
            # Turn 1: not yet (interval=2)
            result1 = mm.should_extract()
            assert result1 is False, "Should not extract on first turn"
            # Turn 2: should trigger (2 turns elapsed, cooldown passed)
            time.sleep(0.02)
            result2 = mm.should_extract()
            assert result2 is True, "Should extract after interval turns + cooldown"
            # Immediately after extraction: turn count reset, should not trigger
            result3 = mm.should_extract()
            assert result3 is False, "Should not extract immediately after extraction"


# ═══════════════════════════════════════════════════════════════════
# Run all tests
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    reset()
    print("Suite 6 - Service Modules")
    print("=" * 60)

    print("\n-- Bridge Protocol --")
    run("rpc_request_serialization", test_rpc_request_serialization)
    run("rpc_router_dispatch", test_rpc_router_dispatch)
    run("rpc_router_method_not_found", test_rpc_router_method_not_found)

    print("\n-- Bridge Auth --")
    run("bridge_auth_generate_validate", test_bridge_auth_generate_validate)
    run("bridge_auth_invalid_token", test_bridge_auth_invalid_token)

    print("\n-- Team Memory --")
    run("team_memory_basic_crud", test_team_memory_basic_crud)
    run("team_memory_scope_filtering", test_team_memory_scope_filtering)
    run("team_memory_context_for_agent", test_team_memory_context_for_agent)
    run("team_memory_persistence", test_team_memory_persistence)

    print("\n-- Analytics --")
    run("feature_flags_defaults", test_feature_flags_defaults)
    run("feature_flags_set_get", test_feature_flags_set_get)
    run("analytics_tracker_recording", test_analytics_tracker_recording)

    print("\n-- Plugins --")
    run("plugin_discover", test_plugin_discover)
    run("plugin_load_single_file", test_plugin_load_single_file)
    run("plugin_broken_isolation", test_plugin_broken_isolation)

    print("\n-- Memory --")
    run("memory_save_load", test_memory_save_load)
    run("memory_extraction_prompt_format", test_memory_extraction_prompt_format)
    run("memory_should_extract_timing", test_memory_should_extract_timing)

    ok = summary("Suite 6: Services")
    sys.exit(0 if ok else 1)
