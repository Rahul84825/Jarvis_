"""
Comprehensive Acceptance and Integration Test Suite for Phase 1:
Reliable Startup and Wake-Word Lifecycle.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

from core.single_instance import SingleInstanceGuard
import core.startup as startup
from core.intent_engine import IntentEngine
from core.command_normalizer import CommandNormalizer
from core.tool_registry import tool_registry
from modules.system.executor import CommandExecutor
from core.wakeword import MockWakeWordDetector, OpenWakeWordDetector, WakeWordDetectorFactory
from core.jarvis_runtime import JarvisRuntime

class TestPhase1StartupAndWakeWord(unittest.TestCase):

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.executor = CommandExecutor()

    # ==========================================
    # 1. SINGLE-INSTANCE ENFORCEMENT TESTS
    # ==========================================
    def test_single_instance_primary_acquire_and_release(self):
        """Verifies that the primary instance successfully acquires the lock and cleans up."""
        guard = SingleInstanceGuard(mutex_name="Global\\TEST_JARVIS_SINGLETON_PRIMARY", ipc_port=49201)
        acquired = guard.acquire()
        self.assertTrue(acquired, "Primary instance should acquire lock successfully.")
        self.assertTrue(guard.is_primary)
        guard.release()
        self.assertFalse(guard.is_primary)

    def test_single_instance_secondary_blocks_and_notifies(self):
        """Verifies that a second instance is prevented from running when one is active."""
        port = 49202
        guard1 = SingleInstanceGuard(mutex_name="Global\\TEST_JARVIS_SINGLETON_PAIR", ipc_port=port)
        self.assertTrue(guard1.acquire())

        activated = []
        guard1.start_ipc_server(on_activate=lambda: activated.append(True))

        # Secondary instance attempt
        guard2 = SingleInstanceGuard(mutex_name="Global\\TEST_JARVIS_SINGLETON_PAIR", ipc_port=port)
        if sys.platform == "win32":
            # On Windows, named mutex exists
            acquired2 = guard2.acquire()
            self.assertFalse(acquired2, "Secondary instance must not acquire lock when primary is running.")

        # Test IPC notification from secondary to primary
        notified = guard2.notify_existing("RESTORE_HUD")
        self.assertTrue(notified, "Secondary instance should successfully send IPC signal to primary.")

        import time
        time.sleep(0.1)
        self.assertTrue(len(activated) > 0, "Primary instance should receive activation callback.")

        guard2.release()
        guard1.release()

    # ==========================================
    # 2. WINDOWS STARTUP INTEGRATION TESTS
    # ==========================================
    @patch('core.startup.is_startup_enabled', return_value=True)
    def test_startup_status_info_enabled(self, mock_enabled):
        """Verifies get_startup_status returns structured dict when startup is enabled."""
        info = startup.get_startup_status()
        self.assertTrue(info["enabled"])
        self.assertIn("minimized", info["command"])
        self.assertIn("minimized tray mode", info["message"])

    @patch('core.startup.is_startup_enabled', return_value=False)
    def test_startup_status_info_disabled(self, mock_disabled):
        """Verifies get_startup_status returns structured dict when startup is disabled."""
        info = startup.get_startup_status()
        self.assertFalse(info["enabled"])
        self.assertIn("disabled", info["message"])

    @patch('core.startup.enable_startup', return_value=True)
    def test_executor_enable_startup(self, mock_enable):
        """Verifies CommandExecutor handles enable_startup action deterministically."""
        res = self.executor.execute({"intent": "system_control", "action": "enable_startup"})
        self.assertTrue(res["success"])
        self.assertIn("start automatically with Windows", res["message"])
        mock_enable.assert_called_once()

    @patch('core.startup.disable_startup', return_value=True)
    def test_executor_disable_startup(self, mock_disable):
        """Verifies CommandExecutor handles disable_startup action deterministically."""
        res = self.executor.execute({"intent": "system_control", "action": "disable_startup"})
        self.assertTrue(res["success"])
        self.assertIn("Automatic Windows startup has been disabled", res["message"])
        mock_disable.assert_called_once()

    @patch('core.startup.is_startup_enabled', return_value=True)
    def test_executor_check_startup_enabled(self, mock_is_enabled):
        """Verifies CommandExecutor handles startup_status query action."""
        res = self.executor.execute({"intent": "system_control", "action": "startup_status"})
        self.assertTrue(res["success"])
        self.assertIn("currently configured to start automatically", res["message"])

    def test_tool_registry_has_startup_and_standby_controls(self):
        """Verifies startup_control and standby_control are registered in ToolRegistry."""
        startup_tool = tool_registry.get_tool("startup_control")
        self.assertIsNotNone(startup_tool)
        self.assertEqual(startup_tool.category, "system")

        standby_tool = tool_registry.get_tool("standby_control")
        self.assertIsNotNone(standby_tool)
        self.assertEqual(standby_tool.category, "system")

    # ==========================================
    # 3. INTENT PARSING & ACTIVATION PHRASES
    # ==========================================
    def test_intent_startup_commands(self):
        """Verifies natural speech phrases map to startup system control intents."""
        test_cases = [
            ("enable startup", "enable_startup"),
            ("start with windows", "enable_startup"),
            ("launch on startup", "enable_startup"),
            ("disable startup", "disable_startup"),
            ("do not start with windows", "disable_startup"),
            ("don't start with windows", "disable_startup"),
            ("check startup", "startup_status"),
            ("is startup enabled", "startup_status"),
        ]
        for phrase, expected_action in test_cases:
            node = self.intent_engine.parse(phrase)
            self.assertEqual(node["intent"], "system_control", f"Failed for '{phrase}'")
            self.assertEqual(node["action"], expected_action, f"Failed for '{phrase}'")

    def test_intent_session_start_command(self):
        """Verifies 'JARVIS, let's start.' and variations map to session_start."""
        test_cases = [
            "let's start",
            "lets start",
            "start session",
            "let's begin",
            "JARVIS, let's start",
            "hey jarvis lets start",
            "jarvis, begin session"
        ]
        for phrase in test_cases:
            node = self.intent_engine.parse(phrase)
            self.assertEqual(node["intent"], "session_start", f"Failed for phrase: '{phrase}'")
            self.assertEqual(node["action"], "start_session", f"Failed for phrase: '{phrase}'")

    def test_intent_standby_and_listening_controls(self):
        """Verifies speech commands for standby, mute mic, and unmute mic."""
        test_cases = [
            ("go to standby", "enter_standby"),
            ("enter standby", "enter_standby"),
            ("standby mode", "enter_standby"),
            ("stop listening", "disable_listening"),
            ("disable listening", "disable_listening"),
            ("mute microphone", "disable_listening"),
            ("mute mic", "disable_listening"),
            ("resume listening", "enable_listening"),
            ("enable listening", "enable_listening"),
            ("unmute microphone", "enable_listening"),
        ]
        for phrase, expected_action in test_cases:
            node = self.intent_engine.parse(phrase)
            self.assertEqual(node["intent"], "system_control", f"Failed for '{phrase}'")
            self.assertEqual(node["action"], expected_action, f"Failed for '{phrase}'")

    def test_activation_followed_by_command(self):
        """Verifies composite utterance: 'Hey JARVIS, open VS Code.' strips wake word and routes to open_app."""
        raw_speech = "Hey JARVIS, open VS Code."
        norm_res = self.normalizer.normalize(raw_speech)
        self.assertNotIn("jarvis", norm_res["normalized"].lower())
        self.assertEqual(norm_res["normalized"], "open vscode")

        node = self.intent_engine.parse(raw_speech)
        self.assertEqual(node["intent"], "open_app")
        self.assertEqual(node["target"], "vscode")

    # ==========================================
    # 4. TRUTHFUL DIAGNOSTICS & PRIVACY TESTS
    # ==========================================
    def test_truthful_diagnostics_mock_detector(self):
        """Verifies that when MockWakeWordDetector is used, hands_free_operational is False."""
        runtime = JarvisRuntime()
        runtime.wakeword_detector = MockWakeWordDetector()
        
        self.assertFalse(runtime.is_hands_free_operational, "Mock detector must NOT report hands-free as operational.")
        diag = runtime.get_wake_word_diagnostics()
        self.assertTrue(diag["is_mock"])
        self.assertFalse(diag["hands_free_operational"])
        self.assertIn("Mock wake-word detector active", diag["status_message"])
        runtime.stop()

    def test_truthful_diagnostics_when_muted(self):
        """Verifies that when muted (privacy mode), hands_free_operational is False."""
        runtime = JarvisRuntime()
        runtime.set_mute_state(True)
        self.assertTrue(runtime.muted)
        self.assertFalse(runtime.is_hands_free_operational)
        diag = runtime.get_wake_word_diagnostics()
        self.assertTrue(diag["is_muted"])
        self.assertFalse(diag["hands_free_operational"])
        runtime.stop()

    def test_runtime_enter_standby(self):
        """Verifies runtime.enter_standby resets pipeline state cleanly."""
        runtime = JarvisRuntime()
        runtime.current_status = "LISTENING"
        runtime.enter_standby(speak=False)
        self.assertEqual(runtime.current_status, "STANDBY")
        self.assertIsNone(runtime.pending_intent)
        runtime.stop()

    def test_runtime_mute_toggles_detector_and_listener(self):
        """Verifies set_mute_state pauses wakeword detector and listener."""
        runtime = JarvisRuntime()
        mock_detector = MagicMock()
        runtime.wakeword_detector = mock_detector
        mock_listener = MagicMock()
        runtime.listener = mock_listener

        # Mute
        runtime.set_mute_state(True)
        self.assertTrue(runtime.muted)
        mock_detector.stop.assert_called_once()
        mock_listener.stop.assert_called_once()

        # Unmute
        runtime.set_mute_state(False)
        self.assertFalse(runtime.muted)
        mock_detector.start.assert_called_once()
        mock_listener.start.assert_called_once()
        runtime.stop()

if __name__ == "__main__":
    unittest.main()
