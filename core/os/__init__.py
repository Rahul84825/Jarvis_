"""Full Operating System Control Layer for Jarvis.
Provides cross-platform terminal management, filesystem operations, process tracking, system telemetry, and project registry capabilities.
"""
from core.os.terminal_manager import TerminalManager
from core.os.filesystem_manager import FilesystemManager
from core.os.process_manager import ProcessManager
from core.os.system_info import SystemInfoProvider
from core.os.project_registry import ProjectRegistry
from core.os.browser_manager import BrowserManager

__all__ = [
    "TerminalManager",
    "FilesystemManager",
    "ProcessManager",
    "SystemInfoProvider",
    "ProjectRegistry",
    "BrowserManager"
]
