"""
Ambient Holographic Energy Particle System for Jarvis Arc Reactor.
Draws floating, drifting energy sparks and orbital nodes.
"""

import math
import random
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

class Particle:
    def __init__(self, cx: float, cy: float, base_radius: float):
        self.cx = cx
        self.cy = cy
        self.angle = random.uniform(0, math.tau)
        self.dist = random.uniform(base_radius * 0.4, base_radius * 1.3)
        self.speed = random.uniform(0.005, 0.02) * (1 if random.random() > 0.5 else -1)
        self.size = random.uniform(1.2, 3.2)
        self.alpha = random.uniform(0.3, 0.9)
        self.pulse_phase = random.uniform(0, math.tau)

    def update(self, cx: float, cy: float, speed_factor: float = 1.0):
        self.cx = cx
        self.cy = cy
        self.angle = (self.angle + self.speed * speed_factor) % math.tau
        self.pulse_phase = (self.pulse_phase + 0.05) % math.tau
        self.alpha = 0.4 + 0.5 * math.sin(self.pulse_phase)

    def get_pos(self) -> QPointF:
        x = self.cx + self.dist * math.cos(self.angle)
        y = self.cy + self.dist * math.sin(self.angle)
        return QPointF(x, y)

class ParticleField:
    """Manages an array of ambient holographic energy particles."""

    def __init__(self, count: int = 36, base_radius: float = 100.0):
        self.count = count
        self.base_radius = base_radius
        self.particles: List[Particle] = [Particle(0, 0, base_radius) for _ in range(count)]

    def update(self, cx: float, cy: float, base_radius: float, speed_factor: float = 1.0):
        self.base_radius = base_radius
        for p in self.particles:
            p.update(cx, cy, speed_factor)

    def draw(self, painter: QPainter, primary_color: QColor):
        painter.setPen(Qt.PenStyle.NoPen)
        r = primary_color.red()
        g = primary_color.green()
        b = primary_color.blue()

        for p in self.particles:
            pos = p.get_pos()
            a = int(max(0.0, min(1.0, p.alpha)) * 255)
            painter.setBrush(QBrush(QColor(r, g, b, a)))
            painter.drawEllipse(pos, p.size / 2.0, p.size / 2.0)
