"""
Comprehensive Performance, Resource Management, and GPU Routing Regression Test Suite for SANTRA.
Tests:
1. SystemResourceManager thread-safety, sampling, and non-blocking snapshot API.
2. Hardware capability detection, honest GPU reporting, and graceful CPU fallback.
3. SpeechTranscriber model lifecycle, idle unloading, and on-demand reloading.
4. Windows automatic startup, pythonw.exe silent execution, and single-instance protection.
5. Runtime sleep/active profile transitions and resource throttling.
6. TelemetryPanel non-blocking UI polling.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from core.system_resource_manager import (
    SystemResourceManager,
    ResourceSnapshot,
    HardwareCapabilityDetector,
    NvmlTelemetry
)
from core.transcriber import SpeechTranscriber
from core.startup import get_app_command, is_startup_enabled, get_startup_status
from core.single_instance import SingleInstanceGuard
from config import config

class TestPerformanceAndResourceRegression(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mgr = SystemResourceManager.get_instance()

    def setUp(self):
        self.mgr.set_profile("STANDBY")

    def tearDown(self):
        if self.mgr._running:
            self.mgr.stop()

    # ==========================================
    # 1. RESOURCE MANAGER & SNAPSHOT TESTS
    # ==========================================
    def test_resource_snapshot_structure_and_completeness(self):
        """Verifies that ResourceSnapshot contains all required process and system metrics."""
        snap = self.mgr.get_snapshot()
        self.assertIsInstance(snap, ResourceSnapshot)
        self.assertGreater(snap.timestamp, 0.0)
        self.assertGreater(snap.process_pid, 0)
        self.assertGreaterEqual(snap.process_rss_mb, 0.0)
        self.assertGreaterEqual(snap.system_cpu_pct, 0.0)
        self.assertGreater(snap.system_ram_total_mb, 0.0)
        self.assertGreater(snap.system_ram_available_mb, 0.0)
        self.assertIn(snap.profile_state, ["STANDBY", "ACTIVE", "PROCESSING", "SLEEPING"])
        self.assertIn(snap.acceleration_status, ["VERIFIED_CUDA", "VERIFIED_CPU_FALLBACK", "UNAVAILABLE"])

    def test_distinguishes_process_from_system_metrics(self):
        """Verifies that Santra process metrics are strictly distinguished from host system metrics."""
        snap = self.mgr.get_snapshot()
        # Process RAM (RSS) is typically smaller than total system RAM used
        self.assertLessEqual(snap.process_rss_mb, snap.system_ram_total_mb)
        # Check dictionary serialization
        d = snap.to_dict()
        self.assertIn("process_rss_mb", d)
        self.assertIn("system_ram_used_mb", d)
        self.assertIn("gpu_mem_used_mb", d)

    def test_profile_state_transitions(self):
        """Verifies that changing profiles updates sampling interval and task description."""
        self.mgr.set_profile("SLEEPING")
        self.assertEqual(self.mgr._profile_state, "SLEEPING")
        self.assertEqual(self.mgr._sampling_interval_sec, 5.0)

        self.mgr.set_profile("PROCESSING")
        self.assertEqual(self.mgr._profile_state, "PROCESSING")
        self.assertEqual(self.mgr._sampling_interval_sec, 1.0)

        self.mgr.set_profile("STANDBY")
        self.assertEqual(self.mgr._profile_state, "STANDBY")
        self.assertEqual(self.mgr._sampling_interval_sec, 2.0)

    def test_update_task_context(self):
        """Verifies updating current task, model, and device reflected in snapshot."""
        self.mgr.update_task_context(
            task="Executing Test Task",
            model="faster-whisper-test",
            device="CPU (int8)"
        )
        self.assertEqual(self.mgr._current_task, "Executing Test Task")
        self.assertEqual(self.mgr._current_model, "faster-whisper-test")
        self.assertEqual(self.mgr._inference_device, "CPU (int8)")

    def test_non_blocking_start_and_stop(self):
        """Verifies background monitor thread starts and stops gracefully within timeout."""
        self.mgr.start()
        self.assertTrue(self.mgr._running)
        time.sleep(0.1)
        self.mgr.stop()
        self.assertFalse(self.mgr._running)

    # ==========================================
    # 2. GPU & CAPABILITY DETECTION TESTS
    # ==========================================
    def test_nvml_telemetry_graceful_on_missing_gpu(self):
        """Verifies NvmlTelemetry returns safe defaults when GPU is unavailable."""
        telemetry = NvmlTelemetry()
        # Mocking uninitialized state
        telemetry.is_initialized = False
        telemetry._device_handle = None
        metrics = telemetry.query_metrics()
        self.assertFalse(metrics["available"])
        self.assertIsNone(metrics["utilization_pct"])
        self.assertIsNone(metrics["mem_used_mb"])

    def test_capability_detector_honest_routing_policy(self):
        """Verifies capability detector recommends CPU int8 when CUDA backend DLL is missing."""
        telemetry = NvmlTelemetry()
        detector = HardwareCapabilityDetector(telemetry)
        
        # Test with mocked CUDA failure
        with patch.object(detector, '_verify_ctranslate2_cuda', return_value=(False, "cublas64_12.dll missing")):
            with patch.dict('sys.modules', {'ctranslate2': MagicMock(get_cuda_device_count=lambda: 1)}):
                caps = detector.get_capabilities(force_refresh=True)
                self.assertFalse(caps["ctranslate2_cuda_verified"])
                self.assertEqual(caps["recommended_stt_device"], "cpu")
                self.assertEqual(caps["recommended_stt_compute"], "int8")
                self.assertIn("safely routed to CPU (int8)", caps["status_message"])

    def test_capability_detector_cuda_verified_when_smoke_test_passes(self):
        """Verifies capability detector activates CUDA float16 when smoke test succeeds."""
        telemetry = NvmlTelemetry()
        detector = HardwareCapabilityDetector(telemetry)
        
        with patch.object(detector, '_verify_ctranslate2_cuda', return_value=(True, "")):
            with patch.dict('sys.modules', {'ctranslate2': MagicMock(get_cuda_device_count=lambda: 1)}):
                caps = detector.get_capabilities(force_refresh=True)
                self.assertTrue(caps["ctranslate2_cuda_verified"])
                self.assertEqual(caps["recommended_stt_device"], "cuda")
                self.assertEqual(caps["recommended_stt_compute"], "float16")

    # ==========================================
    # 3. TRANSCRIBER MODEL LIFECYCLE & IDLE UNLOAD
    # ==========================================
    def test_transcriber_target_device_selection(self):
        """Verifies SpeechTranscriber respects auto routing and capability detector."""
        transcriber = SpeechTranscriber(model_size="base", device="auto")
        dev, compute = transcriber._determine_target_device()
        self.assertIn(dev, ["cpu", "cuda"])
        self.assertIn(compute, ["int8", "float16"])

    def test_transcriber_model_unload_and_activity(self):
        """Verifies unload_model cleans references and check_idle_unload honors timeout."""
        transcriber = SpeechTranscriber(model_size="base", device="cpu")
        self.assertFalse(transcriber.is_loaded())
        
        # Simulate loaded model
        transcriber._model = MagicMock()
        self.assertTrue(transcriber.is_loaded())
        
        # Touch activity
        transcriber.touch_activity()
        self.assertLessEqual(time.time() - transcriber._last_used_time, 0.1)

        # Idle timeout check: not expired
        unloaded = transcriber.check_idle_unload(timeout_sec=100.0)
        self.assertFalse(unloaded)
        self.assertTrue(transcriber.is_loaded())

        # Idle timeout check: expired
        transcriber._last_used_time = time.time() - 200.0
        unloaded = transcriber.check_idle_unload(timeout_sec=100.0)
        self.assertTrue(unloaded)
        self.assertFalse(transcriber.is_loaded())
        self.assertIsNone(transcriber._model)

    # ==========================================
    # 4. WINDOWS STARTUP & SILENT EXECUTION
    # ==========================================
    def test_get_app_command_format(self):
        """Verifies get_app_command constructs a valid path containing --minimized."""
        cmd = get_app_command()
        self.assertIn("--minimized", cmd)
        self.assertIn("main.py", cmd)
        # Should prefer pythonw.exe if it exists on Windows
        if sys.platform == "win32":
            self.assertTrue("python.exe" in cmd or "pythonw.exe" in cmd)

    def test_get_startup_status_dictionary(self):
        """Verifies get_startup_status returns structured dictionary."""
        status = get_startup_status()
        self.assertIn("enabled", status)
        self.assertIn("command", status)
        self.assertIn("platform", status)
        self.assertIn("message", status)

    # ==========================================
    # 5. SINGLE INSTANCE APPLICATION GUARD
    # ==========================================
    def test_single_instance_guard_mutual_exclusion(self):
        """Verifies secondary instance is rejected when primary holds the lock."""
        guard1 = SingleInstanceGuard(mutex_name="Global\\TEST_SANTRA_MUTEX_1", ipc_port=49198)
        guard2 = SingleInstanceGuard(mutex_name="Global\\TEST_SANTRA_MUTEX_1", ipc_port=49198)
        
        primary_acquired = guard1.acquire()
        self.assertTrue(primary_acquired, "Primary instance should acquire lock.")
        
        secondary_acquired = guard2.acquire()
        self.assertFalse(secondary_acquired, "Secondary instance must be rejected.")
        
        # Clean up
        guard2.release()
        guard1.release()

    # ==========================================
    # 6. TELEMETRY PANEL NON-BLOCKING UI
    # ==========================================
    def test_telemetry_panel_polling(self):
        """Verifies TelemetryPanel polls metrics without raising exceptions."""
        from PyQt6.QtWidgets import QApplication
        from ui.panels.telemetry_panel import TelemetryPanel

        app = QApplication.instance() or QApplication(sys.argv)
        panel = TelemetryPanel()
        # Direct trigger poll
        panel._poll_metrics()
        self.assertIn("%", panel._cpu_val.text())
        self.assertIn("%", panel._ram_val.text())
        panel.close()

if __name__ == "__main__":
    unittest.main()
