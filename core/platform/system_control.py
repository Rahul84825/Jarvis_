from typing import Tuple, Dict, Any
from core.platform.platform_manager import platform_manager

def volume_up(step: float = 0.10) -> Tuple[bool, str]:
    return platform_manager.volume_up(step)

def volume_down(step: float = 0.10) -> Tuple[bool, str]:
    return platform_manager.volume_down(step)

def mute_volume() -> Tuple[bool, str]:
    return platform_manager.mute_volume()

def unmute_volume() -> Tuple[bool, str]:
    return platform_manager.unmute_volume()

def lock_pc() -> Tuple[bool, str]:
    return platform_manager.lock_pc()

def sleep_pc() -> Tuple[bool, str]:
    return platform_manager.sleep_pc()

def restart_pc() -> Tuple[bool, str]:
    return platform_manager.restart_pc()

def shutdown_pc() -> Tuple[bool, str]:
    return platform_manager.shutdown_pc()

def get_battery_status() -> Tuple[bool, str]:
    return platform_manager.get_battery_status()

def get_system_metrics() -> Tuple[bool, Dict[str, Any]]:
    return platform_manager.get_system_metrics()
