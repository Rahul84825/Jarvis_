"""Chrome DevTools Protocol (CDP) Client.
Provides native interaction with Chromium/Chrome instances launched with remote debugging
(e.g., --remote-debugging-port=9222) with graceful, verified error handling when CDP is unavailable.
Strictly restricted to localhost (127.0.0.1) for security.
"""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.CDPClient")

class CDPClient:
    """Manages HTTP inspection and control of running Chrome via Chrome DevTools Protocol."""

    def __init__(self, port: int = 9222, host: str = "127.0.0.1"):
        # Security restriction: Only allow loopback interface
        if host not in ["127.0.0.1", "localhost"]:
            logger.warning(f"[CDP] Untrusted host '{host}' requested. Forcing loopback 127.0.0.1.")
            host = "127.0.0.1"

        self.port = port
        self.host = host
        self.base_url = f"http://{host}:{port}"
        self.timeout = 0.8  # Fast non-blocking timeout

    def is_available(self) -> bool:
        """Checks if Chrome DevTools Protocol HTTP port is actively responding."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/version", headers={"User-Agent": "Jarvis-Assistant"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        return False

    def get_status_report(self) -> Dict[str, Any]:
        """Returns diagnostic report of CDP availability with actionable guidance."""
        available = self.is_available()
        version_info = self.get_version_info() if available else None
        return {
            "available": available,
            "host": self.host,
            "port": self.port,
            "browser_version": version_info.get("Browser", "Unknown") if version_info else None,
            "guidance": (
                "CDP connected and ready for page inspection and tab management."
                if available
                else "CDP is offline. Launch Chrome with '--remote-debugging-port=9222' on localhost to enable deep page inspection."
            )
        }

    def get_version_info(self) -> Optional[Dict[str, Any]]:
        """Fetches browser version and CDP endpoints."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/version", headers={"User-Agent": "Jarvis-Assistant"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"[CDP] Version check failed: {e}")
            return None

    def list_tabs(self) -> List[Dict[str, Any]]:
        """Returns list of open page tabs with title and URL."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/list", headers={"User-Agent": "Jarvis-Assistant"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = [tab for tab in data if tab.get("type") == "page"]
                return pages
        except Exception as e:
            logger.debug(f"[CDP] Tab listing unavailable: {e}")
            return []

    def get_active_tab(self) -> Optional[Dict[str, Any]]:
        """Gets currently active tab or first open page."""
        tabs = self.list_tabs()
        if tabs:
            return tabs[0]
        return None

    def get_active_tab_title(self) -> Optional[str]:
        """Returns the title of the active tab."""
        tab = self.get_active_tab()
        return tab.get("title") if tab else None

    def get_active_tab_url(self) -> Optional[str]:
        """Returns the URL of the active tab."""
        tab = self.get_active_tab()
        return tab.get("url") if tab else None

    def inspect_active_page(self) -> Dict[str, Any]:
        """Performs verified page inspection via CDP."""
        if not self.is_available():
            return {
                "success": False,
                "cdp_available": False,
                "message": "Chrome DevTools Protocol (CDP) is offline. Launch Chrome with '--remote-debugging-port=9222' to enable page inspection."
            }
        tab = self.get_active_tab()
        if tab:
            return {
                "success": True,
                "cdp_available": True,
                "tab_id": tab.get("id"),
                "title": tab.get("title", "Untitled"),
                "url": tab.get("url", ""),
                "message": f"Active page: '{tab.get('title', 'Untitled')}' ({tab.get('url', '')})."
            }
        return {
            "success": False,
            "cdp_available": True,
            "message": "CDP is connected but no open web pages were found."
        }

    def new_tab(self, url: str = "") -> Optional[Dict[str, Any]]:
        """Creates a new browser tab via CDP."""
        try:
            target = f"{self.base_url}/json/new"
            if url:
                target += f"?{urllib.parse.quote(url, safe=':/?=&')}"
            req = urllib.request.Request(target, method="PUT", headers={"User-Agent": "Jarvis-Assistant"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"[CDP] New tab creation via CDP failed: {e}")
            return None

    def activate_tab(self, tab_id: str) -> bool:
        """Focuses/activates a specific tab by ID."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/activate/{tab_id}", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug(f"[CDP] Tab activation failed: {e}")
            return False

    def close_tab(self, tab_id: str) -> bool:
        """Closes a specific tab by ID."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/close/{tab_id}", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug(f"[CDP] Tab close failed: {e}")
            return False
