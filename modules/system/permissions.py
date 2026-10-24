import logging

logger = logging.getLogger("Jarvis.Permissions")

class RiskLevel:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

# Intent/Action risk mapping
INTENT_RISK_MAPPING = {
    "open_app": RiskLevel.LOW,
    "application.launch": RiskLevel.LOW,
    "command_management": RiskLevel.LOW,
    "custom_command": RiskLevel.LOW,
    "close_app": RiskLevel.MEDIUM,
    "minimize_app": RiskLevel.LOW,
    "maximize_app": RiskLevel.LOW,
    "open_new_chrome_tab": RiskLevel.LOW,
    "open_new_chrome_window": RiskLevel.LOW,
    "window_control": RiskLevel.MEDIUM,
    "file_access": RiskLevel.MEDIUM,
    "screenshot": RiskLevel.MEDIUM,
    "status_request": RiskLevel.MEDIUM,
    "volume_control": RiskLevel.MEDIUM,
    "lock_pc": RiskLevel.MEDIUM,
    "sleep_assistant": RiskLevel.LOW,
    "sleep_pc": RiskLevel.HIGH,
    "restart_pc": RiskLevel.HIGH,
    "shutdown_pc": RiskLevel.HIGH,
    "hibernate_pc": RiskLevel.HIGH,
    "browser_control": RiskLevel.LOW,
    "youtube_control": RiskLevel.LOW,
    "web_search": RiskLevel.LOW,
    "site_search": RiskLevel.LOW,
    "local_search": RiskLevel.LOW,
    "content_generation": RiskLevel.LOW,
    "filesystem_control": RiskLevel.LOW,
    "developer_workflow": RiskLevel.MEDIUM,
    "follow_up": RiskLevel.LOW,
    "explain_tool_execution": RiskLevel.LOW,
    "memory_control": RiskLevel.LOW,
    "privacy_control": RiskLevel.LOW,
    "unsupported_capability": RiskLevel.LOW,
    "invalid_command": RiskLevel.LOW,
    "panel_visibility": RiskLevel.LOW
}

def get_action_risk_level(intent: str, action: str = None) -> str:
    """Determines the risk level for a given intent/action combination."""
    if intent == "system_control":
        if action in ["sleep_assistant", "enter_sleep", "sleep_mode"]:
            return RiskLevel.LOW
        elif action in ["shutdown", "shutdown_pc"]:
            return RiskLevel.HIGH
        elif action in ["restart", "restart_pc"]:
            return RiskLevel.HIGH
        elif action in ["sleep", "sleep_pc"]:
            return RiskLevel.HIGH
        elif action in ["hibernate", "hibernate_pc"]:
            return RiskLevel.HIGH
        elif action in ["lock", "lock_pc"]:
            return RiskLevel.MEDIUM
        elif action in ["volume_up", "volume_down", "mute", "unmute"]:
            return RiskLevel.MEDIUM
        elif action in ["battery", "cpu", "ram", "disk"]:
            return RiskLevel.MEDIUM

    if intent == "filesystem_control":
        if action in ["delete", "remove", "delete_file", "delete_folder"]:
            return RiskLevel.HIGH
        return RiskLevel.LOW

    if intent == "spotify_control":
        if action in ["delete_playlist", "unfollow_playlist", "replace_tracks", "clear_playlist"]:
            return RiskLevel.HIGH
        elif action in ["create_playlist", "rename_playlist", "add_track", "add_tracks_by_artist", "remove_track", "reorder_track", "cleanup_duplicates"]:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    return INTENT_RISK_MAPPING.get(intent, RiskLevel.MEDIUM)

def is_safe_command(intent: str, params: dict) -> bool:
    """Validates parameters of a command to ensure they are safe and do not contain
    malicious strings or shell injection vectors.
    """
    # Content generation, web search, memory, privacy, command management, spotify, and panel visibility are safe from shell execution
    if intent in ["content_generation", "web_search", "open_website", "conversation", "question", "explain_tool_execution", "memory_control", "privacy_control", "command_management", "custom_command", "spotify_control", "panel_visibility"]:
        # Only verify explicit shell execution targets if present
        check_keys = ["command", "script"]
    else:
        check_keys = ["target", "command", "app"]

    dangerous_chars = [";", "&", "|", "`", "$", ">", "<", "\n"]
    for key in check_keys:
        val = params.get(key)
        if isinstance(val, str):
            if any(char in val for char in dangerous_chars):
                logger.warning(f"Safety violation: block characters detected in param '{key}': {repr(val)}")
                return False

    return True
