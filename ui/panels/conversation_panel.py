"""
Conversation & Neural Chat Stream HUD Panel for Jarvis.
Displays real-time spoken and typed dialogue with futuristic message bubbles.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit
from ui.widgets.hud_frame import HUDFrame
from ui.theme import HUDColors

class ConversationPanel(HUDFrame):
    """Futuristic HUD blade showing live dialogue and assistant responses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        hdr = QLabel("LIVE NEURAL CONVERSATION")
        hdr.setProperty("class", "hudSectionTitle")
        self.layout.addWidget(hdr)

        self._chat_view = QTextEdit()
        self._chat_view.setProperty("class", "chatView")
        self._chat_view.setReadOnly(True)
        self._chat_view.append(
            "<div style='margin-bottom:8px;'><b style='color:#00f0ff;'>[JARVIS ONLINE]</b> "
            "<span style='color:#94a3b8;'>Cyber-HUD Core initialized. Standing by for voice or text commands.</span></div>"
        )
        self.layout.addWidget(self._chat_view)

    def add_message(self, sender: str, message: str, tool: str = None):
        """Appends formatted message bubble to the chat stream."""
        if sender == "user":
            html = (
                f"<div style='margin-bottom:8px;'>"
                f"<span style='color:#00f0ff; font-weight:bold; font-size:11px; letter-spacing:1px;'>YOU:</span> "
                f"<span style='color:#ffffff;'>{message}</span>"
                f"</div>"
            )
        else:
            tool_tag = f" <span style='background-color:#7b68ee; color:#ffffff; padding:1px 5px; border-radius:3px; font-size:9px; font-weight:bold;'>{tool}</span>" if tool else ""
            html = (
                f"<div style='margin-bottom:10px;'>"
                f"<span style='color:#9d4edd; font-weight:bold; font-size:11px; letter-spacing:1px;'>JARVIS:</span>{tool_tag} "
                f"<span style='color:#e2e8f0;'>{message}</span>"
                f"</div>"
            )

        self._chat_view.append(html)
        # Scroll to bottom
        sb = self._chat_view.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())
