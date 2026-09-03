import platform
import logging
from pathlib import Path
from typing import Tuple, Dict, Any, List

logger = logging.getLogger("Jarvis.BasePlatform")

class BasePlatform:
    """Abstract Base Class for Platform Abstraction Layer."""

    @property
    def os_name(self) -> str:
        return platform.system()

    @property
    def os_version(self) -> str:
        return platform.version() or platform.release()

    @property
    def architecture(self) -> str:
        return platform.machine() or platform.architecture()[0]

    def is_windows(self) -> bool:
        return self.os_name.lower() == "windows"

    def is_linux(self) -> bool:
        return self.os_name.lower() == "linux"

    # ==========================================
    # APPLICATION CONTROL INTERFACE
    # ==========================================
    def open_application(self, app_key: str) -> bool:
        raise NotImplementedError

    def close_application(self, app_key: str) -> bool:
        raise NotImplementedError

    def is_application_running(self, app_key: str) -> bool:
        raise NotImplementedError

    def focus_application(self, app_key: str) -> bool:
        raise NotImplementedError

    # ==========================================
    # FOLDER CONTROL INTERFACE
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
        raise NotImplementedError

    # ==========================================
    # URL & BROWSER INTERFACE
    # ==========================================
    def open_url(self, url: str) -> bool:
        raise NotImplementedError

    def get_available_browsers(self) -> List[str]:
        return ["default"]

    def get_default_browser(self) -> str:
        return "default"

    def is_browser_available(self, browser_name: str) -> bool:
        b_clean = browser_name.lower().strip()
        if b_clean in ["default", "system"]:
            return True
        return b_clean in [b.lower() for b in self.get_available_browsers()]

    def open_browser(self, browser_name: str = "default", url: str = None) -> bool:
        raise NotImplementedError

    # ==========================================
    # SYSTEM CONTROL INTERFACE
    # ==========================================
    def volume_up(self, step: float = 0.10) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def volume_down(self, step: float = 0.10) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def mute_volume(self) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def unmute_volume(self) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def lock_pc(self) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def sleep_pc(self) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def restart_pc(self) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def shutdown_pc(self) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def get_battery_status(self) -> Tuple[bool, str]:
        return False, "This operation is not supported on the current system."

    def get_system_metrics(self) -> Tuple[bool, Dict[str, Any]]:
        return False, {"message": "This operation is not supported on the current system."}
