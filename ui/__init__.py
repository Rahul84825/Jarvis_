"""
Jarvis UI Subsystem.
Exposes master HUD window, widgets, reactor, and panels.
"""

from ui.main_window import MainWindow
from ui.state_machine import JarvisUIState
from ui.theme import HUDColors, get_hud_stylesheet
from ui.reactor.arc_reactor import ArcReactorWidget
from ui.reactor.waveform import AudioWaveformVisualizer
from ui.panels.telemetry_panel import TelemetryPanel
from ui.panels.agent_trace_panel import AgentTracePanel
from ui.panels.conversation_panel import ConversationPanel
from ui.panels.quick_actions_panel import QuickActionsPanel
from ui.widgets.hud_frame import HUDFrame
from ui.widgets.status_badge import StatusBadgeWidget
from ui.widgets.boot_overlay import BootOverlayWidget

__all__ = [
    "MainWindow",
    "JarvisUIState",
    "HUDColors",
    "get_hud_stylesheet",
    "ArcReactorWidget",
    "AudioWaveformVisualizer",
    "TelemetryPanel",
    "AgentTracePanel",
    "ConversationPanel",
    "QuickActionsPanel",
    "HUDFrame",
    "StatusBadgeWidget",
    "BootOverlayWidget"
]
