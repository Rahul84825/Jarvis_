import logging
from typing import Tuple, Dict, Any, Union
from core.platform.platform_manager import platform_manager
from core.os.application_resolver import application_resolver, TargetType
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

def open_app(app_key: str) -> bool:
    """Launches application with Application-First priority and seamless website fallback."""
    res, _ = open_app_detailed(app_key)
    return res

def open_app_detailed(app_key: str) -> Tuple[bool, str]:
    """Launches application with structured feedback and website fallback."""
    if not app_key:
        return False, "No application specified."

    key = app_key.lower().strip()
    resolved = application_resolver.resolve(key)

    # 1. Direct Domain / URL Target (e.g. 'wellmeds.in', 'google.com')
    if resolved.target_type == TargetType.DOMAIN_URL:
        logger.info(f"Opening domain URL '{resolved.url}' in browser.")
        ok = web_control.open_url(resolved.url)
        return ok, f"Opened {resolved.canonical_name} in your browser." if ok else f"Failed to open {resolved.canonical_name}."

    # 2. Native Application Launch
    if resolved.target_type == TargetType.NATIVE_APP:
        target_name = resolved.canonical_name
        if is_app_running(target_name) and target_name not in ["explorer", "notepad", "calculator"]:
            logger.info(f"Application '{target_name}' is running. Bringing window to front.")
            if bring_app_to_front(target_name):
                return True, f"Brought {resolved.display_name} to front."

        launched = platform_manager.open_application(target_name)
        if launched:
            return True, f"Opening {resolved.display_name}."

        # If native launch failed but fallback website is available
        if resolved.fallback_url:
            logger.info(f"Native launch failed for '{target_name}'. Opening website fallback: {resolved.fallback_url}")
            ok = web_control.open_url(resolved.fallback_url)
            return ok, f"{resolved.display_name} isn't installed locally, so I opened {resolved.display_name} in your browser."

        return False, f"Failed to launch {resolved.display_name}."

    # 3. Known Website Fallback
    if resolved.target_type == TargetType.WEBSITE:
        target_url = resolved.url or web_control.get_supported_sites().get(resolved.canonical_name)
        if target_url:
            ok = web_control.open_url(target_url)
            return ok, f"{resolved.display_name} isn't installed locally, so I opened {resolved.display_name} in your browser."

    # 4. Fallback attempt directly via platform manager
    direct_ok = platform_manager.open_application(key)
    if direct_ok:
        return True, f"Opening {key.title()}."

    return False, f"Could not find or launch application '{app_key}'."

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
