"""
Configuration parameters for Jarvis Vision, Camera, and Hand Perception.
"""

from dataclasses import dataclass
import os

@dataclass
class VisionConfig:
    camera_enabled: bool = True
    default_camera_index: int = 0
    capture_width: int = 640
    capture_height: int = 480
    capture_fps: int = 30
    vision_fps: int = 12
    buffer_seconds: int = 10
    hand_tracking_enabled: bool = True
    gesture_confidence_threshold: float = 0.75
    gesture_debounce_frames: int = 3
    gesture_cooldown_seconds: float = 0.6

vision_config = VisionConfig()
