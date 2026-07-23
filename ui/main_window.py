import sys
import time
import logging
import psutil
from pathlib import Path
import numpy as np

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QColor, QPainter, QFont, QIcon, QAction, QPen, QBrush
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QProgressBar, QCheckBox, QSystemTrayIcon, QMenu,
    QFrame
)

# Import startup prep
from core.startup import is_startup_enabled, enable_startup, disable_startup

logger = logging.getLogger("Jarvis.UI")

class ListeningVisualizer(QWidget):
    """Custom premium painting widget that renders an animated, pulsing sound wave.
    Animates when active (Listening state) and flattens out when idle.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60)
        self._active = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)  # ~33 fps
        self._heights = np.zeros(15)

    def set_active(self, active: bool):
        self._active = active
        if not active:
            # Gradually decay heights to flat
            self._heights.fill(0)
        self.update()

    def _animate(self):
        if self._active:
            self._phase += 0.15
            # Generate moving sine wave with some noise for organic look
            for i in range(15):
                self._heights[i] = (
                    np.sin(self._phase + i * 0.4) * 0.4 + 
                    np.sin(self._phase * 1.8 + i * 0.8) * 0.2 +
                    np.random.uniform(-0.1, 0.1)
                )
            self.update()
        else:
            if np.any(self._heights > 0.01):
                self._heights *= 0.8  # Decay animation
                self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        center_y = height / 2.0
        
        # Draw clean background
        painter.fillRect(self.rect(), QColor(22, 22, 26, 120))
        
        # Drawing configurations
        num_bars = 15
        bar_spacing = width / (num_bars + 1)
        bar_width = max(4.0, bar_spacing * 0.6)
        
        pen = QPen(Qt.PenStyle.NoPen)
        painter.setPen(pen)
        
        # Color gradients: Cyan to Blue
        for i in range(num_bars):
            x = (i + 1) * bar_spacing - bar_width / 2.0
            
            # Amplitude scaling
            amp = self._heights[i] if self._active else (self._heights[i] * 0.1)
            bar_height = max(4.0, (center_y * 0.9) * abs(amp))
            
            # Draw rounded rectangles for the soundwave spectrum
            grad_color = QColor()
            # Dynamic HSL color shifting
            hue = int(180 + (i * 4) + (self._phase * 5) % 360) % 360
            grad_color.setHsl(hue, 230, 140)
            
            painter.setBrush(QBrush(grad_color))
            painter.drawRoundedRect(
                int(x), 
                int(center_y - bar_height), 
                int(bar_width), 
                int(bar_height * 2.0), 
                int(bar_width / 2.0), 
                int(bar_width / 2.0)
            )


class QSignalingLogHandler(logging.Handler):
    """Custom logging handler that routes logs to a Qt Signal."""
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        log_entry = self.format(record)
        self.signal.emit(log_entry)


class MainWindow(QMainWindow):
    """Futuristic PyQt6 dashboard window representing Jarvis HUD.
    Features state indicators, animated microphone visualizer, system resource telemetry,
    live logs display, and Windows system tray operations.
    """
    
    # Thread-safe signals to update UI elements from background threads
    sig_status_changed = pyqtSignal(str)
    sig_mic_state_changed = pyqtSignal(bool)
    sig_log_received = pyqtSignal(str)
    sig_sys_stats_updated = pyqtSignal(float, float)  # cpu, ram
    sig_speech_text_updated = pyqtSignal(str)          # Shows what user is saying / assistant is processing
    sig_closed = pyqtSignal()
    
    # OS control specific thread-safe signals
    sig_history_updated = pyqtSignal(list)
    sig_last_action_updated = pyqtSignal(str, bool, str)  # action, success, message
    sig_show_permission_dialog = pyqtSignal(str, str)     # action, message
    sig_permission_resolved = pyqtSignal(bool)            # confirmed response signal
    sig_speech_debug_updated = pyqtSignal(str, float, str, float)  # text, confidence, language, duration

    def __init__(self):
        super().__init__()
        
        # Destroy window on close to release memory
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        # Window attributes
        self.setWindowTitle("JARVIS Assistant")
        self.resize(900, 650)
        self.setWindowFlags(Qt.WindowType.Window)
        
        # State variables
        self._mic_muted = False
        
        # Layouts & Styling
        self._init_theme()
        self._init_ui()
        
        # Signal Connections
        self.sig_status_changed.connect(self._on_status_changed)
        self.sig_mic_state_changed.connect(self._on_mic_state_changed)
        self.sig_log_received.connect(self._on_log_received)
        self.sig_sys_stats_updated.connect(self._on_sys_stats_updated)
        self.sig_speech_text_updated.connect(self._on_speech_text_updated)
        self.sig_history_updated.connect(self._on_history_updated)
        self.sig_last_action_updated.connect(self._on_last_action_updated)
        self.sig_show_permission_dialog.connect(self._on_show_permission_dialog)
        self.sig_speech_debug_updated.connect(self._on_speech_debug_updated)
        
        # Setup telemetry timer (1 second interval)
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self._poll_telemetry)
        self._telemetry_timer.start(1000)

        # Wire logging handler
        self._log_handler = QSignalingLogHandler(self.sig_log_received)
        self._log_handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', '%H:%M:%S'))
        self._log_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(self._log_handler)

        # External action callbacks (set by main coordinator)
        self.trigger_wakeword_cb = None
        self.trigger_clap_cb = None
        self.toggle_mute_cb = None

        logger.info("Jarvis PyQt6 User Interface initialized.")

    def _init_theme(self):
        """Applies stylesheet for glassmorphism panels, cyan neon indicators, and dark aesthetic."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0d0d0f;
            }
            QWidget {
                color: #e2e2e9;
                font-family: 'Outfit', 'Inter', 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QFrame#panel {
                background-color: rgba(26, 26, 32, 180);
                border: 1px solid rgba(0, 240, 255, 60);
                border-radius: 12px;
            }
            QLabel#headerTitle {
                font-size: 26px;
                font-weight: bold;
                color: #00f0ff;
                letter-spacing: 3px;
            }
            QLabel#headerSubtitle {
                font-size: 11px;
                color: #0088cc;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QLabel#statusLabel {
                font-size: 15px;
                font-weight: bold;
                color: #8a8a9a;
            }
            QLabel#statusValue {
                font-size: 18px;
                font-weight: bold;
                color: #00f0ff;
            }
            QPushButton {
                background-color: rgba(0, 240, 255, 25);
                border: 1px solid rgba(0, 240, 255, 120);
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                color: #00f0ff;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 55);
                border: 1px solid #00f0ff;
            }
            QPushButton:pressed {
                background-color: rgba(0, 240, 255, 80);
            }
            QPushButton#micButton {
                background-color: rgba(0, 240, 255, 30);
                border: 2px solid #00f0ff;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton#micButton[muted="true"] {
                background-color: rgba(255, 30, 80, 25);
                border: 2px solid #ff1e50;
                color: #ff1e50;
            }
            QProgressBar {
                background-color: rgba(30, 30, 40, 150);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 4px;
                text-align: center;
                font-weight: bold;
                color: white;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #0088cc, stop:1 #00f0ff);
                border-radius: 3px;
            }
            QTextEdit#logConsole {
                background-color: #060608;
                border: 1px solid rgba(0, 240, 255, 30);
                border-radius: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                color: #a8a8b2;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid rgba(0, 240, 255, 120);
                border-radius: 4px;
                background-color: rgba(26, 26, 32, 180);
            }
            QCheckBox::indicator:checked {
                background-color: #00f0ff;
                image: url(none); /* System draws check, or we can customize */
            }
        """)

    def _init_ui(self):
        """Builds all UI layouts and sub-panels."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # 1. HEADER AREA
        header_layout = QHBoxLayout()
        header_text_layout = QVBoxLayout()
        
        title = QLabel("J A R V I S")
        title.setObjectName("headerTitle")
        
        subtitle = QLabel("FOUNDATION SYSTEM v1.0 • ONLINE")
        subtitle.setObjectName("headerSubtitle")
        
        header_text_layout.addWidget(title)
        header_text_layout.addWidget(subtitle)
        header_layout.addLayout(header_text_layout)
        
        # Status LED indicator (circular shape)
        self.status_led = QFrame()
        self.status_led.setFixedSize(16, 16)
        self.status_led.setStyleSheet("border-radius: 8px; background-color: #00f0ff; border: 1px solid #00f0ff;")
        
        status_info_layout = QHBoxLayout()
        status_title = QLabel("STATUS:")
        status_title.setObjectName("statusLabel")
        
        self.status_value = QLabel("STANDBY")
        self.status_value.setObjectName("statusValue")
        
        status_info_layout.addWidget(self.status_led)
        status_info_layout.addWidget(status_title)
        status_info_layout.addWidget(self.status_value)
        status_info_layout.addSpacing(10)
        
        header_layout.addStretch()
        header_layout.addLayout(status_info_layout)
        main_layout.addLayout(header_layout)

        # 2. MAIN LAYOUT (Columns: Left for Audio/Control, Right for Telemetry)
        middle_layout = QHBoxLayout()
        
        # Left Panel (Audio control & visualizer)
        left_panel = QFrame()
        left_panel.setObjectName("panel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(12)
        
        panel_title = QLabel("AUDIO TELEMETRY")
        panel_title.setStyleSheet("font-weight: bold; color: #00f0ff; font-size: 14px;")
        left_layout.addWidget(panel_title)
        
        # Soundwave Animation Visualizer
        self.visualizer = ListeningVisualizer()
        left_layout.addWidget(self.visualizer)
        
        # Speech text label (captures transcription / text output in real-time)
        self.speech_text_display = QLabel("No speech activity detected.")
        self.speech_text_display.setWordWrap(True)
        self.speech_text_display.setMinimumHeight(45)
        self.speech_text_display.setStyleSheet("color: #8a8a9a; font-style: italic; background-color: rgba(22, 22, 26, 80); padding: 8px; border-radius: 6px;")
        left_layout.addWidget(self.speech_text_display)

        # Microphone controller
        self.mic_btn = QPushButton("MICROPHONE ACTIVE")
        self.mic_btn.setObjectName("micButton")
        self.mic_btn.setProperty("muted", "false")
        self.mic_btn.clicked.connect(self._toggle_mic)
        left_layout.addWidget(self.mic_btn)

        # Simulation/Manual Testing Tools Group
        left_layout.addSpacing(5)
        sim_title = QLabel("MANUAL TESTING TRIGGERS")
        sim_title.setStyleSheet("font-weight: bold; color: #8a8a9a; font-size: 11px;")
        left_layout.addWidget(sim_title)
        
        sim_buttons_layout = QHBoxLayout()
        
        btn_wakeword = QPushButton("Wake Word")
        btn_wakeword.clicked.connect(self._trigger_wakeword)
        
        btn_clap = QPushButton("Clap")
        btn_clap.clicked.connect(self._trigger_clap)
        
        sim_buttons_layout.addWidget(btn_wakeword)
        sim_buttons_layout.addWidget(btn_clap)
        left_layout.addLayout(sim_buttons_layout)
        
        middle_layout.addWidget(left_panel, stretch=4)
        
        # Speech Debug Panel
        debug_panel = QFrame()
        debug_panel.setObjectName("panel")
        debug_layout = QVBoxLayout(debug_panel)
        debug_layout.setSpacing(12)
        
        debug_panel_title = QLabel("SPEECH DECODING DEBUG")
        debug_panel_title.setStyleSheet("font-weight: bold; color: #00f0ff; font-size: 14px;")
        debug_layout.addWidget(debug_panel_title)
        
        # Recorded Text Display
        debug_layout.addWidget(QLabel("RECORDED TEXT:"))
        self.debug_text_val = QTextEdit()
        self.debug_text_val.setReadOnly(True)
        self.debug_text_val.setPlaceholderText("No speech recorded yet.")
        self.debug_text_val.setStyleSheet("""
            QTextEdit {
                background-color: #060608;
                border: 1px solid rgba(0, 240, 255, 30);
                border-radius: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                color: #e2e2e9;
            }
        """)
        self.debug_text_val.setMinimumHeight(60)
        self.debug_text_val.setMaximumHeight(90)
        debug_layout.addWidget(self.debug_text_val)
        
        # Confidence Metrics
        self.debug_conf_label = QLabel("CONFIDENCE: 0.0%")
        self.debug_conf_label.setStyleSheet("font-weight: bold; color: #8a8a9a; font-size: 11px;")
        debug_layout.addWidget(self.debug_conf_label)
        
        self.debug_conf_bar = QProgressBar()
        self.debug_conf_bar.setRange(0, 100)
        self.debug_conf_bar.setValue(0)
        self.debug_conf_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(30, 30, 40, 150);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 4px;
                text-align: center;
                font-weight: bold;
                color: white;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #00f0ff, stop:1 #00ff66);
                border-radius: 3px;
            }
        """)
        debug_layout.addWidget(self.debug_conf_bar)
        
        # Language Metric
        lang_layout = QHBoxLayout()
        lang_lbl = QLabel("DETECTED LANGUAGE:")
        lang_lbl.setStyleSheet("font-weight: bold; color: #8a8a9a; font-size: 11px;")
        self.debug_lang_val = QLabel("N/A")
        self.debug_lang_val.setStyleSheet("font-weight: bold; color: #00f0ff; font-size: 12px;")
        lang_layout.addWidget(lang_lbl)
        lang_layout.addWidget(self.debug_lang_val)
        lang_layout.addStretch()
        debug_layout.addLayout(lang_layout)
        
        # Duration Metric
        len_layout = QHBoxLayout()
        len_lbl = QLabel("RECORDING LENGTH:")
        len_lbl.setStyleSheet("font-weight: bold; color: #8a8a9a; font-size: 11px;")
        self.debug_len_val = QLabel("0.00 seconds")
        self.debug_len_val.setStyleSheet("font-weight: bold; color: #00f0ff; font-size: 12px;")
        len_layout.addWidget(len_lbl)
        len_layout.addWidget(self.debug_len_val)
        len_layout.addStretch()
        debug_layout.addLayout(len_layout)
        
        debug_layout.addStretch()
        
        middle_layout.addWidget(debug_panel, stretch=4)

        # Right Panel (System Stats & Startup Configuration)
        right_panel = QFrame()
        right_panel.setObjectName("panel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)
        
        sys_panel_title = QLabel("SYSTEM METRICS")
        sys_panel_title.setStyleSheet("font-weight: bold; color: #00f0ff; font-size: 14px;")
        right_layout.addWidget(sys_panel_title)

        # CPU Metric
        cpu_layout = QVBoxLayout()
        self.cpu_label = QLabel("CPU USAGE: 0%")
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        self.cpu_bar.setValue(0)
        cpu_layout.addWidget(self.cpu_label)
        cpu_layout.addWidget(self.cpu_bar)
        right_layout.addLayout(cpu_layout)

        # Memory Metric
        mem_layout = QVBoxLayout()
        self.ram_label = QLabel("RAM USAGE: 0%")
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setValue(0)
        mem_layout.addWidget(self.ram_label)
        mem_layout.addWidget(self.ram_bar)
        right_layout.addLayout(mem_layout)

        right_layout.addSpacing(10)

        # Windows startup checkbox
        self.startup_check = QCheckBox("Run Jarvis at Windows Startup")
        self.startup_check.setChecked(is_startup_enabled())
        self.startup_check.stateChanged.connect(self._toggle_startup)
        right_layout.addWidget(self.startup_check)
        
        # Recent Commands Panel (Execution History)
        right_layout.addSpacing(8)
        history_title = QLabel("RECENT OS COMMANDS")
        history_title.setStyleSheet("font-weight: bold; color: #00f0ff; font-size: 11px; letter-spacing: 1px;")
        right_layout.addWidget(history_title)
        
        self.history_display = QTextEdit()
        self.history_display.setObjectName("historyConsole")
        self.history_display.setReadOnly(True)
        self.history_display.setMinimumHeight(150)
        self.history_display.setStyleSheet("""
            QTextEdit#historyConsole {
                background-color: #060608;
                border: 1px solid rgba(0, 240, 255, 30);
                border-radius: 8px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                color: #e2e2e9;
            }
        """)
        right_layout.addWidget(self.history_display)
        
        # Last Action status indicators
        self.last_action_label = QLabel("LAST OS ACTION: NONE")
        self.last_action_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #8a8a9a;")
        right_layout.addWidget(self.last_action_label)
        
        self.status_indicator = QLabel("RESULT: -")
        self.status_indicator.setStyleSheet("font-size: 11px; font-weight: bold; color: #8a8a9a;")
        right_layout.addWidget(self.status_indicator)
        
        right_layout.addStretch()
        
        middle_layout.addWidget(right_panel, stretch=4)
        main_layout.addLayout(middle_layout)

        # 3. CONSOLE LOGS TERMINAL
        logs_panel = QFrame()
        logs_panel.setObjectName("panel")
        logs_layout = QVBoxLayout(logs_panel)
        logs_layout.setContentsMargins(10, 10, 10, 10)
        
        console_title = QLabel("SYSTEM CONSOLE LOGS")
        console_title.setStyleSheet("font-weight: bold; color: #00f0ff; font-size: 12px; margin-bottom: 2px;")
        logs_layout.addWidget(console_title)
        
        self.console = QTextEdit()
        self.console.setObjectName("logConsole")
        self.console.setReadOnly(True)
        logs_layout.addWidget(self.console)
        
        main_layout.addWidget(logs_panel, stretch=4)

    # ==========================================
    # EVENT HANDLERS & CALLBACKS
    # ==========================================

    def closeEvent(self, event):
        """Handles closure of the MainWindow. Calls shutdown and notifies coordinator."""
        logger.info("MainWindow close event triggered. Cleaning up signaling handlers and destroying window widget.")
        self.shutdown()
        self.sig_closed.emit()
        event.accept()

    def _poll_telemetry(self):
        """Queries local resources and updates UI labels."""
        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            self.sig_sys_stats_updated.emit(cpu, mem)
        except Exception as e:
            logger.debug(f"Telemetry polling error: {e}")

    # ==========================================
    # UI BRIDGE SLOTS (Executed on Main Thread)
    # ==========================================

    def _on_status_changed(self, status: str):
        status_upper = status.upper().strip()
        self.status_value.setText(status_upper)
        
        # Expanded color mapping based on status requirements
        if status_upper == "LISTENING":
            # Vivid neon green
            self.status_led.setStyleSheet("border-radius: 8px; background-color: #00ff66; border: 1px solid #00ff66;")
            self.status_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #00ff66;")
            self.visualizer.set_active(True)
        elif status_upper == "TRANSCRIBING":
            # Vivid purple/magenta
            self.status_led.setStyleSheet("border-radius: 8px; background-color: #cc00ff; border: 1px solid #cc00ff;")
            self.status_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #cc00ff;")
            self.visualizer.set_active(True) # Pulsing visualizer remains active
        elif status_upper == "THINKING":
            # Deep warm yellow/amber
            self.status_led.setStyleSheet("border-radius: 8px; background-color: #ffcc00; border: 1px solid #ffcc00;")
            self.status_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffcc00;")
            self.visualizer.set_active(False)
        elif status_upper == "SPEAKING":
            # Deep neon blue
            self.status_led.setStyleSheet("border-radius: 8px; background-color: #0088cc; border: 1px solid #0088cc;")
            self.status_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #0088cc;")
            self.visualizer.set_active(True)
        elif status_upper == "EXECUTING":
            # Royal purple
            self.status_led.setStyleSheet("border-radius: 8px; background-color: #a300ff; border: 1px solid #a300ff;")
            self.status_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #a300ff;")
            self.visualizer.set_active(False)
        elif status_upper == "ERROR":
            # Danger neon red
            self.status_led.setStyleSheet("border-radius: 8px; background-color: #ff1e50; border: 1px solid #ff1e50;")
            self.status_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff1e50;")
            self.visualizer.set_active(False)
        else: # STANDBY / IDLE / default
            # Cyber cyan
            self.status_led.setStyleSheet("border-radius: 8px; background-color: #00f0ff; border: 1px solid #00f0ff;")
            self.status_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #00f0ff;")
            self.visualizer.set_active(False)

    def _on_mic_state_changed(self, is_muted: bool):
        self._mic_muted = is_muted
        self.mic_btn.setProperty("muted", "true" if is_muted else "false")
        
        # Reload stylesheet to apply dynamic color rules
        self.style().unpolish(self.mic_btn)
        self.style().polish(self.mic_btn)
        
        if is_muted:
            self.mic_btn.setText("MICROPHONE MUTED")
            logger.info("Microphone input silenced in UI.")
        else:
            self.mic_btn.setText("MICROPHONE ACTIVE")
            logger.info("Microphone input activated in UI.")

    def _on_speech_text_updated(self, text: str):
        self.speech_text_display.setText(text)
        
    def _on_speech_debug_updated(self, text: str, confidence: float, language: str, duration: float):
        self.debug_text_val.setText(text if text else "(Silence / No speech)")
        conf_percent = int(confidence * 100)
        self.debug_conf_bar.setValue(conf_percent)
        self.debug_conf_label.setText(f"CONFIDENCE: {confidence*100:.1f}%")
        self.debug_lang_val.setText(language.upper())
        self.debug_len_val.setText(f"{duration:.2f} seconds")

    def _on_log_received(self, log_entry: str):
        self.console.append(log_entry)
        # Scroll to bottom
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_sys_stats_updated(self, cpu: float, ram: float):
        self.cpu_label.setText(f"CPU USAGE: {cpu:.1f}%")
        self.cpu_bar.setValue(int(cpu))
        
        self.ram_label.setText(f"RAM USAGE: {ram:.1f}%")
        self.ram_bar.setValue(int(ram))

    # ==========================================
    # ACTION TRIGGER METHODS
    # ==========================================

    def _toggle_mic(self):
        """Triggered on button click. Informs main coordinator through callback."""
        target_mute = not self._mic_muted
        # Optimistic UI update, coordinator will enforce
        self.sig_mic_state_changed.emit(target_mute)
        
        if self.toggle_mute_cb:
            self.toggle_mute_cb(target_mute)

    def _toggle_startup(self, state):
        """Enables/disables Windows registry startup configurations."""
        checked = state == 2  # Qt checked state constant
        if checked:
            success = enable_startup()
            if not success:
                self.startup_check.setChecked(False)
        else:
            success = disable_startup()
            if not success:
                self.startup_check.setChecked(True)

    def _trigger_wakeword(self):
        """Simulates wake word detection."""
        if self.trigger_wakeword_cb:
            self.trigger_wakeword_cb()

    def _trigger_clap(self):
        """Simulates a double-clap detection event."""
        if self.trigger_clap_cb:
            self.trigger_clap_cb()
            
    def _on_history_updated(self, history_records: list):
        self.history_display.clear()
        for rec in history_records[-5:]:  # show last 5 actions
            t_str = time.strftime('%H:%M:%S', time.localtime(rec['timestamp']))
            status_text = "SUCCESS" if rec['success'] else "FAILED"
            color = "#00ff66" if rec['success'] else "#ff1e50"
            self.history_display.append(
                f"<span style='color: #8a8a9a;'>[{t_str}]</span> "
                f"<b>{rec['command']}</b> &rarr; "
                f"<span style='color: {color};'>{status_text}</span>: "
                f"<i style='color: #a8a8b2;'>{rec['result']}</i>"
            )

    def _on_last_action_updated(self, action: str, success: bool, message: str):
        self.last_action_label.setText(f"LAST OS ACTION: {action.upper()}")
        color = "#00ff66" if success else "#ff1e50"
        status_text = "SUCCESS" if success else "FAILED"
        self.status_indicator.setText(f"RESULT: {status_text} - {message}")
        self.status_indicator.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {color};")

    def _on_show_permission_dialog(self, action_name: str, message: str):
        from PyQt6.QtWidgets import QMessageBox
        logger.info(f"Displaying safety warning dialog for: {action_name}")
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Safety Confirmation Dialog")
        msg_box.setText(f"Jarvis safety confirmation required for:\n\n{action_name.upper()}\n\n{message}")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        
        # Premium dark styling
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #1a1a20;
                color: #e2e2e9;
            }
            QLabel {
                color: #e2e2e9;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QPushButton {
                background-color: rgba(0, 240, 255, 25);
                border: 1px solid rgba(0, 240, 255, 120);
                border-radius: 4px;
                padding: 5px 15px;
                color: #00f0ff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 55);
            }
        """)
        
        ret = msg_box.exec()
        confirmed = ret == QMessageBox.StandardButton.Yes
        logger.info(f"Safety warning dialog choice: {confirmed}")
        self.sig_permission_resolved.emit(confirmed)

    def shutdown(self):
        """Cleans up PyQt UI components."""
        self._telemetry_timer.stop()
        logging.getLogger().removeHandler(self._log_handler)
        logger.info("UI Shutdown completed.")
