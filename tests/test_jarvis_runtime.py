import unittest
from unittest.mock import MagicMock, patch
from core.jarvis_runtime import JarvisRuntime

class TestJarvisRuntime(unittest.TestCase):

    @patch("core.jarvis_runtime.SpeechListener")
    @patch("core.jarvis_runtime.SpeechTranscriber")
    @patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector")
    def setUp(self, mock_ww, mock_trans, mock_list):
        self.runtime = JarvisRuntime()

    def test_runtime_initial_state(self):
        self.assertEqual(self.runtime.current_status, "STANDBY")
        self.assertFalse(self.runtime.muted)
        self.assertIsNotNone(self.runtime.executor)
        self.assertIsNotNone(self.runtime.tts_manager)

    def test_observer_callbacks_registration(self):
        mock_status_cb = MagicMock()
        mock_speech_cb = MagicMock()

        self.runtime.register_observers(
            on_status_change=mock_status_cb,
            on_speech_text=mock_speech_cb
        )

        self.runtime._update_status("LISTENING")
        mock_status_cb.assert_called_with("LISTENING")

        self.runtime._update_speech_text("Listening...")
        mock_speech_cb.assert_called_with("Listening...")

    @patch("core.jarvis_runtime.CommandExecutor.execute")
    def test_process_command_system_intent(self, mock_exec):
        mock_exec.return_value = {
            "success": True,
            "action": "lock_pc",
            "message": "Computer locked successfully.",
            "pending_confirmation": False
        }

        self.runtime.process_command("Lock computer")
        mock_exec.assert_called()

    def test_duplex_speaker_lockout(self):
        self.runtime._on_speaker_started()
        self.assertTrue(self.runtime._tts_speaking_lock)
        self.assertEqual(self.runtime.current_status, "SPEAKING")

        self.runtime._on_speaker_stopped()
        self.assertFalse(self.runtime._tts_speaking_lock)
        self.assertEqual(self.runtime.current_status, "STANDBY")

    def test_speech_debug_observer(self):
        mock_debug_cb = MagicMock()
        self.runtime.register_observers(on_speech_debug=mock_debug_cb)
        self.assertEqual(self.runtime.on_speech_debug_cb, mock_debug_cb)

    @patch("core.jarvis_runtime.CommandExecutor.execute")
    def test_resolve_permission_confirmed(self, mock_exec):
        mock_exec.return_value = {
            "success": True,
            "action": "shutdown_pc",
            "message": "Shutting down.",
            "pending_confirmation": False
        }
        self.runtime.pending_intent = {"intent": "system_action", "action": "shutdown_pc"}
        self.runtime.resolve_permission(confirmed=True)
        self.assertIsNone(self.runtime.pending_intent)
        mock_exec.assert_called_with({"intent": "system_action", "action": "shutdown_pc"}, confirm=True)

    def test_resolve_permission_rejected(self):
        self.runtime.pending_intent = {"intent": "system_action", "action": "shutdown_pc"}
        self.runtime.resolve_permission(confirmed=False)
        self.assertIsNone(self.runtime.pending_intent)
        self.assertEqual(self.runtime.current_status, "STANDBY")

if __name__ == "__main__":
    unittest.main()
