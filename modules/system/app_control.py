import os
import sys
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from core.platform.platform_manager import platform_manager
from core.apps.application_discovery import app_discovery

logger = logging.getLogger("Jarvis.AppControl")

def resolve_app_path(app_key: str) -> str:
    """Attempts to resolve executable path for app."""
    if hasattr(platform_manager.platform, "resolve_executable"):
        return platform_manager.platform.resolve_executable(app_key)
    return app_key

def is_app_running(app_key: str) -> bool:
    """Checks if application is currently running."""
    return platform_manager.is_application_running(app_key)

def bring_app_to_front(app_key: str) -> bool:
    """Brings application window to front."""
    return platform_manager.focus_application(app_key)

def launch_application(raw_name: str) -> Dict[str, Any]:
    """Generic application launcher resolving against discovered catalogue.

    Returns structured outcome:
    - success: bool
    - message: str
    - outcome: "SUCCESS" | "AMBIGUOUS" | "UNSUPPORTED_CAPABILITY" | "EXECUTION_FAILED"
    - candidates: list of matching names if ambiguous
    """
    key = raw_name.lower().strip()
    if not key:
        return {
            "success": False,
            "message": "Which application should I open, Sir?",
            "outcome": "MISSING_ARGUMENT",
            "candidates": []
        }

    # 1. Search discovered applications catalogue
    best_app, candidates = app_discovery.find_application(key)

    if candidates:
        cand_names = [c.display_name for c in candidates[:4]]
        cand_str = ", ".join(cand_names)
        msg = f"Multiple applications matched '{raw_name}': {cand_str}. Which one would you like to open, Sir?"
        logger.info(f"[LAUNCH] Ambiguous request '{raw_name}': candidates={cand_names}")
        return {
            "success": False,
            "message": msg,
            "outcome": "AMBIGUOUS",
            "candidates": cand_names
        }

    if best_app:
        app_name = best_app.display_name
        exec_path = best_app.executable_path

        # If already running, focus window first
        if is_app_running(best_app.app_id) and best_app.app_id not in ["explorer", "notepad", "calculator"]:
            logger.info(f"Application '{best_app.app_id}' is running. Bringing window to front.")
            if bring_app_to_front(best_app.app_id):
                return {
                    "success": True,
                    "message": f"{app_name} is open, Sir.",
                    "outcome": "SUCCESS",
                    "app": best_app.app_id
                }

        # Launch native application
        logger.info(f"[LAUNCH] Launching native application '{app_name}' from: {exec_path}")
        try:
            if sys.platform.startswith("win"):
                if exec_path.lower().endswith(".lnk"):
                    os.startfile(exec_path)
                else:
                    cmd = [exec_path] + (best_app.arguments or [])
                    subprocess.Popen(cmd, shell=False)
            else:
                cmd = [exec_path] + (best_app.arguments or [])
                subprocess.Popen(cmd, shell=False)

            return {
                "success": True,
                "message": f"{app_name} is open, Sir.",
                "outcome": "SUCCESS",
                "app": best_app.app_id
            }
        except Exception as e:
            logger.error(f"[LAUNCH] Failed to launch '{app_name}': {e}")
            # Try platform_manager as secondary fallback
            if platform_manager.open_application(best_app.app_id):
                return {
                    "success": True,
                    "message": f"{app_name} is open, Sir.",
                    "outcome": "SUCCESS",
                    "app": best_app.app_id
                }
            return {
                "success": False,
                "message": f"Failed to launch {app_name}, Sir.",
                "outcome": "EXECUTION_FAILED"
            }

    # 2. Check platform manager built-ins fallback (notepad, calc, explorer, or known config apps)
    if is_app_running(key) and key not in ["explorer", "notepad", "calculator"]:
        if bring_app_to_front(key):
            return {
                "success": True,
                "message": f"{key.title()} is open, Sir.",
                "outcome": "SUCCESS"
            }

    # Verify if key is a known system executable or configured app before attempting launch
    is_known = (
        key in ["explorer", "notepad", "calculator", "calc", "cmd", "powershell"] or
        (hasattr(platform_manager.platform, "app_registry") and key in platform_manager.platform.app_registry) or
        shutil.which(key) is not None or
        shutil.which(f"{key}.exe") is not None
    )

    if is_known and platform_manager.open_application(key):
        return {
            "success": True,
            "message": f"{key.title()} is open, Sir.",
            "outcome": "SUCCESS"
        }

    # 3. Not found: report missing application with safe discovery offer
    not_found_msg = (
        f"I couldn't find an application named '{raw_name}' installed on this computer. "
        "You can say 'Jarvis, scan applications' to refresh the catalogue."
    )
    logger.info(f"[LAUNCH] Application not found: '{raw_name}'")
    return {
        "success": False,
        "message": not_found_msg,
        "outcome": "UNSUPPORTED_CAPABILITY",
        "candidates": []
    }

def open_app(app_key: str) -> bool:
    """Launches application cross-platform (compatibility wrapper)."""
    res = launch_application(app_key)
    return res.get("success", False)

def close_app(app_key: str) -> bool:
    """Terminates application cross-platform."""
    return platform_manager.close_application(app_key)
