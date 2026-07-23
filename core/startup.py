import sys
import logging
from pathlib import Path

logger = logging.getLogger("Jarvis.Startup")

# winreg is a Windows-only built-in module
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import winreg
else:
    logger.warning("Startup module imported on a non-Windows platform. Windows startup functions will be mocked.")

REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VAL_NAME = "JarvisAssistant"

def get_app_command() -> str:
    """Constructs the command line string to run Jarvis on startup.
    Points to the current Python executable and the main entry point file.
    """
    python_exe = sys.executable
    main_py = Path(__file__).parent.parent / "main.py"
    main_py = main_py.resolve()
    # Runs the app minimized (in the system tray) by default on startup
    return f'"{python_exe}" "{main_py}" --minimized'

def is_startup_enabled() -> bool:
    """Checks if the Jarvis startup entry exists in the Windows Registry."""
    if not IS_WINDOWS:
        logger.debug("is_startup_enabled: Mocked False (Non-Windows platform)")
        return False

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_READ
        )
        try:
            value, reg_type = winreg.QueryValueEx(key, REG_VAL_NAME)
            # Verify if it points to the correct startup command
            expected_cmd = get_app_command()
            is_match = value == expected_cmd
            logger.debug(f"Startup entry found: {value} (Match={is_match})")
            return is_match
        except FileNotFoundError:
            logger.debug("Startup registry entry not found.")
            return False
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Error checking Windows registry startup status: {e}")
        return False

def enable_startup() -> bool:
    """Enables Jarvis startup by writing to the Windows Registry.
    Does NOT modify settings automatically; must be called explicitly.
    """
    if not IS_WINDOWS:
        logger.warning("enable_startup: Operation aborted (Non-Windows platform)")
        return False

    cmd = get_app_command()
    logger.info(f"Enabling Windows Startup for Jarvis. Command: {cmd}")
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_WRITE | winreg.KEY_READ
        )
        try:
            winreg.SetValueEx(
                key,
                REG_VAL_NAME,
                0,
                winreg.REG_SZ,
                cmd
            )
            logger.info("Windows registry startup entry written successfully.")
            return True
        finally:
            winreg.CloseKey(key)
    except PermissionError:
        logger.error("Failed to write startup registry entry: Insufficient permissions.")
        return False
    except Exception as e:
        logger.error(f"Error writing Windows registry startup entry: {e}", exc_info=True)
        return False

def disable_startup() -> bool:
    """Disables Jarvis startup by removing the entry from the Windows Registry."""
    if not IS_WINDOWS:
        logger.warning("disable_startup: Operation aborted (Non-Windows platform)")
        return False

    logger.info("Disabling Windows Startup for Jarvis.")
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_WRITE | winreg.KEY_READ
        )
        try:
            winreg.DeleteValue(key, REG_VAL_NAME)
            logger.info("Windows registry startup entry deleted successfully.")
            return True
        except FileNotFoundError:
            logger.info("Startup registry entry does not exist, nothing to disable.")
            return True
        finally:
            winreg.CloseKey(key)
    except PermissionError:
        logger.error("Failed to delete startup registry entry: Insufficient permissions.")
        return False
    except Exception as e:
        logger.error(f"Error deleting Windows registry startup entry: {e}", exc_info=True)
        return False
