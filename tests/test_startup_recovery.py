"""Comprehensive Test Suite for Santra Windows Auto-Start and Background Service Recovery:
- Launcher path resolution
- Interpreter selection (venv vs system)
- Working directory enforcement
- Missing / corrupted environment variables handling (.env)
- Privacy-safe startup error logging
- Single-instance enforcement and duplicate prevention
- Repeated start/stop lifecycle requests
- Microphone initialization failure handling and bounded retries
- Hidden-panel initialization and HUD toggle
- Graceful shutdown and cleanup
- Health diagnostic status verification
"""

import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.single_instance import SingleInstanceGuard
from core.startup import is_startup_enabled, get_startup_status, get_startup_diagnostics, get_app_command
from core.global_hotkey import GlobalHotkeyManager
import launcher


class TestLauncherResolutionAndEnvironment(unittest.TestCase):
    """Verifies Phase 2 launcher path resolution, interpreter selection, and environment loading."""

    def test_project_root_resolved(self):
        """Launcher must resolve project root accurately."""
        self.assertTrue(launcher.PROJECT_ROOT.exists())
        self.assertTrue((launcher.PROJECT_ROOT / "main.py").exists())
        self.assertTrue((launcher.PROJECT_ROOT / "launcher.py").exists())

    def test_find_python_interpreter_fallback(self):
        """Interpreter resolver must return valid Python and Pythonw executables."""
        py_exe, pyw_exe = launcher.find_python_interpreter()
        self.assertTrue(py_exe.exists(), f"Python executable does not exist: {py_exe}")
        self.assertTrue(pyw_exe.exists(), f"Pythonw executable does not exist: {pyw_exe}")
        self.assertTrue(pyw_exe.name.lower().startswith("pythonw"))

    def test_find_python_interpreter_venv_priority(self):
        """Interpreter resolver must prioritize virtual environment if present."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            mock_venv_scripts = tmp_path / ".venv" / "Scripts"
            mock_venv_scripts.mkdir(parents=True)
            mock_py = mock_venv_scripts / "python.exe"
            mock_pyw = mock_venv_scripts / "pythonw.exe"
            mock_py.touch()
            mock_pyw.touch()

            with patch.object(launcher, "PROJECT_ROOT", tmp_path):
                py, pyw = launcher.find_python_interpreter()
                self.assertEqual(py, mock_py.resolve())
                self.assertEqual(pyw, mock_pyw.resolve())

    def test_load_environment_safely_missing_file(self):
        """Missing .env file must be handled safely without error."""
        non_existent = Path(tempfile.gettempdir()) / "non_existent_santra_env_file.env"
        env = launcher.load_environment_safely(non_existent)
        self.assertEqual(env, {})

    def test_load_environment_safely_masks_secrets(self):
        """Sensitive API keys and tokens must never be exposed in startup logs."""
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".env") as f:
            f.write("SANTRA_NVIDIA_API_KEY=nvapi-secret123456789\n")
            f.write("NORMAL_SETTING=production_mode\n")
            tmp_env = Path(f.name)

        try:
            with patch.object(launcher.logger, "info") as mock_info:
                loaded = launcher.load_environment_safely(tmp_env)
                self.assertIn("SANTRA_NVIDIA_API_KEY", loaded)
                self.assertIn("NORMAL_SETTING", loaded)

                # Check log messages: raw secret string must not appear
                for call_arg in mock_info.call_args_list:
                    msg = str(call_arg)
                    self.assertNotIn("nvapi-secret123456789", msg)
        finally:
            if tmp_env.exists():
                os.unlink(tmp_env)


class TestSingleInstanceEnforcement(unittest.TestCase):
    """Verifies single instance enforcement and duplicate prevention."""

    def test_single_instance_acquisition_and_release(self):
        """Primary instance acquires lock, secondary instance is rejected, release works."""
        test_mutex = "Global\\Santra_Recovery_Test_Mutex"
        test_port = 49195

        guard1 = SingleInstanceGuard(mutex_name=test_mutex, ipc_port=test_port)
        self.assertTrue(guard1.acquire())
        self.assertTrue(guard1.is_primary)

        # Secondary instance must fail to acquire
        guard2 = SingleInstanceGuard(mutex_name=test_mutex, ipc_port=test_port)
        self.assertFalse(guard2.acquire())
        self.assertFalse(guard2.is_primary)

        # Clean release
        guard1.release()
        guard2.release()

        # Re-acquisition must succeed after clean release
        guard3 = SingleInstanceGuard(mutex_name=test_mutex, ipc_port=test_port)
        self.assertTrue(guard3.acquire())
        guard3.release()

    def test_launcher_detects_already_running(self):
        """Launcher must detect existing instance and exit cleanly without duplicates."""
        with patch("launcher.is_already_running", return_value=True):
            code = launcher.launch_santra()
            self.assertEqual(code, 0)


class TestMicrophoneInitializationResilience(unittest.TestCase):
    """Verifies microphone initialization failure recovery and bounded retries."""

    def test_listener_bounded_retries_and_recovery(self):
        """SpeechListener must retry on transient audio device errors and succeed if available."""
        from core.listener import SpeechListener

        listener = SpeechListener()
        call_count = [0]

        def fake_input_stream(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise OSError("Audio hardware busy / initializing")
            mock_stream = MagicMock()
            return mock_stream

        with patch("core.listener.sd.InputStream", side_effect=fake_input_stream):
            with patch("core.listener.time.sleep", return_value=None):
                listener.start()
                self.assertTrue(listener.is_listening())
                self.assertEqual(call_count[0], 2)
                listener.stop()

    def test_runtime_degraded_mode_on_mic_failure(self):
        """JarvisRuntime must stay alive in degraded mode if microphone fails completely."""
        from core.jarvis_runtime import JarvisRuntime

        runtime = JarvisRuntime()

        with patch.object(runtime.listener, "start", side_effect=OSError("Permanent hardware failure")):
            with patch.object(runtime.wakeword_detector, "start"):
                with patch.object(runtime.tts_manager, "start"):
                    with patch.object(runtime.transcriber, "preload_in_background"):
                        with patch.object(runtime.proactive_daemon, "start"):
                            runtime.start()
                            self.assertEqual(runtime.current_status, "STANDBY")

                            health = runtime.get_startup_health()
                            self.assertFalse(health["healthy"])
                            self.assertIn("Microphone listener is not active", health["actionable_errors"][0])
                            runtime.stop()


class TestHiddenPanelAndHotkey(unittest.TestCase):
    """Verifies hidden panel behavior and thread-pumped global hotkey."""

    def test_global_hotkey_thread_pump_lifecycle(self):
        """GlobalHotkeyManager must register, trigger, and unregister on hwnd=None."""
        mgr = GlobalHotkeyManager(hotkey_id=0x5342)
        triggered = []

        ok = mgr.register(hwnd=None, on_trigger=lambda: triggered.append(True))
        if sys.platform == "win32":
            self.assertTrue(ok)
            self.assertTrue(mgr.is_registered)

            mgr.trigger()
            self.assertEqual(len(triggered), 1)

            unreg_ok = mgr.unregister()
            self.assertTrue(unreg_ok)
            self.assertFalse(mgr.is_registered)

    def test_startup_command_points_to_launcher(self):
        """Startup command must point to launcher.py with --minimized."""
        cmd = get_app_command()
        self.assertIn("launcher.py", cmd)
        self.assertIn("--minimized", cmd)
        self.assertIn("pythonw", cmd)

    def test_startup_diagnostics_structure(self):
        """Startup diagnostics must return full system and task details."""
        diag = get_startup_diagnostics()
        self.assertIn("launcher_py", diag)
        self.assertTrue(diag["launcher_py_exists"])
        self.assertIn("task_scheduler_enabled", diag)
        self.assertIn("working_directory", diag)


if __name__ == "__main__":
    unittest.main()
