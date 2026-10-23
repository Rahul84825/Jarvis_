"""Comprehensive Test Suite for JARVIS Verified Learning, Persistent Memory,
Procedure Reusability, Outcome Verification, and Correction Handling.
"""

import os
import sys
import time
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from memory.persistent_memory import PersistentMemory, sanitize_text, sanitize_data
from core.learning.verification_engine import VerificationEngine, OutcomeLevel
from core.learning.procedure_learner import ProcedureLearner
from core.learning.correction_handler import CorrectionHandler
from core.intent_engine import IntentEngine
from core.conversation_manager import ConversationManager


class TestVerifiedLearningAndMemory(unittest.TestCase):
    """Test suite validating all Phases 1-8 of the Verified Learning Architecture."""

    def setUp(self):
        # Create a temporary database for test isolation
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        self.memory = PersistentMemory(db_path=self.temp_db_path)
        self.ver_engine = VerificationEngine()
        self.proc_learner = ProcedureLearner(memory_backend=self.memory)
        self.correction_handler = CorrectionHandler(memory_backend=self.memory)

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    # =========================================================================
    # 1. DATABASE SCHEMA MIGRATION & PRESERVATION
    # =========================================================================
    def test_schema_migration_and_data_preservation(self):
        """Verifies backward-compatible schema migration and table creation."""
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            "schema_migrations", "execution_experiences", "learned_procedures",
            "user_learned_preferences", "verified_cache", "memories", "user_profile"
        ]
        for tbl in expected_tables:
            self.assertIn(tbl, tables, f"Expected table '{tbl}' was not created.")

        # Check migration version recorded
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version, description FROM schema_migrations WHERE version=1")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 1)
            self.assertIn("execution_experiences", row[1])

        # Test data preservation: re-initializing on existing DB preserves rows
        self.memory.set_user_learned_preference("app_alias", "test_app", "real_app")
        # Instantiate second instance on same path (restart simulation)
        memory_restart = PersistentMemory(db_path=self.temp_db_path)
        val = memory_restart.get_user_learned_preference("app_alias", "test_app")
        self.assertEqual(val, "real_app", "Data was lost across database reload.")

    # =========================================================================
    # 2. CREDENTIAL & SECRET SANITIZATION
    # =========================================================================
    def test_credential_and_secret_sanitization(self):
        """Ensures passwords, tokens, API keys, and secret cookies are redacted prior to persistence."""
        dirty_text = "My api_key=nvapi-abc123XYZ45678901234567 and password = SuperSecretPass123! token: ghp_1234567890abcdef1234567890abcdef123456"
        cleaned = sanitize_text(dirty_text)
        self.assertNotIn("nvapi-abc123XYZ45678901234567", cleaned)
        self.assertNotIn("SuperSecretPass123!", cleaned)
        self.assertNotIn("ghp_1234567890abcdef1234567890abcdef123456", cleaned)
        self.assertIn("[REDACTED_KEY]", cleaned)
        self.assertIn("[REDACTED_PASSWORD]", cleaned)

        # Test dictionary recursive sanitization
        dirty_dict = {
            "user": "Rahul",
            "token": "sk-123456789012345678901234567890123456789012345678",
            "nested": {
                "password": "HiddenSecretPassword!",
                "safe_field": "public_data"
            }
        }
        cleaned_dict = sanitize_data(dirty_dict)
        self.assertEqual(cleaned_dict["token"], "[REDACTED_OPENAI_KEY]")
        self.assertEqual(cleaned_dict["nested"]["password"], "[REDACTED_PASSWORD]")
        self.assertEqual(cleaned_dict["nested"]["safe_field"], "public_data")

    # =========================================================================
    # 3. STRUCTURED EXPERIENCE RECORDING & RETRIEVAL
    # =========================================================================
    def test_structured_experience_recording(self):
        """Verifies recording and retrieving rich structured experiences."""
        row_id = self.memory.record_execution_experience(
            user_request="Launch Discord and Spotify",
            normalized_intent="workspace.launch",
            tool_or_procedure="launch_workspace",
            execution_parameters={"workspace": "gaming", "apps": ["discord", "spotify"]},
            execution_outcome=OutcomeLevel.INDEPENDENTLY_VERIFIED.value,
            verification_evidence={"discord_running": True, "spotify_running": True},
            observed_failure=None,
            confidence=0.95
        )
        self.assertGreater(row_id, 0)

        # Retrieve experiences
        experiences = self.memory.get_execution_experiences(limit=5, intent="workspace.launch")
        self.assertEqual(len(experiences), 1)
        exp = experiences[0]
        self.assertEqual(exp["user_request"], "Launch Discord and Spotify")
        self.assertEqual(exp["execution_outcome"], OutcomeLevel.INDEPENDENTLY_VERIFIED.value)
        self.assertEqual(exp["execution_parameters"]["workspace"], "gaming")
        self.assertTrue(exp["verification_evidence"]["discord_running"])

    # =========================================================================
    # 4. PROCEDURE LEARNING, MATCHING & EXECUTION
    # =========================================================================
    def test_procedure_learning_and_trigger_matching(self):
        """Verifies learning a reusable procedure, normalizing triggers, and matching."""
        steps = [
            {"tool": "open_app", "parameters": {"target": "notepad"}, "description": "Open Notepad"},
            {"tool": "open_app", "parameters": {"target": "calc"}, "description": "Open Calculator"}
        ]
        saved = self.proc_learner.learn_procedure(
            name="notes_and_math",
            intent="productivity_workflow",
            user_request="Prepare notes and calculator",
            steps=steps,
            source="test_learning"
        )
        self.assertTrue(saved)

        # Match exact trigger
        matched = self.proc_learner.match_procedure("Prepare notes and calculator")
        self.assertIsNotNone(matched)
        self.assertEqual(matched["name"], "notes_and_math")
        self.assertEqual(len(matched["steps"]), 2)

        # Match normalized trigger variation
        matched_var = self.proc_learner.match_procedure("prepare notes and calculator please")
        self.assertIsNotNone(matched_var)
        self.assertEqual(matched_var["name"], "notes_and_math")

    # =========================================================================
    # 5. PREREQUISITE VALIDATION & STALE PROCEDURE INVALIDATION
    # =========================================================================
    def test_prerequisite_validation_stale_invalidation(self):
        """Verifies that a procedure with unmet prerequisites (e.g. missing app) is rejected."""
        steps = [{"tool": "open_app", "parameters": {"target": "nonexistent_custom_binary_12345"}}]
        prereqs = {
            "required_apps": ["nonexistent_custom_binary_12345"],
            "required_paths": ["C:\\nonexistent_invalid_path_xyz_98765"]
        }
        self.proc_learner.learn_procedure(
            name="stale_custom_procedure",
            intent="custom_workflow",
            user_request="Run custom nonexistent binary",
            steps=steps,
            prerequisites=prereqs
        )

        # Matching must check prerequisites and reject because binary and path do not exist
        matched = self.proc_learner.match_procedure("Run custom nonexistent binary")
        self.assertIsNone(matched, "Stale procedure with missing prerequisites was incorrectly matched!")

    # =========================================================================
    # 6. DYNAMIC CONFIDENCE & RELIABILITY UPDATES
    # =========================================================================
    def test_dynamic_confidence_and_reliability_updates(self):
        """Verifies dynamic reward on success (+0.05) and penalty on failure (-0.25), deactivating below 0.40."""
        self.memory.save_learned_procedure(
            procedure_name="test_reliability_proc",
            intent="test_intent",
            trigger_patterns=["trigger alpha"],
            steps=[{"tool": "test_tool"}],
            confidence=0.50
        )

        # 1. Success update: 0.50 -> 0.55
        self.memory.update_procedure_reliability("test_reliability_proc", success=True)
        p1 = self.memory.get_learned_procedure("test_reliability_proc")
        self.assertAlmostEqual(p1["confidence"], 0.55, places=2)
        self.assertEqual(p1["success_count"], 1)
        self.assertEqual(p1["is_active"], 1)

        # 2. Failure update: 0.55 -> 0.30 (below 0.40 -> deactivated)
        self.memory.update_procedure_reliability("test_reliability_proc", success=False)
        p2 = self.memory.get_learned_procedure("test_reliability_proc")
        self.assertAlmostEqual(p2["confidence"], 0.30, places=2)
        self.assertEqual(p2["failure_count"], 1)
        self.assertEqual(p2["is_active"], 0, "Procedure should be deactivated when confidence < 0.40")

        # Inactive procedures must not be returned by list_learned_procedures(active_only=True)
        active_list = self.memory.list_learned_procedures(active_only=True)
        self.assertNotIn("test_reliability_proc", [p["procedure_name"] for p in active_list])

    # =========================================================================
    # 7. USER CORRECTIONS: APP ALIAS & BROWSER PREFERENCE
    # =========================================================================
    def test_user_correction_app_alias(self):
        """User: 'Open Brave, not Chrome' -> learns alias and browser preference."""
        res = self.correction_handler.handle_correction("Open Brave, not Chrome")
        self.assertTrue(res["success"])
        self.assertEqual(res["correction_type"], "contrast_preference")
        self.assertEqual(res["intended"], "brave")
        self.assertEqual(res["actionable_command"], "open brave")

        # Verify persistent memory has the learned alias and preference
        alias = self.memory.get_user_learned_preference("app_alias", "chrome")
        self.assertEqual(alias, "brave")
        browser_pref = self.memory.get_user_learned_preference("browser_preference", "default_browser")
        self.assertEqual(browser_pref, "brave")

        # Verify IntentEngine respects the learned alias
        intent_engine = IntentEngine()
        with patch("core.intent_engine.persistent_memory", self.memory):
            resolved = intent_engine.resolve_app_name("chrome")
            self.assertEqual(resolved, "brave", "IntentEngine failed to apply learned app alias.")

    # =========================================================================
    # 8. USER CORRECTIONS: FOLDER / PATH CORRECTION
    # =========================================================================
    def test_user_correction_folder_mapping(self):
        """User: 'That is not the folder I meant. Use Projects' -> learns path mapping."""
        res = self.correction_handler.handle_correction("That is not the folder I meant. Use Projects")
        self.assertTrue(res["success"])
        self.assertEqual(res["correction_type"], "folder_correction")
        self.assertEqual(res["intended"], "projects")
        self.assertEqual(res["actionable_command"].lower(), "open folder projects")

        # Verify path mapping learned in persistent memory
        mapping = self.memory.get_user_learned_preference("path_mapping", "folder")
        self.assertEqual(mapping.lower(), "projects")

    # =========================================================================
    # 9. USER CORRECTIONS: METHOD FAILURE CORRECTION
    # =========================================================================
    def test_user_correction_method_failure(self):
        """User: 'This method failed. Use the other supported method' -> records failure."""
        # Setup an active procedure
        self.memory.save_learned_procedure(
            procedure_name="active_failing_proc",
            intent="test",
            trigger_patterns=["run test"],
            steps=[{"tool": "fail_tool"}],
            confidence=0.8
        )
        res = self.correction_handler.handle_correction(
            "This method failed. Use the other supported method",
            context={"last_procedure": "active_failing_proc"}
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["correction_type"], "method_failure")

        # Verify procedure confidence was penalized
        proc = self.memory.get_learned_procedure("active_failing_proc")
        self.assertLess(proc["confidence"], 0.8)

    # =========================================================================
    # 10. VERIFIED REASONING CACHE & DYNAMIC QUERY BYPASS
    # =========================================================================
    def test_verified_reasoning_cache_and_dynamic_bypass(self):
        """Static factual queries are cached; dynamic/temporal queries are NEVER cached."""
        # 1. Static factual query caching
        static_q = "What is the capital of Australia?"
        cached_saved = self.memory.set_cached_query(static_q, "The capital of Australia is Canberra.", source_provider="Nemotron")
        self.assertTrue(cached_saved)

        cached_res = self.memory.get_cached_query(static_q)
        self.assertIsNotNone(cached_res)
        self.assertEqual(cached_res["text"], "The capital of Australia is Canberra.")
        self.assertTrue(cached_res["cached"])

        # 2. Dynamic queries must NOT be cached or retrieved from cache
        dynamic_queries = [
            "What time is it right now?",
            "What is today's date?",
            "What is the current weather forecast?",
            "Show running processes",
            "What is my battery level?",
            "List open tabs"
        ]
        for dq in dynamic_queries:
            # Setting dynamic query to cache must be rejected
            saved = self.memory.set_cached_query(dq, "Dynamic answer")
            self.assertFalse(saved, f"Dynamic query '{dq}' was improperly allowed into cache!")
            # Retrieving dynamic query must return None
            val = self.memory.get_cached_query(dq)
            self.assertIsNone(val, f"Dynamic query '{dq}' was returned from cache!")

    # =========================================================================
    # 11. VERIFICATION ENGINE & REAL-WORLD PROBES
    # =========================================================================
    def test_verification_engine_outcome_levels(self):
        """Verifies independent classification into OutcomeLevels."""
        # 1. File verification: create temp file and verify
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"Hello JARVIS verified learning")
            tf_path = tf.name

        try:
            res_file = self.ver_engine.verify_action_outcome(
                "write_file",
                {"path": tf_path},
                {"success": True, "message": f"Wrote file {tf_path}"}
            )
            self.assertEqual(res_file["outcome"], OutcomeLevel.INDEPENDENTLY_VERIFIED.value)
            self.assertTrue(res_file["verified"])
            self.assertGreater(res_file["evidence"]["file_size_bytes"], 0)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

        # 2. Non-existent file verification: should fail verification probe
        res_nofile = self.ver_engine.verify_action_outcome(
            "write_file",
            {"path": "C:\\nonexistent_invalid_path_abc123.txt"},
            {"success": True, "message": "Reported success"}
        )
        self.assertEqual(res_nofile["outcome"], OutcomeLevel.FAILED.value)
        self.assertFalse(res_nofile["verified"])

        # 3. Explicit tool failure
        res_fail = self.ver_engine.verify_action_outcome(
            "open_app",
            {"target": "unknown_app"},
            {"success": False, "message": "Application executable not found."}
        )
        self.assertEqual(res_fail["outcome"], OutcomeLevel.FAILED.value)

        # 4. Generic tool without independent probe -> COMPLETED with limitation
        res_generic = self.ver_engine.verify_action_outcome(
            "custom_tool_generic",
            {"param": 1},
            {"success": True, "message": "Custom tool executed"}
        )
        self.assertEqual(res_generic["outcome"], OutcomeLevel.COMPLETED.value)
        self.assertIn("self_reported", res_generic["evidence"]["check_type"])
        self.assertIn("independent_verification_unavailable", res_generic["evidence"].get("limitation", ""))

    # =========================================================================
    # 12. END-TO-END CONVERSATION MANAGER CACHING & CORRECTION
    # =========================================================================
    def test_conversation_manager_caching_and_correction(self):
        """Verifies ConversationManager utilizes cache to skip LLM, and learns from correction."""
        conv_mgr = ConversationManager(max_turns=5)
        # Patch persistent_memory to use test instance
        with patch("core.conversation_manager.persistent_memory", self.memory), \
             patch("core.learning.correction_handler.correction_handler.memory", self.memory):
            # 1. First populate cache with static factual question
            self.memory.set_cached_query("Who wrote Hamlet?", "William Shakespeare wrote Hamlet.", source_provider="Nemotron")

            # 2. process_query should hit cache and NOT invoke LLM/Nemotron
            with patch.object(conv_mgr.agent, "reason_and_execute") as mock_agent:
                res = conv_mgr.process_query("Who wrote Hamlet?")
                self.assertIn("William Shakespeare", res["text"])
                self.assertIn("Verified Cache", res.get("source", ""))
                mock_agent.assert_not_called()

            # 3. Correction through conversation manager
            corrected_cmd = conv_mgr.apply_correction("Open Brave, not Chrome")
            self.assertEqual(corrected_cmd, "open brave")
            # Preference learned
            learned_alias = self.memory.get_user_learned_preference("app_alias", "chrome")
            self.assertEqual(learned_alias, "brave")


if __name__ == "__main__":
    unittest.main()
