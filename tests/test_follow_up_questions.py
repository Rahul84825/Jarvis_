import unittest
from unittest.mock import patch
from core.conversation_manager import ConversationManager

class TestFollowUpQuestions(unittest.TestCase):

    def setUp(self):
        self.cm = ConversationManager()

    def test_follow_up_context_preservation(self):
        with patch.object(self.cm.provider_manager, "generate_response") as mock_gen:
            mock_gen.return_value = "Quantum computing uses qubits."
            self.cm.process_query("Explain quantum computing.")

            mock_gen.return_value = "Simpler: Qubits can be 0 and 1 at the same time."
            self.cm.process_query("Make that simpler.")

            # Second call should receive 3 messages: Q1, A1, Q2
            last_call_args = mock_gen.call_args[0][0]
            self.assertEqual(len(last_call_args), 3)
            self.assertEqual(last_call_args[0]["content"], "Explain quantum computing.")
            self.assertEqual(last_call_args[1]["content"], "Quantum computing uses qubits.")
            self.assertEqual(last_call_args[2]["content"], "Make that simpler.")

if __name__ == "__main__":
    unittest.main()
