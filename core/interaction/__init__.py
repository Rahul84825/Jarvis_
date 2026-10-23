"""Universal Desktop Interaction and Context Awareness Package."""

from core.interaction.models import (
    TargetControl,
    DesktopContext,
    ControlType,
    TargetResolution
)
from core.interaction.context_adapter import (
    BaseDesktopContextAdapter,
    WindowsDesktopContextAdapter,
    LinuxDesktopContextAdapter
)
from core.interaction.desktop_context_service import (
    DesktopContextService,
    desktop_context_service
)
from core.interaction.text_entry_service import (
    TextEntryService,
    text_entry_service
)

__all__ = [
    "TargetControl",
    "DesktopContext",
    "ControlType",
    "TargetResolution",
    "BaseDesktopContextAdapter",
    "WindowsDesktopContextAdapter",
    "LinuxDesktopContextAdapter",
    "DesktopContextService",
    "desktop_context_service",
    "TextEntryService",
    "text_entry_service"
]
