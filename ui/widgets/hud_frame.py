"""
HUD Frame Widget with Cyber Reticle Corners.
Provides a futuristic panel container with glassmorphism and holographic corner brackets.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtWidgets import QFrame, QVBoxLayout

class HUDFrame(QFrame):
    """Futuristic HUD Panel Frame with technical corner brackets and glowing border."""

    def __init__(self, parent=None, corner_size: int = 12, border_color: QColor = None):
        super().__init__(parent)
        self._corner_size = corner_size
        self._border_color = border_color or QColor(0, 240, 255, 60)
        self._bg_color = QColor(11, 15, 24, 210)
        self._glow_enabled = True

        # Default layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 14, 14, 14)
        self.layout.setSpacing(10)

    def set_border_accent(self, color: QColor):
        self._border_color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        c = self._corner_size

        # 1. Semi-transparent Glass Background
        painter.fillRect(self.rect(), self._bg_color)

        # 2. Main Thin Border
        pen_border = QPen(QColor(self._border_color.red(), self._border_color.green(), self._border_color.blue(), 45))
        pen_border.setWidth(1)
        painter.setPen(pen_border)
        painter.drawRect(0, 0, w - 1, h - 1)

        # 3. Vivid Cyber Corner Reticle Brackets
        pen_corner = QPen(self._border_color)
        pen_corner.setWidth(2)
        pen_corner.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen_corner)

        # Top-Left Corner
        painter.drawLine(0, 0, c, 0)
        painter.drawLine(0, 0, 0, c)

        # Top-Right Corner
        painter.drawLine(w - 1, 0, w - 1 - c, 0)
        painter.drawLine(w - 1, 0, w - 1, c)

        # Bottom-Left Corner
        painter.drawLine(0, h - 1, c, h - 1)
        painter.drawLine(0, h - 1, 0, h - 1 - c)

        # Bottom-Right Corner
        painter.drawLine(w - 1, h - 1, w - 1 - c, h - 1)
        painter.drawLine(w - 1, h - 1, w - 1, h - 1 - c)

        # 4. Tiny Technical Accent Dots at Reticle Terminus
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._border_color))
        dot_r = 2
        painter.drawRect(c, 0, dot_r, dot_r)
        painter.drawRect(0, c, dot_r, dot_r)
        painter.drawRect(w - 1 - c - dot_r, 0, dot_r, dot_r)
        painter.drawRect(w - 1 - dot_r, c, dot_r, dot_r)
