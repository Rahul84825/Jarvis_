import os
import re
import logging
from typing import Tuple

logger = logging.getLogger("Jarvis.ToolSafetyGate")

# Tools and verbs allowed in safe (read-only) mode
READ_ONLY_TOOLS = {
    "get_time", "get_date", "get_system_status", "get_battery_status",
    "get_weather", "get_news", "morning_briefing", "search_web",
    "check_unread_emails", "get_phone_battery", "ping_phone",
    "read_file", "list_directory", "inspect_tab", "take_screenshot",
    "query_memory", "get_user_profile"
}

WRITE_TOOLS = {
    "send_email", "send_telegram", "send_whatsapp", "control_smart_home",
    "run_terminal_command", "write_file", "delete_file", "edit_file",
    "launch_application", "kill_process", "lock_screen", "restart_pc",
    "shutdown_pc"
}

READ_VERB_PATTERN = re.compile(
    r"^(get|list|read|search|find|query|fetch|check|describe|inspect|show|view|explain|screenshot|ping)",
    re.IGNORECASE
)

EFFECTFUL_VERB_PATTERN = re.compile(
    r"(send|call|post|create|delete|remove|update|edit|write|install|launch|tap|swipe|press|type|buy|pay|charge|publish|deploy|outbound|download|run|exec|kill|shutdown|restart|lock)",
    re.IGNORECASE
)


class ToolSafetyGate:
    """Centralized safety policy gate modeled after J.A.R.V.I.S 2.0 decideTool logic.
    Default-deny for effectful/destructive actions unless write mode is explicitly enabled.
    """

    def __init__(self, allow_writes: bool = None):
        if allow_writes is None:
            self._allow_writes = os.getenv("JARVIS_ALLOW_WRITES", "0").lower() in ("1", "true", "yes")
        else:
            self._allow_writes = allow_writes

    @property
    def allow_writes(self) -> bool:
        return self._allow_writes

    def set_allow_writes(self, allowed: bool):
        self._allow_writes = allowed
        logger.info(f"ToolSafetyGate allow_writes set to {allowed}")

    def decide_tool(self, tool_name: str) -> bool:
        """Returns True if tool is permitted to execute, False otherwise."""
        allowed, _ = self.evaluate_tool(tool_name)
        return allowed

    def evaluate_tool(self, tool_name: str) -> Tuple[bool, str]:
        """Evaluates whether tool is allowed and returns a descriptive reason."""
        clean_name = tool_name.strip()

        # 1. Check explicit read-only registry
        if clean_name in READ_ONLY_TOOLS:
            return True, "Allowed: Whitelisted read-only tool"

        # 2. Check explicit write registry
        if clean_name in WRITE_TOOLS:
            if self._allow_writes:
                return True, "Allowed: Write tool authorized under active write permissions"
            return False, f"Blocked: '{clean_name}' modifies external state and requires write authorization"

        # 3. Effectful verb check
        if EFFECTFUL_VERB_PATTERN.search(clean_name):
            if self._allow_writes:
                return True, "Allowed: Effectful tool authorized under active write permissions"
            return False, f"Blocked: '{clean_name}' contains effectful action and requires write authorization"

        # 4. Read verb check
        if READ_VERB_PATTERN.match(clean_name):
            return True, "Allowed: Read-action verb detected"

        # 5. Default fallback
        if self._allow_writes:
            return True, "Allowed: Safe-mode override active"
        return False, f"Blocked: '{clean_name}' is unverified and denied under default safe-mode policy"


tool_safety_gate = ToolSafetyGate()
