import os
import shutil
import tempfile
import unittest
from pathlib import Path

from memory.conversation_persistence import ConversationPersistence
from memory.session_memory import SessionMemory

class TestConversationPersistence(unittest.TestCase):
    """Test suite for persistent SQLite conversation memory, secret redaction,
    privacy handling, migration safety, and reload across application restarts.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "test_conversations.db")
        self.persistence = ConversationPersistence(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_retrieve_turns(self):
        """Verifies that conversation turns are persisted and retrieved correctly."""
        success = self.persistence.save_turn(
            user_text="What is the weather today?",
            assistant_text="It is clear and 22 degrees.",
            session_id="session_1"
        )
        self.assertTrue(success)

        recent = self.persistence.get_recent_turns(limit=5, session_id="session_1")
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["role"], "user")
        self.assertEqual(recent[0]["content"], "What is the weather today?")
        self.assertEqual(recent[1]["role"], "assistant")
        self.assertEqual(recent[1]["content"], "It is clear and 22 degrees.")

    def test_persistence_across_restarts(self):
        """Verifies that SessionMemory reloads conversation turns from database across restarts."""
        mem1 = SessionMemory(max_turns=10, db_path=self.db_path)
        mem1.add_interaction("Remember my favorite editor is VS Code", "Understood, noted.")
        mem1.add_interaction("What did I just say?", "You mentioned your favorite editor is VS Code.")

        # Simulate application restart with a new SessionMemory instance pointing to same DB
        mem2 = SessionMemory(max_turns=10, db_path=self.db_path)
        mem2.load_from_persistence()
        self.assertEqual(len(mem2.history), 2)
        self.assertEqual(mem2.history[0]["user"], "Remember my favorite editor is VS Code")
        self.assertEqual(mem2.history[1]["assistant"], "You mentioned your favorite editor is VS Code.")

    def test_secret_redaction_before_persistence(self):
        """Verifies that API keys, passwords, and tokens are scrubbed before saving to disk."""
        secret_user = "My OpenAI key is sk-1234567890abcdef123456 and password: SuperSecretPass123"
        secret_asst = "Logged in using Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

        self.persistence.save_turn(secret_user, secret_asst, session_id="sec_test")
        recent = self.persistence.get_recent_turns(limit=5, session_id="sec_test")

        user_content = recent[0]["content"]
        asst_content = recent[1]["content"]

        self.assertNotIn("sk-1234567890abcdef123456", user_content)
        self.assertIn("[REDACTED_OPENAI_KEY]", user_content)
        self.assertNotIn("SuperSecretPass123", user_content)
        self.assertIn("[REDACTED_PASSWORD]", user_content)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", asst_content)

    def test_search_relevant_history(self):
        """Verifies searching past history returns relevant exchanges without whole DB dump."""
        self.persistence.save_turn("How do I configure Docker?", "Use docker-compose.yml to define services.")
        self.persistence.save_turn("What is the capital of France?", "The capital of France is Paris.")
        self.persistence.save_turn("How to restart Docker daemon?", "Run sudo systemctl restart docker.")

        matches = self.persistence.search_relevant_history("Docker", limit=5)
        self.assertTrue(len(matches) >= 2)
        # Verify Paris is not in the Docker results
        for m in matches:
            self.assertNotIn("Paris", m["content"])

    def test_privacy_mode_disabling_persistence(self):
        """Verifies that persistent storage can be disabled via environment setting."""
        os.environ["JARVIS_PERSISTENT_MEMORY"] = "false"
        try:
            pers = ConversationPersistence(db_path=self.db_path)
            self.assertFalse(pers.is_enabled())
            saved = pers.save_turn("Secret thought", "Acknowledged")
            self.assertFalse(saved)
        finally:
            del os.environ["JARVIS_PERSISTENT_MEMORY"]

    def test_corrupt_database_safe_recovery(self):
        """Verifies that a corrupt database file is backed up and safely recovered without crashing."""
        # Write random binary garbage to the database file
        with open(self.db_path, "wb") as f:
            f.write(b"CORRUPTED_GARBAGE_BYTES_NOT_A_SQLITE_FILE")

        # Instantiating ConversationPersistence should detect corruption, recover, and initialize cleanly
        recovered_pers = ConversationPersistence(db_path=self.db_path)
        self.assertTrue(Path(self.db_path).exists())
        # Should be able to save and query normally
        saved = recovered_pers.save_turn("Hello after recovery", "Systems operational.")
        self.assertTrue(saved)
        recent = recovered_pers.get_recent_turns(limit=5)
        self.assertEqual(len(recent), 2)

    def test_context_summary_generation(self):
        """Verifies formatted summary output for compact LLM context injection."""
        self.persistence.save_turn("Hello", "Hello Sir.")
        self.persistence.save_turn("What is 2+2?", "2+2 is 4.")
        summary = self.persistence.get_context_summary(max_turns=2)
        self.assertIn("Relevant previous conversation context:", summary)
        self.assertIn("User: What is 2+2?", summary)
        self.assertIn("Jarvis: 2+2 is 4.", summary)

if __name__ == "__main__":
    unittest.main()
