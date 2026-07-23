import os
import ctypes
import logging
import subprocess
import shutil
import psutil
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

logger = logging.getLogger("Jarvis.SystemControl")

def get_volume_interface():
    """Gets the Pycaw endpoint volume interface."""
    try:
        # Initialize COM libraries in case we are on a different thread
        ctypes.CoInitialize()
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        return volume
    except Exception as e:
        logger.error(f"Pycaw volume interface activation failed: {e}")
        return None

# ==========================================
# VOLUME CONTROL
# ==========================================

def volume_up(step: float = 0.10) -> (bool, str):
    """Increases master volume level."""
    vol_ctrl = get_volume_interface()
    if not vol_ctrl:
        return False, "Could not access audio hardware interface."
    try:
        current_val = vol_ctrl.GetMasterVolumeLevelScalar()
        new_val = min(1.0, current_val + step)
        vol_ctrl.SetMasterVolumeLevelScalar(new_val, None)
        # Unmute if muted
        if vol_ctrl.GetMute():
            vol_ctrl.SetMute(0, None)
        percent = int(new_val * 100)
        return True, f"Volume increased to {percent}%"
    except Exception as e:
        logger.error(f"Volume up failed: {e}")
        return False, f"Failed to adjust volume: {e}"

def volume_down(step: float = 0.10) -> (bool, str):
    """Decreases master volume level."""
    vol_ctrl = get_volume_interface()
    if not vol_ctrl:
        return False, "Could not access audio hardware interface."
    try:
        current_val = vol_ctrl.GetMasterVolumeLevelScalar()
        new_val = max(0.0, current_val - step)
        vol_ctrl.SetMasterVolumeLevelScalar(new_val, None)
        percent = int(new_val * 100)
        return True, f"Volume decreased to {percent}%"
    except Exception as e:
        logger.error(f"Volume down failed: {e}")
        return False, f"Failed to adjust volume: {e}"

def mute_volume() -> (bool, str):
    """Mutes the master volume."""
    vol_ctrl = get_volume_interface()
    if not vol_ctrl:
        return False, "Could not access audio hardware interface."
    try:
        vol_ctrl.SetMute(1, None)
        return True, "Volume muted successfully."
    except Exception as e:
        logger.error(f"Mute failed: {e}")
        return False, f"Failed to mute: {e}"

def unmute_volume() -> (bool, str):
    """Unmutes the master volume."""
    vol_ctrl = get_volume_interface()
    if not vol_ctrl:
        return False, "Could not access audio hardware interface."
    try:
        vol_ctrl.SetMute(0, None)
        current_val = vol_ctrl.GetMasterVolumeLevelScalar()
        percent = int(current_val * 100)
        return True, f"Volume unmuted. Current volume is {percent}%"
    except Exception as e:
        logger.error(f"Unmute failed: {e}")
        return False, f"Failed to unmute: {e}"

# ==========================================
# POWER & OS STATE CONTROL
# ==========================================

def lock_pc() -> (bool, str):
    """Instantly locks the Windows workstation."""
    logger.info("Executing Lock PC command.")
    try:
        ctypes.windll.user32.LockWorkStation()
        return True, "Computer locked successfully."
    except Exception as e:
        logger.error(f"Lock Workstation failed: {e}")
        return False, f"Failed to lock workstation: {e}"

def sleep_pc() -> (bool, str):
    """Suspends the Windows workstation (puts it to sleep)."""
    logger.info("Executing Sleep PC command.")
    try:
        # Invoke SetSuspendState(0, 1, 0)
        # arg1: hibernate (0 = sleep, 1 = hibernate)
        # arg2: forcecritical (1 = force suspend)
        # arg3: disablewakeevents (0 = allow wake events)
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return True, "Putting computer to sleep."
    except Exception as e:
        logger.error(f"Sleep command failed: {e}")
        return False, f"Failed to put computer to sleep: {e}"

def restart_pc() -> (bool, str):
    """Initiates Windows reboot procedure."""
    logger.info("Executing Restart PC command.")
    try:
        subprocess.Popen(["shutdown.exe", "/r", "/t", "0"])
        return True, "Restarting computer immediately."
    except Exception as e:
        logger.error(f"Restart command failed: {e}")
        return False, f"Failed to initiate restart: {e}"

def shutdown_pc() -> (bool, str):
    """Initiates Windows system shutdown procedure."""
    logger.info("Executing Shutdown PC command.")
    try:
        subprocess.Popen(["shutdown.exe", "/s", "/t", "0"])
        return True, "Shutting down computer immediately."
    except Exception as e:
        logger.error(f"Shutdown command failed: {e}")
        return False, f"Failed to initiate shutdown: {e}"

# ==========================================
# TELEMETRY & RESOURCES
# ==========================================

def get_battery_status() -> (bool, str):
    """Retrieves battery state parameters."""
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
        logger.error(f"Failed to query battery status: {e}")
        return False, f"Could not retrieve battery details: {e}"

def get_system_metrics() -> (bool, dict):
    """Retrieves current CPU, RAM, and Disk metrics."""
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
        logger.error(f"Failed to query system metrics: {e}")
        return False, {"message": f"Failed to retrieve system metrics: {e}"}
