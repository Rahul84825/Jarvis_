import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

from config import BASE_DIR
from memory.persistent_memory import persistent_memory
from core.os.project_registry import ProjectRegistry
from core.os.filesystem_manager import FilesystemManager
from core.os.terminal_manager import TerminalManager
from core.os.browser_manager import BrowserManager
from core.os.system_info import SystemInfoProvider
from modules.system.executor import CommandExecutor
from modules.web.web_intel import web_intel

logger = logging.getLogger("Jarvis.ToolRegistry")

class ToolRegistry:
    """Centralized Tool Registry for Jarvis.
    Enforces strict input validation, security boundaries, and structured execution results.
    Prevents unrestricted OS command execution by LLMs.
    """

    def __init__(self, executor: Optional[CommandExecutor] = None):
        self.executor = executor or CommandExecutor()
        self.project_registry = ProjectRegistry()
        self.fs_manager = FilesystemManager()
        self.terminal_manager = TerminalManager()
        self.browser_manager = BrowserManager()
        self.telemetry = SystemInfoProvider()
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_core_tools()

    def _register_core_tools(self):
        """Registers all structured tools with metadata and schema validation."""

        # 1. APPLICATION TOOLS
        self.register(
            name="open_application",
            description="Opens a desktop application by name or alias (e.g. 'chrome', 'vscode', 'spotify').",
            func=self._open_application,
            parameters={"application": "string"},
            category="Applications",
            examples=["Open Spotify", "Launch VS Code", "Open Chrome"]
        )
        self.register(
            name="close_application",
            description="Closes an active application by name or alias.",
            func=self._close_application,
            parameters={"application": "string"},
            category="Applications",
            examples=["Close Chrome", "Exit VS Code"]
        )
        self.register(
            name="minimize_application",
            description="Minimizes an active application window.",
            func=self._minimize_application,
            parameters={"application": "string"},
            category="Applications",
            examples=["Minimize Chrome", "Hide VS Code"]
        )
        self.register(
            name="maximize_application",
            description="Maximizes an active application window.",
            func=self._maximize_application,
            parameters={"application": "string"},
            category="Applications",
            examples=["Maximize Chrome", "Make VS Code fullscreen"]
        )

        # 2. BROWSER TOOLS
        self.register(
            name="open_browser",
            description="Launches a web browser (e.g. 'chrome', 'edge').",
            func=lambda browser="chrome": self._open_application(browser),
            parameters={"browser": "string"},
            category="Browser",
            examples=["Open browser", "Launch Chrome"]
        )
        self.register(
            name="open_url",
            description="Opens a specific website URL in the default browser.",
            func=self._open_url,
            parameters={"url": "string"},
            category="Browser",
            examples=["Open wellmeds.in", "Open https://github.com"]
        )
        self.register(
            name="search_google",
            description="Performs a Google web search in the browser.",
            func=self._search_google,
            parameters={"query": "string"},
            category="Browser",
            examples=["Search Google for Python tutorials", "Search for wellmeds.in"]
        )
        self.register(
            name="search_youtube",
            description="Searches YouTube for videos.",
            func=self._search_youtube,
            parameters={"query": "string"},
            category="Browser",
            examples=["Search YouTube for CodeWithHarry"]
        )
        self.register(
            name="open_new_tab",
            description="Opens a new tab in the active browser.",
            func=self._open_new_tab,
            parameters={},
            category="Browser",
            examples=["Open a new tab", "New Chrome tab"]
        )
        self.register(
            name="open_new_window",
            description="Opens a new independent browser window.",
            func=self._open_new_window,
            parameters={},
            category="Browser",
            examples=["Open another Chrome window", "New browser window"]
        )

        # 3. FILESYSTEM TOOLS
        self.register(
            name="list_directory",
            description="Lists files and directories inside a given folder.",
            func=self._list_directory,
            parameters={"path": "string"},
            category="Files",
            examples=["List files in this folder", "Show current directory"]
        )
        self.register(
            name="find_file",
            description="Searches for files matching a pattern in a directory.",
            func=self._find_file,
            parameters={"filename": "string", "directory": "string"},
            category="Files",
            examples=["Find report.pdf", "Search files for test"]
        )
        self.register(
            name="read_file",
            description="Reads the text content of a safe file.",
            func=self._read_file,
            parameters={"path": "string", "max_lines": "integer"},
            category="Files",
            examples=["Read notes.txt"]
        )
        self.register(
            name="write_file",
            description="Writes text content to a file.",
            func=self._write_file,
            parameters={"path": "string", "content": "string"},
            category="Files",
            examples=["Write notes to file.txt"]
        )
        self.register(
            name="create_directory",
            description="Creates a new directory.",
            func=self._create_directory,
            parameters={"path": "string"},
            category="Files",
            examples=["Create new folder"]
        )
        self.register(
            name="open_file",
            description="Opens a file with its default system application.",
            func=self._open_file,
            parameters={"path": "string"},
            category="Files",
            examples=["Open document.pdf"]
        )

        # 4. TERMINAL & PROCESS TOOLS
        self.register(
            name="execute_terminal",
            description="Executes a safe shell command in a working directory.",
            func=self._execute_terminal,
            parameters={"command": "string", "cwd": "string"},
            category="Terminal",
            examples=["Run npm test", "Execute git status"]
        )

        # 5. SYSTEM & POWER TOOLS
        self.register(
            name="lock_system",
            description="Locks the computer workstation.",
            func=lambda: self._execute_system_intent("lock_computer"),
            parameters={},
            category="Power",
            examples=["Lock the computer", "Lock PC"]
        )
        self.register(
            name="sleep_system",
            description="Puts the computer into low-power sleep mode.",
            func=lambda: self._execute_system_intent("sleep_computer"),
            parameters={},
            category="Power",
            examples=["Put computer to sleep"]
        )
        self.register(
            name="hibernate_system",
            description="Puts the computer into hibernation.",
            func=lambda: self._execute_system_intent("hibernate_computer"),
            parameters={},
            category="Power",
            examples=["Hibernate computer"]
        )
        self.register(
            name="get_system_info",
            description="Returns system CPU, RAM, disk, and battery telemetry.",
            func=self._get_system_info,
            parameters={},
            category="System",
            examples=["What is my CPU usage?", "How much RAM do I have?"]
        )

        # 6. GIT & TESTING TOOLS
        self.register(
            name="git_status",
            description="Runs 'git status' in the current or specified project directory.",
            func=self._git_status,
            parameters={"repo_path": "string"},
            category="Development",
            examples=["Check git status"]
        )
        self.register(
            name="run_tests",
            description="Runs automated test suite for a project.",
            func=self._run_tests,
            parameters={"project": "string"},
            category="Development",
            examples=["Run project tests"]
        )

        # 7. PROJECT TOOLS
        self.register(
            name="identify_project",
            description="Finds project path and details by project alias or name.",
            func=self._identify_project,
            parameters={"project": "string"},
            category="Development",
            examples=["Where is my Jarvis project?"]
        )
        self.register(
            name="list_projects",
            description="Lists all registered projects and their paths.",
            func=self._list_projects,
            parameters={},
            category="Development",
            examples=["List my projects"]
        )
        self.register(
            name="switch_project",
            description="Switches active working project context.",
            func=self._switch_project,
            parameters={"project": "string"},
            category="Development",
            examples=["Switch to Jarvis project"]
        )

        # 8. CAMERA & VISION PERCEPTION TOOLS
        self.register(
            name="camera.list",
            description="Enumerates available connected camera devices.",
            func=self._list_cameras,
            parameters={},
            category="Vision",
            examples=["List cameras", "Show available webcams"]
        )
        self.register(
            name="camera.start",
            description="Turns on the camera and begins video stream ingestion.",
            func=self._start_camera,
            parameters={},
            category="Vision",
            examples=["Turn on camera", "Start webcam"]
        )
        self.register(
            name="camera.stop",
            description="Turns off the camera and releases hardware.",
            func=self._stop_camera,
            parameters={},
            category="Vision",
            examples=["Turn off camera", "Stop webcam"]
        )
        self.register(
            name="camera.status",
            description="Gets the current status and FPS telemetry of the camera.",
            func=self._camera_status,
            parameters={},
            category="Vision",
            examples=["Camera status", "Webcam status"]
        )
        self.register(
            name="camera.capture_frame",
            description="Takes a photo snapshot from the active camera.",
            func=self._capture_camera_frame,
            parameters={"output_path": "string"},
            category="Vision",
            examples=["Take a photo", "Capture picture"]
        )
        self.register(
            name="vision.start",
            description="Starts hand tracking and vision perception.",
            func=self._start_vision,
            parameters={},
            category="Vision",
            examples=["Start vision", "Start hand tracking"]
        )
        self.register(
            name="vision.stop",
            description="Stops vision perception and hand tracking.",
            func=self._stop_vision,
            parameters={},
            category="Vision",
            examples=["Stop vision", "Stop hand tracking"]
        )
        self.register(
            name="vision.status",
            description="Gets the current vision and hand perception telemetry.",
            func=self._vision_status,
            parameters={},
            category="Vision",
            examples=["Vision status", "Hand tracking status"]
        )
        self.register(
            name="gesture.status",
            description="Gets the current gesture engine telemetry and recognized hands.",
            func=self._gesture_status,
            parameters={},
            category="Vision",
            examples=["Gesture status"]
        )


        # 8. MEMORY TOOLS
        self.register(
            name="remember",
            description="Saves a key-value fact or preference into long-term memory.",
            func=self._remember,
            parameters={"key": "string", "value": "string", "category": "string"},
            category="Agent",
            examples=["Remember my favorite editor is VS Code"]
        )
        self.register(
            name="recall",
            description="Retrieves a fact or preference from long-term memory.",
            func=self._recall,
            parameters={"key": "string", "category": "string"},
            category="Agent",
            examples=["What is my favorite editor?"]
        )
        self.register(
            name="search_memory",
            description="Searches long-term knowledge notes and past interactions.",
            func=lambda query: {"success": True, "tool": "search_memory", "target": query, "message": f"Searched notes for '{query}'", "data": persistent_memory.search_notes(query)},
            parameters={"query": "string"},
            category="Agent",
            examples=["Search memory for project setup"]
        )

        # 9. WEB & LIVE INTEL TOOLS
        self.register(
            name="search_web",
            description="Searches the live internet for recent facts or summaries.",
            func=lambda query: {"success": True, "tool": "search_web", "target": query, "message": f"Web search completed for '{query}'", "data": web_intel.search_web(query)},
            parameters={"query": "string"},
            category="Browser",
            examples=["Search web for Artemis NASA news"]
        )
        self.register(
            name="get_weather",
            description="Gets current weather conditions for a city.",
            func=lambda city="": {"success": True, "tool": "get_weather", "target": city, "message": f"Weather retrieved for {city or 'local'}", "data": web_intel.get_weather(city)},
            parameters={"city": "string"},
            category="System",
            examples=["What is the weather today?"]
        )
        self.register(
            name="get_live_news",
            description="Fetches breaking world, tech, or business news headlines.",
            func=lambda category="world": {"success": True, "tool": "get_live_news", "target": category, "message": f"Fetched {category} news", "data": web_intel.get_live_news(category)},
            parameters={"category": "string"},
            category="System",
            examples=["What is the latest world news?"]
        )

    def register(self, name: str, description: str, func: Callable, parameters: Optional[Dict[str, str]] = None, category: str = "General", examples: Optional[List[str]] = None, enabled: bool = True):
        """Registers a tool with standardized schema and capability metadata."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "func": func,
            "parameters": parameters or {},
            "category": category,
            "examples": examples or [],
            "enabled": enabled
        }

    def get_capabilities_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """Returns all registered and enabled tools grouped by category."""
        categories = {}
        for tool in self._tools.values():
            if not tool.get("enabled", True):
                continue
            cat = tool.get("category", "General")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append({
                "name": tool["name"],
                "description": tool["description"],
                "examples": tool.get("examples", [])
            })
        return categories

    def get_categories(self) -> List[str]:
        """Returns list of all active capability category names."""
        return list(self.get_capabilities_by_category().keys())

    def get_capability_summary(self) -> str:
        """Dynamically generates a natural spoken capabilities summary from real registered tools."""
        cats = self.get_capabilities_by_category()
        active_cats = []
        if "Applications" in cats: active_cats.append("open applications")
        if "Browser" in cats: active_cats.append("manage browser tabs")
        if "Files" in cats: active_cats.append("access files")
        if "System" in cats: active_cats.append("monitor telemetry")
        if "Power" in cats: active_cats.append("control power")
        if "Terminal" in cats: active_cats.append("run commands")
        if "Development" in cats: active_cats.append("manage projects")
        if "Vision" in cats: active_cats.append("control camera vision")
        if "Agent" in cats: active_cats.append("execute multi-step tasks")

        if active_cats:
            summary = "I can " + ", ".join(active_cats[:-1]) + ", and " + active_cats[-1] + ", Sir."
        else:
            summary = "I can control applications, Chrome, files, terminal tasks, and system functions, Sir."
        return summary

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return list(self._tools.values())

    def execute(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a tool with validation, error trapping, and structured return format."""
        tool = self.get_tool(tool_name)
        if not tool:
            logger.warning(f"[ToolRegistry] Tool '{tool_name}' not found.")
            return {
                "success": False,
                "tool": tool_name,
                "target": "",
                "message": f"Tool '{tool_name}' is not registered.",
                "data": None
            }

        args = arguments or {}
        logger.info(f"[ToolRegistry] Executing tool '{tool_name}' with arguments: {args}")

        try:
            result = tool["func"](**args)
            if isinstance(result, dict) and "success" in result:
                return result
            return {
                "success": True,
                "tool": tool_name,
                "target": str(args.get("application") or args.get("project") or args.get("path") or args.get("query") or ""),
                "message": f"Tool '{tool_name}' executed successfully.",
                "data": result
            }
        except TypeError as te:
            logger.error(f"[ToolRegistry] Argument mismatch for '{tool_name}': {te}")
            return {
                "success": False,
                "tool": tool_name,
                "target": "",
                "message": f"Invalid arguments for tool '{tool_name}': {te}",
                "data": None
            }
        except Exception as e:
            logger.error(f"[ToolRegistry] Execution error in '{tool_name}': {e}", exc_info=True)
            return {
                "success": False,
                "tool": tool_name,
                "target": "",
                "message": f"Failed to execute '{tool_name}': {str(e)}",
                "data": None
            }

    # ==========================================
    # TOOL IMPLEMENTATION WRAPPERS
    # ==========================================
    def _open_application(self, application: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "open_app", "action": "open_application", "target": application})
        return {
            "success": res.get("success", False),
            "tool": "open_application",
            "target": application,
            "message": res.get("message", f"Opened {application}"),
            "data": res
        }

    def _close_application(self, application: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "close_app", "action": "close_application", "target": application})
        return {
            "success": res.get("success", False),
            "tool": "close_application",
            "target": application,
            "message": res.get("message", f"Closed {application}"),
            "data": res
        }

    def _minimize_application(self, application: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "window_control", "action": "minimize_application", "target": application})
        return {
            "success": res.get("success", False),
            "tool": "minimize_application",
            "target": application,
            "message": res.get("message", f"Minimized {application}"),
            "data": res
        }

    def _maximize_application(self, application: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "window_control", "action": "maximize_application", "target": application})
        return {
            "success": res.get("success", False),
            "tool": "maximize_application",
            "target": application,
            "message": res.get("message", f"Maximized {application}"),
            "data": res
        }

    def _open_url(self, url: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "open_website", "action": "open_url", "target": url})
        return {
            "success": res.get("success", False),
            "tool": "open_url",
            "target": url,
            "message": res.get("message", f"Opened {url}"),
            "data": res
        }

    def _search_google(self, query: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "web_search", "action": "search_google", "target": query})
        return {
            "success": res.get("success", False),
            "tool": "search_google",
            "target": query,
            "message": res.get("message", f"Searched Google for '{query}'"),
            "data": res
        }

    def _search_youtube(self, query: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "web_search", "action": "search_youtube", "target": query})
        return {
            "success": res.get("success", False),
            "tool": "search_youtube",
            "target": query,
            "message": res.get("message", f"Searched YouTube for '{query}'"),
            "data": res
        }

    def _open_new_tab(self) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "window_control", "action": "open_new_browser_tab", "target": "chrome"})
        return {
            "success": res.get("success", False),
            "tool": "open_new_tab",
            "target": "chrome",
            "message": res.get("message", "Opened new browser tab"),
            "data": res
        }

    def _open_new_window(self) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "window_control", "action": "open_new_browser_window", "target": "chrome"})
        return {
            "success": res.get("success", False),
            "tool": "open_new_window",
            "target": "chrome",
            "message": res.get("message", "Opened new browser window"),
            "data": res
        }

    def _execute_system_intent(self, intent_name: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "system_control", "action": intent_name, "target": "system"})
        return {
            "success": res.get("success", False),
            "tool": intent_name,
            "target": "system",
            "message": res.get("message", f"Executed {intent_name}"),
            "data": res
        }

    def _list_directory(self, path: str = ".") -> Dict[str, Any]:
        target_path = Path(path).resolve()
        if not target_path.exists():
            return {"success": False, "tool": "list_directory", "target": str(target_path), "message": f"Path '{path}' does not exist.", "data": []}
        try:
            items = os.listdir(target_path)
            return {"success": True, "tool": "list_directory", "target": str(target_path), "message": f"Found {len(items)} items in {path}", "data": items[:50]}
        except Exception as e:
            return {"success": False, "tool": "list_directory", "target": str(target_path), "message": str(e), "data": []}

    def _find_file(self, filename: str, directory: str = ".") -> Dict[str, Any]:
        target_dir = Path(directory).resolve()
        matches = []
        try:
            for root, _, files in os.walk(target_dir):
                for f in files:
                    if filename.lower() in f.lower():
                        matches.append(os.path.join(root, f))
                        if len(matches) >= 10:
                            break
                if len(matches) >= 10:
                    break
            return {
                "success": len(matches) > 0,
                "tool": "find_file",
                "target": filename,
                "message": f"Found {len(matches)} matching files for '{filename}'",
                "data": matches
            }
        except Exception as e:
            return {"success": False, "tool": "find_file", "target": filename, "message": str(e), "data": []}

    def _read_file(self, path: str, max_lines: int = 100) -> Dict[str, Any]:
        target_file = Path(path).resolve()
        if not target_file.exists():
            return {"success": False, "tool": "read_file", "target": str(target_file), "message": f"File '{path}' does not exist.", "data": ""}
        
        # Guard against sensitive credential files
        if target_file.name.startswith(".env") or "id_rsa" in target_file.name or "credentials" in target_file.name:
            return {"success": False, "tool": "read_file", "target": str(target_file), "message": "Access to security sensitive credential files is restricted.", "data": ""}

        try:
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(max_lines)]
                content = "".join(lines)
            return {"success": True, "tool": "read_file", "target": str(target_file), "message": f"Read {len(lines)} lines from {path}", "data": content}
        except Exception as e:
            return {"success": False, "tool": "read_file", "target": str(target_file), "message": str(e), "data": ""}

    def _write_file(self, path: str, content: str) -> Dict[str, Any]:
        target_file = Path(path).resolve()
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "tool": "write_file", "target": str(target_file), "message": f"Wrote content to {path}", "data": len(content)}
        except Exception as e:
            return {"success": False, "tool": "write_file", "target": str(target_file), "message": str(e), "data": 0}

    def _create_directory(self, path: str) -> Dict[str, Any]:
        target_dir = Path(path).resolve()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            return {"success": True, "tool": "create_directory", "target": str(target_dir), "message": f"Created directory {path}", "data": str(target_dir)}
        except Exception as e:
            return {"success": False, "tool": "create_directory", "target": str(target_dir), "message": str(e), "data": ""}

    def _open_file(self, path: str) -> Dict[str, Any]:
        res = self.executor.execute({"intent": "file_access", "action": "open_file", "target": path})
        return {
            "success": res.get("success", False),
            "tool": "open_file",
            "target": path,
            "message": res.get("message", f"Opened file {path}"),
            "data": res
        }

    def _execute_terminal(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        # Security sanitization
        cmd_clean = command.strip()
        blocked = ["format ", "rm -rf /", "del /f /s /q c:\\", "rd /s /q c:\\"]
        if any(b in cmd_clean.lower() for b in blocked):
            return {"success": False, "tool": "execute_terminal", "target": command, "message": "Command violates security policy and was blocked.", "data": ""}
        
        target_cwd = cwd or str(BASE_DIR)
        res = self.terminal_manager.execute(cmd_clean, cwd=target_cwd)
        return {
            "success": res.get("exit_code") == 0,
            "tool": "execute_terminal",
            "target": command,
            "message": f"Command executed with exit code {res.get('exit_code')}",
            "data": res
        }

    def _get_system_info(self) -> Dict[str, Any]:
        cpu = self.telemetry.get_cpu_info()
        ram = self.telemetry.get_ram_info()
        disk = self.telemetry.get_disk_info()
        os_info = self.telemetry.get_os_info()
        summary = f"{cpu.get('text', '')} {ram.get('text', '')} {disk.get('text', '')}"
        return {
            "success": True,
            "tool": "get_system_info",
            "target": "telemetry",
            "message": "System telemetry retrieved",
            "data": {
                "summary": summary,
                "cpu": cpu,
                "ram": ram,
                "disk": disk,
                "os": os_info
            }
        }

    def _git_status(self, repo_path: Optional[str] = None) -> Dict[str, Any]:
        target = repo_path or str(BASE_DIR)
        res = self.terminal_manager.execute("git status", cwd=target)
        return {
            "success": res.get("exit_code") == 0,
            "tool": "git_status",
            "target": target,
            "message": "Git status retrieved",
            "data": res.get("stdout", "")
        }

    def _run_tests(self, project: Optional[str] = None) -> Dict[str, Any]:
        target_project = project or "jarvis"
        proj_info = persistent_memory.get_project(target_project)
        cwd = proj_info["path"] if proj_info and proj_info.get("path") else str(BASE_DIR)
        test_cmd = proj_info.get("test_cmd") if proj_info and proj_info.get("test_cmd") else "python -m unittest discover tests"
        
        res = self.terminal_manager.execute(test_cmd, cwd=cwd)
        is_success = res.get("exit_code") == 0
        return {
            "success": is_success,
            "tool": "run_tests",
            "target": target_project,
            "message": "Tests passed successfully" if is_success else "Tests completed with failures",
            "data": {
                "exit_code": res.get("exit_code"),
                "output": (res.get("stdout", "") + "\n" + res.get("stderr", ""))[:500]
            }
        }

    def _identify_project(self, project: str) -> Dict[str, Any]:
        proj = persistent_memory.get_project(project)
        if not proj:
            # Check project registry JSON
            p_path = self.project_registry.get_project_path(project)
            if p_path:
                proj = {"alias": project.lower(), "name": project, "path": p_path}
        if proj:
            return {
                "success": True,
                "tool": "identify_project",
                "target": project,
                "message": f"Identified project '{project}' at {proj['path']}",
                "data": proj
            }
        return {
            "success": False,
            "tool": "identify_project",
            "target": project,
            "message": f"Project '{project}' not found in registry.",
            "data": None
        }

    def _list_projects(self) -> Dict[str, Any]:
        projs = persistent_memory.list_projects()
        if not projs:
            projs = [{"alias": k, "name": k.title(), "path": v} for k, v in self.project_registry.projects.items()]
        return {
            "success": True,
            "tool": "list_projects",
            "target": "all",
            "message": f"Found {len(projs)} registered projects",
            "data": projs
        }

    def _switch_project(self, project: str) -> Dict[str, Any]:
        switched = self.project_registry.set_current_project(project)
        if switched:
            persistent_memory.remember("workflow", "active_project", project)
            return {
                "success": True,
                "tool": "switch_project",
                "target": project,
                "message": f"Switched active project context to '{project}'",
                "data": self.project_registry.get_current_project()
            }
        return {
            "success": False,
            "tool": "switch_project",
            "target": project,
            "message": f"Could not switch to project '{project}'. Not found.",
            "data": None
        }

    def _remember(self, key: str, value: str, category: str = "general") -> Dict[str, Any]:
        ok = persistent_memory.remember(category, key, value)
        return {
            "success": ok,
            "tool": "remember",
            "target": key,
            "message": f"Saved '{key}' = '{value}' in [{category}] memory.",
            "data": {"key": key, "value": value, "category": category}
        }

    def _recall(self, key: str, category: Optional[str] = None) -> Dict[str, Any]:
        val = persistent_memory.recall(key, category=category)
        return {
            "success": val is not None,
            "tool": "recall",
            "target": key,
            "message": f"Recalled '{key}': {val}" if val else f"No memory found for '{key}'",
            "data": val
        }

    def _list_cameras(self) -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        cams = camera_manager.list_cameras()
        return {
            "success": True,
            "tool": "camera.list",
            "target": "devices",
            "message": f"Found {len(cams)} camera device(s).",
            "data": cams
        }

    def _start_camera(self) -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        ok = camera_manager.acquire(reason="tool_registry")
        return {
            "success": ok,
            "tool": "camera.start",
            "target": "camera",
            "message": "Camera stream activated and vision perception active." if ok else "Camera unavailable.",
            "data": camera_manager.get_status()
        }

    def _stop_camera(self) -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        camera_manager.force_stop()
        return {
            "success": True,
            "tool": "camera.stop",
            "target": "camera",
            "message": "Camera deactivated and hardware released.",
            "data": camera_manager.get_status()
        }

    def _camera_status(self) -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        status = camera_manager.get_status()
        return {
            "success": True,
            "tool": "camera.status",
            "target": "camera",
            "message": f"Camera is currently {status['state']} ({status['fps_capture']} FPS).",
            "data": status
        }

    def _capture_camera_frame(self, output_path: str = "screenshots/camera_snap.png") -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        ok, path_or_err = camera_manager.capture_snapshot(output_path)
        return {
            "success": ok,
            "tool": "camera.capture_frame",
            "target": path_or_err,
            "message": f"Snapshot captured to '{path_or_err}'" if ok else f"Failed to capture frame: {path_or_err}",
            "data": {"path": path_or_err} if ok else None
        }

    def _start_vision(self) -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        ok = camera_manager.acquire(reason="tool_registry_vision")
        return {
            "success": ok,
            "tool": "vision.start",
            "target": "vision",
            "message": "Vision perception and hand tracking online." if ok else "Vision unavailable.",
            "data": camera_manager.get_status()
        }

    def _stop_vision(self) -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        camera_manager.release(reason="tool_registry_vision")
        return {
            "success": True,
            "tool": "vision.stop",
            "target": "vision",
            "message": "Vision perception released.",
            "data": camera_manager.get_status()
        }

    def _vision_status(self) -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        status = camera_manager.get_status()
        return {
            "success": True,
            "tool": "vision.status",
            "target": "vision",
            "message": f"Vision processing: {status['fps_vision']} FPS, Hands detected: {status['hands_detected']}.",
            "data": status
        }

    def _gesture_status(self) -> Dict[str, Any]:
        from core.perception.camera_manager import camera_manager
        status = camera_manager.get_status()
        return {
            "success": True,
            "tool": "gesture.status",
            "target": "gestures",
            "message": f"Gesture Engine Active: {status['is_active']}, Hands: {status['hands_detected']}.",
            "data": status
        }


# Global singleton
tool_registry = ToolRegistry()
