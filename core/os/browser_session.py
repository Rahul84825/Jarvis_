"""Browser Session and Multi-turn Tab Context Tracker for JARVIS.
Maintains live state of active browser windows, tabs, URLs, loading statuses,
and past search queries to power fluid conversational follow-ups.
"""

import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import logging

from core.os.cdp_client import CDPClient

logger = logging.getLogger("Jarvis.BrowserSession")


@dataclass
class BrowserSessionState:
    """Represents current live browser state and conversational session memory."""
    active_browser: str = "chrome"
    active_window_hwnd: int = 0
    active_window_title: str = ""
    active_tab_id: Optional[str] = None
    active_url: Optional[str] = None
    active_domain: Optional[str] = None
    active_site: Optional[str] = None
    page_title: Optional[str] = None
    is_loading: bool = False
    last_search_query: Optional[str] = None
    last_site: Optional[str] = None
    last_url: Optional[str] = None
    last_domain: Optional[str] = None
    last_action_timestamp: float = field(default_factory=time.time)
    operation_cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_browser": self.active_browser,
            "active_window_hwnd": self.active_window_hwnd,
            "active_window_title": self.active_window_title,
            "active_tab_id": self.active_tab_id,
            "active_url": self.active_url,
            "active_domain": self.active_domain,
            "active_site": self.active_site,
            "page_title": self.page_title,
            "is_loading": self.is_loading,
            "last_search_query": self.last_search_query,
            "last_site": self.last_site,
            "last_url": self.last_url,
            "last_domain": self.last_domain,
            "last_action_timestamp": self.last_action_timestamp,
            "operation_cancelled": self.operation_cancelled
        }


class BrowserSessionManager:
    """Manages cross-turn browser state, tab context, and conversational continuity."""

    def __init__(self):
        self._state = BrowserSessionState()
        self._cdp = CDPClient()

    def get_state(self) -> BrowserSessionState:
        """Returns current session state, refreshing from CDP or UI Automation if available."""
        self._sync_live_tab()
        return self._state

    def _sync_live_tab(self):
        """Attempts fast query of CDP to synchronize active tab and URL with 2.0s debounce."""
        now = time.time()
        if (now - getattr(self, "_last_sync_time", 0.0)) < 2.0:
            return
        self._last_sync_time = now

        if self._cdp.is_available():
            active = self._cdp.get_active_tab()
            if active:
                self._state.active_tab_id = active.get("id")
                url = active.get("url", "")
                if url and not url.startswith("chrome://"):
                    self._state.active_url = url
                    self._state.page_title = active.get("title", "")
                    parsed = urllib.parse.urlparse(url)
                    self._state.active_domain = parsed.netloc
                    # Derive site name (e.g. hianime.to -> hianime)
                    domain_parts = parsed.netloc.replace("www.", "").split(".")
                    if domain_parts:
                        self._state.active_site = domain_parts[0]

    def record_navigation(self, url: str, site_name: Optional[str] = None, browser: str = "chrome"):
        """Records a completed navigation event."""
        self._state.active_browser = browser
        self._state.active_url = url
        parsed = urllib.parse.urlparse(url)
        self._state.active_domain = parsed.netloc
        domain_parts = parsed.netloc.replace("www.", "").split(".")
        derived_site = domain_parts[0] if domain_parts else ""
        self._state.active_site = site_name or derived_site

        # Also store into last_site memory for follow-ups
        self._state.last_url = url
        self._state.last_site = self._state.active_site
        self._state.last_domain = self._state.active_domain
        self._state.last_action_timestamp = time.time()
        self._state.operation_cancelled = False
        logger.info(f"Recorded navigation: site='{self._state.active_site}', url='{url}'")

    def record_search(self, query: str, site_name: Optional[str] = None, url: Optional[str] = None):
        """Records a completed search query."""
        self._state.last_search_query = query
        if site_name:
            self._state.last_site = site_name
        if url:
            self._state.last_url = url
            parsed = urllib.parse.urlparse(url)
            self._state.last_domain = parsed.netloc
        self._state.last_action_timestamp = time.time()
        self._state.operation_cancelled = False
        logger.info(f"Recorded search: query='{query}', site='{self._state.last_site}'")

    def cancel_operation(self):
        """Signals active long-running browser operation to stop immediately."""
        self._state.operation_cancelled = True
        logger.info("Browser operation cancellation signaled.")

    def is_cancelled(self) -> bool:
        return self._state.operation_cancelled

    def reset_cancellation(self):
        self._state.operation_cancelled = False

    def is_website_already_open(self, target_domain_or_url: str) -> Optional[Dict[str, Any]]:
        """Checks if a tab with the target domain is already open in Chrome via CDP."""
        if not target_domain_or_url:
            return None

        clean_target = target_domain_or_url.lower().replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
        if self._cdp.is_available():
            tabs = self._cdp.list_tabs()
            for tab in tabs:
                tab_url = tab.get("url", "").lower().replace("https://", "").replace("http://", "").replace("www.", "")
                if clean_target in tab_url:
                    return tab
        return None

    def get_context_for_parser(self) -> Dict[str, Any]:
        """Returns session context dictionary suitable for BrowserIntentParser."""
        self._sync_live_tab()
        return {
            "active_browser": self._state.active_browser,
            "active_url": self._state.active_url,
            "active_domain": self._state.active_domain,
            "active_site": self._state.active_site,
            "last_site": self._state.last_site,
            "last_url": self._state.last_url,
            "last_domain": self._state.last_domain,
            "last_query": self._state.last_search_query
        }


# Global singleton browser session manager
browser_session_manager = BrowserSessionManager()
