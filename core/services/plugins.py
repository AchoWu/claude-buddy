"""
Plugin System — load user plugins from ~/.claude-buddy/plugins/.
Aligned with Claude Code's services/plugins/ patterns.

Plugin structure:
  ~/.claude-buddy/plugins/
    my_plugin/
      __init__.py       # MUST define PLUGIN_NAME, PLUGIN_TOOLS, PLUGIN_COMMANDS
      config.json       # optional per-plugin configuration

Required exports in __init__.py:
  PLUGIN_NAME: str                          # unique identifier
  PLUGIN_DESCRIPTION: str                   # one-line description
  PLUGIN_TOOLS: list[type[BaseTool]]        # tool classes to register
  PLUGIN_COMMANDS: list[tuple[str,str,Callable]]  # (name, desc, handler)

Optional exports:
  PLUGIN_VERSION: str
  on_load(config: dict) -> None             # called after loading
  on_unload() -> None                       # called before unloading

Lifecycle:
  1. discover() — scan plugins dir, return list of PluginInfo
  2. load_all() — import each plugin, register tools+commands
  3. reload(name) — hot-reload a single plugin (for development)
  4. unload(name) — unregister plugin tools+commands
"""

import importlib
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable

from config import DATA_DIR


PLUGINS_DIR = DATA_DIR / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class PluginInfo:
    """Metadata for a loaded plugin."""
    name: str
    description: str = ""
    version: str = "0.0.0"
    path: Path = field(default_factory=Path)
    status: str = "discovered"  # discovered, loaded, error, unloaded
    error: str = ""
    tool_names: list[str] = field(default_factory=list)
    command_names: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    module: Any = None  # the imported module


class PluginManager:
    """
    Discovers, loads, and manages user plugins.

    Usage:
        pm = PluginManager()
        pm.load_all(tool_registry, command_registry)
        print(pm.list_plugins())
    """

    def __init__(self, plugins_dir: Path | None = None):
        self._dir = plugins_dir or PLUGINS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, PluginInfo] = {}

    # ── Discovery ─────────────────────────────────────────────────

    def discover(self) -> list[PluginInfo]:
        """Scan plugins directory and return list of discoverable plugins."""
        discovered = []

        if not self._dir.exists():
            return discovered

        for item in sorted(self._dir.iterdir()):
            # Directory plugin: my_plugin/__init__.py
            if item.is_dir() and (item / "__init__.py").exists():
                info = PluginInfo(
                    name=item.name,
                    path=item,
                    status="discovered",
                )
                discovered.append(info)

            # Single-file plugin: my_plugin.py
            elif item.is_file() and item.suffix == ".py" and item.name != "__init__.py":
                info = PluginInfo(
                    name=item.stem,
                    path=item,
                    status="discovered",
                )
                discovered.append(info)

        return discovered

    # ── Loading ───────────────────────────────────────────────────

    def load_all(self, tool_registry=None, command_registry=None) -> list[PluginInfo]:
        """
        Discover and load all plugins. Register their tools and commands.
        Returns list of all plugin infos (including failed ones).
        """
        discovered = self.discover()

        for info in discovered:
            self._load_one(info, tool_registry, command_registry)
            self._plugins[info.name] = info

        return list(self._plugins.values())

    def _load_one(self, info: PluginInfo, tool_registry=None, command_registry=None):
        """Load a single plugin. Catches all errors (never crashes BUDDY)."""
        try:
            # Load config.json if exists
            config_path = info.path / "config.json" if info.path.is_dir() else info.path.with_suffix(".json")
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        info.config = json.load(f)
                except Exception:
                    info.config = {}

            # Import the module
            module = self._import_plugin(info)
            if module is None:
                return

            info.module = module

            # Read required metadata
            plugin_name = getattr(module, "PLUGIN_NAME", info.name)
            info.name = plugin_name
            info.description = getattr(module, "PLUGIN_DESCRIPTION", "")
            info.version = getattr(module, "PLUGIN_VERSION", "0.0.0")

            # Call on_load hook
            on_load = getattr(module, "on_load", None)
            if callable(on_load):
                on_load(info.config)

            # Register tools
            plugin_tools = getattr(module, "PLUGIN_TOOLS", [])
            for tool_cls in plugin_tools:
                try:
                    tool_instance = tool_cls()
                    info.tool_names.append(tool_instance.name)
                    if tool_registry:
                        tool_registry._tools[tool_instance.name] = tool_instance
                except Exception as e:
                    info.error += f"Tool {tool_cls}: {e}\n"

            # Register commands
            plugin_commands = getattr(module, "PLUGIN_COMMANDS", [])
            for cmd_tuple in plugin_commands:
                try:
                    if len(cmd_tuple) >= 3:
                        cmd_name, cmd_desc, cmd_handler = cmd_tuple[0], cmd_tuple[1], cmd_tuple[2]
                        info.command_names.append(cmd_name)
                        if command_registry:
                            command_registry.register(cmd_name, cmd_desc, cmd_handler)
                except Exception as e:
                    info.error += f"Command: {e}\n"

            info.status = "loaded"

        except Exception as e:
            info.status = "error"
            info.error = f"{e}\n{traceback.format_exc()}"

    def _import_plugin(self, info: PluginInfo):
        """Import a plugin module using importlib. Returns module or None."""
        try:
            if info.path.is_dir():
                # Directory plugin
                init_file = info.path / "__init__.py"
                spec = importlib.util.spec_from_file_location(
                    f"buddy_plugin_{info.name}", str(init_file),
                    submodule_search_locations=[str(info.path)],
                )
            else:
                # Single-file plugin
                spec = importlib.util.spec_from_file_location(
                    f"buddy_plugin_{info.name}", str(info.path),
                )

            if spec is None or spec.loader is None:
                info.status = "error"
                info.error = "Could not create module spec"
                return None

            module = importlib.util.module_from_spec(spec)
            # Add BUDDY's tools.base to the plugin's import path
            # so plugins can `from tools.base import BaseTool`
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module

        except Exception as e:
            info.status = "error"
            info.error = f"Import failed: {e}"
            return None

    # ── Reload ────────────────────────────────────────────────────

    def reload(self, name: str, tool_registry=None, command_registry=None) -> str:
        """
        Hot-reload a single plugin. Unloads first, then re-imports.
        Returns status message.
        """
        # Unload first
        self.unload(name, tool_registry, command_registry)

        # Re-discover
        all_discovered = self.discover()
        target = None
        for info in all_discovered:
            if info.name == name:
                target = info
                break

        if not target:
            return f"Plugin '{name}' not found in {self._dir}"

        # Reload module cache
        module_name = f"buddy_plugin_{name}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Load
        self._load_one(target, tool_registry, command_registry)
        self._plugins[name] = target

        if target.status == "loaded":
            return f"Plugin '{name}' reloaded: {len(target.tool_names)} tools, {len(target.command_names)} commands"
        return f"Plugin '{name}' reload failed: {target.error}"

    # ── Unload ────────────────────────────────────────────────────

    def unload(self, name: str, tool_registry=None, command_registry=None) -> str:
        """Unload a plugin: call on_unload hook, unregister tools and commands."""
        info = self._plugins.get(name)
        if not info:
            return f"Plugin '{name}' not loaded."

        # Call on_unload hook
        if info.module:
            on_unload = getattr(info.module, "on_unload", None)
            if callable(on_unload):
                try:
                    on_unload()
                except Exception:
                    pass

        # Unregister tools
        if tool_registry:
            for tool_name in info.tool_names:
                tool_registry._tools.pop(tool_name, None)

        # Unregister commands
        if command_registry:
            for cmd_name in info.command_names:
                command_registry._commands.pop(cmd_name, None)

        # Clean up module
        module_name = f"buddy_plugin_{name}"
        sys.modules.pop(module_name, None)

        info.status = "unloaded"
        del self._plugins[name]

        return f"Plugin '{name}' unloaded."

    # ── Query ─────────────────────────────────────────────────────

    def list_plugins(self) -> list[dict]:
        """List all plugins with their status."""
        result = []
        for info in self._plugins.values():
            result.append({
                "name": info.name,
                "description": info.description,
                "version": info.version,
                "status": info.status,
                "tools": info.tool_names,
                "commands": info.command_names,
                "error": info.error[:200] if info.error else "",
            })
        return sorted(result, key=lambda x: x["name"])

    def get_plugin(self, name: str) -> PluginInfo | None:
        return self._plugins.get(name)

    @property
    def loaded_count(self) -> int:
        return sum(1 for p in self._plugins.values() if p.status == "loaded")

    @property
    def total_count(self) -> int:
        return len(self._plugins)

    def format_status(self) -> str:
        """Human-readable status string."""
        plugins = self.list_plugins()
        if not plugins:
            return f"No plugins found. Add plugins to {self._dir}/"

        lines = [f"Plugins ({len(plugins)}):"]
        for p in plugins:
            icon = {"loaded": "[OK]", "error": "[ERR]", "unloaded": "[OFF]"}.get(p["status"], "[?]")
            tools = f", {len(p['tools'])} tools" if p["tools"] else ""
            cmds = f", {len(p['commands'])} cmds" if p["commands"] else ""
            lines.append(f"  {icon} {p['name']} v{p['version']}{tools}{cmds}")
            if p["description"]:
                lines.append(f"      {p['description']}")
            if p["error"]:
                lines.append(f"      Error: {p['error'][:100]}")
        return "\n".join(lines)
