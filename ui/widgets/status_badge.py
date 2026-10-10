"""
Holographic Status Badge Widget for Jarvis HUD.
Displays reactive glowing state pills, animated LEDs, and subtitle indicators.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QLinearGradient
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout

from ui.state_machine import JarvisUIState, STATE_CONFIGS, StateVisualConfig
from ui.theme import HUDColors

class StatusBadgeWidget(QWidget):
    """Futuristic glowing status indicator badge with animated pulsing beacon."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self._state = JarvisUIState.STANDBY
        self._config = STATE_CONFIGS[self._state]
        self._pulse_phase = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Text labels
        text_vbox = QVBoxLayout()
        text_vbox.setSpacing(2)
        text_vbox.setContentsMargins(0, 0, 0, 0)

        self._title_lbl = QLabel(self._config.title)
        self._title_lbl.setStyleSheet(f"color: {self._config.primary_color.name()}; font-weight: 900; font-size: 13px; letter-spacing: 2px;")
        
        self._sub_lbl = QLabel(self._config.subtext)
        self._sub_lbl.setStyleSheet("color: #64748b; font-weight: 700; font-size: 9px; letter-spacing: 1.5px;")

        text_vbox.addWidget(self._title_lbl)
        text_vbox.addWidget(self._sub_lbl)
        layout.addLayout(text_vbox)

        # Beacon pulse timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_pulse)
        self._timer.start(33)  # ~30 FPS

    def set_state(self, state: JarvisUIState):
        self._state = state
        self._config = STATE_CONFIGS.get(state, STATE_CONFIGS[JarvisUIState.STANDBY])
        self._title_lbl.setText(self._config.title)
        self._title_lbl.setStyleSheet(f"color: {self._config.primary_color.name()}; font-weight: 900; font-size: 13px; letter-spacing: 2px;")
        self._sub_lbl.setText(self._config.subtext)
        self.update()

    def _animate_pulse(self):
        self._pulse_phase += self._config.pulse_freq
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        color = self._config.primary_color

        # Background Pill
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 60), 1))
        painter.setBrush(QBrush(QColor(10, 14, 24, 220)))
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 6, 6)

        # Glowing corner accent bars
        painter.setPen(QPen(color, 2))
        painter.drawLine(0, 0, 8, 0)
        painter.drawLine(0, 0, 0, 8)
        painter.drawLine(w - 1, h - 1, w - 9, h - 1)
        painter.drawLine(w - 1, h - 1, w - 1, h - 9)
