"""
System Telemetry HUD Panel for Jarvis.
Displays CPU, RAM, Disk, OS, and hardware metrics with futuristic gauges.
"""

import sys
import platform
import psutil
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from ui.widgets.hud_frame import HUDFrame
from ui.theme import HUDColors

class TelemetryPanel(HUDFrame):
    """Futuristic HUD blade showing real-time host telemetry and resource metrics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

        # Telemetry poll timer (1 Hz)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_metrics)
        self._poll_timer.start(1000)
        self._poll_metrics()

    def _init_ui(self):
        hdr = QLabel("SYSTEM TELEMETRY")
        hdr.setProperty("class", "hudSectionTitle")
        self.layout.addWidget(hdr)

        # 1. CPU Gauge
        cpu_box = QVBoxLayout()
        cpu_box.setSpacing(3)
        cpu_lbl_box = QHBoxLayout()
        cpu_lbl_box.addWidget(QLabel("CPU LOAD:"))
        self._cpu_val = QLabel("0%")
        self._cpu_val.setStyleSheet("color: #00f0ff; font-weight: bold;")
        cpu_lbl_box.addStretch()
        cpu_lbl_box.addWidget(self._cpu_val)
        cpu_box.addLayout(cpu_lbl_box)

        self._cpu_bar = QProgressBar()
        self._cpu_bar.setRange(0, 100)
        self._cpu_bar.setFixedHeight(8)
        cpu_box.addWidget(self._cpu_bar)
        self.layout.addLayout(cpu_box)

        # 2. RAM Gauge
        ram_box = QVBoxLayout()
        ram_box.setSpacing(3)
        ram_lbl_box = QHBoxLayout()
        ram_lbl_box.addWidget(QLabel("RAM USAGE:"))
        self._ram_val = QLabel("0%")
        self._ram_val.setStyleSheet("color: #00f0ff; font-weight: bold;")
        ram_lbl_box.addStretch()
        ram_lbl_box.addWidget(self._ram_val)
        ram_box.addLayout(ram_lbl_box)

        self._ram_bar = QProgressBar()
        self._ram_bar.setRange(0, 100)
        self._ram_bar.setFixedHeight(8)
        ram_box.addWidget(self._ram_bar)
        self.layout.addLayout(ram_box)

        # 3. Disk Space Gauge
        disk_box = QVBoxLayout()
        disk_box.setSpacing(3)
        disk_lbl_box = QHBoxLayout()
        disk_lbl_box.addWidget(QLabel("PRIMARY DISK:"))
        self._disk_val = QLabel("0%")
        self._disk_val.setStyleSheet("color: #00f0ff; font-weight: bold;")
        disk_lbl_box.addStretch()
        disk_lbl_box.addWidget(self._disk_val)
        disk_box.addLayout(disk_lbl_box)

        self._disk_bar = QProgressBar()
        self._disk_bar.setRange(0, 100)
        self._disk_bar.setFixedHeight(8)
        disk_box.addWidget(self._disk_bar)
        self.layout.addLayout(disk_box)

        # 4. OS & Environment Readout
        os_name = f"{platform.system()} {platform.release()} ({platform.machine()})"
        os_lbl = QLabel(f"<b>OS:</b> {os_name}")
        os_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.layout.addWidget(os_lbl)

        python_ver = f"Python {sys.version.split()[0]} // PyQt6"
        py_lbl = QLabel(f"<b>CORE:</b> {python_ver}")
        py_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        self.layout.addWidget(py_lbl)

    def _poll_metrics(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent if sys.platform != "win32" else psutil.disk_usage("C:\\").percent

            self._cpu_val.setText(f"{int(cpu)}%")
            self._cpu_bar.setValue(int(cpu))

            self._ram_val.setText(f"{int(ram)}%")
            self._ram_bar.setValue(int(ram))

            self._disk_val.setText(f"{int(disk)}%")
            self._disk_bar.setValue(int(disk))
        except Exception:
            pass

    def update_telemetry(self, cpu: float, ram: float):
        """Allows direct signal updates from runtime."""
        self._cpu_val.setText(f"{int(cpu)}%")
        self._cpu_bar.setValue(int(cpu))
        self._ram_val.setText(f"{int(ram)}%")
        self._ram_bar.setValue(int(ram))
