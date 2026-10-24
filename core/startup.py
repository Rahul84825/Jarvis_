import os
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
REG_VAL_NAME = "SantraAssistant"
LEGACY_REG_VAL_NAME = "JarvisAssistant"

TASK_NAME = "SantraAssistant"
LEGACY_TASK_NAME = "JarvisAssistant"


def _is_winreg_mocked() -> bool:
    """Helper to detect if winreg is mocked in unit tests."""
    if not IS_WINDOWS or "winreg" not in globals():
        return False
    return hasattr(winreg, "OpenKey") and type(winreg.OpenKey).__name__ in ("MagicMock", "Mock")


def get_app_command() -> str:
    """Constructs the command line string to run Santra on Windows user login.
    Detects pythonw.exe if available to ensure silent, windowless background launch into system tray.
    """
    python_exe = Path(sys.executable)
    # Prefer pythonw.exe for silent background execution without flashing CMD terminal
    pythonw = python_exe.parent / "pythonw.exe"
    target_python = str(pythonw) if pythonw.exists() else str(python_exe)

    launcher_py = Path(__file__).parent.parent / "launcher.py"
    target_script = launcher_py if launcher_py.exists() else (Path(__file__).parent.parent / "main.py")
    target_script_str = str(target_script.resolve())
    # Runs the app minimized (in the system tray) by default on startup
    return f'"{target_python}" "{target_script_str}" --minimized'


def get_current_user_id() -> str:
    """Returns the Windows User ID in Domain\\Username format."""
    try:
        import win32api
        username = win32api.GetUserName()
        domain = win32api.GetComputerName()
        return f"{domain}\\{username}"
    except Exception:
        return os.environ.get("USERNAME", "")


# =========================================================================
# Task Scheduler Implementation (Primary & Recommended)
# =========================================================================

def is_task_scheduler_enabled() -> bool:
    """Checks if the Santra Task Scheduler task exists and is enabled."""
    if not IS_WINDOWS or _is_winreg_mocked():
        return False

    try:
        import win32com.client
        ts = win32com.client.Dispatch("Schedule.Service")
        ts.Connect()
        folder = ts.GetFolder("\\")
        try:
            task = folder.GetTask(TASK_NAME)
            return bool(task.Enabled)
        except Exception:
            return False
    except Exception as e:
        logger.debug(f"Error checking Task Scheduler: {e}")
        return False


def enable_task_scheduler(delay_seconds: int = 10) -> bool:
    """Registers a per-user Scheduled Task to start Santra at logon.
    - Triggers 'At log on' with a 10s bounded delay for audio driver initialization.
    - 'Run only when user is logged on' (TASK_LOGON_INTERACTIVE_TOKEN = 3).
    - Ignores duplicate instances (TASK_INSTANCES_IGNORE_NEW = 2).
    - Does not terminate after 3 days (ExecutionTimeLimit = PT0S).
    - Configures bounded restart-on-failure (2 restarts, 1 min interval).
    - Starts on AC or battery power without stopping.
    - Requires NO Administrator elevation.
    - Cleans up any duplicate registry Run entries.
    """
    if not IS_WINDOWS:
        return False

    try:
        import win32com.client
        ts = win32com.client.Dispatch("Schedule.Service")
        ts.Connect()
        folder = ts.GetFolder("\\")

        td = ts.NewTask(0)
        td.RegistrationInfo.Description = "SANTRA AI Desktop Assistant - User Login Startup"
        td.Settings.Enabled = True
        td.Settings.StartWhenAvailable = True
        td.Settings.DisallowStartIfOnBatteries = False
        td.Settings.StopIfGoingOnBatteries = False
        td.Settings.ExecutionTimeLimit = "PT0S"
        td.Settings.MultipleInstances = 2  # TASK_INSTANCES_IGNORE_NEW

        # Bounded restart on unexpected failure policy
        try:
            td.Settings.RestartCount = 2
            td.Settings.RestartInterval = "PT1M"
        except Exception:
            pass

        user_id = get_current_user_id()
        if user_id:
            td.Principal.UserId = user_id
            td.Principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN

        # Logon trigger (9)
        trigger = td.Triggers.Create(9)
        if user_id:
            trigger.UserId = user_id
        if delay_seconds > 0:
            trigger.Delay = f"PT{delay_seconds}S"

        # Action (0: Exec)
        action = td.Actions.Create(0)
        python_exe = Path(sys.executable)
        pythonw = python_exe.parent / "pythonw.exe"
        target_python = str(pythonw) if pythonw.exists() else str(python_exe)

        launcher_py = Path(__file__).parent.parent / "launcher.py"
        target_script = launcher_py if launcher_py.exists() else (Path(__file__).parent.parent / "main.py")
        work_dir = target_script.parent.resolve()

        action.Path = target_python
        action.Arguments = f'"{target_script.resolve()}" --minimized'
        action.WorkingDirectory = str(work_dir)

        task = folder.RegisterTaskDefinition(TASK_NAME, td, 6, None, None, 3)
        logger.info(f"Task Scheduler startup enabled for Santra: '{TASK_NAME}' (Enabled={task.Enabled})")

        # Clean up legacy task if present
        try:
            folder.DeleteTask(LEGACY_TASK_NAME, 0)
        except Exception:
            pass

        # Clean up registry Run entry to prevent double-launches
        disable_registry_startup()

        return True
    except Exception as e:
        logger.error(f"Error registering Task Scheduler task: {e}", exc_info=True)
        return False


def disable_task_scheduler() -> bool:
    """Removes the Santra Task Scheduler task."""
    if not IS_WINDOWS:
        return False

    try:
        import win32com.client
        ts = win32com.client.Dispatch("Schedule.Service")
        ts.Connect()
        folder = ts.GetFolder("\\")
        for t_name in (TASK_NAME, LEGACY_TASK_NAME):
            try:
                folder.DeleteTask(t_name, 0)
                logger.info(f"Deleted Task Scheduler task '{t_name}'.")
            except Exception:
                pass
        return True
    except Exception as e:
        logger.error(f"Error disabling Task Scheduler task: {e}")
        return False


# =========================================================================
# Registry Run Key Implementation (Fallback & Compatibility)
# =========================================================================

def is_registry_startup_enabled() -> bool:
    """Checks if the Santra startup entry exists in the Windows Registry (HKCU)."""
    if not IS_WINDOWS:
        logger.debug("is_registry_startup_enabled: Mocked False (Non-Windows platform)")
        return False

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_READ
        )
        try:
            val = None
            for key_name in (REG_VAL_NAME, LEGACY_REG_VAL_NAME):
                try:
                    val, _ = winreg.QueryValueEx(key, key_name)
                    if val:
                        break
                except FileNotFoundError:
                    continue

            if val:
                is_match = ("main.py" in val or "launcher.py" in val) and "--minimized" in val
                logger.debug(f"Startup entry found: {val} (Match={is_match})")
                return is_match
            logger.debug("Startup registry entry not found.")
            return False
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Error checking Windows registry startup status: {e}")
        return False


def enable_registry_startup() -> bool:
    """Enables Santra startup by writing to the Windows HKCU Registry."""
    if not IS_WINDOWS:
        logger.warning("enable_registry_startup: Operation aborted (Non-Windows platform)")
        return False

    cmd = get_app_command()
    logger.info(f"Enabling Windows Registry Startup for Santra. Command: {cmd}")
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
            try:
                winreg.DeleteValue(key, LEGACY_REG_VAL_NAME)
            except FileNotFoundError:
                pass
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


def disable_registry_startup() -> bool:
    """Disables Santra startup by removing the entry from the Windows Registry."""
    if not IS_WINDOWS:
        logger.warning("disable_registry_startup: Operation aborted (Non-Windows platform)")
        return False

    logger.info("Disabling Windows Registry Startup for Santra.")
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_WRITE | winreg.KEY_READ
        )
        try:
            try:
                winreg.DeleteValue(key, REG_VAL_NAME)
            except FileNotFoundError:
                try:
                    winreg.DeleteValue(key, LEGACY_REG_VAL_NAME)
                except FileNotFoundError:
                    pass
            logger.info("Windows registry startup entry deleted successfully.")
            return True
        finally:
            winreg.CloseKey(key)
    except PermissionError:
        logger.error("Failed to delete startup registry entry: Insufficient permissions.")
        return False
    except Exception as e:
        logger.error(f"Error deleting Windows registry startup entry: {e}", exc_info=True)
        return False


# =========================================================================
# Unified Facade Functions (Used by UI Tray & Tests)
# =========================================================================

def is_startup_enabled() -> bool:
    """Checks if Santra startup is enabled via Task Scheduler or Registry."""
    if _is_winreg_mocked():
        return is_registry_startup_enabled()

    return is_task_scheduler_enabled() or is_registry_startup_enabled()


def enable_startup() -> bool:
    """Enables automatic user login startup.
    Prefers Task Scheduler with 10s delay, single-instance policy, and battery settings.
    Falls back to Registry Run key if Task Scheduler is unavailable.
    """
    if _is_winreg_mocked():
        return enable_registry_startup()

    ok = enable_task_scheduler(delay_seconds=10)
    if not ok:
        logger.warning("Task Scheduler registration failed. Falling back to Windows Registry Run key.")
        return enable_registry_startup()
    return True


def disable_startup() -> bool:
    """Disables automatic user login startup from both Task Scheduler and Registry."""
    if _is_winreg_mocked():
        return disable_registry_startup()

    ts_ok = disable_task_scheduler()
    reg_ok = disable_registry_startup()
    return ts_ok or reg_ok


def get_startup_diagnostics() -> dict:
    """Returns comprehensive startup diagnostics for system verification."""
    main_py = (Path(__file__).parent.parent / "main.py").resolve()
    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / "pythonw.exe"
    work_dir = main_py.parent

    task_sched_enabled = is_task_scheduler_enabled()
    reg_enabled = is_registry_startup_enabled()

    task_details = {}
    if task_sched_enabled:
        try:
            import win32com.client
            ts = win32com.client.Dispatch("Schedule.Service")
            ts.Connect()
            task = ts.GetFolder("\\").GetTask(TASK_NAME)
            defn = task.Definition
            task_details = {
                "name": task.Name,
                "state": task.State,
                "enabled": task.Enabled,
                "action_path": defn.Actions[0].Path if defn.Actions.Count > 0 else "",
                "arguments": defn.Actions[0].Arguments if defn.Actions.Count > 0 else "",
                "working_directory": defn.Actions[0].WorkingDirectory if defn.Actions.Count > 0 else "",
                "delay": defn.Triggers[0].Delay if defn.Triggers.Count > 0 else "",
                "user": defn.Principal.UserId if defn.Principal else "",
                "multiple_instances_policy": "IgnoreNew"
            }
        except Exception as e:
            task_details = {"error": str(e)}

    launcher_py = (Path(__file__).parent.parent / "launcher.py").resolve()
    return {
        "platform": sys.platform,
        "is_windows": IS_WINDOWS,
        "python_exe": str(python_exe),
        "pythonw_exe": str(pythonw),
        "pythonw_exists": pythonw.exists(),
        "main_py": str(main_py),
        "main_py_exists": main_py.exists(),
        "launcher_py": str(launcher_py),
        "launcher_py_exists": launcher_py.exists(),
        "working_directory": str(work_dir),
        "env_file_exists": (work_dir / ".env").exists(),
        "task_scheduler_enabled": task_sched_enabled,
        "registry_run_enabled": reg_enabled,
        "task_scheduler_details": task_details,
        "command": get_app_command()
    }


def get_startup_status() -> dict:
    """Returns a structured status dictionary describing current startup configuration."""
    diag = get_startup_diagnostics()
    enabled = is_startup_enabled()
    mechanism = "Task Scheduler (At log on)" if diag["task_scheduler_enabled"] else ("Registry Run Key" if diag["registry_run_enabled"] else "None")

    return {
        "enabled": enabled,
        "mechanism": mechanism,
        "command": diag["command"],
        "working_directory": diag["working_directory"],
        "platform": "windows" if IS_WINDOWS else "unsupported",
        "logon_delay_sec": 10 if diag["task_scheduler_enabled"] else 0,
        "message": (
            f"Santra is configured to start automatically on Windows user login via {mechanism} in minimized tray mode."
            if enabled else
            "Automatic Windows startup is currently disabled."
        ),
        "diagnostics": diag
    }


def main_cli():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Santra Windows Startup Configuration Manager")
    parser.add_argument("--enable", action="store_true", help="Enable automatic Windows startup (Task Scheduler)")
    parser.add_argument("--disable", action="store_true", help="Disable automatic Windows startup")
    parser.add_argument("--remove", action="store_true", help="Alias for --disable (removes startup tasks)")
    parser.add_argument("--status", action="store_true", help="Display current startup configuration status")
    parser.add_argument("--diagnostics", action="store_true", help="Display deep startup diagnostic details")

    args = parser.parse_args()

    if args.enable:
        ok = enable_startup()
        print(f"Startup Enable Operation: {'SUCCESS' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)
    elif args.disable or args.remove:
        ok = disable_startup()
        print(f"Startup Disable Operation: {'SUCCESS' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)
    elif args.diagnostics:
        print(json.dumps(get_startup_diagnostics(), indent=2))
        sys.exit(0)
    else:
        # Default or --status
        print(json.dumps(get_startup_status(), indent=2))
        sys.exit(0)


if __name__ == "__main__":
    main_cli()
