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
        self.register(ToolDefinition(
            name="application.properties",
            category="applications",
            description="Open operating system file Properties dialog for an application executable.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="process_check"
        ))
        self.register(ToolDefinition(
            name="application.install_dir",
            category="applications",
            description="Open installation folder in File Explorer / OS desktop file manager with executable selected.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="process_check"
        ))
        self.register(ToolDefinition(
            name="application.settings",
            category="applications",
            description="Open internal application settings (e.g. chrome://settings) or system app details.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="process_check"
        ))
        self.register(ToolDefinition(
            name="application.metadata",
            category="applications",
            description="Retrieve version, publisher, install path, and architecture metadata for an installed application.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="application.status",
            category="applications",
            description="Check if an application is installed and available on the local operating system.",
            args={"target": str},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="application.list_installed",
            category="applications",
            description="List installed desktop applications or available applications in a category like browsers.",
            args={"category": Optional[str], "query": Optional[str]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="application.refresh",
            category="applications",
            description="Refresh the discovered applications catalogue at runtime without restarting JARVIS.",
            args={},
            risk_level="LOW",
            verification_strategy="status_code"
        ))

        # 1.5 Desktop Interaction & Universal Text Entry
        self.register(ToolDefinition(
            name="desktop.get_context",
            category="interaction",
            description="Inspect the active foreground application, window title, focused element, and available input fields.",
            args={"explicit_destination": Optional[str], "allow_ocr": Optional[bool]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="desktop.enter_text",
            category="interaction",
            description="Enter text into the resolved or specified target control with safety window stability check.",
            args={"text": str, "target": Optional[str], "mode": Optional[str]},
            risk_level="MEDIUM",
            has_side_effects=True,
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="desktop.search_in_app",
            category="interaction",
            description="Search for a query within the active application's search bar.",
            args={"query": str, "explicit_destination": Optional[str]},
            risk_level="LOW",
            has_side_effects=True,
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="desktop.replace_selection",
            category="interaction",
            description="Replace the currently selected text with new text in the active control.",
            args={"text": str},
            risk_level="MEDIUM",
            has_side_effects=True,
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="desktop.send_message",
            category="interaction",
            description="Send a drafted message or submit a form, requiring explicit confirmation before execution.",
            args={"confirm": Optional[bool]},
            risk_level="HIGH",
            has_side_effects=True,
            verification_strategy="status_code"
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
        self.register(ToolDefinition(
            name="browser_action",
            category="browser",
            description="Universal intent-driven browser automation for navigating, searching specific websites, interacting with prompts, and tab control.",
            args={"action_type": str, "site_name": Optional[str], "url": Optional[str], "query": Optional[str]},
            risk_level="LOW",
            verification_strategy="url_open"
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
        self.register(ToolDefinition(
            name="open_search_result",
            category="browser",
            description="Open a specific numbered search result (e.g. first result, second result) from the active search.",
            args={"index": int, "provider": Optional[str], "query": Optional[str]},
            risk_level="LOW",
            verification_strategy="url_open"
        ))
        self.register(ToolDefinition(
            name="verify_page_loaded",
            category="browser",
            description="Verify if a web page has finished loading or is ready via browser state.",
            args={"url": Optional[str], "title": Optional[str]},
            risk_level="LOW",
            verification_strategy="browser_state"
        ))
        self.register(ToolDefinition(
            name="write_to_notepad",
            category="content",
            description="Open Notepad and write specified text or explanation into the document.",
            args={"text": str, "title": Optional[str]},
            risk_level="LOW",
            has_side_effects=True,
            verification_strategy="process_check"
        ))

        # 4. Media, YouTube & Spotify playback
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
        self.register(ToolDefinition(
            name="spotify_control",
            category="media",
            description="Unified natural-language control for Spotify playback, playlist management, and devices.",
            args={"action": str, "target": Optional[str], "playlist_name": Optional[str], "track_name": Optional[str]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="spotify.playback",
            category="media",
            description="Control Spotify playback: play, pause, next, previous, seek, volume, shuffle, repeat, transfer device.",
            args={"action": str, "device_id": Optional[str], "position_ms": Optional[int], "volume_percent": Optional[int], "state": Optional[Any]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="spotify.playlist",
            category="media",
            description="Manage Spotify playlists: create, list, rename, add tracks, remove tracks, reorder, deduplicate.",
            args={"action": str, "name": Optional[str], "playlist_id": Optional[str], "tracks": Optional[List[str]]},
            risk_level="MEDIUM",
            has_side_effects=True,
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="spotify.playlist.delete",
            category="media",
            description="Remove/unfollow a playlist from the user's Spotify library (requires explicit user confirmation).",
            args={"playlist_id": str, "name": Optional[str]},
            risk_level="HIGH",
            requires_confirmation=True,
            has_side_effects=True,
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="spotify.playlist.replace",
            category="media",
            description="Replace all contents of a Spotify playlist with new tracks (requires explicit user confirmation).",
            args={"playlist_id": str, "track_uris": List[str]},
            risk_level="HIGH",
            requires_confirmation=True,
            has_side_effects=True,
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="spotify.account",
            category="media",
            description="Manage Spotify account connection, profile, status, and authentication.",
            args={"action": str},
            risk_level="LOW",
            verification_strategy="status_code"
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
        self.register(ToolDefinition(
            name="startup_control",
            category="system",
            description="Manage Windows startup integration: enable, disable, or query startup state.",
            args={"action": str},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="standby_control",
            category="system",
            description="Control assistant listening and standby states (enter standby, mute/disable mic, unmute/enable mic).",
            args={"action": str},
            risk_level="LOW",
            verification_strategy="status_code"
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
        # 10. Social Intelligence, Humor & Personality
        self.register(ToolDefinition(
            name="tell_joke",
            category="social",
            description="Share clean programming, tech, futuristic, and lighthearted jokes.",
            args={"category": Optional[str]},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="fun_fact",
            category="social",
            description="Share fascinating computing, science, and technology facts.",
            args={"category": Optional[str]},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="playful_roast",
            category="social",
            description="Deliver harmless, witty, and playful roasts upon request.",
            args={"target": Optional[str]},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="set_personality",
            category="personality",
            description="Configure conversational tone (normal, professional, funny, dramatic), response length, and humor.",
            args={"tone": Optional[str], "length": Optional[str], "humor": Optional[bool]},
            risk_level="LOW"
        ))
        self.register(ToolDefinition(
            name="dynamic_help",
            category="help",
            description="Explain system capabilities, registered tools, voice commands, and offline support.",
            args={"scope": Optional[str]},
            risk_level="LOW"
        ))

        # 11. Workspaces & Power Management
        self.register(ToolDefinition(
            name="workspace.launch",
            category="workspaces",
            description="Launch declarative workspace environments (Development, Gaming, Study, Research, Excel).",
            args={"target": str, "confirmed_optional_ids": Optional[list], "declined_optional_ids": Optional[list]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="power.scheme",
            category="system",
            description="Query or switch Windows power scheme and report Acer laptop OEM power state.",
            args={"target": str, "action": Optional[str]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="battery.status",
            category="system",
            description="Query live Windows battery percentage, charging state, and estimated runtime.",
            args={},
            risk_level="LOW",
            verification_strategy="status_code"
        ))

        # 12. Desktop Context & Visual Intelligence
        self.register(ToolDefinition(
            name="screen.analyze",
            category="vision",
            description="Capture and visually analyze the active window, region, or entire screen.",
            args={"prompt": Optional[str], "target": Optional[str]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="screen.explain",
            category="vision",
            description="Generate tailored explanations (beginner, technical, step-by-step, code) for visible screen content.",
            args={"query": str, "style": Optional[str]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))

        # 13. File Management & Project Intelligence
        self.register(ToolDefinition(
            name="files.create",
            category="files",
            description="Safely create and verify real files on disk with syntax validation.",
            args={"filename": str, "destination": str, "content": str, "language": Optional[str], "allow_overwrite": Optional[bool]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="files.search",
            category="files",
            description="Search indexed desktop files and projects with stale path pruning.",
            args={"query": str, "extension": Optional[str], "project_alias": Optional[str]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="files.open",
            category="files",
            description="Open a file or folder in File Explorer or its default application.",
            args={"file_path": str},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="project.inspect",
            category="files",
            description="Analyze project architecture, frameworks, dependencies, and entry points.",
            args={"project_path": str},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="ai.get_providers",
            category="ai",
            description="List configured AI providers, availability, models, and priority ranking.",
            args={},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="ai.update_provider",
            category="ai",
            description="Update API key, active model, or priority for an AI provider.",
            args={"provider_id": str, "api_key": Optional[str], "model": Optional[str], "enabled": Optional[bool]},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="ai.cache_stats",
            category="ai",
            description="Report metrics and API calls saved by the multi-layer AI cache.",
            args={},
            risk_level="LOW",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="ai.clear_cache",
            category="ai",
            description="Clear cached AI responses with optional layer filtering.",
            args={"layer": Optional[str]},
            risk_level="MEDIUM",
            verification_strategy="status_code"
        ))
        self.register(ToolDefinition(
            name="ai.forget_cache",
            category="ai",
            description="Invalidate or mark a specific cached query/answer as disputed.",
            args={"query": str},
            risk_level="LOW",
            verification_strategy="status_code"
        ))

        # Panel Visibility
        self.register(ToolDefinition(
            name="panel_visibility",
            category="ui",
            description="Control Santra HUD panel visibility (show, hide, minimize, restore).",
            args={"action": str},
            risk_level="LOW",
            verification_strategy="ui_state"
        ))

# Global singleton
tool_registry = ToolRegistry()
