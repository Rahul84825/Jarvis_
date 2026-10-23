"""Data models for Universal Desktop Interaction and Context Awareness."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class ControlType(str, Enum):
    """Semantic classification of desktop and web input controls."""
    EDIT = "edit"
    DOCUMENT = "document"
    COMBOBOX = "combobox"
    SEARCH_FIELD = "search_field"
    MESSAGE_COMPOSER = "message_composer"
    CODE_EDITOR = "code_editor"
    PROMPT_BOX = "prompt_box"
    EMAIL_TO = "email_to"
    EMAIL_SUBJECT = "email_subject"
    EMAIL_BODY = "email_body"
    BUTTON = "button"
    UNKNOWN = "unknown"


class TargetResolution(str, Enum):
    """Outcome of resolving an intended text entry target."""
    SINGLE_TARGET = "single_target"          # Case A: Clear unambiguous target
    AMBIGUOUS = "ambiguous"                  # Case B: Multiple plausible targets
    NO_TARGET = "no_target"                  # Case C: No reliable target identified
    EXPLICIT_OVERRIDE = "explicit_override"  # Case D: Specific destination requested


@dataclass
class TargetControl:
    """Represents an accessible interactive UI target on screen."""
    control_id: str
    name: str = ""
    control_type: ControlType = ControlType.EDIT
    help_text: str = ""
    automation_id: str = ""
    class_name: str = ""
    is_focused: bool = False
    bounding_box: tuple = (0, 0, 0, 0)  # (left, top, width, height)
    confidence: float = 0.5
    raw_element: Any = None  # Reference to underlying native UIA/DOM element if present

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "name": self.name,
            "control_type": self.control_type.value,
            "help_text": self.help_text,
            "automation_id": self.automation_id,
            "class_name": self.class_name,
            "is_focused": self.is_focused,
            "bounding_box": self.bounding_box,
            "confidence": self.confidence
        }


@dataclass
class DesktopContext:
    """Snapshot of the active desktop interaction state."""
    foreground_app: str = "unknown"
    process_name: str = "unknown"
    window_hwnd: int = 0
    window_title: str = ""
    browser_info: Optional[Dict[str, Any]] = None
    focused_element: Optional[TargetControl] = None
    available_targets: List[TargetControl] = field(default_factory=list)
    selected_text: Optional[str] = None
    context_source: str = "accessibility_tree"  # 'accessibility_tree', 'cdp', 'ocr', 'fallback'
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "foreground_app": self.foreground_app,
            "process_name": self.process_name,
            "window_hwnd": self.window_hwnd,
            "window_title": self.window_title,
            "browser_info": self.browser_info,
            "focused_element": self.focused_element.to_dict() if self.focused_element else None,
            "available_targets": [t.to_dict() for t in self.available_targets],
            "selected_text": self.selected_text,
            "context_source": self.context_source,
            "timestamp": self.timestamp
        }
