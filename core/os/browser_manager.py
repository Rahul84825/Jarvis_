import json
import logging
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import config
from core.platform.platform_manager import platform_manager

logger = logging.getLogger("Jarvis.BrowserManager")

class BrowserManager:
    """Native Cross-Platform Browser Control & Web Search Subsystem Manager for Windows and Ubuntu Linux.
    Provides browser discovery, preferred/fallback priority management, search provider URL synthesis,
    query encoding, and site links registry.
    """

    DEFAULT_SEARCH_PROVIDERS = {
        "google": {"base_url": "https://www.google.com/search?q={query}"},
        "youtube": {"base_url": "https://www.youtube.com/results?search_query={query}"},
        "github": {"base_url": "https://github.com/search?q={query}"},
        "reddit": {"base_url": "https://www.reddit.com/search/?q={query}"},
        "stackoverflow": {"base_url": "https://stackoverflow.com/search?q={query}"}
    }

    def __init__(self, links_path: str = None, browser_config_path: str = None, search_providers_path: str = None):
        base_dir = Path(config.BASE_DIR)
        self.links_path = Path(links_path) if links_path else base_dir / "config" / "links.json"
        self.browser_config_path = Path(browser_config_path) if browser_config_path else base_dir / "config" / "browser.json"
        self.search_providers_path = Path(search_providers_path) if search_providers_path else base_dir / "config" / "search_providers.json"

        self.links: Dict[str, str] = self._load_links()
        self.browser_config: Dict[str, Any] = self._load_browser_config()
        self.search_providers: Dict[str, Any] = self._load_search_providers()

        logger.info(f"BrowserManager initialized for OS '{platform_manager.os_name}' with preferred browser '{self.preferred_browser}'.")

    @property
    def preferred_browser(self) -> str:
        return self.browser_config.get("preferred_browser", "chrome").lower().strip()

    @property
    def fallback_browser_enabled(self) -> bool:
        return bool(self.browser_config.get("fallback_browser", True))

    def _load_links(self) -> Dict[str, str]:
        if self.links_path.exists():
            try:
                with open(self.links_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {k.lower().strip(): v for k, v in data.items()}
            except Exception as e:
                logger.error(f"[BROWSER_ERROR] Failed to load links.json: {e}")
        return {}

    def _load_browser_config(self) -> Dict[str, Any]:
        if self.browser_config_path.exists():
            try:
                with open(self.browser_config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[BROWSER_ERROR] Failed to load browser.json: {e}")
        return {"preferred_browser": "chrome", "fallback_browser": True}

    def _load_search_providers(self) -> Dict[str, Any]:
        if self.search_providers_path.exists():
            try:
                with open(self.search_providers_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[BROWSER_ERROR] Failed to load search_providers.json: {e}")
        return self.DEFAULT_SEARCH_PROVIDERS

    def get_available_browsers(self) -> List[str]:
        return platform_manager.get_available_browsers()

    def get_default_browser(self) -> str:
        return platform_manager.get_default_browser()

    def is_browser_available(self, browser_name: str) -> bool:
        return platform_manager.is_browser_available(browser_name)

    def resolve_target_browser(self, requested_browser: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """Resolves target browser according to priority:
        Requested/Preferred -> Chrome -> Chromium -> Default browser.
        Returns Tuple of (resolved_browser_name_or_default, error_message).
        """
        target = (requested_browser or self.preferred_browser or "chrome").lower().strip()

        if target in ["default", "system"]:
            return "default", None

        # Direct check
        if self.is_browser_available(target):
            return target, None

        logger.warning(f"[BROWSER_RESOLVE] Target browser '{target}' is not installed.")

        if not self.fallback_browser_enabled:
            return None, f"{target.title()} isn't installed. I couldn't open the browser."

        # Fallback chain: Chrome -> Chromium -> Default
        fallbacks = ["chrome", "chromium"]
        for fb in fallbacks:
            if fb != target and self.is_browser_available(fb):
                logger.info(f"[BROWSER_FALLBACK] Falling back from '{target}' to '{fb}'.")
                return fb, None

        logger.info(f"[BROWSER_FALLBACK] Falling back to default system browser.")
        return "default", None

    def build_search_url(self, provider: str, query: str) -> str:
        """Constructs a fully encoded search URL using quote_plus."""
        prov_key = (provider or "google").lower().strip()
        if prov_key == "stack overflow":
            prov_key = "stackoverflow"

        prov_data = self.search_providers.get(prov_key, self.search_providers.get("google", self.DEFAULT_SEARCH_PROVIDERS["google"]))
        template = prov_data.get("base_url", "https://www.google.com/search?q={query}")

        encoded_query = urllib.parse.quote_plus(query.strip())
        return template.format(query=encoded_query)

    def open_url(self, url: str) -> Dict[str, Any]:
        """Opens a direct URL using platform adapter."""
        if not url:
            return {"success": False, "message": "No URL provided."}
        try:
            logger.info(f"[BROWSER] OS: {platform_manager.os_name} | Launching URL: {url}")
            success = platform_manager.open_url(url)
            if success:
                return {"success": True, "message": "Opening link in browser."}
            return {"success": False, "message": "I couldn't open that website."}
        except Exception as e:
            logger.error(f"[BROWSER_ERROR] Failed to open URL '{url}': {e}")
            return {"success": False, "message": "I couldn't open that website."}

    def open_browser(self, browser_name: str = "default", url: str = None) -> Dict[str, Any]:
        """Launches specified or preferred browser with optional URL."""
        resolved, err = self.resolve_target_browser(browser_name)
        if not resolved:
            return {"success": False, "message": err or "I couldn't find a supported browser."}

        try:
            logger.info(f"[BROWSER] OS: {platform_manager.os_name} | Requested: {browser_name} | Selected: {resolved} | URL: {url}")
            success = platform_manager.open_browser(resolved, url=url)
            browser_display = resolved.title() if resolved != "default" else "Browser"
            if success:
                return {"success": True, "message": f"Opening {browser_display}."}
            return {"success": False, "message": "I couldn't open the browser."}
        except Exception as e:
            logger.error(f"[BROWSER_ERROR] Failed to open browser '{browser_name}': {e}")
            return {"success": False, "message": "I couldn't open the browser."}

    def search(self, query: str, provider: str = "google", browser_name: str = "default") -> Dict[str, Any]:
        """Performs a web search using configured browser and URL encoding."""
        if not query or not query.strip():
            return {"success": False, "operation": "web_search", "message": "No search query provided."}

        prov_key = provider.lower().strip() if provider else "google"
        if prov_key == "stack overflow":
            prov_key = "stackoverflow"

        target_url = self.build_search_url(prov_key, query)
        resolved_browser, err = self.resolve_target_browser(browser_name)

        if not resolved_browser:
            return {"success": False, "operation": "web_search", "message": err or "I couldn't find a supported browser."}

        logger.info(f"[BROWSER] OS: {platform_manager.os_name} | Requested Browser: {browser_name} | Selected Browser: {resolved_browser} | Provider: {prov_key.title()} | Query: '{query}' | URL: {target_url} | Result: PENDING")

        try:
            success = platform_manager.open_browser(resolved_browser, url=target_url)
            prov_display = "Stack Overflow" if prov_key == "stackoverflow" else prov_key.title()

            if success:
                logger.info(f"[BROWSER_RESULT] Result: SUCCESS")
                return {
                    "success": True,
                    "operation": "web_search",
                    "provider": prov_key,
                    "query": query,
                    "url": target_url,
                    "message": f"Searching {prov_display}."
                }

            logger.warning(f"[BROWSER_RESULT] Result: FAILED")
            return {"success": False, "operation": "web_search", "message": "I couldn't open the browser."}
        except Exception as e:
            logger.error(f"[BROWSER_ERROR] Search execution error: {e}", exc_info=True)
            return {"success": False, "operation": "web_search", "message": "I couldn't open the browser."}

    def search_google(self, query: str) -> Dict[str, Any]:
        return self.search(query, provider="google")

    def search_youtube(self, query: str) -> Dict[str, Any]:
        return self.search(query, provider="youtube")

    def search_github(self, query: str) -> Dict[str, Any]:
        return self.search(query, provider="github")

    def search_reddit(self, query: str) -> Dict[str, Any]:
        return self.search(query, provider="reddit")

    def search_stackoverflow(self, query: str) -> Dict[str, Any]:
        return self.search(query, provider="stackoverflow")

    def open_site(self, site_key_or_url: str) -> Dict[str, Any]:
        """Opens website from links.json or direct URL."""
        if not site_key_or_url:
            return {"success": False, "message": "No URL or site specified."}

        key = site_key_or_url.lower().strip()
        url = self.links.get(key)

        if not url:
            if key.startswith("http://") or key.startswith("https://"):
                url = key
            elif "." in key and " " not in key:
                url = f"https://{key}"
            else:
                return {"success": False, "message": f"Website '{site_key_or_url}' is not configured."}

        return self.open_url(url)
