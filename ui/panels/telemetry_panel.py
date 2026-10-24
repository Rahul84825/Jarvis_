"""
System Telemetry & Acceleration HUD Panel for SANTRA.
Displays non-blocking CPU, RAM, NVIDIA GPU acceleration, VRAM, and inference device telemetry.
"""

import sys
import platform
import psutil
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from ui.widgets.hud_frame import HUDFrame
from ui.theme import HUDColors
from config import config

class TelemetryPanel(HUDFrame):
    """Futuristic HUD blade showing real-time host telemetry and hardware acceleration metrics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._disk_check_counter = 0
        self._cached_disk_pct = 0
        self._init_ui()

        # Telemetry poll timer (default 2000ms / non-blocking cached snapshot read)
        interval_ms = getattr(config, "telemetry_refresh_interval_ms", 2000)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_metrics)
        self._poll_timer.start(interval_ms)
        self._poll_metrics()

    def _init_ui(self):
        hdr = QLabel("SYSTEM & ACCELERATION TELEMETRY")
        hdr.setProperty("class", "hudSectionTitle")
        self.layout.addWidget(hdr)

        # 1. CPU Section (Host + Santra Process)
        cpu_box = QVBoxLayout()
        cpu_box.setSpacing(2)
        cpu_lbl_box = QHBoxLayout()
        cpu_lbl_box.addWidget(QLabel("CPU LOAD:"))
        self._cpu_val = QLabel("0% (Host)")
        self._cpu_val.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 11px;")
        cpu_lbl_box.addStretch()
        cpu_lbl_box.addWidget(self._cpu_val)
        cpu_box.addLayout(cpu_lbl_box)

        self._cpu_bar = QProgressBar()
        self._cpu_bar.setRange(0, 100)
        self._cpu_bar.setFixedHeight(6)
        cpu_box.addWidget(self._cpu_bar)

        self._proc_cpu_lbl = QLabel("Santra Process: 0.0% CPU")
        self._proc_cpu_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        cpu_box.addWidget(self._proc_cpu_lbl)
        self.layout.addLayout(cpu_box)

        # 2. RAM Section (Host Memory + Santra RSS)
        ram_box = QVBoxLayout()
        ram_box.setSpacing(2)
        ram_lbl_box = QHBoxLayout()
        ram_lbl_box.addWidget(QLabel("SYSTEM RAM:"))
        self._ram_val = QLabel("0%")
        self._ram_val.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 11px;")
        ram_lbl_box.addStretch()
        ram_lbl_box.addWidget(self._ram_val)
        ram_box.addLayout(ram_lbl_box)

        self._ram_bar = QProgressBar()
        self._ram_bar.setRange(0, 100)
        self._ram_bar.setFixedHeight(6)
        ram_box.addWidget(self._ram_bar)

        self._proc_ram_lbl = QLabel("Santra RSS: -- MB | Available: -- GB")
        self._proc_ram_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        ram_box.addWidget(self._proc_ram_lbl)
        self.layout.addLayout(ram_box)

        # 3. GPU & Acceleration Section
        gpu_box = QVBoxLayout()
        gpu_box.setSpacing(2)
        gpu_lbl_box = QHBoxLayout()
        self._gpu_header_lbl = QLabel("GPU ACCELERATION:")
        gpu_lbl_box.addWidget(self._gpu_header_lbl)
        self._gpu_val = QLabel("READY")
        self._gpu_val.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
        gpu_lbl_box.addStretch()
        gpu_lbl_box.addWidget(self._gpu_val)
        gpu_box.addLayout(gpu_lbl_box)

        self._gpu_bar = QProgressBar()
        self._gpu_bar.setRange(0, 100)
        self._gpu_bar.setFixedHeight(6)
        gpu_box.addWidget(self._gpu_bar)

        self._gpu_details_lbl = QLabel("NVIDIA RTX 3050 Laptop GPU")
        self._gpu_details_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        gpu_box.addWidget(self._gpu_details_lbl)

        self._gpu_vram_lbl = QLabel("VRAM: -- / -- MB | Temp: --°C")
        self._gpu_vram_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        gpu_box.addWidget(self._gpu_vram_lbl)
        self.layout.addLayout(gpu_box)

        # 4. Workload Routing & Inference Device
        route_box = QVBoxLayout()
        route_box.setSpacing(2)
        self._device_lbl = QLabel("<b>INFERENCE:</b> CPU (int8)")
        self._device_lbl.setStyleSheet("color: #e2e8f0; font-size: 10px;")
        route_box.addWidget(self._device_lbl)

        self._status_route_lbl = QLabel("<b>STATUS:</b> VERIFIED_CPU_FALLBACK")
        self._status_route_lbl.setStyleSheet("color: #38bdf8; font-size: 10px;")
        route_box.addWidget(self._status_route_lbl)

        self._task_lbl = QLabel("<b>TASK:</b> Standing by for wake word")
        self._task_lbl.setStyleSheet("color: #64748b; font-size: 9px;")
        route_box.addWidget(self._task_lbl)
        self.layout.addLayout(route_box)

        # 5. Disk Space Gauge (Periodic sample)
        disk_box = QVBoxLayout()
        disk_box.setSpacing(2)
        disk_lbl_box = QHBoxLayout()
        disk_lbl_box.addWidget(QLabel("PRIMARY DISK:"))
        self._disk_val = QLabel("0%")
        self._disk_val.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 11px;")
        disk_lbl_box.addStretch()
        disk_lbl_box.addWidget(self._disk_val)
        disk_box.addLayout(disk_lbl_box)

        self._disk_bar = QProgressBar()
        self._disk_bar.setRange(0, 100)
        self._disk_bar.setFixedHeight(6)
        disk_box.addWidget(self._disk_bar)
        self.layout.addLayout(disk_box)

        # 6. Host & Environment
        os_name = f"{platform.system()} {platform.release()} ({platform.machine()})"
        os_lbl = QLabel(f"<b>HOST:</b> {os_name}")
        os_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        self.layout.addWidget(os_lbl)

        python_ver = f"Python {sys.version.split()[0]} // PyQt6"
        py_lbl = QLabel(f"<b>CORE:</b> {python_ver}")
        py_lbl.setStyleSheet("color: #64748b; font-size: 9px;")
        self.layout.addWidget(py_lbl)

    def _poll_metrics(self):
        """Fetches non-blocking cached snapshot from SystemResourceManager."""
        try:
            from core.system_resource_manager import system_resource_manager
            snap = system_resource_manager.get_snapshot()

            # 1. CPU
            sys_cpu = int(snap.system_cpu_pct)
            self._cpu_val.setText(f"{sys_cpu}% (Host)")
            self._cpu_bar.setValue(min(100, max(0, sys_cpu)))
            self._proc_cpu_lbl.setText(f"Santra Process: {snap.process_cpu_pct:.1f}% CPU (PID {snap.process_pid})")

            # 2. RAM
            sys_ram_pct = int(snap.system_ram_percent)
            self._ram_val.setText(f"{sys_ram_pct}%")
            self._ram_bar.setValue(min(100, max(0, sys_ram_pct)))
            avail_gb = snap.system_ram_available_mb / 1024.0
            self._proc_ram_lbl.setText(f"Santra RSS: {snap.process_rss_mb:.1f} MB | Host Avail: {avail_gb:.2f} GB")

            # 3. GPU Telemetry
            if snap.gpu_available and snap.gpu_utilization_pct is not None:
                gpu_pct = int(snap.gpu_utilization_pct)
                self._gpu_val.setText(f"{gpu_pct}%")
                self._gpu_bar.setValue(min(100, max(0, gpu_pct)))
                self._gpu_details_lbl.setText(f"{snap.gpu_name} (v{snap.gpu_driver_version})")

                vram_used = snap.gpu_mem_used_mb or 0.0
                vram_total = snap.gpu_mem_total_mb or 6144.0
                temp_str = f"{int(snap.gpu_temp_c)}°C" if snap.gpu_temp_c is not None else "--"
                power_str = f"{snap.gpu_power_w:.1f}W" if snap.gpu_power_w is not None else "--"
                self._gpu_vram_lbl.setText(f"VRAM: {vram_used:.0f}/{vram_total:.0f} MB | {temp_str} | {power_str}")
            else:
                self._gpu_val.setText("STANDBY")
                self._gpu_bar.setValue(0)
                if snap.gpu_name != "None":
                    self._gpu_details_lbl.setText(f"{snap.gpu_name}")
                else:
                    self._gpu_details_lbl.setText("No NVIDIA GPU Active")
                self._gpu_vram_lbl.setText("GPU Telemetry: Idle / Standby")

            # 4. Workload Routing & Device Status
            self._device_lbl.setText(f"<b>INFERENCE:</b> {snap.inference_device}")
            
            # Highlight acceleration status cleanly
            if "CUDA" in snap.acceleration_status:
                status_color = "#10b981"  # Emerald
                status_text = "CUDA ACCELERATED"
            elif "FALLBACK" in snap.acceleration_status:
                status_color = "#38bdf8"  # Sky blue
                status_text = "CPU (int8) VERIFIED"
            else:
                status_color = "#94a3b8"
                status_text = "STANDARD CPU"

            self._status_route_lbl.setText(f"<b>STATUS:</b> <span style='color: {status_color};'>{status_text}</span>")
            self._task_lbl.setText(f"<b>TASK:</b> [{snap.profile_state}] {snap.current_task}")

            # 5. Disk (polled every 10 ticks to minimize disk I/O)
            self._disk_check_counter += 1
            if self._disk_check_counter >= 10 or self._cached_disk_pct == 0:
                self._disk_check_counter = 0
                disk = psutil.disk_usage("C:\\" if sys.platform == "win32" else "/").percent
                self._cached_disk_pct = int(disk)

            self._disk_val.setText(f"{self._cached_disk_pct}%")
            self._disk_bar.setValue(self._cached_disk_pct)

        except Exception as e:
            pass

    def update_telemetry(self, cpu: float, ram: float):
        """Allows direct signal updates from runtime if needed."""
        self._cpu_val.setText(f"{int(cpu)}%")
        self._cpu_bar.setValue(int(cpu))
        self._ram_val.setText(f"{int(ram)}%")
        self._ram_bar.setValue(int(ram))

    def closeEvent(self, event):
        """Stops timer when panel is destroyed."""
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        super().closeEvent(event)
