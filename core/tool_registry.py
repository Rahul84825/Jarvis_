"""Universal Capability and Tool Registry for JARVIS.
Authoritative registry of all tools, accepted arguments, risk levels, verification strategies,
and dynamic capability discovery.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger("Jarvis.ToolRegistry")

@dataclass
class ToolDefinition:
    name: str
    category: str
    description: str
    args: Dict[str, Any] = field(default_factory=dict)
    supported_os: List[str] = field(default_factory=lambda: ["windows", "linux", "darwin"])
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH
    requires_confirmation: bool = False
    timeout_sec: float = 10.0
    has_side_effects: bool = False
    verification_strategy: str = "status_code"  # process_check, file_exists, url_open, return_code
    fallback_behavior: Optional[str] = None
    implemented: bool = True
    handler: Optional[Callable] = None


class ToolRegistry:
    """Central registry of all executable tools and capabilities."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()
        logger.info(f"ToolRegistry initialized with {len(self._tools)} registered capabilities.")

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_all_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        return [t for t in self._tools.values() if t.category == category]

    def get_categories(self) -> List[str]:
        return sorted(list(set(t.category for t in self._tools.values())))

    def is_action_permitted(self, tool_name: str, confirmed: bool = False) -> tuple[bool, str]:
        tool = self.get_tool(tool_name)
        if not tool:
            return True, "Allowed"
        if tool.risk_level == "HIGH" and not confirmed:
            return False, f"Action '{tool_name}' is classified as HIGH risk and requires user confirmation."
        return True, "Allowed"

    def get_capabilities_summary(self) -> str:
        """Dynamically generates capabilities text for 'What can you do?' and help queries from implemented tools."""
        from core.response_registry import response_registry
        return response_registry.get_capabilities_summary(self)

    def _register_default_tools(self):
        # 1. Applications
        self.register(ToolDefinition(
            name="open_app",
            category="applications",
            description="Launch or focus desktop applications like Chrome, VS Code, Steam, or Spotify.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="process_check"
        ))
        self.register(ToolDefinition(
            name="application.launch",
            category="applications",
            description="Launch installed native desktop applications discovered on the system by name or alias.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="process_check"
        ))
        self.register(ToolDefinition(
            name="close_app",
            category="applications",
            description="Close running desktop applications safely.",
            args={"target": str},
            risk_level="MEDIUM",
            has_side_effects=True,
            verification_strategy="process_check"
        ))
        self.register(ToolDefinition(
            name="switch_window",
            category="applications",
            description="Switch focus to a specific open window by title or app name.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="window_focus"
        ))

        # 2. Browser & Chrome Control
        self.register(ToolDefinition(
            name="open_browser",
            category="browser",
            description="Open Chrome or preferred browser window.",
            args={"browser_name": str, "url": Optional[str]},
            risk_level="LOW",
            verification_strategy="process_check"
        ))
        self.register(ToolDefinition(
            name="open_website",
            category="browser",
            description="Navigate to a website URL or pre-configured web destination.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="url_open"
        ))
        self.register(ToolDefinition(
            name="browser_tab_control",
            category="browser",
            description="Manage browser tabs (new tab, close tab, switch tab, reload, navigate back/forward).",
            args={"action": str, "tab_id": Optional[str]},
            risk_level="LOW",
            verification_strategy="browser_state"
        ))

        # 3. Search (Separated Intents)
        self.register(ToolDefinition(
            name="web_search",
            category="search",
            description="Search the web using Google for current topics and information.",
            args={"query": str},
            risk_level="LOW",
            verification_strategy="url_open"
        ))
        self.register(ToolDefinition(
            name="youtube_search",
            category="search",
            description="Search YouTube specifically for videos, tutorials, or music.",
            args={"query": str},
            risk_level="LOW",
            verification_strategy="url_open"
        ))
        self.register(ToolDefinition(
            name="site_search",
            category="search",
            description="Search targeted websites like GitHub, Reddit, or Stack Overflow.",
            args={"provider": str, "query": str},
            risk_level="LOW",
            verification_strategy="url_open"
        ))
        self.register(ToolDefinition(
            name="local_search",
            category="search",
            description="Search local files, documents, or project code repositories.",
            args={"query": str, "extension": Optional[str]},
            risk_level="LOW",
            verification_strategy="filesystem_check"
        ))

        # 4. Media & YouTube playback
        self.register(ToolDefinition(
            name="media_control",
            category="media",
            description="Control media playback: play, pause, next track, previous track, stop.",
            args={"action": str},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="youtube_control",
            category="media",
            description="Control YouTube video playback in the browser: pause, resume, seek, volume.",
            args={"action": str, "value": Optional[Any]},
            risk_level="LOW"
        ))

        # 5. Filesystem
        self.register(ToolDefinition(
            name="list_directory",
            category="filesystem",
            description="List files and folders in the current project or specified directory.",
            args={"path": str},
            risk_level="LOW",
            verification_strategy="filesystem_check"
        ))
        self.register(ToolDefinition(
            name="create_folder",
            category="filesystem",
            description="Create a new directory at the specified path.",
            args={"folder_path": str},
            risk_level="LOW",
            has_side_effects=True,
            verification_strategy="file_exists"
        ))
        self.register(ToolDefinition(
            name="write_file",
            category="filesystem",
            description="Create or write text/markdown content to a verified destination file.",
            args={"file_path": str, "content": str},
            risk_level="LOW",
            has_side_effects=True,
            verification_strategy="file_exists"
        ))
        self.register(ToolDefinition(
            name="read_file",
            category="filesystem",
            description="Read content from a local file safely.",
            args={"file_path": str},
            risk_level="LOW",
            verification_strategy="filesystem_check"
        ))
        self.register(ToolDefinition(
            name="open_folder",
            category="filesystem",
            description="Open folder in File Explorer / OS desktop file manager.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="process_check"
        ))

        # 6. System & Hardware
        self.register(ToolDefinition(
            name="volume_control",
            category="system",
            description="Adjust master volume up/down, mute, or unmute audio.",
            args={"action": str},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="take_screenshot",
            category="system",
            description="Capture the primary desktop display and save image file.",
            args={},
            risk_level="LOW",
            verification_strategy="file_exists"
        ))
        self.register(ToolDefinition(
            name="lock_pc",
            category="system",
            description="Lock workstation screen immediately.",
            args={},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="sleep_pc",
            category="system",
            description="Put the operating system into sleep mode.",
            args={},
            risk_level="HIGH",
            requires_confirmation=True
        ))
        self.register(ToolDefinition(
            name="restart_pc",
            category="system",
            description="Reboot the computer.",
            args={},
            risk_level="HIGH",
            requires_confirmation=True
        ))
        self.register(ToolDefinition(
            name="shutdown_pc",
            category="system",
            description="Shut down the computer completely.",
            args={},
            risk_level="HIGH",
            requires_confirmation=True
        ))
        self.register(ToolDefinition(
            name="system_metrics",
            category="system",
            description="Report CPU usage, RAM utilization, and disk space.",
            args={},
            risk_level="LOW"
        ))

        # 7. Developer Workflows
        self.register(ToolDefinition(
            name="run_terminal",
            category="developer",
            description="Execute development commands or scripts within project context.",
            args={"command": str},
            risk_level="MEDIUM",
            has_side_effects=True,
            verification_strategy="return_code"
        ))
        self.register(ToolDefinition(
            name="check_port",
            category="developer",
            description="Check if a network port is open or used by an existing process.",
            args={"port": int},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="switch_project",
            category="developer",
            description="Switch active development workspace project directory.",
            args={"target": str},
            risk_level="LOW"
        ))

        # 8. Writing & Reasoning
        self.register(ToolDefinition(
            name="draft_content",
            category="content",
            description="Draft natural language content such as professional emails, reports, documentation, or code.",
            args={"topic": str, "content_type": str},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="explain_concept",
            category="content",
            description="Explain errors, code snippets, or technical concepts.",
            args={"query": str},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="calculate_math",
            category="content",
            description="Perform deterministic mathematical calculations locally.",
            args={"expression": str},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="time_date_query",
            category="content",
            description="Get the current local time or date.",
            args={"query_type": str},
            risk_level="LOW"
        ))

        # 9. Observability, Memory & Privacy
        self.register(ToolDefinition(
            name="explain_tool_execution",
            category="observability",
            description="Explain recent tool calls, selection rationale, and execution evidence.",
            args={"count": int},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="memory_control",
            category="memory",
            description="Manage user profile and persistent memories (save, recall, forget).",
            args={"action": str, "topic": str},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="privacy_control",
            category="privacy",
            description="Inspect or update the 3-tier privacy mode (STRICT, GUARDED, RELAXED).",
            args={"action": str, "mode": Optional[str]},
            risk_level="LOW"
        ))

# Global singleton
tool_registry = ToolRegistry()
