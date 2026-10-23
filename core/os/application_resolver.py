"""
Application & Target Resolver for Jarvis.
Provides intelligent target classification and resolution:
Priority:
1. Running native application
2. Installed native application (Start Menu, Registry, PATH, standard directories)
3. Configured application with website fallback
4. Direct Domain / Website URL (e.g. wellmeds.in, google.com, chatgpt.com)
5. Search query fallback
"""

import os
import re
import json
import logging
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

from config import BASE_DIR
from core.platform.platform_manager import platform_manager
from modules.browser import web_control

logger = logging.getLogger("Jarvis.ApplicationResolver")

class TargetType(str, Enum):
    NATIVE_APP = "NATIVE_APP"
    APPLICATION = "NATIVE_APP"
    WEBSITE = "WEBSITE"
    WEBSITE_FALLBACK = "WEBSITE"
    DOMAIN_URL = "DOMAIN_URL"
    URL = "DOMAIN_URL"
    SEARCH_QUERY = "SEARCH_QUERY"
    SEARCH = "SEARCH_QUERY"
    FILE_FOLDER = "FILE_FOLDER"
    UNKNOWN = "UNKNOWN"

@dataclass
class ResolvedTarget:
    original_target: str
    target_type: TargetType
    canonical_name: str
    executable_path: Optional[str] = None
    url: Optional[str] = None
    is_installed: bool = False
    is_running: bool = False
    fallback_available: bool = False
    fallback_url: Optional[str] = None
    display_name: str = ""

class ApplicationResolver:
    """Intelligently resolves spoken targets into native applications, website URLs,
    or web searches with application-first priority.
    """

    COMMON_DOMAINS_TLD = {
        "in", "com", "org", "net", "io", "ai", "co", "app", "gov", "edu",
        "dev", "me", "info", "xyz", "tech", "online", "store", "site"
    }

    def __init__(self):
        self.apps_json_path = BASE_DIR / "config" / "applications.json"
        self.links_json_path = BASE_DIR / "config" / "links.json"
        self._applications = self._load_applications()
        self._links = self._load_links()
        self._app_definitions = self._applications
        self._link_definitions = self._links
        self._alias_to_key = self._build_alias_map()

    def _load_applications(self) -> Dict[str, Any]:
        if not self.apps_json_path.exists():
            return {}
        try:
            with open(self.apps_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load applications.json: {e}")
            return {}

    def _load_links(self) -> Dict[str, Any]:
        if not self.links_json_path.exists():
            return {}
        try:
            with open(self.links_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load links.json: {e}")
            return {}

    def _build_alias_map(self) -> Dict[str, str]:
        alias_map = {}
        for app_key, app_data in self._applications.items():
            alias_map[app_key.lower()] = app_key
            for alias in app_data.get("aliases", []):
                alias_map[alias.lower().strip()] = app_key
        return alias_map

    def is_domain_or_url(self, target: str) -> bool:
        """Determines if a target string is a website URL or domain name (e.g. 'wellmeds.in', 'google.com')."""
        if not target:
            return False
        clean = target.lower().strip()
        if clean.endswith((".exe", ".bat", ".cmd", ".lnk", ".app", ".msi", ".py", ".sh", ".txt", ".pdf", ".docx", ".xlsx")):
            return False
        if clean.startswith("http://") or clean.startswith("https://") or clean.startswith("www."):
            return True

        # Check domain pattern (e.g. name.tld or sub.name.tld)
        domain_match = re.match(r'^[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+\/?.*$', clean)
        if domain_match:
            parts = clean.split('/')[0].split('.')
            tld = parts[-1]
            if tld in self.COMMON_DOMAINS_TLD or len(tld) in [2, 3]:
                return True

        return False

    def normalize_url(self, target: str) -> str:
        """Normalizes a domain or URL target into a complete https:// URL."""
        clean = target.strip()
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        if clean.startswith("www."):
            return f"https://{clean}"
        return f"https://{clean}"

    def resolve(self, raw_target: str, check_running: bool = False) -> ResolvedTarget:
        """Resolves target with Application-First Priority:
        1. Direct Domain / URL
        2. Known native application (running or installed)
        3. Configured application with website fallback
        4. Known website link
        5. Search query fallback
        """
        if not raw_target:
            return ResolvedTarget(
                original_target="",
                target_type=TargetType.UNKNOWN,
                canonical_name="",
                display_name=""
            )

        clean = raw_target.lower().strip('.!?,:; \t\n')

        # 1. DIRECT DOMAIN / URL CHECK (e.g. "wellmeds.in", "google.com", "chatgpt.com")
        if self.is_domain_or_url(clean):
            norm_url = self.normalize_url(clean)
            logger.info(f"[RESOLVER] Target '{raw_target}' resolved as DOMAIN_URL -> {norm_url}")
            return ResolvedTarget(
                original_target=raw_target,
                target_type=TargetType.DOMAIN_URL,
                canonical_name=clean,
                url=norm_url,
                display_name=clean
            )

        # 2. CHECK APPLICATION REGISTRY
        app_key = self._alias_to_key.get(clean)
        if not app_key:
            # Check partial match on alias
            for alias, key in self._alias_to_key.items():
                if clean == alias or clean.startswith(alias + " ") or clean.endswith(" " + alias):
                    app_key = key
                    break

        if app_key:
            app_data = self._app_definitions.get(app_key, {})
            website_fb = app_data.get("website")

            is_running = False
            if check_running:
                is_running = platform_manager.is_application_running(app_key)

            # Instant recognition for standard known applications
            is_installed = app_key in [
                "calc", "calculator", "notepad", "explorer", "cmd", "powershell", 
                "settings", "chrome", "vscode", "terminal", "edge", "spotify", "discord", "antigravity"
            ]
            exec_path = None
            if not is_installed and hasattr(platform_manager.platform, "resolve_executable"):
                exec_path = platform_manager.platform.resolve_executable(app_key)
                if exec_path:
                    if os.path.isabs(exec_path) and os.path.exists(exec_path):
                        is_installed = True
                    elif not os.path.isabs(exec_path):
                        import shutil
                        if shutil.which(exec_path):
                            is_installed = True

            display_name = app_key.replace("_", " ").title()
            if is_installed or is_running:
                logger.info(f"[RESOLVER] Application '{app_key}' resolved as NATIVE_APP (Installed={is_installed}, Running={is_running})")
                return ResolvedTarget(
                    original_target=raw_target,
                    target_type=TargetType.NATIVE_APP,
                    canonical_name=app_key,
                    executable_path=exec_path,
                    is_installed=is_installed,
                    is_running=is_running,
                    fallback_available=bool(website_fb),
                    fallback_url=website_fb,
                    display_name=display_name
                )
            elif website_fb:
                logger.info(f"[RESOLVER] Application '{app_key}' not installed locally. Using WEBSITE fallback -> {website_fb}")
                return ResolvedTarget(
                    original_target=raw_target,
                    target_type=TargetType.WEBSITE,
                    canonical_name=app_key,
                    url=website_fb,
                    is_installed=False,
                    is_running=False,
                    fallback_available=True,
                    fallback_url=website_fb,
                    display_name=display_name
                )

        # 3. CHECK DISCOVERED APPLICATIONS CATALOGUE DYNAMICALLY (Zero hardcoding)
        try:
            from core.apps.application_discovery import app_discovery
            disc_app, _ = app_discovery.find_application(clean)
            if disc_app and disc_app.is_available:
                logger.info(f"[RESOLVER] Application '{disc_app.display_name}' dynamically resolved from Discovery Catalogue as NATIVE_APP")
                is_running = False
                if check_running:
                    is_running = platform_manager.is_application_running(disc_app.app_id)
                return ResolvedTarget(
                    original_target=raw_target,
                    target_type=TargetType.NATIVE_APP,
                    canonical_name=disc_app.app_id,
                    executable_path=disc_app.executable_path,
                    is_installed=True,
                    is_running=is_running,
                    fallback_available=False,
                    display_name=disc_app.display_name
                )
        except Exception as e:
            logger.debug(f"[RESOLVER] Dynamic application discovery query error: {e}")

        # 4. CHECK KNOWN WEBSITE LINKS REGISTRY
        if clean in self._link_definitions:
            link_url = self._link_definitions[clean]
            logger.info(f"[RESOLVER] Target '{clean}' resolved from links.json as WEBSITE -> {link_url}")
            return ResolvedTarget(
                original_target=raw_target,
                target_type=TargetType.WEBSITE,
                canonical_name=clean,
                url=link_url,
                display_name=clean.title()
            )

        # 5. UNKNOWN / GENERIC TARGET
        return ResolvedTarget(
            original_target=raw_target,
            target_type=TargetType.UNKNOWN,
            canonical_name=clean,
            display_name=clean.title()
        )

    def resolve_search(self, query: str, provider: str = "google") -> ResolvedTarget:
        """Resolves web search query into target URL."""
        import urllib.parse
        clean_q = urllib.parse.quote_plus(query.strip())
        p = provider.lower().strip()
        if p == "youtube":
            url = f"https://www.youtube.com/results?search_query={clean_q}"
        elif p == "github":
            url = f"https://github.com/search?q={clean_q}"
        elif p == "reddit":
            url = f"https://www.reddit.com/search/?q={clean_q}"
        elif p in ["stackoverflow", "stack overflow"]:
            url = f"https://stackoverflow.com/search?q={clean_q}"
        else:
            url = f"https://www.google.com/search?q={clean_q}"

        return ResolvedTarget(
            original_target=query,
            target_type=TargetType.SEARCH_QUERY,
            canonical_name=provider,
            url=url,
            display_name=f"{provider.title()} Search: {query}"
        )

application_resolver = ApplicationResolver()
