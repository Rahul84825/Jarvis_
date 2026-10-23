"""Data models and enumerations for JARVIS Screen Understanding and Visual Intelligence."""

import time
import uuid
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict


class CaptureTarget(str, Enum):
    """Screen capture scope targets."""
    PRIMARY_SCREEN = "primary_screen"
    ALL_SCREENS = "all_screens"
    ACTIVE_WINDOW = "active_window"
    SELECTED_WINDOW = "selected_window"
    REGION = "region"
    CUSTOM_IMAGE = "custom_image"


class ExplanationStyle(str, Enum):
    """Different explanation perspectives and depths."""
    BEGINNER = "beginner"
    SIMPLE_ENGLISH = "simple_english"
    STEP_BY_STEP = "step_by_step"
    IMPORTANT_POINTS = "important_points"
    TECHNICAL = "technical"
    CODE_LINE_BY_LINE = "code_line_by_line"
    EXAMPLE_BASED = "example_based"
    EXAM_ORIENTED = "exam_oriented"
    INTERVIEW_ORIENTED = "interview_oriented"
    SUMMARY_THEN_DETAIL = "summary_then_detail"
    COMPARISON = "comparison"
    EXPLAIN_POINT = "explain_point"


@dataclass
class ScreenRegion:
    """Bounding coordinates for custom screen regions."""
    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> tuple:
        return (self.x, self.y, self.width, self.height)


@dataclass
class VisualElement:
    """Detected UI or graphic element on the captured screen."""
    element_id: str
    element_type: str  # text, code, button, diagram, chart, error_box, image
    label: str
    bounding_rect: Optional[tuple] = None
    confidence: float = 1.0
    text_content: str = ""


@dataclass
class ScreenContext:
    """Normalized structured context captured from the user's desktop."""
    context_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: float = field(default_factory=time.time)
    target: CaptureTarget = CaptureTarget.PRIMARY_SCREEN
    window_title: str = ""
    process_name: str = ""
    app_identity: str = ""
    region: Optional[ScreenRegion] = None
    image_path: Optional[str] = None
    image_base64: Optional[str] = None
    extracted_text: str = ""
    ui_elements: List[Dict[str, Any]] = field(default_factory=list)
    visual_elements: List[Dict[str, Any]] = field(default_factory=list)
    ocr_confidence: float = 1.0
    source: str = "windows_desktop"
    is_fresh: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_readable(self) -> bool:
        """Determines if meaningful text or UI content was extracted from the window."""
        return bool(self.extracted_text and len(self.extracted_text.strip()) >= 5) or len(self.ui_elements) > 0 or len(self.visual_elements) > 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(self.target, CaptureTarget):
            d["target"] = self.target.value
        d["is_readable"] = self.is_readable
        return d


@dataclass
class ScreenExplanation:
    """Structured explanation generated from a screen analysis session."""
    session_id: str
    context_id: str
    style: ExplanationStyle
    summary: str
    important_points: List[str] = field(default_factory=list)
    detailed_text: str = ""
    code_snippets: List[Dict[str, str]] = field(default_factory=list)
    error_diagnosis: Optional[str] = None
    diagram_explanation: Optional[str] = None
    model_used: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(self.style, ExplanationStyle):
            d["style"] = self.style.value
        return d
