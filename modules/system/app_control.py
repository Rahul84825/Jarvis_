import os
import sys
import subprocess
import psutil
import logging
import winreg
from pathlib import Path

logger = logging.getLogger("Jarvis.AppControl")

# Standard app mapping
APP_PROCESS_NAMES = {
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
    "vscode": "code.exe",
    "vs code": "code.exe",
    "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe",  # Modern Windows Calc name
    "explorer": "explorer.exe",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "steam": "steam.exe"
}

# Window title keywords to search for "Bring to front"
APP_WINDOW_KEYWORDS = {
    "chrome": "Google Chrome",
    "edge": "Edge",
    "firefox": "Firefox",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "notepad": "Notepad",
    "calculator": "Calculator",
    "explorer": "File Explorer",
    "spotify": "Spotify",
    "discord": "Discord",
    "steam": "Steam"
}

def resolve_app_path(app_key: str) -> str:
    """Attempts to resolve the full executable path for common apps on Windows
    using registry checks and common location probes.
    """
    key = app_key.lower().strip()
    
    # 1. Native Windows apps in System32 / Windows folder
    if key == "notepad":
        return "notepad.exe"
    elif key == "calculator":
        # Check standard modern Windows Calc shortcut
        return "calc.exe"
    elif key == "explorer":
        return "explorer.exe"
        
    # 2. Probe Registry for Registered Applications
    reg_paths = [
        rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{APP_PROCESS_NAMES.get(key, key + '.exe')}",
        rf"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths\{APP_PROCESS_NAMES.get(key, key + '.exe')}"
    ]
    
    for rp in reg_paths:
        for root in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            try:
                with winreg.OpenKey(root, rp) as rkey:
                    path = winreg.QueryValue(rkey, None)
                    if path:
                        path_str = path.replace('"', '').strip()
                        if os.path.exists(path_str):
                            return path_str
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.debug(f"Registry lookup error for {key} under {rp}: {e}")

    # 3. Common Program Files & User AppData Locations Probing
    user_local = os.environ.get("LOCALAPPDATA", "")
    user_roaming = os.environ.get("APPDATA", "")
    user_profile = os.environ.get("USERPROFILE", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    
    common_probes = {
        "chrome": [
            rf"{program_files}\Google\Chrome\Application\chrome.exe",
            rf"{program_files_x86}\Google\Chrome\Application\chrome.exe"
        ],
        "edge": [
            rf"{program_files_x86}\Microsoft\Edge\Application\msedge.exe",
            rf"{program_files}\Microsoft\Edge\Application\msedge.exe"
        ],
        "firefox": [
            rf"{program_files}\Mozilla Firefox\firefox.exe",
            rf"{program_files_x86}\Mozilla Firefox\firefox.exe"
        ],
        "vscode": [
            rf"{user_local}\Programs\Microsoft VS Code\Code.exe",
            rf"{program_files}\Microsoft VS Code\Code.exe"
        ],
        "vs code": [
            rf"{user_local}\Programs\Microsoft VS Code\Code.exe",
            rf"{program_files}\Microsoft VS Code\Code.exe"
        ],
        "spotify": [
            rf"{user_roaming}\Spotify\Spotify.exe",
            rf"{user_local}\Microsoft\WindowsApps\Spotify.exe"
        ],
        "discord": [
            # Discord installs in AppData/Local/Discord/app-<version>/Discord.exe
            # We check the AppData/Local/Discord folder for any Discord.exe recursively or shortcut
            rf"{user_local}\Discord\Update.exe"  # Can launch via Update.exe --processStart Discord.exe
        ],
        "steam": [
            rf"{program_files_x86}\Steam\steam.exe",
            rf"{program_files}\Steam\steam.exe"
        ]
    }
    
    if key in common_probes:
        for path in common_probes[key]:
            if os.path.exists(path):
                return path

    # Specialized logic for Discord (resolving app-X.X.X/Discord.exe if Update.exe is missing/fails)
    if key == "discord":
        discord_dir = Path(user_local) / "Discord"
        if discord_dir.exists():
            exes = list(discord_dir.glob("app-*/Discord.exe"))
            if exes:
                return str(exes[0])

    # Fallback to command name directly
    return APP_PROCESS_NAMES.get(key, key)

def is_app_running(app_key: str) -> bool:
    """Checks if the application is currently running."""
    key = app_key.lower().strip()
    proc_name = APP_PROCESS_NAMES.get(key, key)
    
    # Check if explorer is running (it always is, but check specifically)
    if key == "explorer":
        return True
        
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == proc_name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    # Also fallback: if calculator check calc.exe
    if key == "calculator":
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() in ["calc.exe", "calculator.exe", "calculatorapp.exe"]:
                    return True
            except:
                pass
                
    return False

def open_app(app_key: str) -> bool:
    """Launches the application. Returns True if successful."""
    key = app_key.lower().strip()
    if is_app_running(key) and key != "explorer" and key != "notepad" and key != "calculator":
        # Bring it to front instead of launching duplicate if running
        logger.info(f"Application '{key}' is already running. Focusing window.")
        return bring_app_to_front(key)
        
    path = resolve_app_path(key)
    logger.info(f"Launching application '{key}' via: {path}")
    
    try:
        if key == "discord" and "Update.exe" in path:
            # Special launch arguments for Discord update manager
            subprocess.Popen([path, "--processStart", "Discord.exe"])
        else:
            # Standard launch
            subprocess.Popen(path if os.path.isabs(path) or ".exe" in path else [path], shell=True if not os.path.isabs(path) else False)
        return True
    except Exception as e:
        logger.error(f"Failed to launch application '{key}' at path '{path}': {e}", exc_info=True)
        return False

def close_app(app_key: str) -> bool:
    """Terminates all instances of the application processes."""
    key = app_key.lower().strip()
    proc_name = APP_PROCESS_NAMES.get(key, key)
    
    # Safety check: do not terminate explorer.exe
    if key == "explorer":
        logger.warning("Attempted to close File Explorer. Blocked for safety.")
        return False
        
    terminated = False
    
    # Calc might run as Calculator.exe or CalculatorApp.exe
    target_names = [proc_name.lower()]
    if key == "calculator":
        target_names.extend(["calc.exe", "calculator.exe", "calculatorapp.exe"])
        
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            name = proc.info['name']
            if name and name.lower() in target_names:
                logger.info(f"Terminating process {name} (PID: {proc.info['pid']})")
                proc.terminate()
                proc.wait(timeout=1.0)
                terminated = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except psutil.TimeoutExpired:
            # Force kill if term times out
            try:
                proc.kill()
                terminated = True
            except:
                pass
                
    return terminated

def bring_app_to_front(app_key: str) -> bool:
    """Brings the window of the application to the foreground."""
    key = app_key.lower().strip()
    import pygetwindow as gw
    
    keyword = APP_WINDOW_KEYWORDS.get(key, key)
    logger.info(f"Attempting to bring window matching '{keyword}' to front.")
    
    try:
        windows = gw.getWindowsWithTitle("")
        target_win = None
        
        # Search for a window title matching the app keyword
        for win in windows:
            if win.title and keyword.lower() in win.title.lower():
                target_win = win
                break
                
        if target_win:
            if target_win.isMinimized:
                target_win.restore()
            target_win.activate()
            logger.info(f"Activated window: '{target_win.title}'")
            return True
            
        logger.warning(f"No active window found matching keyword: '{keyword}'")
        return False
    except Exception as e:
        logger.error(f"Error bringing app '{key}' to front: {e}", exc_info=True)
        return False
