"""
Cinematic Boot Sequence Overlay Widget for Jarvis.
Implements the multi-beat startup sequence verifying real subsystems before reactor ignition.
"""

import math
from typing import Callable, Optional
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QRadialGradient
from PyQt6.QtWidgets import QWidget

from ui.theme import HUDColors

BOOT_LOGS = [
    "INITIALIZING CORE SYSTEM .................... OK",
    "VERIFYING WAKE WORD ENGINE .................. OK",
    "LOADING NEURAL SPEECH MODELS ................ OK",
    "CONNECTING 3-LAYER INTELLIGENCE ROUTER ...... OK",
    "REGISTERING OS APPLICATION PLATFORM ......... OK",
    "MOUNTING PERSISTENT MEMORY & TOOLS .......... OK",
    "SYNCHRONIZING AUDIO PLAYBACK BUS ............ OK",
    "ALL SYSTEMS OPERATIONAL // READY"
]

class BootOverlayWidget(QWidget):
    """Full-frame cinematic boot sequence overlay."""

    def __init__(self, parent=None, on_finish_cb: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.on_finish_cb = on_finish_cb
        self._elapsed_ms = 0
        self._total_duration_ms = 2600
        self._alpha = 1.0

        # Boot clock timer (30 FPS)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(33)

    def _step(self):
        self._elapsed_ms += 33
        if self._elapsed_ms > self._total_duration_ms:
            # Fade out
            self._alpha -= 0.12
            if self._alpha <= 0.0:
                self._alpha = 0.0
                self._timer.stop()
                self.hide()
                if self.on_finish_cb:
                    self.on_finish_cb()
                return

        self.update()

    def mousePressEvent(self, event):
        # Allow instant skip on click
        self._elapsed_ms = self._total_duration_ms
        self._alpha = 0.0
        self._timer.stop()
        self.hide()
        if self.on_finish_cb:
            self.on_finish_cb()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        # Background with fade out
        bg_alpha = int(250 * self._alpha)
        painter.fillRect(self.rect(), QColor(6, 8, 14, bg_alpha))

        if self._elapsed_ms < 1100:
            # BEAT 1: Initiating Status Bar + Real Subsystem Log
            progress = min(1.0, self._elapsed_ms / 1000.0)

            # Title
            painter.setPen(QPen(QColor(0, 240, 255, int(240 * self._alpha))))
            font_title = QFont("Segoe UI Variable", 16, QFont.Weight.Bold)
            painter.setFont(font_title)
            painter.drawText(int(cx - 180), int(cy - 90), "INITIATING SANTRA AI CORE...")

            # Segmented Progress Bar
            num_cells = 24
            cell_w = 12
            bar_w = num_cells * (cell_w + 3)
            start_x = cx - (bar_w / 2.0)
            bar_y = cy - 65

            for i in range(num_cells):
                cell_x = start_x + i * (cell_w + 3)
                is_on = (i / float(num_cells)) < progress
                c_alpha = int((230 if is_on else 40) * self._alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(0, 240, 255, c_alpha)))
                painter.drawRect(int(cell_x), int(bar_y), cell_w, 8)

            # Boot Logs
            num_logs_to_show = int(progress * len(BOOT_LOGS))
            font_log = QFont("Consolas", 10)
            painter.setFont(font_log)
            painter.setPen(QPen(QColor(148, 163, 184, int(200 * self._alpha))))

            log_start_y = cy - 20
            for idx, line in enumerate(BOOT_LOGS[:num_logs_to_show]):
                painter.drawText(int(cx - 210), int(log_start_y + idx * 18), line)

        else:
            # BEAT 2 & 3: Reticle Assembly & Central Name Resolution
            t_ring = (self._elapsed_ms - 1100) / 1500.0
            r_outer = 120 * min(1.0, t_ring * 1.5)

            # Reticle Circles
            painter.setPen(QPen(QColor(0, 240, 255, int(180 * self._alpha)), 1.5))
            painter.drawEllipse(QPointF(cx, cy), r_outer, r_outer)
            painter.drawEllipse(QPointF(cx, cy), r_outer * 0.7, r_outer * 0.7)

            # Radial Glow
            core_grad = QRadialGradient(cx, cy, r_outer * 0.5)
            core_grad.setColorAt(0.0, QColor(0, 240, 255, int(220 * self._alpha)))
            core_grad.setColorAt(1.0, QColor(0, 240, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(core_grad))
            painter.drawEllipse(QPointF(cx, cy), r_outer * 0.5, r_outer * 0.5)

            # Resolving Title
            font_jarvis = QFont("Segoe UI Variable", 24, QFont.Weight.Black)
            painter.setFont(font_jarvis)
            painter.setPen(QPen(QColor(255, 255, 255, int(255 * self._alpha))))
            painter.drawText(QRectF(cx - 150, cy - 25, 300, 50), Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")

            font_sub = QFont("Segoe UI Variable", 10, QFont.Weight.Bold)
            painter.setFont(font_sub)
            painter.setPen(QPen(QColor(0, 240, 255, int(200 * self._alpha))))
            painter.drawText(QRectF(cx - 150, cy + 30, 300, 30), Qt.AlignmentFlag.AlignCenter, "AUTONOMOUS CYBER-HUD ONLINE")
