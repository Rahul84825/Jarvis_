import os
import json
import shutil
import logging
import subprocess
import webbrowser
import psutil
from pathlib import Path
from typing import Tuple, Dict, Any

from core.platform.base_platform import BasePlatform

logger = logging.getLogger("Jarvis.LinuxPlatform")

class LinuxPlatform(BasePlatform):
    """Linux Platform Implementation."""

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
        if name in self.app_registry:
            return name
        for app_key, data in self.app_registry.items():
            aliases = data.get("aliases", [])
            if name in [a.lower() for a in aliases]:
                return app_key
        return name

    def resolve_executable(self, app_key: str) -> str:
        key = self.resolve_app_key(app_key)
        reg_entry = self.app_registry.get(key, {})
        linux_exec = reg_entry.get("linux")
        if linux_exec:
            found = shutil.which(linux_exec)
            if found:
                return found
            return linux_exec

        # Common Linux fallbacks
        probes = {
            "chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
            "vscode": ["code", "vscodium"],
            "notepad": ["gedit", "kate", "kwrite", "mousepad", "xed", "nano"],
            "calculator": ["gnome-calculator", "kcalc", "galculator"],
            "explorer": ["nautilus", "dolphin", "thunar", "nemo"]
        }
        if key in probes:
            for p in probes[key]:
                found = shutil.which(p)
                if found:
                    return found

        return key

    # ==========================================
    # APPLICATION CONTROL
    # ==========================================
    def open_application(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        if self.is_application_running(key) and key not in ["explorer", "notepad", "calculator"]:
            if self.focus_application(key):
                return True

        exec_cmd = self.resolve_executable(key)
        logger.info(f"[Linux] Launching application '{key}' via command: {exec_cmd}")
        try:
            subprocess.Popen([exec_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            logger.error(f"[Linux] Failed to launch application '{key}': {e}")
            return False

    def close_application(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        if key in ["explorer", "nautilus", "dolphin", "thunar", "nemo"]:
            logger.warning("[Linux] Attempted to close File Manager. Blocked for safety.")
            return False

        exec_name = self.resolve_executable(key)
        cmd_name = Path(exec_name).name
        target_names = [cmd_name.lower(), key.lower()]

        terminated = False
        for proc in psutil.process_iter(['name', 'pid', 'cmdline']):
            try:
                name = proc.info['name'] or ""
                cmdline = " ".join(proc.info['cmdline'] or []).lower()
                if any(t in name.lower() or t in cmdline for t in target_names):
                    logger.info(f"[Linux] Terminating process {name} (PID: {proc.info['pid']})")
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

        if not terminated:
            try:
                res = subprocess.run(["pkill", "-f", cmd_name], capture_output=True)
                if res.returncode == 0:
                    terminated = True
            except Exception:
                pass

        return terminated

    def is_application_running(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        exec_name = self.resolve_executable(key)
        cmd_name = Path(exec_name).name
        target_names = [cmd_name.lower(), key.lower()]

        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                name = proc.info['name'] or ""
                cmdline = " ".join(proc.info['cmdline'] or []).lower()
                if any(t in name.lower() or t in cmdline for t in target_names):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def focus_application(self, app_key: str) -> bool:
        key = self.resolve_app_key(app_key)
        # Probe for wmctrl or xdotool on X11 / Wayland compatibility layer
        wmctrl = shutil.which("wmctrl")
        if wmctrl:
            try:
                res = subprocess.run([wmctrl, "-a", key], capture_output=True)
                if res.returncode == 0:
                    logger.info(f"[Linux] Focused window for '{key}' via wmctrl.")
                    return True
            except Exception:
                pass
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
            return home / "Documents"
        elif "desktop" in name:
            return home / "Desktop"
        elif "picture" in name:
            return home / "Pictures"
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
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            logger.error(f"[Linux] Failed to open folder {path}: {e}")
            return False

    # ==========================================
    # URL SYSTEM
    # ==========================================
    def open_url(self, url: str) -> bool:
        xdg = shutil.which("xdg-open")
        if xdg:
            try:
                subprocess.Popen([xdg, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass
        try:
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error(f"[Linux] Failed to open URL '{url}': {e}")
            return False

    def _probe_browser_executable(self, browser_name: str) -> Optional[str]:
        b = browser_name.lower().strip()
        probes = {
            "chrome": ["google-chrome", "google-chrome-stable"],
            "chromium": ["chromium-browser", "chromium"],
            "firefox": ["firefox"],
            "edge": ["microsoft-edge", "microsoft-edge-dev"]
        }
        candidates = probes.get(b, [b])
        for c in candidates:
            found = shutil.which(c)
            if found:
                return found
        return None

    def get_available_browsers(self) -> list:
        browsers = []
        for b in ["chrome", "chromium", "firefox", "edge"]:
            if self._probe_browser_executable(b):
                browsers.append(b)
        if not browsers:
            browsers.append("default")
        return browsers

    def get_default_browser(self) -> str:
        avail = self.get_available_browsers()
        if "chrome" in avail:
            return "chrome"
        if "chromium" in avail:
            return "chromium"
        if "firefox" in avail:
            return "firefox"
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
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception as e:
                logger.error(f"[Linux] Failed to open browser '{browser_name}': {e}")
                return False

        return self.open_url(url) if url else True

    # ==========================================
    # SYSTEM CONTROL (PulseAudio / PipeWire / systemctl)
    # ==========================================
    def _run_audio_cmd(self, pactl_args: list, amixer_args: list) -> bool:
        pactl = shutil.which("pactl")
        if pactl:
            try:
                res = subprocess.run([pactl] + pactl_args, capture_output=True)
                if res.returncode == 0:
                    return True
            except Exception as e:
                logger.debug(f"[Linux] pactl call failed: {e}")

        amixer = shutil.which("amixer")
        if amixer:
            try:
                res = subprocess.run([amixer] + amixer_args, capture_output=True)
                if res.returncode == 0:
                    return True
            except Exception as e:
                logger.debug(f"[Linux] amixer call failed: {e}")
        return False

    def volume_up(self, step: float = 0.10) -> Tuple[bool, str]:
        pct = int(step * 100)
        success = self._run_audio_cmd(
            ["set-sink-volume", "@DEFAULT_SINK@", f"+{pct}%"],
            ["-D", "pulse", "set", "Master", f"{pct}%+"]
        )
        if success:
            return True, "Volume increased."
        return False, "This operation is not supported on the current system."

    def volume_down(self, step: float = 0.10) -> Tuple[bool, str]:
        pct = int(step * 100)
        success = self._run_audio_cmd(
            ["set-sink-volume", "@DEFAULT_SINK@", f"-{pct}%"],
            ["-D", "pulse", "set", "Master", f"{pct}%-"]
        )
        if success:
            return True, "Volume decreased."
        return False, "This operation is not supported on the current system."

    def mute_volume(self) -> Tuple[bool, str]:
        success = self._run_audio_cmd(
            ["set-sink-mute", "@DEFAULT_SINK@", "1"],
            ["-D", "pulse", "set", "Master", "mute"]
        )
        if success:
            return True, "Volume muted successfully."
        return False, "This operation is not supported on the current system."

    def unmute_volume(self) -> Tuple[bool, str]:
        success = self._run_audio_cmd(
            ["set-sink-mute", "@DEFAULT_SINK@", "0"],
            ["-D", "pulse", "set", "Master", "unmute"]
        )
        if success:
            return True, "Volume unmuted."
        return False, "This operation is not supported on the current system."

    def lock_pc(self) -> Tuple[bool, str]:
        lock_cmds = [
            ["loginctl", "lock-session"],
            ["gnome-screensaver-command", "-l"],
            ["xdg-screensaver", "lock"],
            ["i3lock"]
        ]
        for cmd in lock_cmds:
            if shutil.which(cmd[0]):
                try:
                    res = subprocess.run(cmd, capture_output=True)
                    if res.returncode == 0:
                        return True, "Computer locked successfully."
                except Exception:
                    pass
        return False, "This operation is not supported on the current system."

    def sleep_pc(self) -> Tuple[bool, str]:
        if shutil.which("systemctl"):
            try:
                res = subprocess.run(["systemctl", "suspend"], capture_output=True)
                if res.returncode == 0:
                    return True, "Putting computer to sleep."
            except Exception:
                pass
        return False, "This operation is not supported on the current system."

    def restart_pc(self) -> Tuple[bool, str]:
        if shutil.which("systemctl"):
            try:
                subprocess.Popen(["systemctl", "reboot"])
                return True, "Restarting computer immediately."
            except Exception:
                pass
        return False, "This operation is not supported on the current system."

    def shutdown_pc(self) -> Tuple[bool, str]:
        if shutil.which("systemctl"):
            try:
                subprocess.Popen(["systemctl", "poweroff"])
                return True, "Shutting down computer immediately."
            except Exception:
                pass
        return False, "This operation is not supported on the current system."

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
            logger.error(f"[Linux] Battery query failed: {e}")
            return False, f"Could not retrieve battery details: {e}"

    def get_system_metrics(self) -> Tuple[bool, Dict[str, Any]]:
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            total, used, free = shutil.disk_usage("/")
            disk = (used / total) * 100
            metrics = {
                "cpu": cpu,
                "ram": ram,
                "disk": disk,
                "message": f"System Usage - CPU: {cpu:.1f}%, RAM: {ram:.1f}%, Disk /: {disk:.1f}% used."
            }
            return True, metrics
        except Exception as e:
            logger.error(f"[Linux] Failed to query system metrics: {e}")
            return False, {"message": f"Failed to retrieve system metrics: {e}"}
