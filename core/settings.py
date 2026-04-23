"""
Settings — persistent configuration using QSettings.
"""

from PyQt6.QtCore import QSettings
from pathlib import Path

from config import APP_NAME, DEFAULT_PROVIDER, DEFAULT_MODEL, DEFAULT_CHARACTER


PROVIDER_PRESETS = {
    "taiji": {
        "label": "太极 Taiji (无需 function call)",
        "base_url": "http://api.taiji.woa.com/openapi",
        "default_model": "DeepSeek-V3_1-Online-32k",
        "needs_api_key": True,
        "needs_base_url": False,
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "base_url": "",
        "default_model": "claude-sonnet-4-20250514",
        "needs_api_key": True,
        "needs_base_url": False,
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "",
        "default_model": "gpt-4o",
        "needs_api_key": True,
        "needs_base_url": False,
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "needs_api_key": True,
        "needs_base_url": True,
    },
    "qwen": {
        "label": "通义千问 / Qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "needs_api_key": True,
        "needs_base_url": True,
    },
    "ollama": {
        "label": "Ollama (Local)",
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3",
        "needs_api_key": False,
        "needs_base_url": True,
    },
    "custom": {
        "label": "Custom OpenAI-Compatible",
        "base_url": "",
        "default_model": "",
        "needs_api_key": True,
        "needs_base_url": True,
    },
}

# Providers that use PromptToolProvider (no native function calling)
PROMPT_TOOL_PROVIDERS = {"taiji"}


class Settings:
    """Persistent settings wrapper around QSettings."""

    def __init__(self):
        self._qs = QSettings("ClaudeBuddy", APP_NAME)

    # ── Provider / Model ─────────────────────────────────────────────
    @property
    def provider(self) -> str:
        return self._qs.value("provider", DEFAULT_PROVIDER)

    @provider.setter
    def provider(self, v: str):
        self._qs.setValue("provider", v)

    @property
    def api_key(self) -> str:
        return self._qs.value("api_key", "")

    @api_key.setter
    def api_key(self, v: str):
        self._qs.setValue("api_key", v)

    @property
    def base_url(self) -> str:
        return self._qs.value("base_url", "")

    @base_url.setter
    def base_url(self, v: str):
        self._qs.setValue("base_url", v)

    @property
    def model(self) -> str:
        return self._qs.value("model", DEFAULT_MODEL)

    @model.setter
    def model(self, v: str):
        self._qs.setValue("model", v)

    # ── Behavior ─────────────────────────────────────────────────────
    @property
    def permission_mode(self) -> str:
        """default / auto / bypass"""
        return self._qs.value("permission_mode", "default")

    @permission_mode.setter
    def permission_mode(self, v: str):
        self._qs.setValue("permission_mode", v)

    @property
    def idle_timeout(self) -> int:
        return int(self._qs.value("idle_timeout", 300))

    @idle_timeout.setter
    def idle_timeout(self, v: int):
        self._qs.setValue("idle_timeout", v)

    @property
    def streaming_enabled(self) -> bool:
        return self._qs.value("streaming_enabled", "false") == "true"

    @streaming_enabled.setter
    def streaming_enabled(self, v: bool):
        self._qs.setValue("streaming_enabled", "true" if v else "false")

    # ── Character ────────────────────────────────────────────────────
    @property
    def character(self) -> str:
        return self._qs.value("character", DEFAULT_CHARACTER)

    @character.setter
    def character(self, v: str):
        self._qs.setValue("character", v)

    # ── Phase 9-11: CC-aligned extended settings ────────────────────
    @property
    def thinking_enabled(self) -> bool:
        """Extended thinking mode toggle."""
        return self._qs.value("thinking_enabled", "false") == "true"

    @thinking_enabled.setter
    def thinking_enabled(self, v: bool):
        self._qs.setValue("thinking_enabled", "true" if v else "false")

    @property
    def thinking_budget(self) -> int:
        """Thinking token budget (1024-32768)."""
        return int(self._qs.value("thinking_budget", 10000))

    @thinking_budget.setter
    def thinking_budget(self, v: int):
        self._qs.setValue("thinking_budget", max(1024, min(32768, v)))

    @property
    def effort_level(self) -> str:
        """Reasoning effort: low/medium/high or empty for default."""
        return self._qs.value("effort_level", "")

    @effort_level.setter
    def effort_level(self, v: str):
        self._qs.setValue("effort_level", v)

    @property
    def cache_control_enabled(self) -> bool:
        """Prompt caching (cache_control headers)."""
        return self._qs.value("cache_control_enabled", "false") == "true"

    @cache_control_enabled.setter
    def cache_control_enabled(self, v: bool):
        self._qs.setValue("cache_control_enabled", "true" if v else "false")

    @property
    def temperature(self) -> float | None:
        """Temperature (None = model default)."""
        val = self._qs.value("temperature", "")
        if val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @temperature.setter
    def temperature(self, v: float | None):
        self._qs.setValue("temperature", str(v) if v is not None else "")

    # ── Settings merge (CC-aligned: 5-level hierarchy) ──────────────
    def load_project_settings(self, project_dir: str | None = None):
        """
        CC-aligned: merge settings from multiple sources in priority order.
        Later sources OVERRIDE earlier ones (CC: lodash mergeWith):
          1. user (~/.claude-buddy/settings.json) — lowest
          2. project (.claude/config.json in project dir)
          3. local (settings.local.json in data dir)
          4. QSettings (runtime overrides) — highest (not touched here)
        """
        import json as _json
        from config import DATA_DIR

        # Level 1 (lowest): User settings
        user_path = DATA_DIR / "settings.json"
        if user_path.exists():
            try:
                data = _json.loads(user_path.read_text(encoding="utf-8"))
                self._apply_settings_dict(data)
            except Exception:
                pass

        # Level 2: Project settings (overrides user)
        if project_dir:
            for name in [".claude/settings.json", ".claude/config.json",
                         "claude.config.json", ".buddy/config.json"]:
                path = Path(project_dir) / name
                if path.exists():
                    try:
                        data = _json.loads(path.read_text(encoding="utf-8"))
                        self._apply_settings_dict(data, override=True)
                    except Exception:
                        pass
                    break

        # Level 3 (highest file-based): Local settings (overrides project)
        local_path = DATA_DIR / "settings.local.json"
        if local_path.exists():
            try:
                data = _json.loads(local_path.read_text(encoding="utf-8"))
                self._apply_settings_dict(data, override=True)
            except Exception:
                pass

    # ── #49 CC-aligned: MCP config hierarchy (.mcp.json traversal) ──
    def load_mcp_configs(self, start_dir: str | None = None) -> list[dict]:
        """
        CC-aligned: traverse from start_dir (or CWD) up to root,
        collecting .mcp.json files. Closer files take higher priority.
        Returns merged list of MCP server configs.
        """
        import json as _json
        import os

        if start_dir is None:
            start_dir = os.getcwd()

        configs = []
        current = Path(start_dir).resolve()
        visited = set()

        while True:
            if str(current) in visited:
                break
            visited.add(str(current))

            for name in [".mcp.json", ".claude/mcp.json"]:
                mcp_path = current / name
                if mcp_path.exists():
                    try:
                        data = _json.loads(mcp_path.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            servers = data.get("mcpServers", data.get("servers", []))
                            if isinstance(servers, dict):
                                # Convert dict format to list
                                for srv_name, srv_cfg in servers.items():
                                    if isinstance(srv_cfg, dict):
                                        srv_cfg["name"] = srv_name
                                        configs.append(srv_cfg)
                            elif isinstance(servers, list):
                                configs.extend(servers)
                    except Exception:
                        pass

            parent = current.parent
            if parent == current:
                break
            current = parent

        # Also check user-level MCP config
        from config import DATA_DIR
        user_mcp = DATA_DIR / "mcp.json"
        if user_mcp.exists():
            try:
                data = _json.loads(user_mcp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    servers = data.get("mcpServers", data.get("servers", []))
                    if isinstance(servers, dict):
                        for srv_name, srv_cfg in servers.items():
                            if isinstance(srv_cfg, dict):
                                srv_cfg["name"] = srv_name
                                configs.append(srv_cfg)
                    elif isinstance(servers, list):
                        configs.extend(servers)
            except Exception:
                pass

        return configs

    def _apply_settings_dict(self, data: dict, override: bool = False):
        """
        Apply a dict of settings.
        CC-aligned: later sources OVERRIDE earlier ones (not first-set-wins).
        When override=True, always set. When False, only set if key absent.
        """
        mapping = {
            "provider": "provider", "api_key": "api_key", "model": "model",
            "base_url": "base_url", "permission_mode": "permission_mode",
            "thinking_enabled": "thinking_enabled",
            "thinking_budget": "thinking_budget",
            "effort_level": "effort_level",
            "cache_control_enabled": "cache_control_enabled",
            "temperature": "temperature",
            "streaming_enabled": "streaming_enabled",
        }
        for json_key, settings_key in mapping.items():
            if json_key in data:
                if override or not self._qs.contains(settings_key):
                    self._qs.setValue(settings_key, str(data[json_key]))

    # ── Helper ───────────────────────────────────────────────────────
    def create_provider(self):
        """Create the appropriate provider based on current settings."""
        provider_name = self.provider
        api_key = self.api_key
        model = self.model
        base_url = self.base_url

        # Guard: if provider is unknown (e.g. deleted preset), reset to default
        if provider_name not in PROVIDER_PRESETS:
            provider_name = DEFAULT_PROVIDER
            self.provider = provider_name

        # Prompt-based provider (no native function calling)
        if provider_name in PROMPT_TOOL_PROVIDERS:
            preset = PROVIDER_PRESETS.get(provider_name, {})
            if preset.get("needs_api_key", True) and not api_key:
                return None
            effective_url = base_url or preset.get("base_url", "")
            effective_model = model or preset.get("default_model", "")
            from core.providers.prompt_tool_provider import PromptToolProvider
            return PromptToolProvider(
                api_key=api_key,
                model=effective_model,
                base_url=effective_url or None,
            )

        # API-based providers need a key (except Ollama)
        preset = PROVIDER_PRESETS.get(provider_name, {})
        if preset.get("needs_api_key", True) and not api_key:
            return None

        # Anthropic native
        if provider_name == "anthropic":
            from core.providers.anthropic_provider import AnthropicProvider
            return AnthropicProvider(api_key=api_key, model=model)

        # OpenAI-compatible (with native function calling)
        from core.providers.openai_provider import OpenAIProvider
        if not base_url and provider_name in PROVIDER_PRESETS:
            base_url = PROVIDER_PRESETS[provider_name]["base_url"]
        kwargs = {
            "api_key": api_key or "ollama",
            "model": model,
            "reasoning_enabled": self.thinking_enabled,
        }
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAIProvider(**kwargs)
