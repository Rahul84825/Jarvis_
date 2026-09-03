import logging
from core.platform.platform_manager import platform_manager

logger = logging.getLogger("Jarvis.AppControl")

def resolve_app_path(app_key: str) -> str:
    """Attempts to resolve executable path for app."""
    if hasattr(platform_manager.platform, "resolve_executable"):
        return platform_manager.platform.resolve_executable(app_key)
    return app_key

def is_app_running(app_key: str) -> bool:
    """Checks if application is currently running."""
    return platform_manager.is_application_running(app_key)

def bring_app_to_front(app_key: str) -> bool:
    """Brings application window to front."""
    return platform_manager.focus_application(app_key)

def open_app(app_key: str) -> bool:
    """Launches application cross-platform."""
    key = app_key.lower().strip()
    if is_app_running(key) and key not in ["explorer", "notepad", "calculator"]:
        logger.info(f"Application '{key}' is running. Attempting to bring window to front.")
        if bring_app_to_front(key):
            return True
        logger.info(f"Could not focus existing window for '{key}'. Launching executable.")
    return platform_manager.open_application(key)

def close_app(app_key: str) -> bool:
    """Terminates application cross-platform."""
    return platform_manager.close_application(app_key)
