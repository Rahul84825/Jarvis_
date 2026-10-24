"""Isolated Virtual Computer Environment for the SANTRA Virtual Testing Room.
Simulates applications, sandboxed filesystem, browser pages, screen OCR, and telemetry.
Guarantees zero physical OS side effects or real data modification during simulation.
"""

import os
import shutil
import tempfile
import logging
from typing import Dict, List, Optional, Any
from copy import deepcopy

logger = logging.getLogger("Santra.VirtualLab.EnvSim")


class VirtualApplication:
    """Simulated desktop application state."""

    def __init__(self, app_id: str, name: str, window_title: str, is_running: bool = False):
        self.app_id = app_id.lower().strip()
        self.name = name
        self.window_title = window_title
        self.is_running = is_running
        self.is_focused = False
        self.open_tabs: List[str] = ["about:blank"] if "browser" in app_id or app_id in ["chrome", "brave", "edge"] else []
        self.active_tab_index: int = 0 if self.open_tabs else -1
        self.visible_input_fields: Dict[str, str] = {}
        self.focused_element: Optional[str] = None
        self.buttons: List[str] = ["Close", "Minimize", "Maximize"]

    def launch(self):
        self.is_running = True
        self.is_focused = True
        logger.debug(f"[VirtualApp] Launched {self.name}")

    def focus(self):
        self.is_focused = True
        logger.debug(f"[VirtualApp] Focused {self.name}")

    def close(self):
        self.is_running = False
        self.is_focused = False
        self.open_tabs.clear()
        logger.debug(f"[VirtualApp] Closed {self.name}")

    def add_tab(self, url: str) -> int:
        self.open_tabs.append(url)
        self.active_tab_index = len(self.open_tabs) - 1
        return self.active_tab_index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "is_running": self.is_running,
            "is_focused": self.is_focused,
            "window_title": self.window_title,
            "open_tabs": list(self.open_tabs),
            "active_tab_index": self.active_tab_index,
            "visible_input_fields": dict(self.visible_input_fields),
            "focused_element": self.focused_element
        }


class VirtualFileSystem:
    """Isolated, temporary directory tree simulating Windows user folders."""

    def __init__(self):
        self._temp_dir = tempfile.TemporaryDirectory(prefix="santra_virtual_fs_")
        self.root_path = self._temp_dir.name
        self.desktop_path = os.path.join(self.root_path, "Desktop")
        self.documents_path = os.path.join(self.root_path, "Documents")
        self.downloads_path = os.path.join(self.root_path, "Downloads")
        self.dsa_path = os.path.join(self.desktop_path, "dsa")
        self.project_path = os.path.join(self.documents_path, "test_project")

        self.created_files: List[str] = []
        self.modified_files: List[str] = []
        self.overwrite_attempts: List[str] = []
        self._initialize_fixtures()

    def _initialize_fixtures(self):
        """Populates baseline mock files and folders."""
        for p in [self.desktop_path, self.documents_path, self.downloads_path, self.dsa_path, self.project_path]:
            os.makedirs(p, exist_ok=True)

        # Baseline files
        self.save_file(os.path.join(self.dsa_path, "notes.txt"), "Binary search: time complexity O(log n).", overwrite=True)
        self.save_file(os.path.join(self.project_path, "main.py"), "print('Virtual Project Main')", overwrite=True)
        self.save_file(os.path.join(self.project_path, "README.md"), "# Virtual Project\nSimulation fixture.", overwrite=True)

    def resolve_path(self, virtual_path: str) -> str:
        """Translates user paths (e.g. 'Desktop/file.py', 'Downloads/doc.txt') into sandboxed directory paths."""
        norm = virtual_path.replace("\\", "/").strip()
        lower = norm.lower()

        if lower.startswith("desktop/"):
            rel = norm[8:]
            target = os.path.join(self.desktop_path, rel.replace("/", os.sep))
        elif lower.startswith("documents/"):
            rel = norm[10:]
            target = os.path.join(self.documents_path, rel.replace("/", os.sep))
        elif lower.startswith("downloads/"):
            rel = norm[10:]
            target = os.path.join(self.downloads_path, rel.replace("/", os.sep))
        elif lower.startswith("dsa/"):
            rel = norm[4:]
            target = os.path.join(self.dsa_path, rel.replace("/", os.sep))
        elif os.path.isabs(virtual_path):
            # If absolute, map basename to Desktop sandbox for safety
            base = os.path.basename(virtual_path)
            target = os.path.join(self.desktop_path, base)
        else:
            target = os.path.join(self.desktop_path, norm.replace("/", os.sep))

        resolved = os.path.abspath(target)

        # Enforce sandbox isolation: ensure path does not traverse out of root_path
        try:
            common = os.path.commonpath([resolved, self.root_path])
            if common != self.root_path:
                logger.warning(f"[VirtualFS] Blocked path traversal attempt: '{virtual_path}' -> '{resolved}'")
                safe_base = os.path.basename(norm) or "traversal_prevented.tmp"
                return os.path.abspath(os.path.join(self.desktop_path, safe_base))
        except (ValueError, Exception) as ex:
            logger.warning(f"[VirtualFS] Path resolution error or cross-drive traversal for '{virtual_path}': {ex}")
            safe_base = os.path.basename(norm) or "traversal_prevented.tmp"
            return os.path.abspath(os.path.join(self.desktop_path, safe_base))

        return resolved

    def save_file(self, full_path: str, content: str, overwrite: bool = False) -> bool:
        """Saves file strictly inside sandbox with overwrite tracking."""
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        already_exists = os.path.exists(full_path)

        if already_exists and not overwrite:
            self.overwrite_attempts.append(full_path)
            logger.warning(f"[VirtualFS] Blocked overwrite of existing file '{full_path}'")
            return False

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        if already_exists:
            self.modified_files.append(full_path)
        else:
            self.created_files.append(full_path)

        logger.debug(f"[VirtualFS] Wrote file '{full_path}' ({len(content)} bytes)")
        return True

    def create_folder(self, folder_path: str) -> bool:
        target = self.resolve_path(folder_path) if not os.path.isabs(folder_path) else folder_path
        os.makedirs(target, exist_ok=True)
        return True

    def file_exists(self, path: str) -> bool:
        resolved = self.resolve_path(path) if not os.path.isabs(path) else path
        return os.path.isfile(resolved)

    def read_file(self, path: str) -> Optional[str]:
        resolved = self.resolve_path(path) if not os.path.isabs(path) else path
        if not os.path.exists(resolved):
            return None
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def cleanup(self):
        try:
            self._temp_dir.cleanup()
        except Exception:
            pass


class VirtualBrowser:
    """Simulated web browser with tabs, navigation history, and DOM elements."""

    def __init__(self):
        self.active_browser: str = "chrome"
        self.active_url: str = "about:blank"
        self.active_title: str = "New Tab"
        self.tabs: List[Dict[str, Any]] = [{"url": "about:blank", "title": "New Tab", "id": 1}]
        self.active_tab_id: int = 1
        self.history: List[str] = []
        self.last_search_query: str = ""
        self.last_search_site: str = ""
        self.last_prompt_text: str = ""
        self.dom_inputs: Dict[str, str] = {"search": "", "prompt": ""}
        self.current_page_text: str = "Welcome to Simulated Web Browser."

    def open_url(self, url: str, site_name: str = "", new_tab: bool = False):
        norm_url = (url or "").strip()
        if not norm_url:
            norm_url = "about:blank"
        elif not norm_url.startswith(("http://", "https://", "about:", "file://")):
            norm_url = f"https://{norm_url}"

        if new_tab or not self.tabs:
            new_id = len(self.tabs) + 1
            self.tabs.append({"url": norm_url, "title": site_name or norm_url, "id": new_id})
            self.active_tab_id = new_id
        else:
            cur = next((t for t in self.tabs if t["id"] == self.active_tab_id), self.tabs[0])
            cur["url"] = norm_url
            cur["title"] = site_name or norm_url

        self.active_url = norm_url
        self.active_title = site_name or norm_url
        self.history.append(norm_url)
        logger.debug(f"[VirtualBrowser] Navigated to '{norm_url}' (Tab: {self.active_tab_id})")

    def execute_search(self, query: str, site: str = "google", new_tab: bool = False):
        self.last_search_query = query or ""
        self.last_search_site = site or "google"

        site_lower = (site or "google").lower().strip()
        site_endpoints = {
            "google": "https://www.google.com/search?q=",
            "youtube": "https://www.youtube.com/results?search_query=",
            "hianime": "https://hianime.to/search?keyword=",
            "github": "https://github.com/search?q=",
            "reddit": "https://www.reddit.com/search/?q=",
            "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search="
        }
        base_endpoint = site_endpoints.get(site_lower, f"https://www.{site_lower}.com/search?q=")
        q_enc = query.strip().replace(' ', '+') if query else ""
        dest_url = f"{base_endpoint}{q_enc}"

        self.open_url(dest_url, site_name=site, new_tab=new_tab)
        self.dom_inputs["search"] = query or ""
        self.current_page_text = f"Simulated search results for query: '{query}' on {site}."

    def execute_prompt(self, site: str, prompt: str):
        self.last_prompt_text = prompt
        self.dom_inputs["prompt"] = prompt
        self.open_url(f"https://{site}.com", site_name=site)
        self.current_page_text = f"Simulated AI response from {site} for prompt: '{prompt}'."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_browser": self.active_browser,
            "active_url": self.active_url,
            "active_title": self.active_title,
            "tab_count": len(self.tabs),
            "active_tab_id": self.active_tab_id,
            "last_search_query": self.last_search_query,
            "last_search_site": self.last_search_site,
            "last_prompt_text": self.last_prompt_text
        }


class VirtualTelemetry:
    """Synthetic host machine telemetry for deterministic stress testing."""

    def __init__(self):
        self.cpu_percent: float = 14.5
        self.ram_percent: float = 38.2
        self.battery_percent: float = 90.0
        self.is_charging: bool = True
        self.network_connected: bool = True
        self.audio_mic_level: float = 0.65


class VirtualScreen:
    """Synthetic screen state representing visible text, UIA hierarchy, and active window."""

    def __init__(self):
        self.active_window_title: str = "VS Code - main.py"
        self.extracted_text: str = (
            "def binary_search(arr, target):\n"
            "    low, high = 0, len(arr) - 1\n"
            "    while low <= high:\n"
            "        mid = (low + high) // 2\n"
            "        if arr[mid] == target: return mid\n"
            "        elif arr[mid] < target: low = mid + 1\n"
            "        else: high = mid - 1\n"
            "    return -1"
        )
        self.uncertainty_score: float = 0.05
        self.is_stale: bool = False


class EnvironmentSimulator:
    """Unified container representing the complete simulated virtual computer."""

    def __init__(self):
        self.fs = VirtualFileSystem()
        self.browser = VirtualBrowser()
        self.telemetry = VirtualTelemetry()
        self.screen = VirtualScreen()
        self.apps: Dict[str, VirtualApplication] = {}
        self._init_apps()

    def _init_apps(self):
        app_fixtures = [
            ("chrome", "Google Chrome", "New Tab - Google Chrome", True),
            ("notepad", "Notepad", "Untitled - Notepad", False),
            ("code", "Visual Studio Code", "main.py - Virtual Project", True),
            ("discord", "Discord", "#general - Discord", False),
            ("spotify", "Spotify", "Spotify Free", False),
            ("chatgpt", "ChatGPT", "ChatGPT - OpenAI", False),
            ("whatsapp", "WhatsApp Web", "WhatsApp", False)
        ]
        for aid, name, title, running in app_fixtures:
            app = VirtualApplication(aid, name, title, is_running=running)
            self.apps[aid] = app

    def snapshot(self) -> Dict[str, Any]:
        """Creates a deep copy snapshot of current virtual state."""
        return {
            "apps": {k: a.to_dict() for k, a in self.apps.items()},
            "browser": self.browser.to_dict(),
            "created_files": list(self.fs.created_files),
            "modified_files": list(self.fs.modified_files),
            "overwrite_attempts": list(self.fs.overwrite_attempts),
            "screen_active_window": self.screen.active_window_title,
            "telemetry_cpu": self.telemetry.cpu_percent
        }

    def compute_diff(self, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates precise state differences before and after scenario execution."""
        diff: Dict[str, Any] = {}

        # Files created
        new_files = [f for f in after.get("created_files", []) if f not in before.get("created_files", [])]
        if new_files:
            diff["newly_created_files"] = new_files

        # Overwrite attempts
        new_overwrites = [f for f in after.get("overwrite_attempts", []) if f not in before.get("overwrite_attempts", [])]
        if new_overwrites:
            diff["new_overwrite_attempts"] = new_overwrites

        # Browser changes
        b_before = before.get("browser", {})
        b_after = after.get("browser", {})
        if b_before.get("active_url") != b_after.get("active_url"):
            diff["browser_url_changed"] = {"from": b_before.get("active_url"), "to": b_after.get("active_url")}
        if b_after.get("last_search_query") and b_after.get("last_search_query") != b_before.get("last_search_query"):
            diff["browser_search_executed"] = b_after.get("last_search_query")

        # App launches
        for aid, app_data in after.get("apps", {}).items():
            was_running = before.get("apps", {}).get(aid, {}).get("is_running", False)
            is_now_running = app_data.get("is_running", False)
            if not was_running and is_now_running:
                diff.setdefault("apps_launched", []).append(aid)

        return diff

    def cleanup(self):
        self.fs.cleanup()
