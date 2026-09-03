import unittest
from unittest.mock import patch, MagicMock
from core.jarvis_runtime import JarvisRuntime
from config import config

class TestCommandVsConversationRouting(unittest.TestCase):

    @patch("core.jarvis_runtime.SpeechListener")
    @patch("core.jarvis_runtime.SpeechTranscriber")
    @patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector")
    def setUp(self, mock_ww, mock_trans, mock_list):
        self.runtime = JarvisRuntime()

    @patch("core.jarvis_runtime.CommandExecutor.execute")
    def test_local_command_bypasses_ai(self, mock_exec):
        mock_exec.return_value = {"success": True, "action": "open_app", "message": "Opening Chrome."}

        with patch.object(self.runtime.conversation_manager, "process_query") as mock_cm:
            res = self.runtime._process_single_command("Open Chrome", speak=False)
            mock_exec.assert_called()
            mock_cm.assert_not_called()
            self.assertEqual(res["action"], "open_app")

    def test_general_query_routes_to_conversation_manager(self):
        with patch.object(self.runtime.conversation_manager, "process_query") as mock_cm:
            mock_cm.return_value = {
                "text": "Quantum computing uses qubits.",
                "source": "Mock Provider",
                "ai_available": True
            }
            res = self.runtime._process_single_command("What is quantum computing?", speak=False)
            mock_cm.assert_called_with("What is quantum computing?")
            self.assertEqual(res["action"], "conversation")

if __name__ == "__main__":
    unittest.main()
