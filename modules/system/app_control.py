import os
import sys
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Tuple, Dict, Any, Union, Optional
from core.platform.platform_manager import platform_manager
from core.os.application_resolver import application_resolver, TargetType
from core.apps.application_discovery import app_discovery
from modules.browser import web_control

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
    """Generic application launcher resolving against discovered catalogue and resolver.

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

    # 1. Resolve through application_resolver (handles URLs, domains, aliases)
    resolved = application_resolver.resolve(key)

    if resolved.target_type == TargetType.DOMAIN_URL:
        logger.info(f"Opening domain URL '{resolved.url}' in browser.")
        ok = web_control.open_url(resolved.url)
        return {
            "success": ok,
            "message": f"Opened {resolved.canonical_name} in your browser." if ok else f"Failed to open {resolved.canonical_name}.",
            "outcome": "SUCCESS" if ok else "EXECUTION_FAILED",
            "candidates": []
        }

    if resolved.target_type == TargetType.WEBSITE:
        target_url = resolved.url or web_control.get_supported_sites().get(resolved.canonical_name)
        if target_url:
            ok = web_control.open_url(target_url)
            return {
                "success": ok,
                "message": f"{resolved.display_name} isn't installed locally, so I opened {resolved.display_name} in your browser." if ok else f"Failed to open {resolved.display_name}.",
                "outcome": "SUCCESS" if ok else "EXECUTION_FAILED",
                "candidates": []
            }

    # Check temporal installation query ("the application I installed yesterday")
    if "yesterday" in key:
        yesterday_app = app_discovery.find_application_by_date(day_offset=1)
        if yesterday_app:
            best_app = yesterday_app
            candidates = []
        else:
            return {
                "success": False,
                "message": "I couldn't find any application installed yesterday, Sir.",
                "outcome": "UNSUPPORTED_CAPABILITY",
                "candidates": []
            }
    else:
        # 2. Search discovered applications catalogue
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

        if is_app_running(best_app.app_id) and best_app.app_id not in ["explorer", "notepad", "calculator"]:
            logger.info(f"Application '{best_app.app_id}' is running. Bringing window to front.")
            if bring_app_to_front(best_app.app_id):
                return {
                    "success": True,
                    "message": f"{app_name} is open, Sir.",
                    "outcome": "SUCCESS",
                    "app": best_app.app_id
                }

        logger.info(f"[LAUNCH] Launching native application '{app_name}' from: {exec_path}")
        try:
            if sys.platform.startswith("win"):
                if exec_path.lower().endswith(".lnk") or best_app.launch_mechanism == "uwp":
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
            if platform_manager.open_application(best_app.app_id):
                return {
                    "success": True,
                    "message": f"{app_name} is open, Sir.",
                    "outcome": "SUCCESS",
                    "app": best_app.app_id
                }
            if resolved.fallback_url:
                ok = web_control.open_url(resolved.fallback_url)
                if ok:
                    return {
                        "success": True,
                        "message": f"{resolved.display_name} couldn't be launched locally, so I opened it in your browser.",
                        "outcome": "SUCCESS"
                    }
            return {
                "success": False,
                "message": f"Failed to launch {app_name}, Sir.",
                "outcome": "EXECUTION_FAILED"
            }

    # 3. Check native app resolution / platform manager
    target_name = resolved.canonical_name if resolved.target_type == TargetType.NATIVE_APP else key
    if is_app_running(target_name) and target_name not in ["explorer", "notepad", "calculator"]:
        if bring_app_to_front(target_name):
            return {
                "success": True,
                "message": f"Brought {resolved.display_name or target_name.title()} to front.",
                "outcome": "SUCCESS"
            }

    is_known = (
        target_name in ["explorer", "notepad", "calculator", "calc", "cmd", "powershell"] or
        (hasattr(platform_manager.platform, "app_registry") and target_name in platform_manager.platform.app_registry) or
        shutil.which(target_name) is not None or
        shutil.which(f"{target_name}.exe") is not None
    )

    if is_known and platform_manager.open_application(target_name):
        return {
            "success": True,
            "message": f"Opening {resolved.display_name or target_name.title()}.",
            "outcome": "SUCCESS"
        }

    # Fallback attempt directly via platform manager
    if platform_manager.open_application(target_name):
        return {
            "success": True,
            "message": f"Opening {resolved.display_name or target_name.title()}.",
            "outcome": "SUCCESS"
        }

    # Fallback to website if available
    if resolved.fallback_url:
        logger.info(f"Native launch failed for '{target_name}'. Opening website fallback: {resolved.fallback_url}")
        ok = web_control.open_url(resolved.fallback_url)
        return {
            "success": ok,
            "message": f"{resolved.display_name} isn't installed locally, so I opened {resolved.display_name} in your browser." if ok else f"Failed to launch {resolved.display_name}.",
            "outcome": "SUCCESS" if ok else "EXECUTION_FAILED"
        }

    # 4. Not found
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

def open_app_detailed(app_key: str) -> Tuple[bool, str]:
    """Launches application with structured feedback and website fallback."""
    res = launch_application(app_key)
    return res.get("success", False), res.get("message", "")

def open_app(app_key: str) -> bool:
    """Launches application cross-platform (compatibility wrapper)."""
    res = launch_application(app_key)
    return res.get("success", False)

def close_app(app_key: str) -> bool:
    """Terminates application cross-platform."""
    return platform_manager.close_application(app_key)

from modules.system import window_control

def minimize_app(app_key: str = None) -> bool:
    """Minimizes application window cross-platform."""
    return window_control.minimize_window(app_key)

def maximize_app(app_key: str = None) -> bool:
    """Maximizes application window cross-platform."""
    return window_control.maximize_window(app_key)

# Desktop Control & Properties Operations
def open_app_properties(app_key: str) -> Dict[str, Any]:
    """Opens file properties dialog for an application executable."""
    return app_discovery.open_properties_dialog(app_key)

def open_app_install_dir(app_key: str) -> Dict[str, Any]:
    """Opens installation folder in file manager."""
    return app_discovery.open_install_folder(app_key)

def open_app_settings(app_key: str) -> Dict[str, Any]:
    """Opens application internal or system settings."""
    return app_discovery.open_app_settings(app_key)

def get_app_metadata(app_key: str) -> Dict[str, Any]:
    """Retrieves version, publisher, path, and details for an application."""
    return app_discovery.get_app_metadata(app_key)

def is_app_installed(app_key: str) -> Dict[str, Any]:
    """Checks if an application is installed and available."""
    return app_discovery.is_app_installed(app_key)

def list_installed_apps(category: Optional[str] = None) -> Dict[str, Any]:
    """Lists installed applications or filters by category."""
    return app_discovery.list_installed_apps(category=category)

def refresh_apps() -> Dict[str, Any]:
    """Refreshes discovered applications catalogue at runtime."""
    count = app_discovery.refresh()
    return {
        "success": True,
        "count": count,
        "message": f"Application registry refreshed. Discovered {count} applications."
    }
