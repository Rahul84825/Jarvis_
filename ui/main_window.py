"""
Master Jarvis 2.0 Holographic HUD MainWindow.
Faithfully translates the Jarvis 2.0 reference interface into native high-performance PyQt6:
- Near-black holographic canvas with corner brackets and scanlines
- Header brand mark and pulsing state beacon
- Left 'SYSTEMS' rail with diamond ticks
- Right 'SIGNAL' rail with live animated level meter
- Central breathing Arc Reactor core
- Top-center floating Tool Badge with spinner
- Floating bottom conversation stream & live transcript captions
- Keyboard shortcuts (Space to talk, Enter to command)
"""

import math
import logging
from typing import Optional, List, Dict
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QRadialGradient,
    QLinearGradient, QKeySequence, QShortcut
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QGraphicsDropShadowEffect
)

from ui.theme import HUDColors, get_hud_stylesheet
from ui.state_machine import JarvisUIState, map_runtime_status_to_ui_state
from ui.reactor.arc_reactor import ArcReactorWidget
from ui.widgets.boot_overlay import BootOverlayWidget

logger = logging.getLogger("Jarvis.UI")

class MainWindow(QMainWindow):
    """Exact Jarvis 2.0 Holographic HUD Interface."""

    sig_status_changed = pyqtSignal(str)
    sig_mic_state_changed = pyqtSignal(bool)
    sig_log_received = pyqtSignal(str)
    sig_sys_stats_updated = pyqtSignal(float, float)
    sig_speech_text_updated = pyqtSignal(str)
    sig_closed = pyqtSignal()
    sig_panel_visibility_requested = pyqtSignal(str)
    sig_command_submitted = pyqtSignal(str)
    sig_history_updated = pyqtSignal(list)
    sig_last_action_updated = pyqtSignal(str, bool, str)
    sig_show_permission_dialog = pyqtSignal(str, str)
    sig_permission_resolved = pyqtSignal(bool)
    sig_speech_debug_updated = pyqtSignal(str, float, str, float)
    sig_pipeline_stage_updated = pyqtSignal(str, str, str, str, str, str)
    sig_audio_amplitude_updated = pyqtSignal(float)
    sig_camera_state_updated = pyqtSignal(object)
    sig_gesture_detected = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("J.A.R.V.I.S. // Autonomous System")
        self.resize(1180, 780)
        self.setMinimumSize(960, 620)
        self.global_hotkey_manager = None

        self._current_state = JarvisUIState.STANDBY
        self._status_text = "STANDBY"
        self._camera_state_str = "OFF"

        self._mic_muted = False
        self._signal_level = 0.85
        self._target_signal_level = 0.85
        self._active_tool = ""
        self._tool_spinner_angle = 0.0
        self._pulse_phase = 0.0
        self._caption_text = ""
        self._error_text = ""

        # Conversation history turns: [{"role": "user"|"jarvis", "text": "..."}]
        self._turns: List[Dict[str, str]] = []

        # Connected system capabilities for Left Rail
        self._systems = [
            "Windows Platform",
            "Browser & Web",
            "Native Apps",
            "3-Layer Brain",
            "Audio Bus",
            "Vision Perception"
        ]

        # Apply Global Stylesheet
        self.setStyleSheet(get_hud_stylesheet())

        self._init_ui()
        self._wire_signals()
        self._setup_shortcuts()

        # HUD Animation Timer (60 FPS) for pulsing dots, signal meter & tool spinner
        self._hud_timer = QTimer(self)
        self._hud_timer.timeout.connect(self._on_hud_tick)
        self._hud_timer.start(16)

        self.trigger_wakeword_cb = None
        self.toggle_mute_cb = None
        self.toggle_sleep_cb = None
        self.speak_cb = None

        logger.info("Jarvis 2.0 Holographic HUD initialized.")

    def _init_ui(self):
        # Central HUD widget
        self.canvas = QWidget(self)
        self.setCentralWidget(self.canvas)
        self.canvas.setAutoFillBackground(False)

        # Central Arc Reactor positioned in middle
        self.arc_reactor = ArcReactorWidget(self.canvas)

        # --- Top Tool Badge (Floating Chip) ---
        self.tool_badge_frame = QWidget(self.canvas)
        self.tool_badge_frame.setStyleSheet("""
            QWidget {
                background: rgba(2, 10, 12, 0.82);
                border: 1px solid rgba(0, 229, 255, 0.45);
                border-radius: 3px;
            }
        """)
        tool_layout = QHBoxLayout(self.tool_badge_frame)
        tool_layout.setContentsMargins(14, 6, 16, 6)
        tool_layout.setSpacing(10)

        self.lbl_tool_kicker = QLabel("ACCESSING")
        self.lbl_tool_kicker.setStyleSheet("""
            color: rgba(0, 229, 255, 0.7);
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.3em;
            border: none;
            background: transparent;
        """)
        tool_layout.addWidget(self.lbl_tool_kicker)

        self.lbl_tool_name = QLabel("")
        self.lbl_tool_name.setStyleSheet("""
            color: #f2fbff;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.2em;
            border: none;
            background: transparent;
        """)
        tool_layout.addWidget(self.lbl_tool_name)
        self.tool_badge_frame.hide()

        # --- Floating Conversation Area (Bottom Center) ---
        self.log_widget = QWidget(self.canvas)
        self.log_layout = QVBoxLayout(self.log_widget)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(8)
        self.log_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)

        # --- Live Caption Label ---
        self.lbl_caption = QLabel(self.canvas)
        self.lbl_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_caption.setStyleSheet("""
            color: #ffffff;
            font-size: 15px;
            letter-spacing: 0.03em;
            background: transparent;
        """)
        self.lbl_caption.hide()

        # --- Bottom Input Bar ---
        self.input_container = QWidget(self.canvas)
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self.cmd_input = QLineEdit()
        self.cmd_input.setProperty("class", "cyberInput")
        self.cmd_input.setPlaceholderText("Command Santra (voice or text e.g. 'Open Chrome and search wellmeds.in')...")
        self.cmd_input.returnPressed.connect(self._on_submit_command)
        input_layout.addWidget(self.cmd_input, stretch=1)

        self.btn_execute = QPushButton("EXECUTE ➜")
        self.btn_execute.setProperty("class", "cyberButton")
        self.btn_execute.clicked.connect(self._on_submit_command)
        input_layout.addWidget(self.btn_execute)

        self.btn_screen = QPushButton("🔍 SCREEN")
        self.btn_screen.setProperty("class", "cyberButton")
        self.btn_screen.setToolTip("Analyze and explain visible desktop screen content (Ctrl+Shift+S)")
        self.btn_screen.clicked.connect(self._open_screen_intelligence)
        input_layout.addWidget(self.btn_screen)

        self.btn_ai_settings = QPushButton("⚙️ AI")
        self.btn_ai_settings.setProperty("class", "cyberButton")
        self.btn_ai_settings.setToolTip("Manage AI providers, API keys, models, and priority (Ctrl+Shift+A)")
        self.btn_ai_settings.clicked.connect(self._open_ai_settings)
        input_layout.addWidget(self.btn_ai_settings)

        self.btn_pronunciation = QPushButton("🗣️ ACCENT")
        self.btn_pronunciation.setProperty("class", "cyberButton")
        self.btn_pronunciation.setToolTip("Configure Indian Accent Pronunciation & Wake-Word Intelligence (Ctrl+Shift+P)")
        self.btn_pronunciation.clicked.connect(self._open_pronunciation_settings)
        input_layout.addWidget(self.btn_pronunciation)

        self.btn_lab = QPushButton("🧪 LAB")
        self.btn_lab.setProperty("class", "cyberButton")
        self.btn_lab.setToolTip("Open Santra Virtual Testing Room & Capability Lab (Ctrl+Shift+L)")
        self.btn_lab.clicked.connect(self._open_virtual_lab)
        input_layout.addWidget(self.btn_lab)

        self.btn_spotify = QPushButton("🎵 SPOTIFY")
        self.btn_spotify.setProperty("class", "cyberButton")
        self.btn_spotify.setToolTip("Open Spotify Integration, Playback & Playlist Manager (Ctrl+Shift+M)")
        self.btn_spotify.clicked.connect(self._open_spotify_panel)
        input_layout.addWidget(self.btn_spotify)

        self.btn_sleep = QPushButton("🌙 SLEEP")
        self.btn_sleep.setProperty("class", "cyberButton")
        self.btn_sleep.setToolTip("Toggle low-resource Sleep Mode (wake with 'Santra' or Wake button)")
        self.btn_sleep.clicked.connect(self._on_sleep_clicked)
        input_layout.addWidget(self.btn_sleep)

        self.btn_mic = QPushButton("🎙️ TALK")
        self.btn_mic.setProperty("class", "cyberButton")
        self.btn_mic.clicked.connect(self._on_wake_clicked)
        input_layout.addWidget(self.btn_mic)

        # -------------------------------------------------------------
        # Cinematic Boot Sequence Overlay
        # -------------------------------------------------------------
        self.boot_overlay = BootOverlayWidget(self, on_finish_cb=self._on_boot_finished)
        self.boot_overlay.resize(self.size())
        self.boot_overlay.raise_()

    def _setup_shortcuts(self):
        # Spacebar activates voice wake when input is not focused
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.shortcut_space.activated.connect(self._on_space_pressed)

        # Screen Intelligence shortcut
        self.shortcut_screen = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.shortcut_screen.activated.connect(self._open_screen_intelligence)

        # AI Settings shortcut
        self.shortcut_ai = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        self.shortcut_ai.activated.connect(self._open_ai_settings)

        # Virtual Testing Room shortcut
        self.shortcut_lab = QShortcut(QKeySequence("Ctrl+Shift+L"), self)
        self.shortcut_lab.activated.connect(self._open_virtual_lab)

        # Pronunciation & Accent Intelligence shortcut
        self.shortcut_pronunciation = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self.shortcut_pronunciation.activated.connect(self._open_pronunciation_settings)

        # Spotify Suite shortcut
        self.shortcut_spotify = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        self.shortcut_spotify.activated.connect(self._open_spotify_panel)

    def _open_spotify_panel(self):
        try:
            from ui.panels.spotify_panel import SpotifyDialog
            dialog = SpotifyDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Spotify Dialog: {e}", exc_info=True)

    def _open_screen_intelligence(self):
        try:
            from ui.panels.screen_intelligence_panel import ScreenIntelligencePanel
            from PyQt6.QtWidgets import QDialog, QVBoxLayout
            dialog = QDialog(self)
            dialog.setWindowTitle("SANTRA — Visual Screen Intelligence")
            dialog.resize(760, 560)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(10, 10, 10, 10)
            from core.ai.provider_manager import ProviderManager
            prov_mgr = getattr(self, "provider_manager", None) or ProviderManager()
            panel = ScreenIntelligencePanel(dialog, on_speech_output_cb=getattr(self, "speak_cb", None), provider_manager=prov_mgr)
            layout.addWidget(panel)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Screen Intelligence: {e}")

    def _open_ai_settings(self):
        try:
            from ui.panels.ai_settings_dialog import AISettingsDialog
            dialog = AISettingsDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open AI Settings: {e}")

    def _open_pronunciation_settings(self):
        try:
            from ui.panels.pronunciation_settings_dialog import PronunciationSettingsDialog
            dialog = PronunciationSettingsDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Pronunciation Settings: {e}", exc_info=True)

    def _open_virtual_lab(self):
        try:
            from ui.panels.virtual_lab_panel import VirtualLabDialog
            dialog = VirtualLabDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Virtual Lab: {e}", exc_info=True)

    def _on_space_pressed(self):
        if not self.cmd_input.hasFocus():
            self._on_wake_clicked()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()

        if hasattr(self, "boot_overlay") and self.boot_overlay.isVisible():
            self.boot_overlay.resize(self.size())

        # Center Arc Reactor
        reactor_size = min(int(min(w, h) * 0.58), 420)
        rx = int((w - reactor_size) / 2)
        ry = int((h - reactor_size) / 2) - 30
        self.arc_reactor.setGeometry(rx, ry, reactor_size, reactor_size)

        # Top Tool Badge
        bw = min(540, int(w * 0.6))
        self.tool_badge_frame.setGeometry(int((w - bw) / 2), 70, bw, 36)

        # Conversation log area (Bottom Center)
        lw = min(720, int(w * 0.72))
        self.log_widget.setGeometry(int((w - lw) / 2), h - 235, lw, 120)

        # Caption (Above input)
        self.lbl_caption.setGeometry(int((w - lw) / 2), h - 110, lw, 24)

        # Input container
        self.input_container.setGeometry(int((w - lw) / 2), h - 80, lw, 38)

    def _on_hud_tick(self):
        # Animate pulsing beacon and signal level interpolation
        self._pulse_phase = (self._pulse_phase + 0.05) % math.tau
        self._tool_spinner_angle = (self._tool_spinner_angle + 6.0) % 360.0

        # Smooth signal meter movement
        diff = self._target_signal_level - self._signal_level
        self._signal_level += diff * 0.15

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 1. Background Void (#01060c)
        painter.fillRect(0, 0, w, h, HUDColors.BG)

        # 2. Radial Vignette Falloff
        grad = QRadialGradient(w / 2.0, h / 2.0, max(w, h) * 0.6)
        grad.setColorAt(0.0, QColor(0, 229, 255, 6))
        grad.setColorAt(0.6, QColor(0, 0, 0, 40))
        grad.setColorAt(1.0, QColor(0, 0, 0, 200))
        painter.fillRect(0, 0, w, h, QBrush(grad))

        # 3. Subtle Scanlines
        scan_pen = QPen(QColor(0, 229, 255, 6), 1.0)
        painter.setPen(scan_pen)
        for y in range(0, h, 4):
            painter.drawLine(0, y, w, y)

        # 4. Corner Reticle Brackets (46x46px)
        c_size = 46
        pad = 26
        c_pen = QPen(HUDColors.BORDER_CYAN, 1.2)
        painter.setPen(c_pen)

        # Top-Left (TL)
        painter.drawLine(pad, pad, pad + c_size, pad)
        painter.drawLine(pad, pad, pad, pad + c_size)

        # Top-Right (TR)
        painter.drawLine(w - pad - c_size, pad, w - pad, pad)
        painter.drawLine(w - pad, pad, w - pad, pad + c_size)

        # Bottom-Left (BL)
        painter.drawLine(pad, h - pad, pad + c_size, h - pad)
        painter.drawLine(pad, h - pad - c_size, pad, h - pad)

        # Bottom-Right (BR)
        painter.drawLine(w - pad - c_size, h - pad, w - pad, h - pad)
        painter.drawLine(w - pad, h - pad - c_size, w - pad, h - pad)

        # 5. Top Header HUD Chrome
        top_y = 48
        pad_x = 72

        # Brand Mark: J.A.R.V.I.S.
        font_brand = QFont("Chakra Petch", 16, QFont.Weight.Bold)
        font_brand.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6.0)
        painter.setFont(font_brand)
        painter.setPen(QColor(0, 229, 255, 240))
        painter.drawText(pad_x, top_y, "J.A.R.V.I.S.")

        # Subtitle
        font_sub = QFont("Chakra Petch", 8, QFont.Weight.Normal)
        font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        painter.setFont(font_sub)
        painter.setPen(QColor(0, 229, 255, 110))
        painter.drawText(pad_x, top_y + 16, "JUST A RATHER VERY INTELLIGENT SYSTEM")

        # Top-Right Status Line with Pulsing Dot
        state_color = HUDColors.STANDBY_CYAN
        if self._current_state == JarvisUIState.SLEEPING:
            state_color = QColor(100, 160, 255)
        elif self._current_state == JarvisUIState.WAKING:
            state_color = HUDColors.CYAN_PRIMARY
        elif self._current_state in [JarvisUIState.LISTENING, JarvisUIState.TRANSCRIBING]:
            state_color = HUDColors.LISTENING_CYAN
        elif self._current_state in [JarvisUIState.UNDERSTANDING, JarvisUIState.THINKING, JarvisUIState.EXECUTING]:
            state_color = HUDColors.THINKING_GOLD
        elif self._current_state == JarvisUIState.SPEAKING:
            state_color = HUDColors.SPEAKING_TEAL
        elif self._current_state == JarvisUIState.ERROR:
            state_color = HUDColors.ERROR_CORAL

        status_str = f"● {self._status_text}"
        font_status = QFont("Chakra Petch", 10, QFont.Weight.DemiBold)
        font_status.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        painter.setFont(font_status)
        painter.setPen(state_color)
        painter.drawText(w - pad_x - 170, top_y + 6, 170, 20, Qt.AlignmentFlag.AlignRight, status_str)

        # 6. Left Rail: 'SYSTEMS'
        rail_left_x = pad_x
        rail_y = int(h / 2.0) - 60

        font_rail_title = QFont("Chakra Petch", 7, QFont.Weight.Bold)
        font_rail_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        painter.setFont(font_rail_title)
        painter.setPen(QColor(0, 229, 255, 100))
        painter.drawText(rail_left_x, rail_y, "SYSTEMS")

        font_rail_item = QFont("Chakra Petch", 9, QFont.Weight.Normal)
        font_rail_item.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        painter.setFont(font_rail_item)

        item_y = rail_y + 18
        for sys_name in self._systems:
            is_active_sys = (sys_name == "Vision Perception" and self._camera_state_str == "ACTIVE")
            tick_color = HUDColors.THINKING_GOLD if is_active_sys else HUDColors.ACCENT_CYAN

            # Diamond tick ◆
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(tick_color))
            painter.save()
            painter.translate(rail_left_x + 3, item_y - 4)
            painter.rotate(45)
            painter.drawRect(-2, -2, 5, 5)
            painter.restore()

            disp_name = f"{sys_name} ●" if is_active_sys else sys_name
            text_color = QColor(255, 220, 100, 240) if is_active_sys else QColor(234, 249, 255, 200)
            painter.setPen(text_color)
            painter.drawText(rail_left_x + 16, item_y, disp_name)
            item_y += 20


        # 7. Right Rail: 'SIGNAL'
        rail_right_x = w - pad_x - 40
        painter.setFont(font_rail_title)
        painter.setPen(QColor(0, 229, 255, 100))
        painter.drawText(rail_right_x - 30, rail_y, 60, 16, Qt.AlignmentFlag.AlignRight, "SIGNAL")

        # Vertical Level Meter
        meter_w = 3
        meter_h = 88
        meter_x = rail_right_x + 10
        meter_y = rail_y + 16

        # Background track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 229, 255, 35)))
        painter.drawRect(meter_x, meter_y, meter_w, meter_h)

        # Fill bar (from bottom up)
        fill_h = int(meter_h * max(0.05, min(1.0, self._signal_level)))
        painter.setBrush(QBrush(HUDColors.ACCENT_CYAN))
        painter.drawRect(meter_x, meter_y + (meter_h - fill_h), meter_w, fill_h)

        # Readout text (Monospace)
        font_mono = QFont("JetBrains Mono", 8, QFont.Weight.Normal)
        painter.setFont(font_mono)
        painter.setPen(QColor(0, 229, 255, 210))
        pct_str = f"{int(self._signal_level * 100):03d}%"
        painter.drawText(rail_right_x - 30, meter_y + meter_h + 16, 60, 16, Qt.AlignmentFlag.AlignRight, pct_str)

        # 8. Bottom Footer Hint
        font_hint = QFont("Chakra Petch", 8, QFont.Weight.Normal)
        font_hint.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
        painter.setFont(font_hint)
        painter.setPen(QColor(0, 229, 255, 95))
        hint_text = 'SAY "HEY SANTRA" • SPACE TO TALK • ENTER TO COMMAND • V VOICE ENGINE'
        painter.drawText(0, h - 28, w, 20, Qt.AlignmentFlag.AlignCenter, hint_text)

    def _on_boot_finished(self):
        """Called when startup boot sequence finishes."""
        self._on_status_changed("STANDBY")

    def _wire_signals(self):
        self.sig_status_changed.connect(self._on_status_changed)
        self.sig_mic_state_changed.connect(self._on_mic_state_changed)
        self.sig_sys_stats_updated.connect(self._on_sys_stats_updated)
        self.sig_speech_text_updated.connect(self._on_speech_text_updated)
        self.sig_last_action_updated.connect(self._on_last_action_updated)
        self.sig_pipeline_stage_updated.connect(self._on_pipeline_stage_updated)
        self.sig_history_updated.connect(self._on_history_updated)
        self.sig_show_permission_dialog.connect(self._on_show_permission_dialog)
        self.sig_speech_debug_updated.connect(self._on_speech_debug_updated)
        self.sig_audio_amplitude_updated.connect(self.arc_reactor.set_audio_amplitude)
        self.sig_camera_state_updated.connect(self._on_camera_state_updated)
        self.sig_gesture_detected.connect(self._on_gesture_detected)

    def _on_camera_state_updated(self, event):
        """Updates UI with real camera telemetry and state."""
        if hasattr(event, "state"):
            state_val = event.state.value if hasattr(event.state, "value") else str(event.state)
            self._camera_state_str = state_val
            is_active = (state_val == "ACTIVE")
            self.arc_reactor.set_camera_active(is_active)
            if is_active and hasattr(event, "fps_capture"):
                self.lbl_tool_kicker.setText("PERCEPTION")
                self.lbl_tool_name.setText(f"CAMERA ACTIVE ({int(event.fps_capture)} FPS)")
                self.tool_badge_frame.show()
                QTimer.singleShot(2500, self.tool_badge_frame.hide)
            self.update()

    def _on_gesture_detected(self, event):
        """Triggers subtle Arc Reactor pulse on confirmed gesture."""
        if hasattr(event, "gesture"):
            g_name = event.gesture.value if hasattr(event.gesture, "value") else str(event.gesture)
            self.arc_reactor.trigger_gesture_pulse(g_name)
            self.lbl_tool_kicker.setText("GESTURE")
            self.lbl_tool_name.setText(f"{g_name} ({getattr(event, 'hand', 'Hand')})")
            self.tool_badge_frame.show()
            QTimer.singleShot(1800, self.tool_badge_frame.hide)


    # ==========================================
    def _on_wake_clicked(self):
        if self.trigger_wakeword_cb:
            self.trigger_wakeword_cb()

    def _on_sleep_clicked(self):
        if self._current_state == JarvisUIState.SLEEPING:
            self._on_wake_clicked()
        elif self.toggle_sleep_cb:
            self.toggle_sleep_cb()
        else:
            self.sig_command_submitted.emit("enter sleep mode")

    def _on_submit_command(self):
        cmd = self.cmd_input.text().strip()
        if cmd:
            self.cmd_input.clear()
            self._add_turn("user", cmd)
            if cmd.lower() in ["open virtual lab", "open virtual testing room", "virtual lab", "virtual testing room", "test lab"]:
                self._open_virtual_lab()
                return
            self.sig_command_submitted.emit(cmd)

    def _add_turn(self, role: str, text: str):
        self._turns.append({"role": role, "text": text})
        if len(self._turns) > 6:
            self._turns = self._turns[-6:]
        self._rebuild_log_view()

    def _rebuild_log_view(self):
        # Clear existing layout items
        while self.log_layout.count():
            item = self.log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for turn in self._turns[-3:]:
            lbl = QLabel()
            lbl.setWordWrap(True)
            if turn["role"] == "user":
                lbl.setStyleSheet("""
                    color: rgba(255, 255, 255, 0.55);
                    font-size: 13px;
                    font-weight: 500;
                    letter-spacing: 0.02em;
                    background: transparent;
                """)
                lbl.setText(f"YOU  ➜  {turn['text']}")
            else:
                lbl.setStyleSheet("""
                    color: #eaf9ff;
                    font-size: 14px;
                    font-weight: 600;
                    letter-spacing: 0.03em;
                    background: transparent;
                """)
                lbl.setText(f"SANTRA  ➜  {turn['text']}")
            self.log_layout.addWidget(lbl)

    def _on_status_changed(self, status: str):
        self._status_text = status.upper()
        self._current_state = map_runtime_status_to_ui_state(status)
        self.arc_reactor.set_state(self._current_state)

        # Modulate buttons based on sleep vs active state
        if self._current_state == JarvisUIState.SLEEPING:
            self.btn_mic.setText("⚡ WAKE")
            self.btn_mic.setToolTip("Wake SANTRA from Sleep Mode")
            self.btn_sleep.setText("⚡ WAKE")
            self.btn_sleep.setToolTip("Wake SANTRA from Sleep Mode")
        else:
            self.btn_mic.setText("🎙️ TALK")
            self.btn_mic.setToolTip("Activate voice listening")
            self.btn_sleep.setText("🌙 SLEEP")
            self.btn_sleep.setToolTip("Put SANTRA into low-resource Sleep Mode")

        # Modulate signal meter level based on state
        if self._current_state in [JarvisUIState.LISTENING, JarvisUIState.TRANSCRIBING]:
            self._target_signal_level = 0.95
            self.lbl_caption.show()
        elif self._current_state == JarvisUIState.SPEAKING:
            self._target_signal_level = 0.90
        elif self._current_state in [JarvisUIState.THINKING, JarvisUIState.UNDERSTANDING]:
            self._target_signal_level = 0.75
        elif self._current_state == JarvisUIState.SLEEPING:
            self._target_signal_level = 0.10
            self.lbl_caption.hide()
        else:
            self._target_signal_level = 0.35
            self.lbl_caption.hide()

        self.update()

    def _on_mic_state_changed(self, is_active: bool):
        if is_active:
            self._on_status_changed("LISTENING")
        else:
            self._on_status_changed("STANDBY")

    def _on_sys_stats_updated(self, cpu: float, ram: float):
        if self._current_state == JarvisUIState.STANDBY:
            self._target_signal_level = (cpu + ram) / 200.0

    def _on_speech_text_updated(self, text: str):
        self._caption_text = text
        self.lbl_caption.setText(text)
        if text:
            self.lbl_caption.show()

    def _on_pipeline_stage_updated(self, raw: str, norm: str, intent: str, exec_str: str, resp: str, state: str):
        if raw and not any(t["text"] == raw for t in self._turns if t["role"] == "user"):
            self._add_turn("user", raw)
        if resp:
            self._add_turn("jarvis", resp)

        if exec_str:
            self._active_tool = exec_str
            self.lbl_tool_name.setText(exec_str.upper())
            self.tool_badge_frame.show()
            QTimer.singleShot(3500, self.tool_badge_frame.hide)

    def _on_last_action_updated(self, action: str, success: bool, msg: str):
        if action:
            self._active_tool = action
            self.lbl_tool_name.setText(action.upper())
            self.tool_badge_frame.show()
            QTimer.singleShot(3500, self.tool_badge_frame.hide)

    def _on_history_updated(self, history: list):
        pass

    def _on_show_permission_dialog(self, action: str, message: str):
        reply = QMessageBox.question(
            self,
            "Security Authorization Required",
            f"Santra is requesting confirmation to execute:\n\nAction: {action}\nDetails: {message}\n\nDo you authorize this operation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        self.sig_permission_resolved.emit(reply == QMessageBox.StandardButton.Yes)

    def _on_speech_debug_updated(self, text: str, conf: float, lang: str, dur: float):
        pass

    def closeEvent(self, event):
        # Hide window to system tray instead of destroying application
        event.ignore()
        self.hide()
        self.sig_closed.emit()

