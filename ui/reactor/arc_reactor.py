"""
Central Arc Reactor HUD Widget for Jarvis.
Implements multi-layered concentric rotating tick rings, glowing plasma core,
and state-reactive breathing animations in native PyQt6 (60 FPS).
"""

import math
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient, QLinearGradient
from PyQt6.QtWidgets import QWidget

from ui.state_machine import JarvisUIState, STATE_CONFIGS, StateVisualConfig
from ui.theme import HUDColors
from ui.reactor.particles import ParticleField

class ArcReactorWidget(QWidget):
    """Futuristic Central Arc Reactor with rotating rings, reticles, and pulsing core."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)

        self._state = JarvisUIState.STANDBY
        self._config = STATE_CONFIGS[self._state]

        # Animation states
        self._angle_outer = 0.0
        self._angle_inner = 0.0
        self._angle_ticks = 0.0
        self._pulse_phase = 0.0
        self._core_scale = 1.0

        # Particle field
        self._particles = ParticleField(count=32, base_radius=90.0)

        # 60 FPS Render Timer (~16.6ms)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_frame)
        self._timer.start(16)

    def set_state(self, state: JarvisUIState):
        self._state = state
        self._config = STATE_CONFIGS.get(state, STATE_CONFIGS[JarvisUIState.STANDBY])
        self.update()

    def set_audio_amplitude(self, amp: float):
        """Modulates core size and glow based on live speech/mic amplitude."""
        clamped = max(0.0, min(1.0, amp))
        self._core_scale = 1.0 + clamped * 0.35

    def set_camera_active(self, is_active: bool):
        """Adjusts subtle ambient glow when camera is actively streaming."""
        self._camera_active = is_active
        self.update()

    def trigger_gesture_pulse(self, gesture_name: str):
        """Triggers a subtle reactive pulse on the Arc Reactor when a gesture is confirmed."""
        g = gesture_name.upper()
        if "PINCH" in g:
            self._core_scale = 1.30
        elif "POINT" in g:
            self._angle_outer = (self._angle_outer + 30.0) % 360.0
            self._core_scale = 1.15
        elif "OPEN_PALM" in g:
            self._core_scale = 1.25
        elif "THUMBS_UP" in g:
            self._core_scale = 1.20
        self.update()


    def _animate_frame(self):
        speed = self._config.rotation_speed
        self._angle_outer = (self._angle_outer + 0.6 * speed) % 360.0
        self._angle_inner = (self._angle_inner - 0.9 * speed) % 360.0
        self._angle_ticks = (self._angle_ticks + 0.3 * speed) % 360.0

        self._pulse_phase = (self._pulse_phase + self._config.pulse_freq) % math.tau

        # Update particles
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        base_r = min(cx, cy) * 0.75
        self._particles.update(cx, cy, base_r, self._config.particle_speed)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        max_r = min(cx, cy) - 10.0

        if max_r < 30:
            return

        color = self._config.primary_color
        r, g, b = color.red(), color.green(), color.blue()

        # 1. Floating Particles
        self._particles.draw(painter, color)

        # 2. Outer Halo Glow
        glow_grad = QRadialGradient(cx, cy, max_r)
        glow_grad.setColorAt(0.0, QColor(r, g, b, 50))
        glow_grad.setColorAt(0.5, QColor(r, g, b, 15))
        glow_grad.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_grad))
        painter.drawEllipse(QPointF(cx, cy), max_r, max_r)

        # 3. Outer Reticle Ring with Broken Arcs
        r_outer = max_r * 0.92
        pen_outer = QPen(QColor(r, g, b, 140), 1.5)
        painter.setPen(pen_outer)
        painter.drawEllipse(QPointF(cx, cy), r_outer, r_outer)

        # Outer Segment Arcs (Rotating)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle_outer)
        pen_arc = QPen(QColor(r, g, b, 230), 3.0)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)

        arc_rect = QRectF(-r_outer, -r_outer, r_outer * 2, r_outer * 2)
        # Draw 3 prominent segmented arcs (120 deg apart)
        for i in range(3):
            painter.drawArc(arc_rect, int((i * 120) * 16), int(45 * 16))
        painter.restore()

        # 4. Concentric Ticks Ring (Rotating Counter-Clockwise)
        r_ticks = max_r * 0.78
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle_ticks)
        pen_tick = QPen(QColor(r, g, b, 90), 1.0)
        painter.setPen(pen_tick)

        num_ticks = 36
        for i in range(num_ticks):
            angle_rad = (i * (360.0 / num_ticks)) * (math.pi / 180.0)
            is_major = (i % 6 == 0)
            t_len = 7.0 if is_major else 3.5
            if is_major:
                painter.setPen(QPen(QColor(r, g, b, 200), 1.5))
            else:
                painter.setPen(QPen(QColor(r, g, b, 70), 1.0))

            x1 = (r_ticks - t_len) * math.cos(angle_rad)
            y1 = (r_ticks - t_len) * math.sin(angle_rad)
            x2 = r_ticks * math.cos(angle_rad)
            y2 = r_ticks * math.sin(angle_rad)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        painter.restore()

        # 5. Intermediate Ring with Segment Blocks
        r_mid = max_r * 0.62
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle_inner)

        pen_mid = QPen(QColor(r, g, b, 120), 1.0)
        painter.setPen(pen_mid)
        painter.drawEllipse(QPointF(0, 0), r_mid, r_mid)

        # 4 Segment Blocks
        pen_block = QPen(QColor(r, g, b, 240), 3.5)
        painter.setPen(pen_block)
        mid_rect = QRectF(-r_mid, -r_mid, r_mid * 2, r_mid * 2)
        for i in range(4):
            painter.drawArc(mid_rect, int((i * 90 + 10) * 16), int(30 * 16))
        painter.restore()

        # 6. Inner Glowing Plasma Core
        pulse_val = 0.5 + 0.5 * math.sin(self._pulse_phase)
        r_core_base = max_r * 0.38
        r_core = r_core_base * (0.92 + 0.16 * pulse_val) * self._core_scale

        core_grad = QRadialGradient(cx, cy, r_core)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 250))
        core_grad.setColorAt(0.25, QColor(r, g, b, 240))
        core_grad.setColorAt(0.70, QColor(r, g, b, 120))
        core_grad.setColorAt(1.0, QColor(r, g, b, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), r_core, r_core)

        # Central Arc Core Reticle Crosshair & Ring
        pen_core_ring = QPen(QColor(255, 255, 255, 190), 1.5)
        painter.setPen(pen_core_ring)
        painter.drawEllipse(QPointF(cx, cy), r_core * 0.45, r_core * 0.45)

        # Crosshairs
        pen_cross = QPen(QColor(r, g, b, 160), 1.0)
        painter.setPen(pen_cross)
        c_len = r_core * 0.8
        painter.drawLine(QPointF(cx - c_len, cy), QPointF(cx - r_core * 0.2, cy))
        painter.drawLine(QPointF(cx + r_core * 0.2, cy), QPointF(cx + c_len, cy))
        painter.drawLine(QPointF(cx, cy - c_len), QPointF(cx, cy - r_core * 0.2))
        painter.drawLine(QPointF(cx, cy + r_core * 0.2), QPointF(cx, cy + c_len))
