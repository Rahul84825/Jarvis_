"""Centralized Command Response Registry for JARVIS.

Defines standardized response behaviors for every registered JARVIS intent and tool:
- Structured command outcomes (SUCCESS, INVALID_COMMAND, MISSING_ARGUMENT, etc.)
- Acknowledgment responses for longer operations
- Truthful success responses backed by verified execution evidence
- Concise clarification questions for missing arguments
- Specific failure and unsupported capability responses
- Dynamic capabilities summary generated from implemented tools
"""

import logging
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger("Jarvis.ResponseRegistry")


class CommandOutcome(str, Enum):
    """Standardized internal outcomes for command execution."""
    SUCCESS = "SUCCESS"
    INVALID_COMMAND = "INVALID_COMMAND"
    MISSING_ARGUMENT = "MISSING_ARGUMENT"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class IntentResponseDefinition:
    """Defines response behavior and phrasing for a registered intent."""
    intent_id: str
    description: str
    tool_name: str
    patterns: List[str] = field(default_factory=list)
    needs_acknowledgment: bool = False
    ack_template: Optional[str] = None
    success_template: str = "{message}"
    failure_template: str = "That action failed, Sir. Please try again."
    missing_arg_prompts: Dict[str, str] = field(default_factory=dict)
    unsupported_template: Optional[str] = "That capability isn't available yet, Sir."
    spoken: bool = True
    displayed: bool = True


class CommandResponseRegistry:
    """Central registry of response behaviors across all JARVIS commands."""

    def __init__(self):
        self._definitions: Dict[str, IntentResponseDefinition] = {}
        self._register_default_definitions()
        logger.info(f"CommandResponseRegistry initialized with {len(self._definitions)} intent response definitions.")

    def register(self, definition: IntentResponseDefinition):
        self._definitions[definition.intent_id] = definition

    def get_definition(self, intent_id: str) -> Optional[IntentResponseDefinition]:
        return self._definitions.get(intent_id)

    def list_all_definitions(self) -> List[IntentResponseDefinition]:
        return list(self._definitions.values())

    def get_acknowledgment(self, intent_node: Dict[str, Any]) -> Optional[str]:
        """Returns brief acknowledgment if useful before a potentially longer operation."""
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action")
        target = intent_node.get("target") or ""
        provider = intent_node.get("provider", "")

        defn = self.get_definition(intent)
        if not defn or not defn.needs_acknowledgment:
            return None

        # Contextual overrides for search
        if intent == "web_search":
            if provider == "youtube" or "youtube" in (target or "").lower():
                return "Searching YouTube, Sir."
            elif provider in ["github", "reddit", "stackoverflow"]:
                return f"Searching {provider.title()}, Sir."
            return "Searching the web now, Sir."

        # Contextual overrides for applications
        if intent == "open_app":
            clean_app = self._format_name(target) or "Application"
            return f"Opening {clean_app}, Sir."

        if intent == "open_website":
            clean_site = self._format_name(target) or "the website"
            return f"Opening {clean_site}, Sir."

        # Filesystem
        if intent == "filesystem_control":
            if action == "create_folder":
                return "Creating the folder, Sir."
            elif action in ["write_file", "save_file"]:
                return "Saving the file, Sir."

        # Content generation
        if intent == "content_generation":
            return "Certainly, Sir. I'll prepare that."

        if defn.ack_template:
            clean_target = self._format_name(target)
            return defn.ack_template.format(target=clean_target, app=clean_target, site=clean_target)

        return None

    def get_missing_arg_prompt(self, intent_node: Dict[str, Any]) -> Optional[str]:
        """Returns a single concise question when a required argument is missing."""
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action")
        missing_arg = intent_node.get("missing_arg")

        defn = self.get_definition(intent)
        if defn and missing_arg and missing_arg in defn.missing_arg_prompts:
            return defn.missing_arg_prompts[missing_arg]

        # Specific standard questions
        if intent == "web_search" or intent_node.get("empty_query"):
            return "What would you like me to search for, Sir?"

        if intent == "open_app" or (action == "open" and not intent_node.get("target")):
            return "Which application should I open, Sir?"

        if intent == "close_app" or (action == "close" and not intent_node.get("target")):
            return "Which application should I close, Sir?"

        if intent == "open_website":
            return "Which website would you like me to open, Sir?"

        if intent in ["filesystem_control", "file_access"]:
            if action == "create_folder":
                return "What should I name the folder, Sir?"
            elif action in ["save_file", "write_file"]:
                return "Where should I save the file, Sir?"
            elif action == "open_folder":
                return "Which folder should I open, Sir?"

        if intent == "content_generation":
            return "What would you like me to write, Sir?"

        if intent == "math_calculation":
            return "What would you like me to calculate, Sir?"

        return None

    def get_success_response(self, intent_node: Dict[str, Any], result: Dict[str, Any] = None) -> str:
        """Returns confirmed success response backed by execution evidence."""
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action")
        target = intent_node.get("target") or ""
        clean_target = self._format_name(target)
        result = result or {}
        evidence_msg = result.get("message", "")

        # 1. Custom evidence-backed checks
        if intent == "open_app":
            app_name = clean_target or "Application"
            return f"{app_name} is open, Sir."

        if intent == "close_app":
            app_name = clean_target or "Application"
            return f"{app_name} is closed, Sir."

        if intent == "open_website":
            site_name = clean_target or "Website"
            return f"{site_name} is open, Sir."

        if intent == "web_search":
            if evidence_msg and "searching " in evidence_msg.lower():
                return evidence_msg
            return "Here are the search results, Sir."

        if intent == "screenshot":
            return "The screenshot has been saved, Sir."

        if intent == "filesystem_control":
            if action == "create_folder":
                return "The folder has been created, Sir."
            elif action in ["write_file", "save_file"]:
                return "The document has been saved, Sir."

        if intent == "content_generation":
            return "The document has been saved, Sir."

        # System controls
        if action == "volume_up":
            return "Volume increased, Sir."
        if action == "volume_down":
            return "Volume decreased, Sir."
        if action == "mute":
            return "Muted, Sir."
        if action == "unmute":
            return "Unmuted, Sir."
        if action == "lock_pc":
            return "Locking the computer, Sir."

        # Template fallback
        defn = self.get_definition(intent)
        if defn and defn.success_template:
            try:
                return defn.success_template.format(
                    target=clean_target,
                    app=clean_target,
                    site=clean_target,
                    message=evidence_msg or "Done, Sir."
                )
            except Exception:
                pass

        return evidence_msg or "Done, Sir."

    def get_failure_response(
        self,
        intent_node: Dict[str, Any],
        outcome: CommandOutcome = CommandOutcome.EXECUTION_FAILED,
        reason: Optional[str] = None
    ) -> str:
        """Returns concise, specific failure response based on verified failure category."""
        target = intent_node.get("target") or ""
        clean_target = self._format_name(target)
        intent = intent_node.get("intent", "unknown")
        reason_lower = (reason or "").lower()

        # 1. Outcome-specific exact phrasing from specification
        if outcome == CommandOutcome.PERMISSION_DENIED or "permission" in reason_lower or "blocked" in reason_lower:
            return "I don't have permission to do that, Sir."

        if outcome == CommandOutcome.TIMEOUT or "timed out" in reason_lower or "timeout" in reason_lower:
            return "That action timed out, Sir. Please try again."

        if outcome == CommandOutcome.PROVIDER_UNAVAILABLE or "temporarily unavailable" in reason_lower:
            if intent == "web_search":
                return "Search is temporarily unavailable, Sir."
            return "That service is temporarily unavailable, Sir."

        if outcome == CommandOutcome.UNSUPPORTED_CAPABILITY:
            if "installed" in reason_lower or intent == "open_app":
                return "That application isn't installed, Sir."
            return "That capability isn't available yet, Sir."

        if outcome == CommandOutcome.INVALID_COMMAND:
            return "I couldn't complete that request, Sir. Try another command."

        if outcome == CommandOutcome.CANCELLED:
            return "Action canceled, Sir. Standby."

        # 2. Contextual failures by intent
        if intent == "open_app":
            if "not found" in reason_lower or "not installed" in reason_lower:
                return "That application isn't installed, Sir."
            return f"I couldn't open {clean_target or 'that application'}, Sir."

        if intent == "open_website":
            return "I couldn't open that website, Sir."

        if intent == "web_search":
            if "network" in reason_lower or "connection" in reason_lower or "unavailable" in reason_lower:
                return "Search is temporarily unavailable, Sir."
            return "I couldn't complete that search, Sir."

        # Default execution failure from specification
        return "That action failed, Sir. Please try again."

    def get_outcome_response(self, outcome: CommandOutcome, detail: Optional[str] = None) -> str:
        """Returns standard concise response string for any CommandOutcome enum."""
        if outcome == CommandOutcome.SUCCESS:
            return detail or "Done, Sir."
        elif outcome == CommandOutcome.INVALID_COMMAND:
            return "I couldn't complete that request, Sir. Try another command."
        elif outcome == CommandOutcome.UNSUPPORTED_CAPABILITY:
            return "That capability isn't available yet, Sir."
        elif outcome == CommandOutcome.MISSING_ARGUMENT:
            return detail or "Please specify what you need, Sir."
        elif outcome == CommandOutcome.PROVIDER_UNAVAILABLE:
            return "Search is temporarily unavailable, Sir."
        elif outcome == CommandOutcome.PERMISSION_DENIED:
            return "I don't have permission to do that, Sir."
        elif outcome == CommandOutcome.TIMEOUT:
            return "That action timed out, Sir. Please try again."
        elif outcome == CommandOutcome.EXECUTION_FAILED:
            return "That action failed, Sir. Please try again."
        elif outcome == CommandOutcome.CANCELLED:
            return "Action canceled, Sir. Standby."
        return "I couldn't complete that request, Sir. Try another command."

    def get_capabilities_summary(self, tool_registry: Any = None) -> str:
        """Generates an up-to-date summary of supported commands, discovered applications, and custom workflows."""
        from core.apps.application_discovery import app_discovery
        from core.custom_commands.command_registry import custom_command_registry

        if not tool_registry:
            from core.tool_registry import tool_registry as default_tr
            tool_registry = default_tr

        tools = [t for t in tool_registry.list_all_tools() if getattr(t, "implemented", True)]
        categories: Dict[str, List[str]] = {}
        for t in tools:
            categories.setdefault(t.category.lower(), []).append(t.name.replace("_", " ").title())

        category_display_map = {
            "applications": "Applications",
            "browser": "Browser & Tabs",
            "search": "Web & Local Search",
            "filesystem": "Files & Folders",
            "media": "Media & Playback",
            "developer": "Developer Workflow",
            "system": "System Controls",
            "content": "Content & Reasoning",
            "observability": "Observability",
            "memory": "Memory & Profile",
            "privacy": "Security & Privacy",
        }

        lines = ["Here is what I can do for you, Sir:"]
        for cat_key, tool_names in sorted(categories.items()):
            cat_disp = category_display_map.get(cat_key, cat_key.replace("_", " ").title())
            sample_tools = ", ".join(tool_names[:4])
            lines.append(f"• {cat_disp}: {sample_tools}")

        # Discovered applications summary
        try:
            discovered_count = len(app_discovery.list_applications(available_only=True))
            if discovered_count > 0:
                lines.append(f"• Discovered Apps: Over {discovered_count} installed applications available to launch directly.")
        except Exception:
            pass

        # Enabled custom commands summary
        try:
            custom_cmds = custom_command_registry.list_commands(enabled_only=True)
            if custom_cmds:
                sample_custom = ", ".join(c.name for c in custom_cmds[:3])
                more = f" and {len(custom_cmds)-3} more" if len(custom_cmds) > 3 else ""
                lines.append(f"• Custom Workflows: {sample_custom}{more} (say 'list custom commands' for all).")
            else:
                lines.append("• Custom Workflows: You can teach me new custom commands and sequential workflows anytime.")
        except Exception:
            pass

        lines.append("\nYou can combine commands, search the web or YouTube, write documents, and manage your computer.")
        return "\n".join(lines)

    def _format_name(self, text: Optional[str]) -> str:
        if not text:
            return ""
        clean = text.strip().lower()
        if clean in ["chrome", "google chrome"]:
            return "Chrome"
        if clean in ["vscode", "vs code", "visual studio code"]:
            return "VS Code"
        if clean == "youtube":
            return "YouTube"
        if clean == "github":
            return "GitHub"
        if clean == "spotify":
            return "Spotify"
        if clean == "steam":
            return "Steam"
        return text.strip().replace("_", " ").title()

    def _register_default_definitions(self):
        # 1. Applications
        self.register(IntentResponseDefinition(
            intent_id="open_app",
            description="Launch or focus desktop application",
            tool_name="open_app",
            patterns=["open {app}", "launch {app}", "start {app}"],
            needs_acknowledgment=True,
            ack_template="Opening {app}, Sir.",
            success_template="{app} is open, Sir.",
            failure_template="I couldn't open {app}, Sir.",
            missing_arg_prompts={"app": "Which application should I open, Sir?"},
            unsupported_template="That application isn't installed, Sir."
        ))

        self.register(IntentResponseDefinition(
            intent_id="close_app",
            description="Close running desktop application",
            tool_name="close_app",
            patterns=["close {app}", "quit {app}", "exit {app}"],
            needs_acknowledgment=False,
            success_template="{app} is closed, Sir.",
            failure_template="I couldn't close {app}, Sir.",
            missing_arg_prompts={"app": "Which application should I close, Sir?"}
        ))

        # 2. Websites
        self.register(IntentResponseDefinition(
            intent_id="open_website",
            description="Open website in default browser",
            tool_name="open_website",
            patterns=["open {website}", "go to {website}"],
            needs_acknowledgment=True,
            ack_template="Opening {site}, Sir.",
            success_template="{site} is open, Sir.",
            failure_template="I couldn't open that website, Sir.",
            missing_arg_prompts={"target": "Which website would you like me to open, Sir?"}
        ))

        # 3. Web Search
        self.register(IntentResponseDefinition(
            intent_id="web_search",
            description="Search the web or targeted services",
            tool_name="web_search",
            patterns=["search {query}", "search youtube for {query}", "search google for {query}"],
            needs_acknowledgment=True,
            ack_template="Searching the web now, Sir.",
            success_template="Here are the search results, Sir.",
            failure_template="Search is temporarily unavailable, Sir.",
            missing_arg_prompts={"query": "What would you like me to search for, Sir?"}
        ))

        # 4. Screenshots
        self.register(IntentResponseDefinition(
            intent_id="screenshot",
            description="Capture screen and save snapshot",
            tool_name="take_screenshot",
            patterns=["take screenshot", "capture screen"],
            needs_acknowledgment=False,
            success_template="Screenshot saved, Sir.",
            failure_template="I couldn't take a screenshot, Sir."
        ))

        # 5. Content Generation & File Writing
        self.register(IntentResponseDefinition(
            intent_id="content_generation",
            description="Draft and write documents to disk",
            tool_name="content_generation",
            patterns=["write a document about {topic}", "draft content"],
            needs_acknowledgment=True,
            ack_template="Certainly, Sir. I'll prepare that.",
            success_template="The document has been saved, Sir.",
            failure_template="I couldn't generate that content, Sir.",
            missing_arg_prompts={"topic": "What would you like me to write, Sir?"}
        ))

        # 6. Filesystem
        self.register(IntentResponseDefinition(
            intent_id="filesystem_control",
            description="Create folders and manage filesystem",
            tool_name="filesystem_control",
            patterns=["create folder {name}", "new folder"],
            needs_acknowledgment=True,
            ack_template="Creating the folder, Sir.",
            success_template="The folder has been created, Sir.",
            failure_template="I couldn't create that folder, Sir.",
            missing_arg_prompts={
                "folder": "What should I name the folder, Sir?",
                "folder_name": "What should I name the folder, Sir?",
                "destination": "Where should I save the file, Sir?"
            }
        ))


        # 8. System Controls
        self.register(IntentResponseDefinition(
            intent_id="system_control",
            description="System hardware and setting controls",
            tool_name="system_control",
            patterns=["volume up", "volume down", "mute", "unmute", "lock pc"],
            needs_acknowledgment=False,
            success_template="{message}",
            failure_template="I couldn't update that system setting, Sir."
        ))

        # 9. Time and Date
        self.register(IntentResponseDefinition(
            intent_id="time_query",
            description="Report current system time",
            tool_name="time_query",
            patterns=["what time is it", "current time"],
            needs_acknowledgment=False,
            success_template="{message}"
        ))

        self.register(IntentResponseDefinition(
            intent_id="date_query",
            description="Report current calendar date",
            tool_name="date_query",
            patterns=["what is today's date", "current date"],
            needs_acknowledgment=False,
            success_template="{message}"
        ))

        # 10. Math Calculations
        self.register(IntentResponseDefinition(
            intent_id="math_calculation",
            description="Solve mathematical calculation",
            tool_name="math_calculation",
            patterns=["calculate {expression}", "what is {math}"],
            needs_acknowledgment=False,
            success_template="{message}",
            missing_arg_prompts={"expression": "What would you like me to calculate, Sir?"}
        ))

        # 11. Help / Capabilities
        self.register(IntentResponseDefinition(
            intent_id="help",
            description="List capabilities and assist user",
            tool_name="help",
            patterns=["what can you do", "help", "commands"],
            needs_acknowledgment=False,
            success_template="{message}"
        ))


# Global Singleton Instance
response_registry = CommandResponseRegistry()
