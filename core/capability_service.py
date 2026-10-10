"""Dynamic Capability Service for JARVIS.

Uses ToolRegistry as the single source of truth to discover and organize:
- Available built-in tools
- Available application and browser operations
- Configured AI providers
- Enabled custom commands
- Temporarily unavailable tools
- Unsupported / unimplemented capabilities

Provides:
- Short category-based overview for "Jarvis, help"
- Fuller organized command reference for "Jarvis, show all commands"
- Scoped command listings for "Jarvis, show browser commands", "what file operations can you perform", etc.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("Jarvis.CapabilityService")


class CapabilityService:
    """Dynamic capability catalogue and discovery service."""

    def __init__(self, tool_reg=None, discovery=None, custom_cmds=None, prov_mgr=None):
        self._tool_registry = tool_reg
        self._app_discovery = discovery
        self._custom_command_registry = custom_cmds
        self._provider_manager = prov_mgr
        logger.info("CapabilityService initialized.")

    @property
    def tool_registry(self):
        if self._tool_registry is None:
            from core.tool_registry import tool_registry
            self._tool_registry = tool_registry
        return self._tool_registry

    @property
    def app_discovery(self):
        if self._app_discovery is None:
            try:
                from core.apps.application_discovery import app_discovery
                self._app_discovery = app_discovery
            except Exception:
                self._app_discovery = None
        return self._app_discovery

    @property
    def custom_command_registry(self):
        if self._custom_command_registry is None:
            try:
                from core.custom_commands.command_registry import custom_command_registry
                self._custom_command_registry = custom_command_registry
            except Exception:
                self._custom_command_registry = None
        return self._custom_command_registry

    @property
    def provider_manager(self):
        if self._provider_manager is None:
            try:
                from core.ai.provider_manager import provider_manager
                self._provider_manager = provider_manager
            except Exception:
                self._provider_manager = None
        return self._provider_manager

    # =========================================================================
    # INTROSPECTION & PARTITIONING
    # =========================================================================

    def get_capabilities_breakdown(self) -> Dict[str, Any]:
        """Distinguishes built-in tools, apps, providers, custom commands, and unavailable capabilities."""
        all_tools = self.tool_registry.list_all_tools()
        import platform
        current_os = platform.system().lower()
        if current_os == "darwin":
            os_key = "darwin"
        elif current_os == "windows":
            os_key = "windows"
        else:
            os_key = "linux"

        available_tools = []
        unsupported_tools = []

        for tool in all_tools:
            if not getattr(tool, "implemented", True):
                unsupported_tools.append(tool)
            elif tool.supported_os and os_key not in tool.supported_os:
                unsupported_tools.append(tool)
            else:
                available_tools.append(tool)

        # AI providers
        configured_providers = []
        if self.provider_manager:
            try:
                configured_providers = self.provider_manager.get_available_providers()
            except Exception:
                pass

        # Discovered applications
        apps_count = 0
        if self.app_discovery:
            try:
                apps = self.app_discovery.list_applications(available_only=True)
                apps_count = len(apps)
            except Exception:
                pass

        # Enabled custom commands
        custom_commands = []
        if self.custom_command_registry:
            try:
                custom_commands = self.custom_command_registry.list_commands(enabled_only=True)
            except Exception:
                pass

        return {
            "available_tools": available_tools,
            "unsupported_tools": unsupported_tools,
            "configured_providers": configured_providers,
            "discovered_apps_count": apps_count,
            "enabled_custom_commands": custom_commands,
        }

    # =========================================================================
    # USER-FACING COMMAND DISCOVERY RESPONSES
    # =========================================================================

    def get_help_overview(self) -> str:
        """Short category-based overview for 'Jarvis, help'."""
        breakdown = self.get_capabilities_breakdown()
        tools = breakdown["available_tools"]

        categories = sorted(list(set(t.category.lower() for t in tools)))
        cat_map = {
            "applications": "Applications",
            "browser": "Browser & Tabs",
            "search": "Web & Local Search",
            "filesystem": "Files & Folders",
            "system": "System Controls",
            "developer": "Developer Workflow",
            "content": "Content & Reasoning",
            "media": "Media & Playback"
        }

        active_categories = [cat_map[c] for c in categories if c in cat_map]
        overview_items = ", ".join(active_categories[:5])
        if len(active_categories) > 5:
            overview_items += f", and {active_categories[5]}"

        text = (
            f"Here is what I can do for you, Sir:\n"
            f"• Core Capabilities: {overview_items}.\n"
            f"• Applications: Over {breakdown['discovered_apps_count']} local applications recognized.\n"
            f"• Custom Commands: {len(breakdown['enabled_custom_commands'])} active workflows.\n\n"
            f"Say 'show all commands' for full reference, or 'show browser commands' for specific areas."
        )
        return text

    def get_all_commands_reference(self) -> str:
        """Fuller, organized command reference with examples and arguments for 'Jarvis, show all commands'."""
        breakdown = self.get_capabilities_breakdown()
        tools = breakdown["available_tools"]

        # Group tools by category
        grouped: Dict[str, List[Any]] = {}
        for t in tools:
            grouped.setdefault(t.category.lower(), []).append(t)

        cat_order = [
            ("applications", "Applications & Desktop Programs"),
            ("browser", "Websites & Browser Actions"),
            ("search", "Search Operations"),
            ("filesystem", "Files & Folders"),
            ("system", "System & Computer Controls"),
            ("developer", "Developer & Project Workflow"),
            ("content", "AI & Content Generation"),
            ("media", "Media & Video Playback"),
        ]

        examples_map = {
            "applications": ["'open Chrome'", "'launch VS Code'", "'switch to Notepad'", "'close Blender'"],
            "browser": ["'open ChatGPT in Chrome'", "'open YouTube'", "'open a new Chrome tab'", "'go back in Chrome'", "'read the current webpage'"],
            "search": ["'search Python tutorials'", "'search YouTube for lofi'", "'search GitHub for react'", "'find file main.py'"],
            "filesystem": ["'open Downloads'", "'create folder Projects on Desktop'", "'list files'", "'read notes.txt'"],
            "system": ["'mute volume'", "'set volume to 50'", "'lock computer'", "'system status'", "'take screenshot'"],
            "developer": ["'run tests'", "'check git status'", "'switch to Jarvis project'"],
            "content": ["'explain this python error'", "'write a professional email about project update'", "'summarize page'"],
            "media": ["'pause music'", "'next track'", "'toggle playback'"],
        }

        sections = ["JARVIS Comprehensive Command Reference:"]

        for cat_key, cat_title in cat_order:
            if cat_key in grouped:
                exs = examples_map.get(cat_key, [])
                ex_str = " | ".join(exs) if exs else "See individual commands"
                tool_names = ", ".join(t.name for t in grouped[cat_key][:4])
                sections.append(f"\n[{cat_title}]\n• Registered tools: {tool_names}\n• Examples: {ex_str}")

        if breakdown["enabled_custom_commands"]:
            custom_names = ", ".join(c.name for c in breakdown["enabled_custom_commands"][:4])
            sections.append(f"\n[Custom Workflows]\n• Active workflows: {custom_names}\n• Examples: 'run Focus Mode'")

        return "\n".join(sections)

    def get_scoped_commands(self, scope: str) -> str:
        """Lists only capabilities for a specific requested category (e.g. browser, files, system)."""
        scope_clean = scope.lower().strip()
        scope_alias_map = {
            "browser": "browser",
            "web": "browser",
            "chrome": "browser",
            "tabs": "browser",
            "file": "filesystem",
            "files": "filesystem",
            "folder": "filesystem",
            "folders": "filesystem",
            "filesystem": "filesystem",
            "application": "applications",
            "applications": "applications",
            "apps": "applications",
            "app": "applications",
            "system": "system",
            "os": "system",
            "computer": "system",
            "search": "search",
            "developer": "developer",
            "dev": "developer",
            "code": "developer",
            "content": "content",
            "ai": "content",
            "writing": "content",
            "media": "media",
            "custom": "custom",
        }

        target_cat = scope_alias_map.get(scope_clean, scope_clean)

        if target_cat == "custom":
            if self.custom_command_registry:
                cmds = self.custom_command_registry.list_commands(enabled_only=True)
                if cmds:
                    names = ", ".join(c.name for c in cmds)
                    return f"Active custom commands: {names}. You can say 'run <command>' to execute any of them."
            return "No custom commands are currently registered. You can create one anytime by saying 'create command Focus Mode'."

        breakdown = self.get_capabilities_breakdown()
        tools = [t for t in breakdown["available_tools"] if t.category.lower() == target_cat]

        if not tools:
            return f"I couldn't find specific commands registered under '{scope}'. Try asking for browser, files, applications, or system commands."

        tool_descs = [f"• {t.name}: {t.description}" for t in tools[:6]]
        desc_block = "\n".join(tool_descs)

        cat_names = {
            "browser": "Browser & Web Navigation",
            "filesystem": "File & Folder Operations",
            "applications": "Application Controls",
            "system": "System Controls",
            "search": "Search Capabilities",
            "developer": "Developer Workflows",
            "content": "Content & AI Generation",
            "media": "Media Playback Controls"
        }
        disp_title = cat_names.get(target_cat, target_cat.title())

        return f"Here are the supported {disp_title} commands, Sir:\n{desc_block}"


# Global Singleton Instance
capability_service = CapabilityService()
