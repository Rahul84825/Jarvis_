"""
Fluid Holographic Audio Waveform & Spectrum Visualizer.
Renders responsive spectrum bars reacting to voice activity and TTS playback.
"""

import math
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient
from PyQt6.QtWidgets import QWidget

from ui.state_machine import JarvisUIState, STATE_CONFIGS
from ui.theme import HUDColors

class AudioWaveformVisualizer(QWidget):
    """Futuristic animated audio spectrum visualizer."""

    def __init__(self, parent=None, bars: int = 32):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setMinimumWidth(200)

        self._bars = bars
        self._heights = np.zeros(bars)
        self._state = JarvisUIState.STANDBY
        self._config = STATE_CONFIGS[self._state]
        self._phase = 0.0
        self._active = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)  # ~33 FPS

    def set_state(self, state: JarvisUIState):
        self._state = state
        self._config = STATE_CONFIGS.get(state, STATE_CONFIGS[JarvisUIState.STANDBY])
        self._active = state in [JarvisUIState.LISTENING, JarvisUIState.SPEAKING, JarvisUIState.THINKING, JarvisUIState.EXECUTING]

    def set_amplitude(self, amp: float):
        """Injects live audio RMS amplitude to modulate spectrum peaks."""
        self._active = True
        scale = max(0.1, min(1.0, amp))
        for i in range(self._bars):
            self._heights[i] = max(self._heights[i], scale * (0.5 + 0.5 * math.sin(i * 0.4 + self._phase)))

    def _animate(self):
        if self._active:
            self._phase += 0.22
            for i in range(self._bars):
                # Harmonic wave equation with slight random perturbation
                v = (
                    math.sin(self._phase + i * 0.28) * 0.45 +
                    math.sin(self._phase * 1.7 + i * 0.6) * 0.35 +
                    np.random.uniform(-0.1, 0.1)
                )
                self._heights[i] = max(0.06, abs(v))
            self.update()
        else:
            if np.any(self._heights > 0.02):
                self._heights *= 0.82
                self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cy = h / 2.0

        bar_spacing = w / (self._bars + 1)
        bar_w = max(2.5, bar_spacing * 0.55)

        color = self._config.primary_color
        r, g, b = color.red(), color.green(), color.blue()

        painter.setPen(Qt.PenStyle.NoPen)

        for i in range(self._bars):
            x = (i + 1) * bar_spacing - bar_w / 2.0
            amp = self._heights[i] if self._active else (self._heights[i] * 0.12)
            bar_h = max(2.5, (cy * 0.88) * amp)

            # Futuristic gradient from base to top
            grad = QLinearGradient(x, cy - bar_h, x, cy + bar_h)
            grad.setColorAt(0.0, QColor(r, g, b, 230))
            grad.setColorAt(0.5, QColor(255, 255, 255, 240))
            grad.setColorAt(1.0, QColor(r, g, b, 230))

            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(
                int(x),
                int(cy - bar_h),
                int(bar_w),
                int(bar_h * 2.0),
                int(bar_w / 2.0),
                int(bar_w / 2.0)
            )
