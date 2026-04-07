"""
Claude Code Buddy — Desktop Pixel Pet Assistant
Entry point: launch QApplication, create pet window, connect all components.
"""

import sys
import os
import random
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QTimer

from config import APP_NAME, GLOBAL_QSS, PET_SIZE
from ui.pet_window import PetWindow, PetState
from ui.context_menu import PetContextMenu
from ui.tray import SystemTray
from ui.speech_bubble import SpeechBubble
from ui.chat_dialog import ChatDialog
from ui.notification import NotificationQueue
from ui.task_panel import TaskPanel
from ui.settings_dialog import SettingsDialog
from ui.permission_dialog import PermissionManager
from core.engine import LLMEngine
from core.tool_registry import ToolRegistry
from core.task_manager import TaskManager
from core.commands import CommandRegistry
from core.settings import Settings, PROVIDER_PRESETS


class BuddyApp:
    """Central application controller — wires all components together."""

    def __init__(self, app: QApplication):
        self.app = app


        # ── Settings ─────────────────────────────────────────────────
        self.settings = Settings()

        # ── Pet window ───────────────────────────────────────────────
        self.pet = PetWindow(character=self.settings.character)
        self.pet.show()

        # ── Context menu ─────────────────────────────────────────────
        self.context_menu = PetContextMenu()
        self.pet.right_clicked.connect(self.context_menu.show_at)

        self.context_menu.chat_requested.connect(self._open_chat)
        self.context_menu.task_panel_requested.connect(self._open_tasks)
        self.context_menu.settings_requested.connect(self._open_settings)
        self.context_menu.sleep_requested.connect(
            lambda: self.pet.set_pet_state(PetState.SLEEPING)
        )
        self.context_menu.wake_requested.connect(
            lambda: self.pet.set_pet_state(PetState.IDLE)
        )
        self.context_menu.quit_requested.connect(self._quit)

        # ── System tray ──────────────────────────────────────────────
        self.tray = SystemTray(character=self.settings.character)
        self.tray.show_pet_requested.connect(self.pet.show)
        self.tray.hide_pet_requested.connect(self.pet.hide)
        self.tray.chat_requested.connect(self._open_chat)
        self.tray.task_panel_requested.connect(self._open_tasks)
        self.tray.settings_requested.connect(self._open_settings)
        self.tray.quit_requested.connect(self._quit)
        self.tray.show()

        # ── Speech bubble ────────────────────────────────────────────
        self._speech_bubble = SpeechBubble()

        # ── Notifications ────────────────────────────────────────────
        self._notifications = NotificationQueue()

        # ── Task manager ─────────────────────────────────────────────
        self.task_manager = TaskManager()
        self.task_manager.task_completed.connect(self._on_task_completed)
        self.task_manager.task_created.connect(self._on_task_created)

        # ── Permission manager ───────────────────────────────────────
        self._permission_mgr = PermissionManager()

        # ── Memory system ───────────────────────────────────────────
        from core.memory import MemoryManager
        self._memory_mgr = MemoryManager()

        # ── AI Engine ────────────────────────────────────────────────
        self.engine = LLMEngine()
        self.engine._streaming_enabled = self.settings.streaming_enabled
        # Share file-read state between engine (conversation) and tool registry
        file_read_state = self.engine.conversation.file_read_state
        self._tool_registry = ToolRegistry(
            task_manager=self.task_manager,
            file_read_state=file_read_state,
            engine=self.engine,
        )
        self._tool_registry.register_all_to_engine(self.engine)
        # Wire plan mode state into engine for tool blocking
        self.engine.set_plan_mode_state(self._tool_registry.plan_mode_state)

        # Load memory into engine
        memory_content = self._memory_mgr.load_memory(project_path=os.getcwd())
        if memory_content:
            self.engine.set_memory(memory_content)
        self.engine.set_memory_manager(self._memory_mgr)

        # ── Command Registry ────────────────────────────────────────────
        self._command_registry = CommandRegistry()

        # ── Team memory ─────────────────────────────────────────────
        from core.services.team_memory import TeamMemoryStore
        self._team_memory = TeamMemoryStore()
        self.engine.set_team_memory(self._team_memory)

        # ── Plugin system ───────────────────────────────────────────
        from core.services.plugins import PluginManager
        self._plugin_mgr = PluginManager()
        self._plugin_mgr.load_all(
            tool_registry=self._tool_registry,
            command_registry=None,  # TODO: wire CommandRegistry when created in main
        )

        # ── Cron Scheduler ─────────────────────────────────────────
        from core.cron.scheduler import CronScheduler
        from pathlib import Path
        data_dir = Path.home() / ".claude-buddy"
        self._cron_scheduler = CronScheduler(data_dir, self._on_cron_fire)
        self._cron_scheduler.start()

        # Load previous conversation if available
        if self.engine.conversation.load_last():
            pass  # conversation restored silently

        # Auto-save conversation every 30 seconds
        self._autosave_timer = QTimer()
        self._autosave_timer.setInterval(30_000)
        self._autosave_timer.timeout.connect(self._autosave_conversation)
        self._autosave_timer.start()

        # Connect engine signals
        self.engine.response_text.connect(self._on_engine_response)
        self.engine.response_chunk.connect(self._on_engine_chunk)
        self.engine.intermediate_text.connect(self._on_intermediate_text)
        self.engine.tool_start.connect(self._on_tool_start)
        self.engine.tool_result.connect(self._on_tool_result)
        self.engine.state_changed.connect(self._on_engine_state)
        self.engine.error.connect(self._on_engine_error)
        self.engine.plan_mode_changed.connect(self._on_plan_mode_changed)
        self.engine.ask_user.connect(self._on_ask_user)

        # Initialize provider
        self._refresh_provider()

        # ── Pet click → speech bubble; double-click → chat dialog ────
        self.pet.clicked.connect(self._on_pet_clicked)
        self.pet.double_clicked.connect(self._open_chat)

        # ── Pet drag → followers reposition ───────────────────────────
        self.pet.pet_moved.connect(self._on_pet_moved)

        # Dialogs (lazy init)
        self._chat_dialog: ChatDialog | None = None
        self._task_panel: TaskPanel | None = None
        self._settings_dialog: SettingsDialog | None = None

        # ── First-run guide: auto-open settings if no API key ────────
        QTimer.singleShot(800, self._check_first_run)

    # ── Helpers ──────────────────────────────────────────────────────
    def _on_cron_fire(self, job_id: str, prompt: str):
        """Handle cron job firing by sending the prompt to the engine."""
        print(f"[Cron] Firing job {job_id}: {prompt[:50]}...")
        if self.engine:
            self.engine.send_message(prompt)

    def _check_first_run(self):
        """If no API key configured, show a hint and open settings."""
        needs_key = PROVIDER_PRESETS.get(self.settings.provider, {}).get("needs_api_key", True)
        if needs_key and not self.settings.api_key:
            self.show_bubble("Welcome! Please set your API key first~")
            QTimer.singleShot(600, self._open_settings)

    def _pet_anchor(self) -> QPoint:
        """Get global position of pet's top-center for anchoring bubbles."""
        return self.pet.anchor_point()

    def _on_pet_moved(self, anchor: QPoint):
        """Pet was dragged — move all followers to stay attached."""
        self._speech_bubble.follow_anchor(anchor)
        self._notifications.set_anchor(anchor)
        if self._chat_dialog is not None and self._chat_dialog.isVisible():
            self._chat_dialog.follow_anchor(anchor)

    def _refresh_provider(self):
        """Create provider from current settings and set on engine."""
        provider = self.settings.create_provider()
        if provider:
            self.engine.set_provider(provider)

    # ── Pet interaction ──────────────────────────────────────────────
    def _on_pet_clicked(self):
        """Show speech bubble with a greeting."""
        greetings = [
            "Hi! 👋 Double-click me to chat!",
            "Need help? I'm here!",
            "Right-click for more options~",
            "What shall we work on today?",
            "I'm your Claude Buddy! 🧡",
        ]
        self._speech_bubble.show_message(
            random.choice(greetings), self._pet_anchor()
        )
        if self.pet.pet_state == PetState.SLEEPING:
            self.pet.set_pet_state(PetState.IDLE)
        else:
            self.pet.set_pet_state(PetState.TALKING)
            QTimer.singleShot(3000, lambda: (
                self.pet.set_pet_state(PetState.IDLE)
                if self.pet.pet_state == PetState.TALKING else None
            ))

    def show_bubble(self, text: str):
        """Public helper to show a speech bubble."""
        self._speech_bubble.show_message(text, self._pet_anchor())

    def _on_plan_mode_changed(self, active: bool):
        """Plan mode toggled — update chat dialog badge."""
        if self._chat_dialog is not None:
            self._chat_dialog.set_plan_mode(active)

    def _on_ask_user(self, question: str, options: object, multi_select: bool):
        """Engine's AskUser tool requests user input — show inline bubble in chat."""
        try:
            opts = list(options) if options else []
            if self._chat_dialog is not None:
                self._chat_dialog.add_ask_user(question, opts, multi_select)
                # Make sure chat is visible
                if not self._chat_dialog.isVisible():
                    self._chat_dialog.show()
            else:
                # Fallback: no chat open, resolve immediately
                self.engine.resolve_ask_user("[Chat not open]")
        except Exception as e:
            print(f"[AskUser] Inline bubble error: {e}")
            import traceback; traceback.print_exc()
            self.engine.resolve_ask_user(f"[Error: {e}]")

    # ── Chat dialog ──────────────────────────────────────────────────
    def _open_chat(self):
        if self._chat_dialog is None:
            self._chat_dialog = ChatDialog()
            self._chat_dialog.message_sent.connect(self._on_user_message)
            self._chat_dialog.open_settings.connect(self._open_settings)
            self._chat_dialog.clear_requested.connect(self._on_clear_history)
            self._chat_dialog.abort_requested.connect(self._on_abort)
            self._chat_dialog.ask_user_answered.connect(self.engine.resolve_ask_user)
        # Load conversation history into the UI
        self._chat_dialog.load_history(self.engine.conversation.all_messages)
        # Sync plan mode badge with current state
        plan_active = (self._tool_registry.plan_mode_state.active
                       if self._tool_registry.plan_mode_state else False)
        self._chat_dialog.set_plan_mode(plan_active)
        self._chat_dialog.show_near(self._pet_anchor())

    def _on_user_message(self, text: str):
        """User sent a message in the chat dialog."""
        # ── Slash commands: intercept before sending to LLM ──
        if text.startswith("/"):
            self._handle_command(text)
            return

        # Check if provider is ready
        needs_key = PROVIDER_PRESETS.get(self.settings.provider, {}).get("needs_api_key", True)
        if needs_key and not self.settings.api_key:
            if self._chat_dialog:
                self._chat_dialog.add_assistant_message(
                    "I need an API key to chat! Click the <b>gear icon</b> "
                    "in the title bar to open Settings."
                )
            return
        if self._chat_dialog:
            self._chat_dialog.set_thinking(True)
            self._chat_dialog.save_checkpoint()  # mark UI rollback point before engine starts
        self.pet.set_pet_state(PetState.WORKING)
        self.engine.send_message(text)

    def _handle_command(self, text: str):
        """Execute a slash command and show result in chat."""
        ctx = {
            "engine": self.engine,
            "conversation": self.engine.conversation,
            "command_registry": self._command_registry,
            "tool_registry": self._tool_registry,
            "evolution_mgr": self.engine._evolution_mgr,
            "task_manager": self.task_manager,
            "settings": self.settings,
            "memory_mgr": self.engine._memory_mgr,
            "plugin_mgr": getattr(self, '_plugin_mgr', None),
            "analytics": None,
            "permission_mgr": getattr(self, '_permission_mgr', None),
        }
        result = self._command_registry.execute(text, ctx)
        reply = result if result else f"Command `{text}` returned no output."

        # Special handling for /clear — archive session and clear UI
        if reply == "Session archived. Starting fresh.":
            self._on_clear_history()
            return

        # Special handling for /exit — show session ID, save and quit
        if reply.startswith("__EXIT__"):
            session_id = reply.replace("__EXIT__", "")
            if self._chat_dialog and session_id:
                self._chat_dialog.add_assistant_message(
                    f"Session saved. To resume later, use:\n\n"
                    f"  `/resume {session_id[:8]}`"
                )
                # Brief delay so user can see the message
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(5000, self._quit)
            else:
                self._quit()
            return

        # Special handling for /resume — reload chat UI with conversation history
        if "Resumed" in reply and ("conversation" in reply or "session" in reply):
            if self._chat_dialog:
                self._chat_dialog.load_history(self.engine.conversation.all_messages)
                self._chat_dialog.add_assistant_message(reply)
            # Save after command too
            self.engine.save_conversation()
            return

        # CC-aligned: __LLM_PROMPT__ prefix means "send this as a user message to the LLM"
        if reply.startswith("__LLM_PROMPT__"):
            prompt = reply[len("__LLM_PROMPT__"):]
            # Don't add_user_message here — _on_send() already showed the command in UI
            if self._chat_dialog:
                self._chat_dialog.set_thinking(True)
                self._chat_dialog.save_checkpoint()
            self.pet.set_pet_state(PetState.WORKING)
            # send_prompt: stores display_text ("/init") in conversation, sends full prompt to model
            self.engine.send_prompt(prompt, display_text=text)
            return

        # Normal command: persist both command and reply to conversation
        self.engine.conversation.add_user_message(text)
        self.engine.conversation.add_assistant_message(reply)

        if self._chat_dialog:
            self._chat_dialog.add_assistant_message(reply)

    # ── Engine signal handlers ───────────────────────────────────────
    def _on_engine_response(self, text: str):
        """Final text response from the engine."""
        if getattr(self, '_ui_abort_active', False):
            return  # user already clicked stop, ignore late response
        if self._chat_dialog:
            self._chat_dialog.add_assistant_message(text)
            self._chat_dialog.set_thinking(False)
            # Sync plan mode badge (tool may have toggled it mid-loop)
            plan_active = (self._tool_registry.plan_mode_state.active
                           if self._tool_registry.plan_mode_state else False)
            self._chat_dialog.set_plan_mode(plan_active)
        display = text[:150] + "..." if len(text) > 150 else text
        self.show_bubble(display)
        # Auto-save after each complete response
        self.engine.save_conversation()
        self._ui_abort_active = False

    def _on_engine_chunk(self, text: str):
        """Streaming text chunk — display in real time in chat dialog."""
        if getattr(self, '_ui_abort_active', False):
            return
        if self._chat_dialog:
            self._chat_dialog.append_streaming_chunk(text)

    def _on_intermediate_text(self, text: str):
        """Mid-loop text (e.g. 'I'll search for...') — show as a standalone message."""
        if getattr(self, '_ui_abort_active', False):
            return
        if self._chat_dialog:
            # Finalize any active streaming bubble first
            if self._chat_dialog._streaming_bubble:
                self._chat_dialog._streaming_bubble = None
            self._chat_dialog.add_assistant_message(text)

    def _on_tool_start(self, name: str, input_data: dict):
        if getattr(self, '_ui_abort_active', False):
            return
        if self._chat_dialog:
            # Extract a meaningful summary from tool input
            summary = (
                input_data.get("command")
                or input_data.get("file_path")
                or input_data.get("pattern")
                or input_data.get("query")       # WebSearch, Grep
                or input_data.get("url")         # WebFetch
                or input_data.get("skill")       # Skill
                or input_data.get("subject")     # TaskCreate
                or input_data.get("prompt")      # Agent, CronCreate
                or input_data.get("entry")       # DiaryWrite
                or input_data.get("file")        # SelfReflect
                or input_data.get("description") # Agent
                or ""
            )
            if isinstance(summary, str):
                summary = summary[:120]
            else:
                summary = str(summary)[:120]
            self._chat_dialog.add_tool_call(name, summary)

    def _on_tool_result(self, name: str, output: str):
        """Tool execution completed."""
        pass  # tool results shown as part of the assistant's next message

    def _on_engine_state(self, state: str):
        """Engine reports state change."""
        if state == "idle":
            if self.pet.pet_state == PetState.WORKING:
                self.pet.set_pet_state(PetState.IDLE)
            # Ensure chat UI is restored (safety net if response_text was missed)
            if self._chat_dialog and self._chat_dialog._is_thinking:
                self._chat_dialog.set_thinking(False)
        elif state == "work":
            self.pet.set_pet_state(PetState.WORKING)

    def _on_engine_error(self, error: str):
        if self._chat_dialog:
            if "cancel" in error.lower():
                # Abort complete — engine has already persisted the marker via _persist_abort().
                # CC-aligned: do NOT rollback — keep all completed tool calls and text visible.
                # Just finalize any in-progress streaming bubble and show interrupt indicator.
                if self._chat_dialog._streaming_bubble is not None:
                    self._chat_dialog._streaming_bubble = None
                # Show styled interrupt indicator
                self._chat_dialog.add_interrupt_message()
            else:
                self._chat_dialog.add_assistant_message(f"⚠️ {error}")
            self._chat_dialog.set_thinking(False)
        self.pet.set_pet_state(PetState.IDLE)
        if "cancel" not in error.lower():
            self._notifications.set_anchor(self._pet_anchor())
            self._notifications.notify_error(error)
        self._ui_abort_active = False  # ← disarm the safety timer

    def _on_abort(self):
        """User clicked stop button — abort the current engine operation."""
        self._ui_abort_active = True
        self.engine.abort()
        if self._chat_dialog:
            self._chat_dialog._send_btn.setEnabled(False)
            self._chat_dialog._send_btn.setText("...")
            self._chat_dialog.set_status("Cancelling...")

        # Safety net: if engine thread doesn't respond within 3s, force-restore UI
        # (API call may be blocking and can't be interrupted)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, self._force_restore_ui)

    def _force_restore_ui(self):
        """
        Force-restore chat UI if engine is still stuck after abort.
        This is a SAFETY NET only — fires 3s after abort request.
        If engine already responded (set _ui_abort_active=False), this is a no-op.
        """
        if not self._ui_abort_active:
            return  # Engine already responded normally — nothing to do

        self._ui_abort_active = False
        if self._chat_dialog:
            # CC-aligned: do NOT rollback — keep completed work visible
            if self._chat_dialog._streaming_bubble is not None:
                self._chat_dialog._streaming_bubble = None
            self._chat_dialog.set_thinking(False)
            self._chat_dialog.set_status("Ready")

            # Show styled interrupt indicator
            self._chat_dialog.add_interrupt_message()

        # Persist: patch incomplete tool_use + add interrupt marker
        # (only if engine didn't already do it via _persist_abort)
        msgs = self.engine.conversation.messages
        has_marker = any(
            m.get("content") == "[Request interrupted by user]"
            for m in msgs[-3:]
        )
        if not has_marker:
            # Call the engine's persist_abort which now does the right thing
            # (patch missing tool_results + append marker, no rollback)
            self.engine._persist_abort()
        self.engine.save_conversation()

    # ── Task events ──────────────────────────────────────────────────
    def _on_task_created(self, task):
        """Task created → show notification."""
        self._notifications.set_anchor(self._pet_anchor())
        self._notifications.notify_task_created(task.subject)

    def _on_task_completed(self, task):
        """Task completed → celebrate + notify."""
        self.pet.set_pet_state(PetState.CELEBRATING)
        self._notifications.set_anchor(self._pet_anchor())
        self._notifications.notify_task_completed(task.subject)
        QTimer.singleShot(3000, lambda: (
            self.pet.set_pet_state(PetState.IDLE)
            if self.pet.pet_state == PetState.CELEBRATING else None
        ))

    # ── Task panel ───────────────────────────────────────────────────
    def _open_tasks(self):
        if self._task_panel is None:
            self._task_panel = TaskPanel()

        tasks = [t.to_dict() for t in self.task_manager.all_tasks()]
        self._task_panel.refresh(tasks)
        self._task_panel.show_near(self._pet_anchor())

    # ── Settings dialog ──────────────────────────────────────────────
    def _open_settings(self):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.settings)
            self._settings_dialog.settings_changed.connect(self._on_settings_changed)
        self._settings_dialog.show_centered()

    def _on_settings_changed(self):
        """User saved new settings — refresh the provider and character."""
        self._refresh_provider()
        self.engine._streaming_enabled = self.settings.streaming_enabled

        # Switch character if changed
        new_char = self.settings.character
        if new_char != self.pet._character:
            self.pet.set_character(new_char)
            self.tray.set_character(new_char)

        self.show_bubble("Settings saved! 🧡")

    # ── Persistence ──────────────────────────────────────────────────
    def _autosave_conversation(self):
        """Auto-save conversation if there are unsaved changes."""
        if self.engine.conversation.is_dirty:
            self.engine.save_conversation()

    def _on_clear_history(self):
        """Archive current session, clear UI, start fresh."""
        self.engine.conversation.archive()
        if self._chat_dialog:
            self._chat_dialog._clear_messages()
        self.show_bubble("Session archived, starting fresh!")

    def _quit(self):
        """Save state and quit."""
        self.engine.save_conversation()
        self.app.quit()


def main():
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # keep running when dialogs close
    app.setStyleSheet(GLOBAL_QSS)

    buddy = BuddyApp(app)
    app._buddy = buddy  # prevent GC  # type: ignore

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
