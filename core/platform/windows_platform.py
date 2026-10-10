import os
import json
import ctypes
import shutil
import logging
import subprocess
import webbrowser
import psutil
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

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
        name = raw_name.lower().strip()
        # Direct match in registry keys
        if name in self.app_registry:
            return name
        # Search in aliases
        for app_key, data in self.app_registry.items():
            aliases = data.get("aliases", [])
            if name in [a.lower() for a in aliases]:
                return app_key
        return name

    def _probe_windows_app_path(self, app_name: str) -> Optional[str]:
        """Probes Windows Registry App Paths for registered applications."""
        try:
            import winreg
            candidates = [app_name]
            if not app_name.endswith(".exe"):
                candidates.append(f"{app_name}.exe")

            for name in candidates:
                for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    for sub in (
                        fr"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}",
                        fr"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{name}"
                    ):
                        try:
                            with winreg.OpenKey(root, sub) as key:
                                val, _ = winreg.QueryValueEx(key, "")
                                if val:
                                    clean_p = val.strip('\"')
                                    if Path(clean_p).exists():
                                        return clean_p
                        except OSError:
                            pass
        except Exception as e:
            logger.debug(f"Failed to query registry App Paths for '{app_name}': {e}")
        return None

    def _probe_application_executable(self, app_key: str) -> Optional[str]:
        """Resolves installed absolute executable path using multiple Windows discovery methods."""
        key = self.resolve_app_key(app_key)

        # 1. Probing browsers via built-in browser discovery
        if key in ["chrome", "edge", "firefox", "chromium", "browser"]:
            b_target = "chrome" if key == "browser" else key
            probed_b = self._probe_browser_executable(b_target)
            if probed_b:
                return probed_b

        # 2. Check Windows Registry App Paths (e.g. chrome.exe, msedge.exe)
        reg_path = self._probe_windows_app_path(key)
        if reg_path:
            return reg_path

        # 3. Check system PATH via shutil.which
        which_path = shutil.which(key) or shutil.which(f"{key}.exe")
        if which_path:
            return which_path

        # 4. Probing known application paths on Windows
        local_app = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", "C:\\Program Files")
        pfx86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        app_data = os.environ.get("APPDATA", "")

        known_paths = {
            "vscode": [
                Path(local_app) / "Programs" / "Microsoft VS Code" / "Code.exe",
                Path(pf) / "Microsoft VS Code" / "Code.exe",
                Path(pfx86) / "Microsoft VS Code" / "Code.exe"
            ],
            "spotify": [
                Path(app_data) / "Spotify" / "Spotify.exe",
                Path(local_app) / "Microsoft" / "WindowsApps" / "spotify.exe"
            ],
            "discord": [
                Path(local_app) / "Discord" / "Update.exe"
            ]
        }
        for p in known_paths.get(key, []):
            if p.exists():
                return str(p)

        return None

    def resolve_executable(self, app_key: str) -> str:
        key = self.resolve_app_key(app_key)

        # Check probed absolute executable first
        probed = self._probe_application_executable(key)
        if probed:
            return probed

        reg_entry = self.app_registry.get(key, {})
        win_exec = reg_entry.get("windows")
        if win_exec:
            probed_win = self._probe_application_executable(win_exec)
            if probed_win:
                return probed_win
            if not win_exec.endswith(".exe") and win_exec not in ["calc", "notepad", "explorer"]:
                win_exec += ".exe"
            return win_exec

        # Probing fallback
        if key == "notepad":
            return "notepad.exe"
        elif key == "calculator":
            return "calc.exe"
        elif key == "explorer":
            return "explorer.exe"
        elif key == "chrome":
            return "chrome.exe"
        elif key in ["vscode", "vs code"]:
            return "code.exe"

        return f"{key}.exe"

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
        try:
            if os.path.isabs(exec_path) and os.path.exists(exec_path):
                subprocess.Popen([exec_path])
                return True

            which_p = shutil.which(exec_path) or shutil.which(f"{exec_path}.exe")
            if which_p and os.path.exists(which_p):
                subprocess.Popen([which_p])
                return True

            if key in ["chrome", "edge", "firefox", "chromium", "browser"]:
                if self.open_browser(key):
                    return True

            try:
                os.startfile(exec_path)
                return True
            except Exception:
                pass

            subprocess.Popen(exec_path if os.path.isabs(exec_path) else [exec_path], shell=True if not os.path.isabs(exec_path) else False)
            return True
        except Exception as e:
            logger.error(f"[Windows] Failed to launch application '{key}': {e}", exc_info=True)
            return False

    def close_application(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        if key == "explorer":
            logger.warning("[Windows] Attempted to close File Explorer. Blocked for safety.")
            return False

        exec_name = self.resolve_executable(key).lower()
        base_name = Path(exec_name).name.lower()
        target_names = [exec_name, base_name]
        if not base_name.endswith(".exe"):
            target_names.append(f"{base_name}.exe")
        if key == "calculator":
            target_names.extend(["calc.exe", "calculator.exe", "calculatorapp.exe"])

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

        exec_name = self.resolve_executable(key).lower()
        base_name = Path(exec_name).name.lower()
        target_names = [exec_name, base_name]
        if not base_name.endswith(".exe"):
            target_names.append(f"{base_name}.exe")
        if key == "calculator":
            target_names.extend(["calc.exe", "calculator.exe", "calculatorapp.exe"])

        for proc in psutil.process_iter(['name']):
            try:
                name = proc.info['name']
                if name and name.lower() in target_names:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def _force_foreground_window(self, hwnd: int) -> bool:
        """Forces window to foreground bypassing Windows LockSetForegroundWindow."""
        try:
            user32 = ctypes.windll.user32
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            else:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW

            user32.keybd_event(0x12, 0, 0, 0)  # ALT down
            user32.keybd_event(0x12, 0, 2, 0)  # ALT up
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            return True
        except Exception as e:
            logger.debug(f"[Windows] Force foreground failed for hwnd {hwnd}: {e}")
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
                "steam": "Steam"
            }
            keyword = window_keywords.get(key, key)
            windows = gw.getWindowsWithTitle("")
            for win in windows:
                if win.title and keyword.lower() in win.title.lower():
                    try:
                        if win.isMinimized:
                            win.restore()
                        win.activate()
                    except Exception:
                        if hasattr(win, "_hWnd"):
                            self._force_foreground_window(win._hWnd)
                    logger.info(f"[Windows] Focused window: '{win.title}'")
                    return True
        except Exception as e:
            logger.debug(f"[Windows] Could not focus application window for '{key}': {e}")
        return False

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
