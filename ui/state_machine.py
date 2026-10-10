"""
Jarvis UI Visual State Machine.
Defines UI visual states, theme mappings, and reactive visual parameters.
"""

from enum import Enum
from dataclasses import dataclass
from PyQt6.QtGui import QColor
from ui.theme import HUDColors

class JarvisUIState(str, Enum):
    OFFLINE = "OFFLINE"
    BOOT = "BOOT"
    STANDBY = "STANDBY"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    UNDERSTANDING = "UNDERSTANDING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"

@dataclass
class StateVisualConfig:
    title: str
    subtext: str
    primary_color: QColor
    glow_color: QColor
    rotation_speed: float  # Degrees per frame
    pulse_freq: float      # Core breathing rate
    particle_speed: float  # Particle velocity multiplier

STATE_CONFIGS = {
    JarvisUIState.OFFLINE: StateVisualConfig(
        title="SYSTEM OFFLINE",
        subtext="DISCONNECTED",
        primary_color=HUDColors.TEXT_MUTED,
        glow_color=HUDColors.BORDER_MUTED,
        rotation_speed=0.2,
        pulse_freq=0.02,
        particle_speed=0.3
    ),
    JarvisUIState.BOOT: StateVisualConfig(
        title="INITIALIZING SYSTEM",
        subtext="VERIFYING SUBSYSTEMS",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=1.8,
        pulse_freq=0.08,
        particle_speed=1.5
    ),
    JarvisUIState.STANDBY: StateVisualConfig(
        title="ONLINE // STANDBY",
        subtext="SAY 'JARVIS' TO ACTIVATE",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=0.5,
        pulse_freq=0.03,
        particle_speed=0.6
    ),
    JarvisUIState.LISTENING: StateVisualConfig(
        title="LISTENING",
        subtext="CAPTURING VOICE STREAM",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=QColor(0, 240, 255, 120),
        rotation_speed=1.4,
        pulse_freq=0.09,
        particle_speed=1.8
    ),
    JarvisUIState.TRANSCRIBING: StateVisualConfig(
        title="TRANSCRIBING",
        subtext="PROCESSING NEURAL SPEECH",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=2.0,
        pulse_freq=0.10,
        particle_speed=2.0
    ),
    JarvisUIState.UNDERSTANDING: StateVisualConfig(
        title="UNDERSTANDING",
        subtext="RESOLVING INTENT",
        primary_color=HUDColors.AMBER_STANDBY,
        glow_color=HUDColors.AMBER_GLOW,
        rotation_speed=2.2,
        pulse_freq=0.12,
        particle_speed=2.2
    ),
    JarvisUIState.THINKING: StateVisualConfig(
        title="REASONING",
        subtext="AGENTIC COGNITION ONLINE",
        primary_color=HUDColors.VIOLET_THINKING,
        glow_color=HUDColors.VIOLET_GLOW,
        rotation_speed=2.8,
        pulse_freq=0.14,
        particle_speed=2.5
    ),
    JarvisUIState.EXECUTING: StateVisualConfig(
        title="EXECUTING",
        subtext="DISPATCHING TOOL ACTION",
        primary_color=HUDColors.AMBER_STANDBY,
        glow_color=HUDColors.AMBER_GLOW,
        rotation_speed=3.2,
        pulse_freq=0.15,
        particle_speed=3.0
    ),
    JarvisUIState.SPEAKING: StateVisualConfig(
        title="RESPONDING",
        subtext="NEURAL VOICE SYNTHESIS",
        primary_color=HUDColors.TEAL_SPEAKING,
        glow_color=HUDColors.TEAL_GLOW,
        rotation_speed=1.6,
        pulse_freq=0.12,
        particle_speed=1.6
    ),
    JarvisUIState.ERROR: StateVisualConfig(
        title="SYSTEM ALERT",
        subtext="ACTION FAILED / RECOVERING",
        primary_color=HUDColors.CRIMSON_ERROR,
        glow_color=HUDColors.CRIMSON_GLOW,
        rotation_speed=0.6,
        pulse_freq=0.06,
        particle_speed=0.5
    ),
}

def map_runtime_status_to_ui_state(status: str) -> JarvisUIState:
    """Maps runtime status strings from core to JarvisUIState."""
    s = (status or "").upper().strip()
    if "LISTEN" in s:
        return JarvisUIState.LISTENING
    if "TRANSCRIB" in s:
        return JarvisUIState.TRANSCRIBING
    if "THINK" in s or "REASON" in s:
        return JarvisUIState.THINKING
    if "EXEC" in s or "TOOL" in s or "ACTION" in s:
        return JarvisUIState.EXECUTING
    if "SPEAK" in s or "VOICE" in s:
        return JarvisUIState.SPEAKING
    if "ERR" in s or "FAIL" in s:
        return JarvisUIState.ERROR
    if "BOOT" in s or "INIT" in s:
        return JarvisUIState.BOOT
    if "OFFLINE" in s:
        return JarvisUIState.OFFLINE
    return JarvisUIState.STANDBY
