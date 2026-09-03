import logging
from typing import Tuple, Dict, Any
from core.platform.platform_manager import platform_manager

logger = logging.getLogger("Jarvis.SystemControl")

def get_volume_interface():
    """Returns Pycaw volume interface if available/mocked."""
    if hasattr(platform_manager.platform, "_get_volume_interface"):
        return platform_manager.platform._get_volume_interface()
    return None

def volume_up(step: float = 0.10) -> Tuple[bool, str]:
    vol_ctrl = get_volume_interface()
    if vol_ctrl is not None:
        try:
            current_val = vol_ctrl.GetMasterVolumeLevelScalar()
            new_val = min(1.0, current_val + step)
            vol_ctrl.SetMasterVolumeLevelScalar(new_val, None)
            if vol_ctrl.GetMute():
                vol_ctrl.SetMute(0, None)
            percent = int(new_val * 100)
            return True, f"Volume increased to {percent}%"
        except Exception as e:
            return False, f"Failed to adjust volume: {e}"
    return platform_manager.volume_up(step)

def volume_down(step: float = 0.10) -> Tuple[bool, str]:
    vol_ctrl = get_volume_interface()
    if vol_ctrl is not None:
        try:
            current_val = vol_ctrl.GetMasterVolumeLevelScalar()
            new_val = max(0.0, current_val - step)
            vol_ctrl.SetMasterVolumeLevelScalar(new_val, None)
            percent = int(new_val * 100)
            return True, f"Volume decreased to {percent}%"
        except Exception as e:
            return False, f"Failed to adjust volume: {e}"
    return platform_manager.volume_down(step)

def mute_volume() -> Tuple[bool, str]:
    vol_ctrl = get_volume_interface()
    if vol_ctrl is not None:
        try:
            vol_ctrl.SetMute(1, None)
            return True, "Volume muted successfully."
        except Exception as e:
            return False, f"Failed to mute: {e}"
    return platform_manager.mute_volume()

def unmute_volume() -> Tuple[bool, str]:
    vol_ctrl = get_volume_interface()
    if vol_ctrl is not None:
        try:
            vol_ctrl.SetMute(0, None)
            current_val = vol_ctrl.GetMasterVolumeLevelScalar()
            percent = int(current_val * 100)
            return True, f"Volume unmuted. Current volume is {percent}%"
        except Exception as e:
            return False, f"Failed to unmute: {e}"
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
