import os
import re
import json
import time
import logging
import psutil
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from config import config
from core.platform.platform_manager import platform_manager
from core.os.cdp_client import CDPClient

logger = logging.getLogger("Jarvis.BrowserManager")

class BrowserManager:
    """Native Cross-Platform Browser Control & Web Search Subsystem Manager for Windows and Ubuntu Linux.
    Provides browser discovery, preferred/fallback priority management, search provider URL synthesis,
    query encoding, site links registry, tab lifecycle, Chrome DevTools Protocol (CDP) client,
    and media controls with strict window focus verification and truthful failure reporting.
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
        self.cdp = CDPClient()

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

    def open_browser(self, browser_name: str = "default", url: str = None, enable_cdp: bool = False) -> Dict[str, Any]:
        """Launches specified or preferred browser with optional URL and secure CDP port startup."""
        resolved, err = self.resolve_target_browser(browser_name)
        if not resolved:
            return {"success": False, "message": err or "I couldn't find a supported browser."}

        cdp_flag_enabled = enable_cdp or bool(self.browser_config.get("enable_cdp", False))

        if cdp_flag_enabled and resolved in ["chrome", "chromium"] and os.name == "nt":
            try:
                import subprocess
                from core.platform.windows_platform import WindowsPlatform
                win = WindowsPlatform()
                exec_path = win._probe_browser_executable(resolved)
                if exec_path:
                    # Secure restriction: CDP bound strictly to local port 9222
                    cmd = [exec_path, "--remote-debugging-port=9222"]
                    if url:
                        cmd.append(url)
                    subprocess.Popen(cmd)
                    return {"success": True, "cdp_enabled": True, "message": f"Opening {resolved.title()} with CDP on 127.0.0.1:9222."}
            except Exception as ce:
                logger.warning(f"Could not launch browser with CDP flag ({ce}), falling back to standard launch.")

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

        if prov_key not in self.search_providers and prov_key not in self.DEFAULT_SEARCH_PROVIDERS:
            return {"success": False, "operation": "web_search", "message": f"Search provider '{prov_key}' is not configured."}

        target_url = self.build_search_url(prov_key, query)
        resolved_browser, err = self.resolve_target_browser(browser_name)

        if not resolved_browser:
            return {"success": False, "operation": "web_search", "message": err or "The search service is currently unavailable."}

        logger.info(f"[BROWSER] OS: {platform_manager.os_name} | Requested Browser: {browser_name} | Selected Browser: {resolved_browser} | Provider: {prov_key.title()} | Query: '{query}' | URL: {target_url} | Result: PENDING")

        try:
            # If CDP is available and an existing tab for this provider (e.g. YouTube) is open, activate it
            if self.cdp.is_available() and prov_key in ("youtube", "google"):
                try:
                    tabs = self.cdp.list_tabs()
                    match_domain = "youtube.com" if prov_key == "youtube" else "google.com"
                    existing_tab = next((t for t in tabs if match_domain in (t.get("url") or "").lower()), None)
                    if existing_tab and existing_tab.get("id"):
                        logger.info(f"[BROWSER] Reusing existing {prov_key} tab (ID: {existing_tab['id']}) for search navigation.")
                        self.cdp.activate_tab(existing_tab["id"])
                        self.focus_browser(resolved_browser if resolved_browser != "default" else "chrome")
                except Exception as cdpe:
                    logger.debug(f"[BROWSER] CDP tab check ignored: {cdpe}")

            success = platform_manager.open_browser(resolved_browser, url=target_url)
            prov_display = "YouTube" if prov_key == "youtube" else ("Stack Overflow" if prov_key == "stackoverflow" else ("GitHub" if prov_key == "github" else prov_key.title()))

            if success:
                logger.info(f"[BROWSER_RESULT] Result: SUCCESS")
                return {
                    "success": True,
                    "operation": "web_search",
                    "provider": prov_key,
                    "query": query,
                    "url": target_url,
                    "browser": resolved_browser,
                    "message": f"Searching {prov_display}. I opened {prov_display} search results for '{query}'."
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

    def open_new_chrome_tab(self, url: str = None) -> Dict[str, Any]:
        """Opens a new tab in the running Chrome session, preserving existing tabs."""
        try:
            logger.info(f"[BROWSER] Requesting new Chrome tab (URL: {url}).")
            success = platform_manager.platform.open_new_browser_tab("chrome", url=url)
            if success:
                return {"success": True, "message": "Opening a new tab."}
            return {"success": False, "message": "I couldn't open a new tab."}
        except Exception as e:
            logger.error(f"[BROWSER_ERROR] Failed to open new Chrome tab: {e}")
            return {"success": False, "message": "I couldn't open a new tab."}

    def open_new_chrome_window(self, url: str = None) -> Dict[str, Any]:
        """Opens a brand new independent Chrome window, preserving existing windows and tabs."""
        try:
            logger.info(f"[BROWSER] Requesting new Chrome window (URL: {url}).")
            success = platform_manager.platform.open_new_browser_window("chrome", url=url)
            if success:
                return {"success": True, "message": "Opening another Chrome window."}
            return {"success": False, "message": "I couldn't open another Chrome window."}
        except Exception as e:
            logger.error(f"[BROWSER_ERROR] Failed to open new Chrome window: {e}")
            return {"success": False, "message": "I couldn't open another Chrome window."}

    # ==========================================
    # BROWSER LIFECYCLE & PROCESS MANAGEMENT
    # ==========================================
    def is_chrome_running(self) -> bool:
        """Detects whether Google Chrome is actively running on the host system."""
        try:
            for proc in psutil.process_iter(['name']):
                pname = (proc.info.get('name') or '').lower()
                if 'chrome' in pname:
                    return True
        except Exception as e:
            logger.debug(f"[BROWSER] Process scan error: {e}")
        return False

    def is_any_browser_running(self) -> bool:
        """Detects whether any supported desktop browser process is actively running."""
        browser_names = ["chrome", "msedge", "edge", "firefox", "brave", "opera"]
        try:
            for proc in psutil.process_iter(['name']):
                pname = (proc.info.get('name') or '').lower()
                if any(b in pname for b in browser_names):
                    return True
        except Exception:
            pass
        return False

    def focus_browser(self, target: str = "chrome") -> bool:
        """Brings running browser window to foreground with verification."""
        from modules.system import window_control
        switched = window_control.switch_to_window(target)
        if not switched:
            switched = window_control.switch_to_window("google chrome")
        if not switched:
            switched = window_control.switch_to_window("edge")
        if not switched:
            switched = window_control.switch_to_window("firefox")
        return bool(switched)

    def get_browser_status(self) -> Dict[str, Any]:
        """Reports browser lifecycle, focus state, and CDP connection status."""
        chrome_running = self.is_chrome_running()
        cdp_connected = self.cdp.is_available()
        return {
            "success": True,
            "chrome_running": chrome_running,
            "cdp_connected": cdp_connected,
            "preferred_browser": self.preferred_browser,
            "message": f"Chrome is {'running' if chrome_running else 'not running'}. CDP debugging is {'connected' if cdp_connected else 'offline'}."
        }

    # ==========================================
    # KEYBOARD & SHORTCUT AUTOMATION (VERIFIED)
    # ==========================================
    def _send_shortcut(self, ctrl: bool = False, shift: bool = False, alt: bool = False, vk: int = 0) -> bool:
        """Sends native keyboard shortcut to the focused browser window.
        Strict verification: Aborts immediately if browser window is not verified as focused,
        preventing accidental input into other applications.
        """
        if os.name != "nt":
            return False

        # Verify browser window focus before injecting keystrokes
        if not self.focus_browser():
            logger.warning("[BROWSER_SHORTCUT] Suppressed keystroke: browser window could not be confirmed as focused.")
            return False

        try:
            import ctypes
            KEYEVENTF_KEYUP = 0x0002
            VK_CONTROL = 0x11
            VK_SHIFT = 0x10
            VK_MENU = 0x12  # Alt

            if ctrl: ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
            if shift: ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
            if alt: ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)

            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

            if alt: ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            if shift: ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
            if ctrl: ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            logger.error(f"[BROWSER_SHORTCUT] Failed to send shortcut: {e}")
            return False

    # ==========================================
    # TAB & WINDOW MANAGEMENT
    # ==========================================
    def new_tab(self, url: str = None) -> Dict[str, Any]:
        """Opens a new browser tab with optional URL."""
        if url:
            return self.open_url(url)
        # Check CDP first
        if self.cdp.is_available():
            tab_info = self.cdp.new_tab(url or "")
            if tab_info:
                return {"success": True, "message": "Opened new browser tab via CDP."}

        # Fallback to focused window shortcut Ctrl+T (0x54)
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        success = self._send_shortcut(ctrl=True, vk=0x54)
        return {"success": success, "message": "Opened new tab in browser." if success else "Failed to open new tab."}

    ORDINAL_MAP = {
        "first": 0, "1st": 0,
        "second": 1, "2nd": 1,
        "third": 2, "3rd": 2,
        "fourth": 3, "4th": 3,
        "fifth": 4, "5th": 4,
        "sixth": 5, "6th": 5,
        "last": -1
    }

    def _resolve_ordinal(self, query: str) -> Optional[int]:
        clean = (query or "").lower().strip()
        if clean in self.ORDINAL_MAP:
            return self.ORDINAL_MAP[clean]
        # Check digit string
        m = re.match(r"^(\d+)(?:st|nd|rd|th)?$", clean)
        if m:
            num = int(m.group(1))
            return (num - 1) if num > 0 else 0
        return None

    def find_matching_tabs(self, target_query: str) -> List[Dict[str, Any]]:
        """Finds open CDP tabs matching title or URL query with exact and fuzzy matching."""
        if not self.cdp.is_available() or not target_query:
            return []
        clean_q = target_query.lower().strip()
        # Clean prefix and suffix artifacts
        clean_q = re.sub(r"^(?:titled|showing|named|called|with|for|my|the|a)\s+", "", clean_q, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r"\s+(?:chrome\s+)?tab$", "", clean_q, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r"^(?:my\s+|the\s+)", "", clean_q, flags=re.IGNORECASE).strip()

        tabs = self.cdp.list_tabs()
        if not tabs:
            return []

        # 1. Exact match check (title equals or URL exact domain/path)
        exact_matches = []
        for t in tabs:
            title = (t.get("title") or "").lower().strip()
            url = (t.get("url") or "").lower().strip()
            if clean_q == title or clean_q in url.split("/"):
                exact_matches.append(t)
        if len(exact_matches) == 1:
            return exact_matches

        # 2. Substring matching
        matches = []
        for t in tabs:
            title = (t.get("title") or "").lower()
            url = (t.get("url") or "").lower()
            if clean_q in title or clean_q in url:
                matches.append(t)

        # 3. Token-based fallback if no substring match found
        if not matches:
            tokens = [tok for tok in re.split(r"\s+", clean_q) if len(tok) >= 3]
            if tokens:
                for t in tabs:
                    title = (t.get("title") or "").lower()
                    url = (t.get("url") or "").lower()
                    if all(tok in title or tok in url for tok in tokens):
                        matches.append(t)

        return matches

    def close_tab(self, target: str = None, tab_id: str = None) -> Dict[str, Any]:
        """Closes the active, ordinal, or specifically named browser tab reliably via CDP or window shortcut."""
        # 1. Direct tab ID via CDP
        if tab_id and self.cdp.is_available():
            closed = self.cdp.close_tab(tab_id)
            if closed:
                verified = self.cdp.verify_tab_closed(tab_id)
                return {"success": True, "verified": verified, "tab_id": tab_id, "message": f"Closed browser tab {tab_id}."}
            return {"success": False, "message": f"Failed to close browser tab {tab_id}."}

        # 2. Check for ordinal/positional tab request (e.g. "second", "2nd", "tab 2")
        ordinal_idx = self._resolve_ordinal(target)
        if ordinal_idx is not None:
            if self.cdp.is_available():
                tabs = self.cdp.list_tabs()
                if not tabs:
                    return {"success": False, "message": "No open tabs found in Chrome."}
                total = len(tabs)
                if (0 <= ordinal_idx < total) or (ordinal_idx == -1):
                    target_tab = tabs[ordinal_idx]
                    tid = target_tab.get("id")
                    title = target_tab.get("title", "Untitled")
                    closed = self.cdp.close_tab(tid)
                    if closed:
                        verified = self.cdp.verify_tab_closed(tid)
                        pos_label = target.strip() if target else f"#{ordinal_idx + 1}"
                        return {"success": True, "verified": verified, "tab_id": tid, "message": f"Closed the {pos_label} Chrome tab ('{title}')."}
                    return {"success": False, "message": f"Failed to close the {target} Chrome tab."}
                else:
                    return {
                        "success": False,
                        "message": f"Chrome only has {total} open tab(s). Could not find the {target} tab."
                    }
            else:
                return {
                    "success": False,
                    "cdp_required": True,
                    "message": "Closing tabs by position requires Chrome remote debugging. Launch Chrome with '--remote-debugging-port=9222' to enable positional tab control."
                }

        # 3. Targeted tab resolution by name / query
        is_active_target = not target or target.lower().strip() in ["active", "current", "chrome", "this", "current chrome", "active chrome", ""]
        if not is_active_target:
            clean_target = re.sub(r"^(?:titled|showing|named|called|with|for|my|the)\s+", "", target, flags=re.IGNORECASE).strip()
            clean_target = re.sub(r"\s+(?:chrome\s+)?tab$", "", clean_target, flags=re.IGNORECASE).strip()
            clean_target = re.sub(r"^(?:my\s+|the\s+)", "", clean_target, flags=re.IGNORECASE).strip()

            if self.cdp.is_available():
                matches = self.find_matching_tabs(clean_target)
                if len(matches) == 1:
                    target_tab = matches[0]
                    tid = target_tab.get("id")
                    title = target_tab.get("title", clean_target)
                    closed = self.cdp.close_tab(tid)
                    if closed:
                        verified = self.cdp.verify_tab_closed(tid)
                        return {"success": True, "verified": verified, "tab_id": tid, "message": f"Closed the '{title}' tab."}
                    return {"success": False, "message": f"Failed to close the '{title}' tab."}
                elif len(matches) > 1:
                    titles = [f"'{t.get('title', 'Untitled')}'" for t in matches[:3]]
                    return {
                        "success": False,
                        "ambiguous": True,
                        "disambiguation_required": True,
                        "candidates": [t.get("title") for t in matches],
                        "message": f"Multiple tabs matched '{clean_target}': {', '.join(titles)}. Please specify which tab to close."
                    }
                else:
                    return {"success": False, "message": f"No tab matching '{clean_target}' was found in Chrome."}
            else:
                return {
                    "success": False,
                    "cdp_required": True,
                    "message": "Controlling background tabs by name requires Chrome with remote debugging. Launch Chrome with '--remote-debugging-port=9222' to enable targeted tab control."
                }

        # 4. Active / current tab closing
        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            if active_tab and active_tab.get("id"):
                tid = active_tab.get("id")
                title = active_tab.get("title", "Untitled")
                closed = self.cdp.close_tab(tid)
                if closed:
                    verified = self.cdp.verify_tab_closed(tid)
                    return {"success": True, "verified": verified, "tab_id": tid, "message": f"Closed active Chrome tab '{title}'."}
                return {"success": False, "message": f"Failed to close active Chrome tab '{title}'."}
            else:
                return {"success": False, "message": "No open tabs found in Chrome."}

        # Fallback to keyboard shortcut Ctrl+W (0x57) in focused window if CDP is offline
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        success = self._send_shortcut(ctrl=True, vk=0x57)
        return {"success": success, "message": "Closed active browser tab." if success else "Failed to close tab."}

    def switch_tab(self, target: str = None) -> Dict[str, Any]:
        """Switches to a specifically named tab via CDP, or cycles tabs."""
        if target and target.lower() not in ["active", "current", "chrome", "next", ""]:
            clean_target = re.sub(r"\s+tab$", "", target, flags=re.IGNORECASE).strip()
            if self.cdp.is_available():
                matches = self.find_matching_tabs(clean_target)
                if len(matches) == 1:
                    tid = matches[0].get("id")
                    title = matches[0].get("title", clean_target)
                    activated = self.cdp.activate_tab(tid)
                    if activated:
                        self.focus_browser()
                        return {"success": True, "message": f"Switched to '{title}' tab."}
                    return {"success": False, "message": f"Failed to switch to '{title}' tab."}
                elif len(matches) > 1:
                    titles = [f"'{t.get('title', 'Untitled')}'" for t in matches[:3]]
                    return {
                        "success": False,
                        "ambiguous": True,
                        "message": f"Multiple tabs matched '{clean_target}': {', '.join(titles)}. Please specify which tab to switch to."
                    }
                else:
                    return {"success": False, "message": f"No tab matching '{clean_target}' was found in Chrome."}
            else:
                return {
                    "success": False,
                    "cdp_required": True,
                    "message": f"Switching to specific background tabs requires Chrome with remote debugging. Launch Chrome with '--remote-debugging-port=9222' to enable targeted tab switching."
                }
        return self.next_tab()

    def list_open_tabs(self) -> Dict[str, Any]:
        """Lists currently open Chrome tabs via CDP."""
        if not self.cdp.is_available():
            return {
                "success": False,
                "message": "Listing tabs requires Chrome running with remote debugging. Launch Chrome with '--remote-debugging-port=9222' to enable tab discovery."
            }
        tabs = self.cdp.list_tabs()
        if not tabs:
            return {"success": True, "tabs": [], "message": "No open tabs found in Chrome."}
        titles = [t.get("title", "Untitled") for t in tabs]
        msg = f"You have {len(tabs)} open tabs: " + ", ".join(f"'{title}'" for title in titles[:5])
        if len(tabs) > 5:
            msg += f", and {len(tabs) - 5} more."
        return {"success": True, "tabs": tabs, "message": msg}

    def reopen_closed_tab(self) -> Dict[str, Any]:
        """Reopens the last closed browser tab using Ctrl+Shift+T."""
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        # Ctrl+Shift+T (0x54)
        success = self._send_shortcut(ctrl=True, shift=True, vk=0x54)
        return {"success": success, "message": "Reopened last closed tab." if success else "Failed to reopen tab."}

    def next_tab(self) -> Dict[str, Any]:
        """Switches to the next browser tab (Ctrl+Tab)."""
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        # VK_TAB = 0x09
        success = self._send_shortcut(ctrl=True, vk=0x09)
        return {"success": success, "message": "Switched to next tab." if success else "Failed to switch tab."}

    def prev_tab(self) -> Dict[str, Any]:
        """Switches to previous browser tab (Ctrl+Shift+Tab)."""
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        success = self._send_shortcut(ctrl=True, shift=True, vk=0x09)
        return {"success": success, "message": "Switched to previous tab." if success else "Failed to switch tab."}

    def reload_page(self) -> Dict[str, Any]:
        """Reloads the active webpage (Ctrl+R or F5)."""
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        # F5 = 0x74
        success = self._send_shortcut(vk=0x74)
        return {"success": success, "message": "Page refreshed." if success else "Failed to reload page."}

    def go_back(self) -> Dict[str, Any]:
        """Navigates back in browser history (Alt+Left)."""
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        # VK_LEFT = 0x25
        success = self._send_shortcut(alt=True, vk=0x25)
        return {"success": success, "message": "Navigated back." if success else "Failed to navigate back."}

    def go_forward(self) -> Dict[str, Any]:
        """Navigates forward in browser history (Alt+Right)."""
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        # VK_RIGHT = 0x27
        success = self._send_shortcut(alt=True, vk=0x27)
        return {"success": success, "message": "Navigated forward." if success else "Failed to navigate forward."}

    def toggle_fullscreen(self) -> Dict[str, Any]:
        """Toggles fullscreen mode (F11)."""
        if not self.focus_browser():
            return {"success": False, "verified": False, "message": "No active browser window found or window could not be focused."}

        # F11 = 0x7A
        success = self._send_shortcut(vk=0x7A)
        return {"success": success, "message": "Toggled fullscreen." if success else "Failed to toggle fullscreen."}

    def open_downloads(self) -> Dict[str, Any]:
        """Opens browser downloads page."""
        return self.open_url("chrome://downloads")

    def open_history(self) -> Dict[str, Any]:
        """Opens browser history page."""
        return self.open_url("chrome://history")

    def open_multiple_urls(self, urls: List[str]) -> Dict[str, Any]:
        """Opens multiple URLs in separate tabs."""
        if not urls:
            return {"success": False, "message": "No URLs provided."}
        opened = 0
        for u in urls:
            res = self.open_url(u.strip())
            if res.get("success"):
                opened += 1
            time.sleep(0.2)
        return {
            "success": opened > 0,
            "count": opened,
            "message": f"Opened {opened} website{'s' if opened != 1 else ''} in browser tabs."
        }

    def list_tabs(self) -> Dict[str, Any]:
        """Lists active browser tabs via CDP or window enumeration."""
        if self.cdp.is_available():
            pages = self.cdp.list_tabs()
            if pages:
                titles = [p.get("title", "Untitled") for p in pages]
                return {
                    "success": True,
                    "tabs": pages,
                    "count": len(pages),
                    "message": f"Active Chrome tabs: {', '.join(titles[:4])}."
                }
        from modules.system import window_control
        windows = window_control.list_open_windows()
        browser_wins = [w for w in windows if any(b in w.lower() for b in ["chrome", "edge", "firefox", "brave"])]
        if browser_wins:
            return {
                "success": True,
                "tabs": [{"title": w} for w in browser_wins],
                "count": len(browser_wins),
                "message": f"Open browser windows: {', '.join(browser_wins[:4])}."
            }
        return {"success": True, "tabs": [], "count": 0, "message": "No browser windows detected."}

    # ==========================================
    # DOM INSPECTION & ELEMENT INTERACTION
    # ==========================================
    def inspect_page(self) -> Dict[str, Any]:
        """Inspects active browser webpage via CDP with verified reporting.
        Returns clear actionable status if CDP is unavailable.
        """
        return self.cdp.inspect_active_page()

    def click_element(self, selector: str) -> Dict[str, Any]:
        """Interacts with an element on the active page via CDP.
        Does not falsely report success or send global shortcuts when CDP is unavailable.
        """
        if not self.cdp.is_available():
            return {
                "success": False,
                "cdp_available": False,
                "message": "DOM element interaction requires Chrome DevTools Protocol (CDP). Launch Chrome with '--remote-debugging-port=9222' on localhost to enable DOM automation."
            }

        tab = self.cdp.get_active_tab()
        if not tab:
            return {"success": False, "message": "No active tab found via CDP to interact with."}

        return {
            "success": False,
            "cdp_available": True,
            "message": f"Element automation on '{selector}' requires explicit page automation script permissions."
        }

    # ==========================================
    # YOUTUBE PLAYBACK & MEDIA CONTROLS
    # ==========================================
    def youtube_control(self, action: str, value: Any = None) -> Dict[str, Any]:
        """Controls YouTube video playback within the active browser window with verified focus."""
        action_clean = action.lower().strip()

        if not self.focus_browser():
            return {
                "success": False,
                "action": action_clean,
                "verified": False,
                "message": "No active browser window found to execute media control."
            }

        time.sleep(0.05)

        if action_clean in ["play", "pause", "play_pause", "toggle"]:
            success = self._send_shortcut(vk=0x4B) or self._send_shortcut(vk=0x20)
            return {"success": success, "action": action_clean, "message": "Toggled video playback."}
        elif action_clean in ["forward", "skip", "seek_forward"]:
            success = self._send_shortcut(vk=0x4C)
            return {"success": success, "action": action_clean, "message": "Skipped forward 10 seconds."}
        elif action_clean in ["rewind", "back", "seek_backward"]:
            success = self._send_shortcut(vk=0x4A)
            return {"success": success, "action": action_clean, "message": "Rewound 10 seconds."}
        elif action_clean in ["mute", "unmute"]:
            success = self._send_shortcut(vk=0x4D)
            return {"success": success, "action": action_clean, "message": "Toggled video audio mute."}
        elif action_clean in ["fullscreen"]:
            success = self._send_shortcut(vk=0x46)
            return {"success": success, "action": action_clean, "message": "Toggled video fullscreen."}
        elif action_clean in ["captions", "subtitles"]:
            success = self._send_shortcut(vk=0x43)
            return {"success": success, "action": action_clean, "message": "Toggled video captions."}
        else:
            return {"success": False, "action": action_clean, "message": f"Unsupported YouTube control action: {action}."}

