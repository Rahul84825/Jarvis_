import unittest
import time
from unittest.mock import patch
from core.conversation_manager import ConversationManager

class TestConversationManager(unittest.TestCase):

    def setUp(self):
        self.cm = ConversationManager(max_turns=3, session_timeout=0.5)

    def test_session_history_trimming(self):
        with patch.object(self.cm.provider_manager, "generate_response", return_value="Sample Answer"):
            for i in range(5):
                self.cm.process_query(f"Question {i}")
            # Max turns = 3 -> max 6 messages (3 turns)
            self.assertLessEqual(len(self.cm.history), 6)

    def test_session_timeout(self):
        with patch.object(self.cm.provider_manager, "generate_response", return_value="Sample Answer"):
            self.cm.process_query("Question 1")
            self.assertEqual(len(self.cm.history), 2)
            time.sleep(0.6)  # Wait past session_timeout = 0.5s
            self.cm.process_query("Question 2")
            # History reset, only contains 1 turn (2 messages)
            self.assertEqual(len(self.cm.history), 2)

    def test_clear_session(self):
        self.cm.history = [{"role": "user", "content": "hi"}]
        self.cm.clear_session()
        self.assertEqual(len(self.cm.history), 0)

if __name__ == "__main__":
    unittest.main()
