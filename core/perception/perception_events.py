"""
Perception Event Dataclasses for Jarvis.
Provides structured event types for gesture recognition, camera lifecycle, and vision tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Optional, List, Dict, Any, Tuple


class CameraState(str, Enum):
    OFF = "OFF"
    IDLE = "OFF"  # Backward compatibility alias
    STARTING = "STARTING"
    ACTIVE = "ACTIVE"
    STOPPING = "STOPPING"
    ERROR = "ERROR"
    UNAVAILABLE = "UNAVAILABLE"


class GestureType(str, Enum):
    NONE = "NONE"
    PINCH = "PINCH"
    POINT = "POINT"
    OPEN_PALM = "OPEN_PALM"
    CLOSED_FIST = "CLOSED_FIST"
    THUMBS_UP = "THUMBS_UP"
    PEACE = "PEACE"


@dataclass
class NormalizedLandmark:
    x: float
    y: float
    z: float = 0.0


@dataclass
class HandObservation:
    hand_id: int
    handedness: str  # "Left" | "Right"
    confidence: float
    landmarks: List[NormalizedLandmark]  # 21 points
    bbox: Tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)
    timestamp: float = field(default_factory=time.time)


@dataclass
class GestureEvent:
    gesture: GestureType
    confidence: float
    hand: str  # "Left" | "Right"
    pointer_pos: Optional[Tuple[float, float]] = None  # (norm_x, norm_y)
    timestamp: float = field(default_factory=time.time)


@dataclass
class CameraDeviceInfo:
    index: int
    name: str
    backend: str = "DEFAULT"
    is_default: bool = False
    available: bool = True
    width: int = 640
    height: int = 480
    fps: int = 30


@dataclass
class CameraStateEvent:
    state: CameraState
    device_index: int
    device_name: str
    fps_capture: float = 0.0
    fps_vision: float = 0.0
    message: str = ""
    timestamp: float = field(default_factory=time.time)

