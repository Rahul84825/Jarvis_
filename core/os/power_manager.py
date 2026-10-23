"""Windows Power Scheme and Laptop Battery Telemetry Manager.
Handles Windows power plan discovery and switching via powercfg with read-back verification,
battery telemetry via Win32_Battery, and truthful reporting of Acer OEM Control Center features.
"""

import os
import re
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("Jarvis.PowerManager")


class AcerOEMAdapter:
    """Dedicated adapter for Acer ALG / OEM laptop hardware interfaces.
    Provides truthful boundary reporting for proprietary fan profiles and battery limits.
    """

    SUPPORTED_PROFILES = ["Performance", "Entertainment", "Quiet", "Power-saving"]

    def __init__(self):
        self.laptop_model = "Acer ALG Gaming (AELEN15G52) with NVIDIA RTX 3050"
        self.control_center_service = "CCDCHUService"

    def is_supported(self) -> bool:
        """Indicates whether direct programmatic control is supported via public Windows APIs."""
        # Hardware audit confirmed: Insyde DCHU package controls fans & battery threshold
        # via proprietary AcpiBridge.sys without public WMI methods or CLI binaries.
        return False

    def get_active_profile(self) -> Dict[str, Any]:
        """Queries the active Acer OEM fan/performance profile."""
        return {
            "profile": "Unknown / Unverified (OEM only)",
            "supported": False,
            "verified": False,
            "message": "Acer OEM performance profile cannot be read programmatically without proprietary ACPI driver calls."
        }

    def set_oem_profile(self, profile_name: str) -> Dict[str, Any]:
        """Attempts to set the Acer OEM performance profile (Performance, Entertainment, Quiet, Power-saving)."""
        clean = (profile_name or "").strip()
        matched_profile = None
        for p in self.SUPPORTED_PROFILES:
            if clean.lower() == p.lower() or p.lower() in clean.lower():
                matched_profile = p
                break

        if not matched_profile:
            return {
                "success": False,
                "supported": False,
                "verified": False,
                "message": f"'{profile_name}' is not a recognized Acer OEM profile. Supported profiles: {', '.join(self.SUPPORTED_PROFILES)}."
            }

        # Truthful report: Public Windows API does not support direct ACPI write
        return {
            "success": False,
            "supported": False,
            "verified": False,
            "profile": matched_profile,
            "message": (
                f"Direct switching to Acer OEM '{matched_profile}' profile is not supported via public Windows APIs on this Acer ALG laptop "
                "(requires proprietary AcpiBridge driver writes). You can switch profiles using the OEM Fn hotkey (Fn+1) "
                "or through the Acer Control Center application."
            ),
            "recommended_action": "launch_control_center"
        }

    def get_battery_threshold(self) -> Dict[str, Any]:
        """Queries the configured battery charging threshold."""
        return {
            "threshold": "Unknown / Unverified (OEM only)",
            "supported": False,
            "verified": False,
            "message": "Battery charging threshold cannot be read programmatically via standard Windows APIs."
        }

    def set_battery_threshold(self, threshold_pct: int = 80) -> Dict[str, Any]:
        """Attempts to set battery charging threshold limit (e.g. 80%)."""
        return {
            "success": False,
            "supported": False,
            "verified": False,
            "threshold": "Unchanged",
            "message": (
                f"Direct modification of the battery charging threshold to {threshold_pct}% is not supported via public Windows APIs on this Acer ALG laptop. "
                "The threshold remains unchanged. You can configure battery protection safely in the Acer Control Center application."
            ),
            "recommended_action": "launch_control_center"
        }

    def launch_control_center(self) -> Dict[str, Any]:
        """Launches the Acer Control Center application for manual adjustment."""
        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "ControlCenter" / "CClnk.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "ControlCenter" / "CClnk.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "ControlCenter" / "ControlCenter.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "ControlCenter" / "ControlCenter.exe",
        ]
        for c in candidates:
            if c.exists():
                try:
                    os.startfile(str(c))
                    return {
                        "success": True,
                        "message": "Launched Acer Control Center for manual performance/battery profile adjustment."
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"Failed to launch Control Center at {c}: {e}"
                    }
        return {
            "success": False,
            "message": "Acer Control Center application was not found at standard installation locations."
        }


class PowerManager:
    """Manages Windows power schemes, battery telemetry, and Acer OEM profile interfaces."""

    def __init__(self):
        self._cached_schemes: Optional[List[Dict[str, Any]]] = None
        self.acer_adapter = AcerOEMAdapter()

    def list_power_schemes(self) -> List[Dict[str, Any]]:
        """Queries Windows power schemes using powercfg /list."""
        schemes = []
        try:
            res = subprocess.run(
                ["powercfg", "/list"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False
            )
            for line in res.stdout.splitlines():
                # Format: Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *
                m = re.search(r"Power Scheme GUID:\s*([a-fA-F0-9\-]+)\s*\((.*?)\)(\s*\*?)", line)
                if m:
                    guid = m.group(1).strip()
                    name = m.group(2).strip()
                    is_active = bool(m.group(3) and "*" in m.group(3))
                    schemes.append({
                        "guid": guid,
                        "name": name,
                        "is_active": is_active
                    })
            self._cached_schemes = schemes
        except Exception as e:
            logger.error(f"Error querying Windows power schemes: {e}")
        return schemes

    def get_active_scheme(self) -> Optional[Dict[str, Any]]:
        """Returns the currently active Windows power scheme."""
        schemes = self.list_power_schemes()
        for s in schemes:
            if s["is_active"]:
                return s
        return schemes[0] if schemes else None

    def set_power_scheme(self, name_or_guid: str) -> Dict[str, Any]:
        """Sets the active Windows power scheme by name or GUID with read-back verification."""
        schemes = self.list_power_schemes()
        target_guid = None
        target_name = name_or_guid

        for s in schemes:
            if name_or_guid.lower() in s["name"].lower() or name_or_guid.lower() == s["guid"].lower():
                target_guid = s["guid"]
                target_name = s["name"]
                break

        if not target_guid:
            active = self.get_active_scheme()
            active_name = active["name"] if active else "Balanced"
            available_names = [f"{s['name']} ({s['guid']})" for s in schemes]
            msg = (
                f"Windows power scheme '{name_or_guid}' is not available on this laptop. "
                f"Available schemes: {', '.join(available_names) or 'None'}. "
                f"Active scheme remains '{active_name}'."
            )
            logger.warning(msg)
            return {
                "success": False,
                "verified": False,
                "message": msg,
                "active_scheme": active_name,
                "available_schemes": schemes
            }

        try:
            res = subprocess.run(
                ["powercfg", "/setactive", target_guid],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False
            )
            if res.returncode == 0:
                # Read-back verification
                read_back = self.get_active_scheme()
                if read_back and read_back["guid"].lower() == target_guid.lower():
                    msg = f"Windows power scheme successfully set and verified as '{target_name}'."
                    logger.info(msg)
                    return {"success": True, "verified": True, "message": msg, "scheme": target_name, "guid": target_guid}
                else:
                    current_name = read_back["name"] if read_back else "Unknown"
                    msg = f"Powercfg commanded '{target_name}', but active scheme remains '{current_name}' upon verification."
                    logger.warning(msg)
                    return {"success": False, "verified": False, "message": msg, "scheme": current_name}
            else:
                msg = f"Failed to activate power scheme '{target_name}': {res.stderr.strip()}"
                return {"success": False, "verified": False, "message": msg}
        except Exception as e:
            msg = f"Error switching power scheme: {e}"
            logger.error(msg)
            return {"success": False, "verified": False, "message": msg}

    def get_battery_telemetry(self) -> Dict[str, Any]:
        """Queries battery status and charge percentage via Windows WMI."""
        try:
            cmd = "Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False
            )
            lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
            if len(lines) >= 3:
                # The data line is after the header and dash separator
                data_line = lines[2]
                parts = data_line.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    pct = int(parts[0])
                    status_code = int(parts[1]) if parts[1].isdigit() else 1
                    # BatteryStatus: 1 = Discharging, 2 = AC / Unknown, 3 = Fully Charged, 4 = Low, 5 = Critical, 6 = Charging
                    is_charging = status_code in (2, 3, 6)
                    status_desc = "Charging" if status_code == 6 else ("Plugged in" if status_code == 2 else "On battery")
                    return {
                        "success": True,
                        "percentage": pct,
                        "status": status_desc,
                        "is_charging": is_charging,
                        "message": f"Battery is at {pct}%, {status_desc}."
                    }
        except Exception as e:
            logger.debug(f"WMI battery query error: {e}")

        # Fallback to psutil if installed
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt:
                pct = int(batt.percent)
                plugged = batt.power_plugged
                status_desc = "Plugged in" if plugged else "On battery"
                return {
                    "success": True,
                    "percentage": pct,
                    "status": status_desc,
                    "is_charging": plugged,
                    "message": f"Battery is at {pct}%, {status_desc}."
                }
        except Exception:
            pass

        return {
            "success": False,
            "message": "Battery telemetry is unavailable or system is connected to desktop AC power."
        }

    def get_acer_oem_report(self) -> Dict[str, Any]:
        """Provides a truthful report on Acer ALG OEM Control Center profiles and capabilities.
        Separates standard Windows power plans from proprietary OEM fan/battery settings.
        """
        active_plan = self.get_active_scheme()
        batt = self.get_battery_telemetry()
        return {
            "laptop_model": self.acer_adapter.laptop_model,
            "active_windows_scheme": active_plan["name"] if active_plan else "Balanced",
            "battery_status": batt.get("message", "Unknown"),
            "oem_control_service": f"{self.acer_adapter.control_center_service} (Control Center Hotkey Service active)",
            "supported_oem_profiles": [
                "Performance Mode (Maximum fan throughput & sustained TDP)",
                "Entertainment Mode (Balanced fan acoustics for media and casual gaming)",
                "Power-saving Mode (Eco throttling, iGPU priority)",
                "Quiet Mode (Whisper acoustic profile for low-load tasks)"
            ],
            "battery_charging_limit": "80% Battery Protection Limit supported via Control Center",
            "integration_status": (
                "Windows power plans and battery telemetry are controlled programmatically. "
                "Proprietary Acer fan profiles (Performance/Quiet) and the 80% battery limit "
                "operate via ACPI bridge driver (CCDCHUService) and must be set via the Acer Control Center application "
                "or OEM Fn hotkeys to prevent hardware and battery safety risks."
            )
        }

    def get_comprehensive_status(self, app_states: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Exposes separate truthful status fields for all power, battery, and app states."""
        active_plan = self.get_active_scheme()
        batt = self.get_battery_telemetry()
        oem_prof = self.acer_adapter.get_active_profile()
        oem_thresh = self.acer_adapter.get_battery_threshold()

        # Check Valorant state
        val_status = "Not Running"
        if app_states and "valorant" in app_states:
            val_status = app_states["valorant"]
        else:
            try:
                import psutil
                for p in psutil.process_iter(['name']):
                    pname = (p.info['name'] or '').lower()
                    if pname in ["valorant.exe", "valorant-win64-shipping.exe"]:
                        val_status = "Running"
                        break
                    elif pname == "riotclientservices.exe":
                        val_status = "Launcher Active"
            except Exception:
                pass

        # Check Discord state
        disc_status = "Not Running"
        if app_states and "discord" in app_states:
            disc_status = app_states["discord"]
        else:
            try:
                import psutil
                for p in psutil.process_iter(['name']):
                    pname = (p.info['name'] or '').lower()
                    if "discord" in pname:
                        disc_status = "Running"
                        break
            except Exception:
                pass

        return {
            "active_windows_power_plan": active_plan["name"] if active_plan else "Unknown",
            "active_windows_power_guid": active_plan["guid"] if active_plan else None,
            "active_acer_oem_profile": oem_prof["profile"],
            "battery_percentage": batt.get("percentage"),
            "battery_charging_status": batt.get("status", "Unknown"),
            "is_charging": batt.get("is_charging", False),
            "configured_battery_charging_threshold": oem_thresh["threshold"],
            "valorant_launch_status": val_status,
            "discord_launch_status": disc_status
        }


power_manager = PowerManager()
