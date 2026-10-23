"""
Agent & 3-Layer Intelligence Trace HUD Panel for Jarvis.
Displays active cognitive layer, tool dispatches, and execution verification.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from ui.widgets.hud_frame import HUDFrame
from ui.theme import HUDColors

class AgentTracePanel(HUDFrame):
    """Futuristic HUD blade showing 3-layer intelligence routing and live tool execution traces."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        hdr = QLabel("NEURAL INTELLIGENCE TRACE")
        hdr.setProperty("class", "hudSectionTitle")
        self.layout.addWidget(hdr)

        # 1. Active Intelligence Layer Badge
        self._layer_card = QFrame()
        self._layer_card.setStyleSheet("background-color: rgba(16, 22, 36, 220); border: 1px solid rgba(0, 240, 255, 40); border-radius: 6px; padding: 8px;")
        layer_layout = QVBoxLayout(self._layer_card)
        layer_layout.setContentsMargins(8, 6, 8, 6)
        layer_layout.setSpacing(2)

        self._layer_badge = QLabel("LAYER 1 // FAST REFLEX CORE")
        self._layer_badge.setStyleSheet("color: #00f0ff; font-weight: 800; font-size: 11px; letter-spacing: 1px;")

        self._layer_desc = QLabel("Deterministic Local Execution (0.5ms)")
        self._layer_desc.setStyleSheet("color: #64748b; font-size: 10px;")

        layer_layout.addWidget(self._layer_badge)
        layer_layout.addWidget(self._layer_desc)
        self.layout.addWidget(self._layer_card)

        # 2. Last Executed Action / Tool Card
        self._tool_card = QFrame()
        self._tool_card.setStyleSheet("background-color: rgba(12, 16, 26, 200); border: 1px solid rgba(255, 255, 255, 15); border-radius: 6px; padding: 8px;")
        tool_layout = QVBoxLayout(self._tool_card)
        tool_layout.setContentsMargins(8, 6, 8, 6)
        tool_layout.setSpacing(4)

        tool_hdr_box = QHBoxLayout()
        tool_title = QLabel("ACTIVE TOOL DISPATCH")
        tool_title.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 10px; letter-spacing: 1px;")
        self._status_pill = QLabel("IDLE")
        self._status_pill.setStyleSheet("background-color: rgba(0, 240, 255, 30); color: #00f0ff; padding: 1px 6px; border-radius: 3px; font-weight: bold; font-size: 9px;")
        tool_hdr_box.addWidget(tool_title)
        tool_hdr_box.addStretch()
        tool_hdr_box.addWidget(self._status_pill)
        tool_layout.addLayout(tool_hdr_box)

        self._action_lbl = QLabel("No active tool operations.")
        self._action_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        self._action_lbl.setWordWrap(True)
        tool_layout.addWidget(self._action_lbl)

        self.layout.addWidget(self._tool_card)
        self.layout.addStretch()

    def update_pipeline_stage(self, raw: str, norm: str, intent: str, exec_str: str, resp: str, state: str):
        """Updates trace card from runtime pipeline events."""
        # Determine layer
        if intent.startswith("os_action") or intent in ["open_app", "close_app", "open_url", "screenshot", "system_control"]:
            self._layer_badge.setText("LAYER 1 // FAST REFLEX CORE")
            self._layer_badge.setStyleSheet("color: #00f0ff; font-weight: 800; font-size: 11px; letter-spacing: 1px;")
            self._layer_desc.setText("Deterministic Local Execution (<2ms)")
        elif intent in ["conversation", "help", "identity", "history_query"]:
            self._layer_badge.setText("LAYER 2 // CONTEXT & UNDERSTANDING")
            self._layer_badge.setStyleSheet("color: #ffb300; font-weight: 800; font-size: 11px; letter-spacing: 1px;")
            self._layer_desc.setText("Conversational Context & Target Resolver")
        elif "nvidia" in exec_str.lower() or "nemotron" in exec_str.lower() or "nemotron" in intent.lower():
            self._layer_badge.setText("LAYER 3 // NVIDIA NEMOTRON REASONING")
            self._layer_badge.setStyleSheet("color: #76b900; font-weight: 800; font-size: 11px; letter-spacing: 1px;")  # NVIDIA green
            self._layer_desc.setText(f"Cloud Reasoning Brain ({exec_str})")
        else:
            self._layer_badge.setText("LAYER 3 // REASONING & PLANNING")
            self._layer_badge.setStyleSheet("color: #9d4edd; font-weight: 800; font-size: 11px; letter-spacing: 1px;")
            self._layer_desc.setText("Autonomous Agent & Tool Chaining")

    def update_action_result(self, action: str, success: bool, message: str):
        """Updates tool card with verified execution result."""
        status_text = "✔ SUCCESS" if success else "✖ FAILED"
        status_bg = "rgba(0, 229, 163, 40)" if success else "rgba(255, 51, 102, 40)"
        status_fg = "#00e5a3" if success else "#ff3366"

        self._status_pill.setText(status_text)
        self._status_pill.setStyleSheet(f"background-color: {status_bg}; color: {status_fg}; padding: 1px 6px; border-radius: 3px; font-weight: bold; font-size: 9px;")

        self._action_lbl.setText(f"<b>{action}:</b> {message}")
