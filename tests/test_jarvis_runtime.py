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

        self.runtime._process_command_worker("Lock computer")
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

    def test_tts_manager_is_playing_and_synthesizing(self):
        tts = self.runtime.tts_manager
        tts._state = "IDLE"
        tts._is_speaking = False
        self.assertFalse(tts.is_playing())
        self.assertFalse(tts.is_synthesizing())

        tts._state = "TTS_SYNTHESIZING"
        self.assertTrue(tts.is_synthesizing())
        self.assertFalse(tts.is_playing())

        tts._state = "TTS_PLAYING"
        self.assertTrue(tts.is_playing())
        self.assertFalse(tts.is_synthesizing())

    def test_on_wakeword_barge_in_during_playback(self):
        self.runtime.tts_manager.interrupt = MagicMock()
        self.runtime.tts_manager.play_wake_chime = MagicMock()
        self.runtime.listener.trigger_manual_recording = MagicMock()

        self.runtime.tts_manager._state = "TTS_PLAYING"
        self.runtime._tts_speaking_lock = True

        self.runtime._on_wakeword("jarvis")

        self.runtime.tts_manager.interrupt.assert_called_with(force=True)
        self.assertFalse(self.runtime._tts_speaking_lock)
        self.assertEqual(self.runtime.current_status, "LISTENING")

    def test_on_wakeword_suppressed_during_synthesis(self):
        self.runtime.tts_manager.interrupt = MagicMock()
        self.runtime.tts_manager.play_wake_chime = MagicMock()

        self.runtime.tts_manager._state = "TTS_SYNTHESIZING"
        self.runtime._tts_speaking_lock = True
        self.runtime.current_status = "STANDBY"

        self.runtime._on_wakeword("jarvis")

        self.runtime.tts_manager.interrupt.assert_not_called()
        self.assertEqual(self.runtime.current_status, "STANDBY")

    def test_on_wakeword_manual_click_always_interrupts(self):
        self.runtime.tts_manager.interrupt = MagicMock()
        self.runtime.tts_manager.play_wake_chime = MagicMock()
        self.runtime.listener.trigger_manual_recording = MagicMock()

        self.runtime.tts_manager._state = "TTS_SYNTHESIZING"
        self.runtime._tts_speaking_lock = True

        self.runtime._on_wakeword("manual_click")

        self.runtime.tts_manager.interrupt.assert_called_with(force=True)
        self.assertFalse(self.runtime._tts_speaking_lock)
        self.assertEqual(self.runtime.current_status, "LISTENING")

    def test_synthesizing_status_transition(self):
        self.runtime._update_status("STANDBY")
        self.runtime._on_speaker_synthesizing()
        self.assertEqual(self.runtime.current_status, "SYNTHESIZING")

        self.runtime._on_speaker_started()
        self.assertEqual(self.runtime.current_status, "SPEAKING")

        self.runtime._on_speaker_stopped()
        self.assertEqual(self.runtime.current_status, "STANDBY")

if __name__ == "__main__":
    unittest.main()

