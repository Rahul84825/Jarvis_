import os
import json
import ctypes
import shutil
import logging
import subprocess
import webbrowser
import psutil
from pathlib import Path
from typing import Tuple, Dict, Any

from core.platform.base_platform import BasePlatform

logger = logging.getLogger("Jarvis.WindowsPlatform")

class WindowsPlatform(BasePlatform):
    """Windows Platform Implementation."""

    def __init__(self, apps_json_path: Path = None):
        if apps_json_path is None:
            apps_json_path = Path(__file__).parent.parent.parent / "config" / "applications.json"
        self.apps_json_path = apps_json_path
        self.app_registry = self._load_app_registry()

    def _load_app_registry(self) -> dict:
        if self.apps_json_path.exists():
            try:
                with open(self.apps_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load applications.json: {e}")
        return {}

    def resolve_app_key(self, raw_name: str) -> str:
        name = raw_name.lower().strip('.!?,:; \t\n')
        # Direct match in registry keys
        if name in self.app_registry:
            return name
        # Search in aliases
        for app_key, data in self.app_registry.items():
            aliases = data.get("aliases", [])
            if name in [a.lower().strip('.!?,:; ') for a in aliases]:
                return app_key
        return name

    def resolve_executable(self, app_key: str) -> str:
        if not hasattr(self, "_exec_cache"):
            self._exec_cache = {}
        if app_key in self._exec_cache:
            return self._exec_cache[app_key]

        res = self._resolve_executable_uncached(app_key)
        self._exec_cache[app_key] = res
        return res

    def _resolve_executable_uncached(self, app_key: str) -> str:
        key = self.resolve_app_key(app_key)
        reg_entry = self.app_registry.get(key, {})
        win_exec = reg_entry.get("windows")
        if win_exec:
            if not win_exec.endswith(".exe") and win_exec not in ["calc", "notepad", "explorer"]:
                win_exec += ".exe"
            exe_candidate = win_exec
        else:
            exe_map = {
                "chrome": "chrome.exe",
                "google chrome": "chrome.exe",
                "edge": "msedge.exe",
                "firefox": "firefox.exe",
                "vscode": "code.exe",
                "vs code": "code.exe",
                "notepad": "notepad.exe",
                "calculator": "calc.exe",
                "calc": "calc.exe",
                "explorer": "explorer.exe",
                "spotify": "spotify.exe",
                "discord": "discord.exe",
                "terminal": "wt.exe",
                "powershell": "powershell.exe",
                "cmd": "cmd.exe"
            }
            exe_candidate = exe_map.get(key, f"{key}.exe" if not key.endswith(".exe") else key)

        # 1. Direct which search in PATH
        found = shutil.which(exe_candidate)
        if found:
            return found

        # 2. Probe Windows App Paths in Registry (HKLM & HKCU)
        try:
            import winreg
            for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for reg_sub in [
                    f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_candidate}",
                    f"SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_candidate}"
                ]:
                    try:
                        with winreg.OpenKey(root, reg_sub) as rk:
                            val, _ = winreg.QueryValueEx(rk, "")
                            if val and os.path.exists(val):
                                return val
                    except Exception:
                        pass
        except Exception:
            pass

        # 3. Probe standard Program Files and LocalAppData installation paths
        pf = os.environ.get("ProgramFiles", "C:\\Program Files")
        pfx86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        local_app = os.environ.get("LOCALAPPDATA", "")
        app_data = os.environ.get("APPDATA", "")

        app_known_locations = {
            "chrome": [
                Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(pfx86) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(local_app) / "Google" / "Chrome" / "Application" / "chrome.exe",
            ],
            "edge": [
                Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(pfx86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ],
            "firefox": [
                Path(pf) / "Mozilla Firefox" / "firefox.exe",
                Path(pfx86) / "Mozilla Firefox" / "firefox.exe",
            ],
            "vscode": [
                Path(local_app) / "Programs" / "Microsoft VS Code" / "Code.exe",
                Path(pf) / "Microsoft VS Code" / "Code.exe",
                Path(pfx86) / "Microsoft VS Code" / "Code.exe",
            ],
            "spotify": [
                Path(app_data) / "Spotify" / "Spotify.exe",
                Path(local_app) / "Microsoft" / "WindowsApps" / "spotify.exe",
            ],
            "discord": [
                Path(local_app) / "Discord" / "Update.exe",
            ],
            "antigravity": [
                Path(local_app) / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe",
                Path(local_app) / "Programs" / "antigravity" / "Antigravity.exe",
                Path(local_app) / "Programs" / "Antigravity" / "Antigravity.exe",
                Path(pf) / "Antigravity IDE" / "Antigravity IDE.exe",
                Path(pfx86) / "Antigravity IDE" / "Antigravity IDE.exe",
                Path(os.path.expanduser("~")) / ".gemini" / "antigravity" / "antigravity.exe",
                Path(os.path.expanduser("~")) / ".gemini" / "antigravity-ide" / "antigravity-ide.exe",
            ]
        }

        for path_obj in app_known_locations.get(key, []):
            if path_obj.exists():
                return str(path_obj)

        return exe_candidate

    # ==========================================
    # APPLICATION CONTROL
    # ==========================================
    def open_application(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        if self.is_application_running(key) and key not in ["explorer", "notepad", "calculator"]:
            if self.focus_application(key):
                return True

        exec_path = self.resolve_executable(key)
        logger.info(f"[Windows] Launching application '{key}' via: {exec_path}")

        # Attempt 1: Absolute path execution
        if os.path.isabs(exec_path):
            if os.path.exists(exec_path):
                try:
                    subprocess.Popen([exec_path])
                    return True
                except Exception as e:
                    logger.warning(f"[Windows] Subprocess absolute launch failed for '{exec_path}': {e}")
            else:
                logger.warning(f"[Windows] Resolved path does not exist on disk: '{exec_path}'")
                return False

        # Attempt 2: Command found in system PATH or Windows built-ins (e.g. notepad, calc, explorer, wt, cmd)
        is_builtin = key in ["calc", "calculator", "notepad", "explorer", "cmd", "powershell", "settings"] or exec_path.startswith("ms-")
        which_path = shutil.which(exec_path)

        if which_path:
            try:
                subprocess.Popen([which_path])
                return True
            except Exception as e:
                logger.debug(f"[Windows] Failed to launch via which path: {e}")

        if is_builtin:
            try:
                os.startfile(exec_path)
                return True
            except Exception as e:
                logger.debug(f"[Windows] os.startfile failed for '{exec_path}': {e}")
                try:
                    subprocess.Popen(f'start "" "{exec_path}"', shell=True)
                    return True
                except Exception:
                    pass

        logger.warning(f"[Windows] Could not locate executable for '{key}'.")
        return False

    def close_application(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        if key == "explorer":
            logger.warning("[Windows] Attempted to close File Explorer. Blocked for safety.")
            return False

        exec_name = Path(self.resolve_executable(key)).name.lower()
        target_names = [exec_name, f"{key}.exe", key]
        if not exec_name.endswith(".exe"):
            target_names.append(f"{exec_name}.exe")
        if key == "chrome":
            target_names.extend(["chrome.exe", "google chrome.exe"])
        elif key == "calculator":
            target_names.extend(["calc.exe", "calculator.exe", "calculatorapp.exe"])
        elif key in ["vscode", "vs code"]:
            target_names.extend(["code.exe"])
        elif key == "edge":
            target_names.extend(["msedge.exe", "edge.exe"])

        terminated = False
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                name = proc.info['name']
                if name and name.lower() in target_names:
                    logger.info(f"[Windows] Terminating process {name} (PID: {proc.info['pid']})")
                    proc.terminate()
                    proc.wait(timeout=1.0)
                    terminated = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except psutil.TimeoutExpired:
                try:
                    proc.kill()
                    terminated = True
                except:
                    pass
        return terminated

    def is_application_running(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        if key == "explorer":
            return True

        exec_name = Path(self.resolve_executable(key)).name.lower()
        target_names = [exec_name, f"{key}.exe", key]
        if not exec_name.endswith(".exe"):
            target_names.append(f"{exec_name}.exe")
        if key == "chrome":
            target_names.extend(["chrome.exe", "google chrome.exe"])
        elif key == "calculator":
            target_names.extend(["calc.exe", "calculator.exe", "calculatorapp.exe"])
        elif key in ["vscode", "vs code"]:
            target_names.extend(["code.exe"])
        elif key == "edge":
            target_names.extend(["msedge.exe", "edge.exe"])

        for proc in psutil.process_iter(['name']):
            try:
                name = proc.info['name']
                if name and name.lower() in target_names:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def focus_application(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        try:
            import pygetwindow as gw
            window_keywords = {
                "chrome": "Google Chrome",
                "edge": "Edge",
                "firefox": "Firefox",
                "vscode": "Visual Studio Code",
                "notepad": "Notepad",
                "calculator": "Calculator",
                "explorer": "File Explorer",
                "spotify": "Spotify",
                "discord": "Discord",
                "steam": "Steam",
                "terminal": "Terminal"
            }
            keyword = window_keywords.get(key, key)
            windows = gw.getWindowsWithTitle("")
            for win in windows:
                if win.title and keyword.lower() in win.title.lower():
                    if win.isMinimized:
                        win.restore()
                    win.activate()
                    logger.info(f"[Windows] Focused window: '{win.title}'")
                    return True
        except Exception as e:
            logger.debug(f"[Windows] Could not focus application window for '{key}': {e}")
        return False

    def minimize_application(self, app_key: str = None) -> bool:
        try:
            import pygetwindow as gw
            if not app_key:
                active = gw.getActiveWindow()
                if active and not active.isMinimized:
                    active.minimize()
                    return True
                return False

            key = self.resolve_app_key(app_key)
            window_keywords = {
                "chrome": "Google Chrome", "edge": "Edge", "firefox": "Firefox",
                "vscode": "Visual Studio Code", "notepad": "Notepad", "calculator": "Calculator",
                "explorer": "File Explorer", "spotify": "Spotify", "discord": "Discord", "steam": "Steam"
            }
            keyword = window_keywords.get(key, key)
            windows = gw.getWindowsWithTitle("")
            minimized = False
            for win in windows:
                if win.title and keyword.lower() in win.title.lower():
                    if not win.isMinimized:
                        win.minimize()
                        minimized = True
            return minimized
        except Exception as e:
            logger.error(f"[Windows] Minimize failed for '{app_key}': {e}")
            return False

    def maximize_application(self, app_key: str = None) -> bool:
        try:
            import pygetwindow as gw
            if not app_key:
                active = gw.getActiveWindow()
                if active:
                    if active.isMinimized:
                        active.restore()
                    active.maximize()
                    return True
                return False

            key = self.resolve_app_key(app_key)
            window_keywords = {
                "chrome": "Google Chrome", "edge": "Edge", "firefox": "Firefox",
                "vscode": "Visual Studio Code", "notepad": "Notepad", "calculator": "Calculator",
                "explorer": "File Explorer", "spotify": "Spotify", "discord": "Discord", "steam": "Steam"
            }
            keyword = window_keywords.get(key, key)
            windows = gw.getWindowsWithTitle("")
            maximized = False
            for win in windows:
                if win.title and keyword.lower() in win.title.lower():
                    if win.isMinimized:
                        win.restore()
                    win.maximize()
                    win.activate()
                    maximized = True
            return maximized
        except Exception as e:
            logger.error(f"[Windows] Maximize failed for '{app_key}': {e}")
            return False

    def open_file(self, file_path_or_name: str) -> Tuple[bool, str, list]:
        """Safely searches and opens a requested file."""
        if not file_path_or_name:
            return False, "No file specified.", []

        clean_path = Path(file_path_or_name.strip('"\''))
        # 1. Direct absolute path check
        if clean_path.is_absolute() and clean_path.exists() and clean_path.is_file():
            try:
                os.startfile(str(clean_path))
                return True, f"Opened file {clean_path.name}.", []
            except Exception as e:
                logger.error(f"[Windows] Failed to open direct file {clean_path}: {e}")
                return False, f"Could not open file: {e}", []

        # 2. Search common user directories
        home = Path.home()
        search_dirs = [
            home / "Downloads",
            home / "Documents",
            home / "OneDrive" / "Documents",
            home / "Desktop",
            home / "OneDrive" / "Desktop",
            home / "Pictures",
            home / "Music",
            home / "Videos"
        ]
        target_name = clean_path.name.lower()
        matches = []

        for sdir in search_dirs:
            if sdir.exists():
                try:
                    for f in sdir.iterdir():
                        if f.is_file():
                            if f.name.lower() == target_name or (not clean_path.suffix and f.stem.lower() == target_name):
                                matches.append(f)
                except Exception:
                    pass

        if len(matches) == 1:
            try:
                os.startfile(str(matches[0]))
                return True, f"Opened {matches[0].name}.", []
            except Exception as e:
                return False, f"Could not open file: {e}", []
        elif len(matches) > 1:
            match_paths = [str(m) for m in matches[:5]]
            return False, f"I found multiple files matching '{file_path_or_name}'. Which one should I open?", match_paths
        else:
            return False, f"I couldn't find a file matching '{file_path_or_name}'.", []

    # ==========================================
    # FOLDER CONTROL
    # ==========================================
    def get_folder_path(self, folder_name: str) -> Path:
        name = folder_name.lower().strip()
        home = Path.home()
        if "download" in name:
            return home / "Downloads"
        elif "document" in name:
            onedrive = home / "OneDrive" / "Documents"
            return onedrive if onedrive.exists() else home / "Documents"
        elif "desktop" in name:
            onedrive = home / "OneDrive" / "Desktop"
            return onedrive if onedrive.exists() else home / "Desktop"
        elif "picture" in name:
            onedrive = home / "OneDrive" / "Pictures"
            return onedrive if onedrive.exists() else home / "Pictures"
        elif "video" in name:
            return home / "Videos"
        elif "music" in name:
            return home / "Music"
        return home

    def open_folder(self, folder_name: str) -> bool:
        path = self.get_folder_path(folder_name)
        if not path.exists():
            probe = Path(folder_name)
            if probe.exists() and probe.is_dir():
                path = probe
            else:
                return False

        try:
            os.startfile(str(path))
            return True
        except Exception as e:
            logger.error(f"[Windows] Failed to open folder {path}: {e}")
            return False

    # ==========================================
    # URL & BROWSER SYSTEM
    # ==========================================
    def open_url(self, url: str) -> bool:
        try:
            os.startfile(url)
            return True
        except Exception:
            try:
                webbrowser.open(url)
                return True
            except Exception as e:
                logger.error(f"[Windows] Failed to open URL '{url}': {e}")
                return False

    def _probe_browser_executable(self, browser_name: str) -> Optional[str]:
        b = browser_name.lower().strip()
        probes = {
            "chrome": ["chrome.exe", "google-chrome"],
            "chromium": ["chromium.exe", "chromium"],
            "edge": ["msedge.exe", "edge.exe"],
            "firefox": ["firefox.exe", "firefox"]
        }
        candidates = probes.get(b, [f"{b}.exe", b])
        for c in candidates:
            found = shutil.which(c)
            if found:
                return found

        # Probe standard Windows installation paths
        pf = os.environ.get("ProgramFiles", "C:\\Program Files")
        pfx86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        local_app = os.environ.get("LOCALAPPDATA", "")

        path_checks = {
            "chrome": [
                Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(pfx86) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(local_app) / "Google" / "Chrome" / "Application" / "chrome.exe"
            ],
            "edge": [
                Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(pfx86) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            ],
            "firefox": [
                Path(pf) / "Mozilla Firefox" / "firefox.exe",
                Path(pfx86) / "Mozilla Firefox" / "firefox.exe"
            ],
            "chromium": [
                Path(local_app) / "Chromium" / "Application" / "chrome.exe"
            ]
        }

        for path in path_checks.get(b, []):
            if path.exists():
                return str(path)

        return None

    def get_available_browsers(self) -> list:
        browsers = []
        for b in ["chrome", "chromium", "edge", "firefox"]:
            if self._probe_browser_executable(b):
                browsers.append(b)
        if not browsers:
            browsers.append("default")
        return browsers

    def get_default_browser(self) -> str:
        avail = self.get_available_browsers()
        if "chrome" in avail:
            return "chrome"
        if "edge" in avail:
            return "edge"
        return avail[0] if avail else "default"

    def open_browser(self, browser_name: str = "default", url: str = None) -> bool:
        b_key = browser_name.lower().strip()
        if b_key in ["default", "system"]:
            return self.open_url(url) if url else self.open_url("https://www.google.com")

        exec_path = self._probe_browser_executable(b_key)
        if exec_path:
            cmd = [exec_path]
            if url:
                cmd.append(url)
            try:
                subprocess.Popen(cmd)
                return True
            except Exception as e:
                logger.error(f"[Windows] Failed to open browser '{browser_name}': {e}")
                return False

        return self.open_url(url) if url else True

    def open_new_browser_tab(self, browser_name: str = "chrome", url: str = None) -> bool:
        """Opens a new tab in the running browser session without disturbing existing tabs/windows."""
        b_key = browser_name.lower().strip()
        exec_path = self._probe_browser_executable(b_key)
        target_url = url or "chrome://newtab"

        if self.is_application_running(b_key) and exec_path:
            try:
                subprocess.Popen([exec_path, target_url])
                logger.info(f"[Windows] Opened new tab in existing '{b_key}' session via CLI.")
                return True
            except Exception as e:
                logger.warning(f"[Windows] Failed to open new tab via subprocess ({e}). Trying fallback.")

        try:
            return webbrowser.open_new_tab(target_url if target_url != "chrome://newtab" else "https://www.google.com")
        except Exception as e:
            logger.error(f"[Windows] Fallback open_new_tab failed: {e}")
            return self.open_browser(browser_name, url=url)

    def open_new_browser_window(self, browser_name: str = "chrome", url: str = None) -> bool:
        """Opens a brand new, independent browser window preserving all existing windows and tabs."""
        b_key = browser_name.lower().strip()
        exec_path = self._probe_browser_executable(b_key)

        if exec_path:
            cmd = [exec_path, "--new-window"]
            if url:
                cmd.append(url)
            try:
                subprocess.Popen(cmd)
                logger.info(f"[Windows] Opened new independent window for '{b_key}' with command {cmd}.")
                return True
            except Exception as e:
                logger.error(f"[Windows] Failed to launch new window via --new-window flag: {e}")

        try:
            return webbrowser.open_new(url or "https://www.google.com")
        except Exception as e:
            logger.error(f"[Windows] Fallback open_new window failed: {e}")
            return False

    # ==========================================
    # SYSTEM CONTROL (Pycaw + Win32 Power)
    # ==========================================
    def _get_volume_interface(self):
        try:
            from comtypes import CLSCTX_ALL, CoInitialize
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return interface.QueryInterface(IAudioEndpointVolume)
        except Exception as e:
            logger.error(f"[Windows] Pycaw volume interface failed: {e}")
            return None

    def volume_up(self, step: float = 0.10) -> Tuple[bool, str]:
        vol_ctrl = self._get_volume_interface()
        if not vol_ctrl:
            return False, "Could not access audio hardware interface."
        try:
            current_val = vol_ctrl.GetMasterVolumeLevelScalar()
            new_val = min(1.0, current_val + step)
            vol_ctrl.SetMasterVolumeLevelScalar(new_val, None)
            if vol_ctrl.GetMute():
                vol_ctrl.SetMute(0, None)
            percent = int(new_val * 100)
            return True, f"Volume increased to {percent}%"
        except Exception as e:
            logger.error(f"[Windows] Volume up failed: {e}")
            return False, f"Failed to adjust volume: {e}"

    def volume_down(self, step: float = 0.10) -> Tuple[bool, str]:
        vol_ctrl = self._get_volume_interface()
        if not vol_ctrl:
            return False, "Could not access audio hardware interface."
        try:
            current_val = vol_ctrl.GetMasterVolumeLevelScalar()
            new_val = max(0.0, current_val - step)
            vol_ctrl.SetMasterVolumeLevelScalar(new_val, None)
            percent = int(new_val * 100)
            return True, f"Volume decreased to {percent}%"
        except Exception as e:
            logger.error(f"[Windows] Volume down failed: {e}")
            return False, f"Failed to adjust volume: {e}"

    def mute_volume(self) -> Tuple[bool, str]:
        vol_ctrl = self._get_volume_interface()
        if not vol_ctrl:
            return False, "Could not access audio hardware interface."
        try:
            vol_ctrl.SetMute(1, None)
            return True, "Volume muted successfully."
        except Exception as e:
            logger.error(f"[Windows] Mute failed: {e}")
            return False, f"Failed to mute: {e}"

    def unmute_volume(self) -> Tuple[bool, str]:
        vol_ctrl = self._get_volume_interface()
        if not vol_ctrl:
            return False, "Could not access audio hardware interface."
        try:
            vol_ctrl.SetMute(0, None)
            current_val = vol_ctrl.GetMasterVolumeLevelScalar()
            percent = int(current_val * 100)
            return True, f"Volume unmuted. Current volume is {percent}%"
        except Exception as e:
            logger.error(f"[Windows] Unmute failed: {e}")
            return False, f"Failed to unmute: {e}"

    def lock_pc(self) -> Tuple[bool, str]:
        try:
            ctypes.windll.user32.LockWorkStation()
            return True, "Computer locked successfully."
        except Exception as e:
            logger.error(f"[Windows] Lock Workstation failed: {e}")
            return False, f"Failed to lock workstation: {e}"

    def sleep_pc(self) -> Tuple[bool, str]:
        try:
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return True, "Putting computer to sleep."
        except Exception as e:
            logger.error(f"[Windows] Sleep command failed: {e}")
            return False, f"Failed to put computer to sleep: {e}"

    def restart_pc(self) -> Tuple[bool, str]:
        try:
            subprocess.Popen(["shutdown.exe", "/r", "/t", "0"])
            return True, "Restarting computer immediately."
        except Exception as e:
            logger.error(f"[Windows] Restart command failed: {e}")
            return False, f"Failed to initiate restart: {e}"

    def shutdown_pc(self) -> Tuple[bool, str]:
        try:
            subprocess.Popen(["shutdown.exe", "/s", "/t", "0"])
            return True, "Shutting down computer immediately."
        except Exception as e:
            logger.error(f"[Windows] Shutdown command failed: {e}")
            return False, f"Failed to initiate shutdown: {e}"

    def hibernate_pc(self) -> Tuple[bool, str]:
        try:
            subprocess.Popen(["shutdown.exe", "/h"])
            return True, "Putting computer into hibernation."
        except Exception as e:
            logger.error(f"[Windows] Hibernate command failed: {e}")
            return False, f"Failed to hibernate computer: {e}"

    def get_battery_status(self) -> Tuple[bool, str]:
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return True, "No battery detected (plugged in to AC source)."
            percent = battery.percent
            plugged = battery.power_plugged
            status = "plugged in" if plugged else "discharging"
            msg = f"Battery status: {percent}% charged, currently {status}."
            if not plugged and battery.secsleft != psutil.POWER_TIME_UNLIMITED:
                hours = battery.secsleft // 3600
                mins = (battery.secsleft % 3600) // 60
                msg += f" Estimated remaining time: {hours} hours and {mins} minutes."
            return True, msg
        except Exception as e:
            logger.error(f"[Windows] Battery status query failed: {e}")
            return False, f"Could not retrieve battery details: {e}"

    def get_system_metrics(self) -> Tuple[bool, Dict[str, Any]]:
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            total, used, free = shutil.disk_usage("C:\\")
            disk = (used / total) * 100
            metrics = {
                "cpu": cpu,
                "ram": ram,
                "disk": disk,
                "message": f"System Usage - CPU: {cpu:.1f}%, RAM: {ram:.1f}%, Disk C: {disk:.1f}% used."
            }
            return True, metrics
        except Exception as e:
            logger.error(f"[Windows] Failed to query system metrics: {e}")
            return False, {"message": f"Failed to retrieve system metrics: {e}"}
