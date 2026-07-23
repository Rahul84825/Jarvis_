import logging

logger = logging.getLogger("Jarvis.Permissions")

class RiskLevel:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

# Intent/Action risk mapping
INTENT_RISK_MAPPING = {
    "open_app": RiskLevel.LOW,
    "close_app": RiskLevel.MEDIUM,
    "window_control": RiskLevel.MEDIUM,
    "file_access": RiskLevel.MEDIUM,
    "screenshot": RiskLevel.MEDIUM,
    "status_request": RiskLevel.MEDIUM,
    "volume_control": RiskLevel.MEDIUM,
    "lock_pc": RiskLevel.MEDIUM, # Primary goal asks for 'lock my computer' to work smoothly
    "sleep_pc": RiskLevel.HIGH,
    "restart_pc": RiskLevel.HIGH,
    "shutdown_pc": RiskLevel.HIGH
}

def get_action_risk_level(intent: str, action: str = None) -> str:
    """Determines the risk level for a given intent/action combination."""
    if intent == "system_control":
        if action in ["shutdown", "shutdown_pc"]:
            return RiskLevel.HIGH
        elif action in ["restart", "restart_pc"]:
            return RiskLevel.HIGH
        elif action in ["sleep", "sleep_pc"]:
            return RiskLevel.HIGH
        elif action in ["lock", "lock_pc"]:
            return RiskLevel.MEDIUM
        elif action in ["volume_up", "volume_down", "mute", "unmute"]:
            return RiskLevel.MEDIUM
        elif action in ["battery", "cpu", "ram", "disk"]:
            return RiskLevel.MEDIUM
            
    return INTENT_RISK_MAPPING.get(intent, RiskLevel.MEDIUM)

def is_safe_command(intent: str, params: dict) -> bool:
    """Validates parameters of a command to ensure they are safe and do not contain
    malicious strings or shell injection vectors.
    """
    # Block shell characters in targets/queries
    for key, val in params.items():
        if isinstance(val, str):
            # Check for shell metacharacters that could be used for injection
            if any(char in val for char in [";", "&", "|", "`", "$", ">", "<", "\n"]):
                logger.warning(f"Safety violation: block characters detected in param '{key}': {repr(val)}")
                return False
    return True
