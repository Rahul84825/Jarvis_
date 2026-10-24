"""Mock Tool and System Adapters for the SANTRA Virtual Testing Room.
Safely intercepts and redirects execution during Simulation Mode so no physical
OS changes, file overwrites, or paid API requests occur.
"""

import os
import logging
from typing import Dict, Any, Optional
from core.virtual_lab.environment_simulator import EnvironmentSimulator

logger = logging.getLogger("Santra.VirtualLab.Adapters")


class MockToolAdapters:
    """Interception adapters routing Santra tool operations to the virtual environment."""

    def __init__(self, env: EnvironmentSimulator):
        self.env = env
        self.executed_tools: list = []
        self.last_spoken_text: Optional[str] = None
        self.permission_requests: list = []

    def handle_app_control(self, action: str, target: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Intercepts open_app, close_app, focus_window."""
        self.executed_tools.append({"tool": "app_control", "action": action, "target": target, "args": args})
        tgt = (target or "").lower().strip()

        # Comprehensive alias map to prevent creating duplicate virtual applications
        alias_map = {
            "chrome": "chrome",
            "google chrome": "chrome",
            "google chrome browser": "chrome",
            "chrome browser": "chrome",
            "chrome.exe": "chrome",
            "notepad": "notepad",
            "notepad.exe": "notepad",
            "notepad editor": "notepad",
            "microsoft notepad": "notepad",
            "text editor": "notepad",
            "code": "code",
            "vs code": "code",
            "vscode": "code",
            "visual studio code": "code",
            "code editor": "code",
            "code.exe": "code",
            "discord": "discord",
            "spotify": "spotify",
            "chatgpt": "chatgpt",
            "whatsapp": "whatsapp",
            "whatsapp web": "whatsapp"
        }
        canonical_id = alias_map.get(tgt, tgt)

        # Find or create virtual application without duplicate records
        app = self.env.apps.get(canonical_id)
        if not app:
            # Check if any existing app has this name or title
            for existing_id, existing_app in self.env.apps.items():
                if existing_app.name.lower() == tgt or existing_app.app_id == canonical_id:
                    app = existing_app
                    break

        if not app:
            from core.virtual_lab.environment_simulator import VirtualApplication
            app = VirtualApplication(canonical_id, target.title(), f"{target.title()} Window", is_running=False)
            self.env.apps[canonical_id] = app

        if action in ["open", "launch", "start"]:
            # Focus this app and unfocus all other apps
            for other_id, other_app in self.env.apps.items():
                if other_app != app:
                    other_app.is_focused = False
            app.launch()
            return {"success": True, "message": f"Successfully launched virtual {app.name}.", "action": action, "target": target}
        elif action in ["close", "terminate", "kill"]:
            app.close()
            return {"success": True, "message": f"Successfully closed virtual {app.name}.", "action": action, "target": target}
        elif action in ["focus", "switch", "activate"]:
            for other_id, other_app in self.env.apps.items():
                if other_app != app:
                    other_app.is_focused = False
            app.focus()
            return {"success": True, "message": f"Switched focus to virtual {app.name}.", "action": action, "target": target}

        return {"success": True, "message": f"App action '{action}' performed on virtual {app.name}."}

    def handle_browser(self, action: str, target: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Intercepts web navigation, search, and tab operations."""
        self.executed_tools.append({"tool": "browser", "action": action, "target": target, "args": args})
        args = args or {}
        new_tab = bool(args.get("new_tab", False))

        if action in ["search", "search_website", "search_web"]:
            query = args.get("search_query") or args.get("query") or target or ""
            site = args.get("site_name") or args.get("provider") or "google"
            self.env.browser.execute_search(query=query, site=site, new_tab=new_tab)
            return {"success": True, "message": f"Executed virtual search for '{query}' on {site}.", "action": "search", "query": query, "site": site}
        elif action == "open_url" or "navigate" in action:
            url = args.get("url") or target or "about:blank"
            self.env.browser.open_url(url=url, site_name=args.get("site_name", ""), new_tab=new_tab)
            return {"success": True, "message": f"Navigated virtual browser to '{url}'.", "action": "open_url", "url": url}
        elif action == "interact_prompt":
            site = args.get("site_name", "chatgpt")
            prompt = args.get("prompt_query") or target or ""
            self.env.browser.execute_prompt(site=site, prompt=prompt)
            return {"success": True, "message": f"Prompt submitted to virtual {site}: '{prompt}'.", "action": "interact_prompt"}

        return {"success": True, "message": f"Virtual browser action '{action}' completed."}

    def handle_filesystem(self, action: str, target: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Intercepts file creation, folder indexing, and saves into isolated sandbox."""
        self.executed_tools.append({"tool": "filesystem", "action": action, "target": target, "args": args})
        args = args or {}
        content = args.get("content", f"# Virtual File: {target}\nGenerated during test.")
        overwrite = bool(args.get("overwrite", False))

        if action in ["save_file", "create_file", "write_file"]:
            sandboxed_path = self.env.fs.resolve_path(target)
            ok = self.env.fs.save_file(sandboxed_path, content=content, overwrite=overwrite)
            if not ok:
                return {
                    "success": False,
                    "message": f"File '{target}' already exists and overwrite was prevented.",
                    "error": "OVERWRITE_PREVENTED",
                    "path": sandboxed_path
                }
            return {"success": True, "message": f"Successfully created file '{target}'.", "path": sandboxed_path}
        elif action in ["create_folder", "create_directory"]:
            sandboxed_dir = self.env.fs.resolve_path(target)
            self.env.fs.create_folder(sandboxed_dir)
            return {"success": True, "message": f"Created folder '{target}'.", "path": sandboxed_dir}

        return {"success": True, "message": f"Filesystem action '{action}' completed."}

    def handle_ai_generate(self, messages: list, context: Optional[dict] = None) -> str:
        """Deterministic mock response generator for AI calls in simulation mode."""
        self.executed_tools.append({"tool": "ai_provider", "action": "generate_response", "messages": messages})
        last_msg = messages[-1].get("content", "") if messages else ""

        # Deterministic responses
        if "binary search" in last_msg.lower():
            return "Binary search is an efficient algorithm for finding an item from a sorted list of items with O(log n) time complexity."
        if "python" in last_msg.lower():
            return "Python is a high-level, general-purpose programming language emphasizing readability."
        if "recursion" in last_msg.lower():
            return "Recursion is a programming method where the solution to a problem depends on solutions to smaller instances of the same problem."

        return f"Simulated AI response for: '{last_msg[:60]}'."

    def handle_screen_explain(self, context: Optional[dict] = None) -> Dict[str, Any]:
        """Returns synthetic screen analysis without taking physical screenshots."""
        self.executed_tools.append({"tool": "screen_explainer", "action": "explain"})
        return {
            "success": True,
            "active_window": self.env.screen.active_window_title,
            "explanation": f"The user is viewing '{self.env.screen.active_window_title}'. Visible text describes binary search algorithm.",
            "extracted_text": self.env.screen.extracted_text,
            "uncertainty_score": self.env.screen.uncertainty_score
        }

    def record_speech(self, text: str):
        """Simulates TTS speech without emitting physical sound."""
        self.last_spoken_text = text
        logger.debug(f"[MockSpeech] Spoke: '{text[:60]}...'")
