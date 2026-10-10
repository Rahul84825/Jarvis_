import os
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
import subprocess
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.CDPChrome")

DEFAULT_CDP_PORT = 9222

class CDPChromeManager:
    """Direct Chrome DevTools Protocol (CDP) connection manager.
    Connects to the user's running Chrome browser to query tabs, inspect DOM,
    and capture screenshots with real session cookies.
    """

    def __init__(self, port: int = DEFAULT_CDP_PORT):
        self.port = port
        self.endpoint = f"http://127.0.0.1:{self.port}"

    def is_available(self) -> bool:
        """Checks if Chrome is listening on the CDP debugging endpoint."""
        try:
            req = urllib.request.Request(f"{self.endpoint}/json/version", headers={"User-Agent": "Jarvis-CDP"})
            with urllib.request.urlopen(req, timeout=1.5) as response:
                return response.status == 200
        except Exception:
            return False

    def list_tabs(self) -> List[Dict[str, Any]]:
        """Returns all open page tabs in Chrome."""
        try:
            req = urllib.request.Request(f"{self.endpoint}/json/list", headers={"User-Agent": "Jarvis-CDP"})
            with urllib.request.urlopen(req, timeout=2.0) as response:
                data = json.loads(response.read().decode("utf-8"))
                return [t for t in data if t.get("type") == "page"]
        except Exception as e:
            logger.debug(f"Could not list Chrome tabs: {e}")
            return []

    def get_active_tab(self) -> Optional[Dict[str, Any]]:
        """Finds the most recently active web tab."""
        tabs = self.list_tabs()
        return tabs[0] if tabs else None

    def get_active_page_info(self) -> Dict[str, str]:
        """Returns title and URL of the active tab."""
        tab = self.get_active_tab()
        if tab:
            return {
                "title": tab.get("title", ""),
                "url": tab.get("url", ""),
                "id": tab.get("id", "")
            }
        return {"error": "Chrome DevTools is not reachable or no active tabs are open."}

    def open_tab(self, url: str) -> Dict[str, Any]:
        """Opens a new tab in Chrome with the given URL."""
        if not self.is_available():
            # Fallback to system default browser launch
            import webbrowser
            webbrowser.open(url)
            return {"status": "success", "note": "Launched via system browser fallback"}

        try:
            encoded_url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=")
            req = urllib.request.Request(f"{self.endpoint}/json/new?{encoded_url}", method="PUT")
            with urllib.request.urlopen(req, timeout=3.0) as response:
                data = json.loads(response.read().decode("utf-8"))
                return {"status": "success", "tab_id": data.get("id"), "url": data.get("url")}
        except Exception as e:
            logger.error(f"Failed to open tab via CDP: {e}")
            import webbrowser
            webbrowser.open(url)
            return {"status": "success", "note": f"Fallback opened: {e}"}

    def capture_active_tab_screenshot(self, output_path: str = "screenshots/chrome_tab.png") -> Dict[str, Any]:
        """Takes a screenshot of the active tab using CDP or OS fallback."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        try:
            # Fallback to pyautogui / pillow screenshot
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
            screenshot.save(output_path)
            return {"status": "success", "path": output_path}
        except Exception as e:
            return {"status": "error", "message": str(e)}


cdp_chrome = CDPChromeManager()
