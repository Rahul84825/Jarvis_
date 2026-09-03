import platform
import logging
from typing import Tuple, Dict, Any
from pathlib import Path

from core.platform.base_platform import BasePlatform
from core.platform.windows_platform import WindowsPlatform
from core.platform.linux_platform import LinuxPlatform

logger = logging.getLogger("Jarvis.PlatformManager")

class PlatformManager:
    """Singleton Platform Manager to detect OS and route calls to platform implementation."""

    def __init__(self):
        self._current_os = platform.system()
        self._platform: BasePlatform = self._create_platform_instance()
        logger.info(f"Platform Manager initialized for OS: {self.os_name} ({self.os_version}, {self.architecture})")

    def _create_platform_instance(self) -> BasePlatform:
        sys_name = self._current_os.lower()
        if sys_name == "windows":
            return WindowsPlatform()
        elif sys_name == "linux":
            return LinuxPlatform()
        else:
            logger.warning(f"Unsupported platform: {self._current_os}. Instantiating BasePlatform fallback.")
            return BasePlatform()

    @property
    def platform(self) -> BasePlatform:
        return self._platform

    @property
    def os_name(self) -> str:
        return self._platform.os_name

    @property
    def os_version(self) -> str:
        return self._platform.os_version

    @property
    def architecture(self) -> str:
        return self._platform.architecture

    def is_windows(self) -> bool:
        return self._platform.is_windows()

    def is_linux(self) -> bool:
        return self._platform.is_linux()

    # ==========================================
    # DELEGATED PLATFORM INTERFACES
    # ==========================================
    def open_application(self, app_key: str) -> bool:
        return self._platform.open_application(app_key)

    def close_application(self, app_key: str) -> bool:
        return self._platform.close_application(app_key)

    def is_application_running(self, app_key: str) -> bool:
        return self._platform.is_application_running(app_key)

    def focus_application(self, app_key: str) -> bool:
        return self._platform.focus_application(app_key)

    def get_folder_path(self, folder_name: str) -> Path:
        return self._platform.get_folder_path(folder_name)

    def open_folder(self, folder_name: str) -> bool:
        return self._platform.open_folder(folder_name)

    def open_url(self, url: str) -> bool:
        return self._platform.open_url(url)

    def get_available_browsers(self) -> list:
        return self._platform.get_available_browsers()

    def get_default_browser(self) -> str:
        return self._platform.get_default_browser()

    def is_browser_available(self, browser_name: str) -> bool:
        return self._platform.is_browser_available(browser_name)

    def open_browser(self, browser_name: str = "default", url: str = None) -> bool:
        return self._platform.open_browser(browser_name, url=url)

    def volume_up(self, step: float = 0.10) -> Tuple[bool, str]:
        return self._platform.volume_up(step)

    def volume_down(self, step: float = 0.10) -> Tuple[bool, str]:
        return self._platform.volume_down(step)

    def mute_volume(self) -> Tuple[bool, str]:
        return self._platform.mute_volume()

    def unmute_volume(self) -> Tuple[bool, str]:
        return self._platform.unmute_volume()

    def lock_pc(self) -> Tuple[bool, str]:
        return self._platform.lock_pc()

    def sleep_pc(self) -> Tuple[bool, str]:
        return self._platform.sleep_pc()

    def restart_pc(self) -> Tuple[bool, str]:
        return self._platform.restart_pc()

    def shutdown_pc(self) -> Tuple[bool, str]:
        return self._platform.shutdown_pc()

    def get_battery_status(self) -> Tuple[bool, str]:
        return self._platform.get_battery_status()

    def get_system_metrics(self) -> Tuple[bool, Dict[str, Any]]:
        return self._platform.get_system_metrics()

# Global platform_manager instance
platform_manager = PlatformManager()
