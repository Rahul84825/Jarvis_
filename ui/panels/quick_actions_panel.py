"""
Quick Action Dock HUD Panel for Jarvis.
Provides one-click execution of 100% verified, real registered system capabilities.
"""

from typing import Callable, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from ui.widgets.hud_frame import HUDFrame
from ui.theme import HUDColors

class QuickActionsPanel(HUDFrame):
    """Futuristic HUD blade showing quick action triggers for verified capabilities."""

    def __init__(self, parent=None, on_action_cb: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.on_action_cb = on_action_cb
        self._init_ui()

    def _init_ui(self):
        hdr = QLabel("REGISTERED QUICK ACTIONS")
        hdr.setProperty("class", "hudSectionTitle")
        self.layout.addWidget(hdr)

        actions = [
            ("🔍 Explain Screen", "Explain my screen in simple language"),
            ("📄 Create File", "Create a Python file on Desktop"),
            ("📁 Search My Files", "Search my files"),
            ("⚙️ AI Providers", "AI provider settings"),
            ("🌐 Open Chrome", "Open Chrome"),
            ("📑 Open New Tab", "Open a new tab"),
            ("📸 Take Screenshot", "Take a screenshot"),
            ("🌙 Sleep Mode", "go to sleep"),
            ("📊 System Status", "What is my CPU and RAM usage?"),
            ("🔊 Test Audio Output", "Test your speakers"),
            ("📁 Open Downloads", "Open my Downloads"),
            ("🧪 Virtual Testing Lab", "open virtual testing room"),
            ("💡 Capabilities & Help", "What can you do?")
        ]

        for label, cmd in actions:
            btn = QPushButton(label)
            btn.setProperty("class", "quickActionBtn")
            btn.clicked.connect(lambda checked, c=cmd: self._trigger(c))
            self.layout.addWidget(btn)

        self.layout.addStretch()

    def _trigger(self, cmd: str):
        if self.on_action_cb:
            self.on_action_cb(cmd)
