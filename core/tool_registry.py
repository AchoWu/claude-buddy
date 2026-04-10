"""
Tool Registry v5 — registers ALL tools.
Injects shared state: TaskManager, FileReadState, PlanModeState, Engine, MCP, LSP.
Aligned with Claude Code's tool registration patterns.

#33 CC-aligned: tools use defer_loading pattern — heavy tools are imported lazily
on first use rather than at import time, matching CC's lazy require() pattern.
"""

import platform

from core.providers.base import ToolDef
from tools.base import BaseTool

# ── Core tools (always loaded eagerly) ───────────────────────────
from tools.file_read_tool import FileReadTool
from tools.file_write_tool import FileWriteTool
from tools.file_edit_tool import FileEditTool
from tools.bash_tool import BashTool
from tools.glob_tool import GlobTool
from tools.grep_tool import GrepTool
from tools.ask_user_tool import AskUserQuestionTool

# ── #33 CC-aligned: Deferred tool loaders (lazy import on first use) ─
def _get_web_search_tool():
    from tools.web_search_tool import WebSearchTool
    return WebSearchTool

def _get_web_fetch_tool():
    from tools.web_fetch_tool import WebFetchTool
    return WebFetchTool

def _get_task_tools():
    from tools.task_tool import TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool
    return TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool

def _get_task_output_tools():
    from tools.task_output_tool import TaskOutputTool, TaskStopTool
    return TaskOutputTool, TaskStopTool

def _get_agent_tool():
    from tools.agent_tool import AgentTool
    return AgentTool

def _get_send_message_tools():
    from tools.send_message_tool import SendMessageTool, AgentRegistry
    return SendMessageTool, AgentRegistry

def _get_team_tools():
    from tools.team_tool import TeamCreateTool, TeamDeleteTool
    return TeamCreateTool, TeamDeleteTool

def _get_plan_mode_tools():
    from tools.plan_mode_tool import EnterPlanModeTool, ExitPlanModeTool, PlanModeState
    return EnterPlanModeTool, ExitPlanModeTool, PlanModeState

def _get_cron_tools():
    from tools.cron_tool import CronCreateTool, CronDeleteTool, CronListTool
    return CronCreateTool, CronDeleteTool, CronListTool

def _get_notebook_tool():
    from tools.notebook_edit_tool import NotebookEditTool
    return NotebookEditTool

def _get_protocol_tools():
    from tools.mcp_tool import MCPTool
    from tools.lsp_tool import LSPTool
    return MCPTool, LSPTool

def _get_worktree_tools():
    from tools.worktree_tool import EnterWorktreeTool, ExitWorktreeTool
    return EnterWorktreeTool, ExitWorktreeTool

def _get_skill_tool():
    from tools.skill_tool import SkillTool
    return SkillTool

def _get_config_tool():
    from tools.config_tool import ConfigTool
    return ConfigTool

def _get_soul_tools():
    from tools.soul_tools import SelfReflectTool, SelfModifyTool, DiaryWriteTool
    return SelfReflectTool, SelfModifyTool, DiaryWriteTool

def _get_utility_tools():
    from tools.utility_tools import SleepTool, REPLTool
    return SleepTool, REPLTool

def _get_extra_tools():
    from tools.extra_tools import BriefTool, PowerShellTool, TodoWriteTool, ToolSearchTool
    return BriefTool, PowerShellTool, TodoWriteTool, ToolSearchTool

# Eagerly import PlanModeState and AgentRegistry (needed at init time)
from tools.plan_mode_tool import PlanModeState
from tools.send_message_tool import AgentRegistry


class ToolRegistry:
    """Central registry for all available tools."""

    def __init__(self, task_manager=None, file_read_state=None, engine=None,
                 mcp_manager=None, lsp_manager=None, command_registry=None,
                 evolution_manager=None):
        self._tools: dict[str, BaseTool] = {}
        self._task_manager = task_manager
        self._file_read_state = file_read_state
        self._engine = engine
        self._mcp_manager = mcp_manager
        self._lsp_manager = lsp_manager
        self._command_registry = command_registry
        self._evolution_manager = evolution_manager
        self._plan_mode_state = PlanModeState()
        self._agent_registry = AgentRegistry()
        self._register_defaults()

    @property
    def plan_mode_state(self) -> PlanModeState:
        return self._plan_mode_state

    @property
    def agent_registry(self) -> AgentRegistry:
        return self._agent_registry

    def _register_defaults(self):
        """Register all built-in tools.
        NOTE: CC uses lazy require() getters that defer import until first tool use.
        BUDDY loads all tools at init time for simplicity. The _get_*_tool() functions
        split imports for readability but are called eagerly here.
        TODO: Implement true lazy loading via __getattr__ proxy on _tools dict."""

        # ── File tools: inject FileReadState (core, eagerly loaded) ──
        file_read = FileReadTool()
        file_write = FileWriteTool()
        file_edit = FileEditTool()
        if self._file_read_state:
            file_read._file_read_state = self._file_read_state
            file_write._file_read_state = self._file_read_state
            file_edit._file_read_state = self._file_read_state
        self._tools[file_read.name] = file_read
        self._tools[file_write.name] = file_write
        self._tools[file_edit.name] = file_edit

        # ── Search & Execution (core eagerly, web deferred) ──────────
        for cls in [BashTool, GlobTool, GrepTool]:
            t = cls()
            self._tools[t.name] = t
        # Deferred web tools
        WebSearchTool = _get_web_search_tool()
        WebFetchTool = _get_web_fetch_tool()
        for cls in [WebSearchTool, WebFetchTool]:
            t = cls()
            self._tools[t.name] = t

        # ── Task tools: inject TaskManager (deferred) ─────────────────
        TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool = _get_task_tools()
        for cls in [TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool]:
            t = cls()
            if self._task_manager is not None:
                t._task_manager = self._task_manager
            self._tools[t.name] = t

        # ── TaskOutput/TaskStop: inject engine + bash (deferred) ──────
        TaskOutputTool, TaskStopTool = _get_task_output_tools()
        task_out = TaskOutputTool()
        task_out._engine = self._engine
        task_out._bash_tool = self._tools.get("Bash")
        self._tools[task_out.name] = task_out

        task_stop = TaskStopTool()
        task_stop._engine = self._engine
        self._tools[task_stop.name] = task_stop

        # ── AskUser (core, eagerly loaded) ────────────────────────────
        self._tools[AskUserQuestionTool().name] = AskUserQuestionTool()

        # ── NotebookEdit (deferred) ───────────────────────────────────
        NotebookEditTool = _get_notebook_tool()
        self._tools[NotebookEditTool().name] = NotebookEditTool()

        # ── Agent: inject engine (deferred) ───────────────────────────
        AgentTool = _get_agent_tool()
        agent = AgentTool()
        agent._engine = self._engine
        self._tools[agent.name] = agent

        # ── SendMessage: inject engine + agent registry (deferred) ────
        SendMessageTool, _ = _get_send_message_tools()
        send_msg = SendMessageTool()
        send_msg._engine = self._engine
        send_msg._agent_registry = self._agent_registry
        self._tools[send_msg.name] = send_msg

        # ── Team tools: inject agent registry (deferred) ──────────────
        TeamCreateTool, TeamDeleteTool = _get_team_tools()
        team_create = TeamCreateTool()
        team_create._agent_registry = self._agent_registry
        self._tools[team_create.name] = team_create

        team_delete = TeamDeleteTool()
        team_delete._agent_registry = self._agent_registry
        self._tools[team_delete.name] = team_delete

        # ── Plan mode: share PlanModeState (deferred) ─────────────────
        EnterPlanModeTool, ExitPlanModeTool, _ = _get_plan_mode_tools()
        enter_plan = EnterPlanModeTool()
        exit_plan = ExitPlanModeTool()
        enter_plan._plan_mode_state = self._plan_mode_state
        exit_plan._plan_mode_state = self._plan_mode_state
        self._tools[enter_plan.name] = enter_plan
        self._tools[exit_plan.name] = exit_plan

        # ── Cron tools (deferred) ─────────────────────────────────────
        CronCreateTool, CronDeleteTool, CronListTool = _get_cron_tools()
        for cls in [CronCreateTool, CronDeleteTool, CronListTool]:
            self._tools[cls().name] = cls()

        # ── MCP tool: inject MCP manager (deferred) ───────────────────
        MCPTool, LSPTool = _get_protocol_tools()
        mcp = MCPTool()
        mcp._mcp_manager = self._mcp_manager
        self._tools[mcp.name] = mcp

        # ── LSP tool: inject LSP manager ──────────────────────────────
        lsp = LSPTool()
        lsp._lsp_manager = self._lsp_manager
        self._tools[lsp.name] = lsp

        # ── Worktree tools (deferred) ─────────────────────────────────
        EnterWorktreeTool, ExitWorktreeTool = _get_worktree_tools()
        self._tools[EnterWorktreeTool().name] = EnterWorktreeTool()
        self._tools[ExitWorktreeTool().name] = ExitWorktreeTool()

        # ── Skill tool: inject command registry + skill manager (deferred) ──
        SkillTool = _get_skill_tool()
        skill = SkillTool()
        skill._command_registry = self._command_registry
        if self._engine and hasattr(self._engine, '_skill_mgr'):
            skill._skill_mgr = self._engine._skill_mgr
        self._tools[skill.name] = skill

        # ── Config tool (deferred) ────────────────────────────────────
        ConfigTool = _get_config_tool()
        self._tools[ConfigTool().name] = ConfigTool()

        # ── Utility tools (deferred) ──────────────────────────────────
        SleepTool, REPLTool = _get_utility_tools()
        self._tools[SleepTool().name] = SleepTool()
        self._tools[REPLTool().name] = REPLTool()

        # ── Extra tools (deferred) ────────────────────────────────────
        BriefTool, PowerShellTool, TodoWriteTool, ToolSearchTool = _get_extra_tools()
        brief = BriefTool()
        brief._engine = self._engine
        self._tools[brief.name] = brief

        if platform.system() == "Windows":
            self._tools[PowerShellTool().name] = PowerShellTool()

        self._tools[TodoWriteTool().name] = TodoWriteTool()

        tool_search = ToolSearchTool()
        tool_search._tool_registry = self
        self._tools[tool_search.name] = tool_search

        # ── Soul tools: inject EvolutionManager (deferred) ────────────
        SelfReflectTool, SelfModifyTool, DiaryWriteTool = _get_soul_tools()
        self_reflect = SelfReflectTool()
        self_reflect._evolution_mgr = self._evolution_manager
        self._tools[self_reflect.name] = self_reflect

        self_modify = SelfModifyTool()
        self_modify._evolution_mgr = self._evolution_manager
        self._tools[self_modify.name] = self_modify

        diary_write = DiaryWriteTool()
        diary_write._evolution_mgr = self._evolution_manager
        self._tools[diary_write.name] = diary_write

        # ── Phase 4+5+6: New CC-aligned tools (deferred) ────────────
        try:
            from tools.monitor_tool import MonitorTool
            self._tools[MonitorTool().name] = MonitorTool()
        except ImportError:
            pass  # psutil not installed

        from tools.workflow_tool import WorkflowTool
        self._tools[WorkflowTool().name] = WorkflowTool()

        from tools.snip_tool import SnipTool
        self._tools[SnipTool().name] = SnipTool()

        from tools.ctx_inspect_tool import CtxInspectTool
        ctx_inspect = CtxInspectTool()
        ctx_inspect._engine = self._engine
        self._tools[ctx_inspect.name] = ctx_inspect

        from tools.push_notification_tool import PushNotificationTool
        self._tools[PushNotificationTool().name] = PushNotificationTool()

        from tools.terminal_capture_tool import TerminalCaptureTool
        self._tools[TerminalCaptureTool().name] = TerminalCaptureTool()

        from tools.send_user_file_tool import SendUserFileTool
        self._tools[SendUserFileTool().name] = SendUserFileTool()

        from tools.subscribe_pr_tool import SubscribePRTool
        self._tools[SubscribePRTool().name] = SubscribePRTool()

        # ── Round 2: MCP resource tools ──────────────────────────
        from tools.mcp_resource_tools import ListMcpResourcesTool, ReadMcpResourceTool
        list_mcp_res = ListMcpResourcesTool()
        list_mcp_res._mcp_manager = self._mcp_manager
        self._tools[list_mcp_res.name] = list_mcp_res

        read_mcp_res = ReadMcpResourceTool()
        read_mcp_res._mcp_manager = self._mcp_manager
        self._tools[read_mcp_res.name] = read_mcp_res

        # ── Round 2: WebBrowserTool (optional — playwright) ──────
        try:
            from tools.web_browser_tool import WebBrowserTool
            self._tools[WebBrowserTool().name] = WebBrowserTool()
        except Exception:
            pass  # playwright not installed

        # ── CC-aligned: mark concurrency-safe tools ──────────────
        # CC: isConcurrencySafe() — read-only tools with no side effects
        _CONCURRENT_SAFE = {
            "FileRead", "Glob", "Grep", "WebSearch", "WebFetch",
            "TaskList", "TaskGet", "CronList", "ToolSearch",
            "LSP", "CtxInspect",
        }
        for name, tool in self._tools.items():
            if name in _CONCURRENT_SAFE:
                tool.concurrency_safe = True

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def all_tool_defs(self) -> list[ToolDef]:
        return [t.to_tool_def() for t in self._tools.values()]

    def register_all_to_engine(self, engine):
        """Register all tools with the LLM engine."""
        for tool in self._tools.values():
            engine.register_tool(
                tool_def=tool.to_tool_def(),
                executor=tool.execute,
                is_read_only=tool.is_read_only,
                concurrency_safe=getattr(tool, 'concurrency_safe', False),
            )
