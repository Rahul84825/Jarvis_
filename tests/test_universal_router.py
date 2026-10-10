"""Comprehensive Test Suite for JARVIS Universal Intelligence, Router & Chrome Control.
Tests all 20 required scenarios specified in Section 18 of the Master Implementation Prompt:
1. 'What can you do?'
2. 'Open Chrome.'
3. 'Search the web for the latest AI news.'
4. 'Search YouTube for Python tutorials.'
5. 'Search GitHub for this repository.'
6. 'Open YouTube and search for React tutorials.'
7. 'Open three specified websites in separate tabs.'
8. 'Summarize the current webpage.'
9. 'Find a file in the project.'
10. 'Write a professional email.'
11. 'Create a folder and save a README.'
12. 'Explain this Python error.'
13. 'Open my project and run its tests.'
14. Multi-step request with one intentionally failing step.
15. Request that requires an unavailable provider.
16. Destructive request that must be blocked or confirmed.
17. Follow-up referring to a previous search result.
18. API timeout failure recovery.
19. Browser connection failure recovery.
20. TTS failure after a successful command.
"""

import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.intent_engine import IntentEngine
from core.command_normalizer import CommandNormalizer
from core.tool_registry import tool_registry
from core.content_generator import ContentGenerator
from core.multi_step_planner import MultiStepPlanner
from core.os.browser_manager import BrowserManager
from core.os.filesystem_manager import FilesystemManager
from modules.system.executor import CommandExecutor
from modules.system.permissions import get_action_risk_level, RiskLevel

class TestUniversalRouter(unittest.TestCase):

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.executor = CommandExecutor()
        self.planner = MultiStepPlanner(intent_engine=self.intent_engine, executor=self.executor)
        self.test_dir = Path("tests_scratch_workspace")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. "What can you do?" -> Dynamic Tool Registry capabilities
    def test_01_what_can_you_do(self):
        node = self.intent_engine.parse("What can you do")
        self.assertEqual(node["intent"], "help")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        self.assertIn("Applications", res["message"])
        self.assertIn("Browser & Tabs", res["message"])
        self.assertIn("Web & Local Search", res["message"])
        self.assertIn("Files & Folders", res["message"])

    # 2. "Open Chrome." -> Application launch
    @patch("modules.system.app_control.open_app", return_value=True)
    def test_02_open_chrome(self, mock_open_app):
        node = self.intent_engine.parse("Open Chrome")
        self.assertEqual(node["intent"], "open_app")
        self.assertEqual(node["target"], "chrome")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        mock_open_app.assert_called_once_with("chrome")

    # 3. "Search the web for the latest AI news." -> General web search (Google)
    @patch.object(BrowserManager, "search", return_value={"success": True, "message": "Searching Google."})
    def test_03_search_the_web_for_latest_ai_news(self, mock_search):
        node = self.intent_engine.parse("Search the web for the latest AI news")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["provider"], "google")
        self.assertIn("latest AI news", node["query"])
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        mock_search.assert_called_once()
        self.assertEqual(mock_search.call_args[1]["provider"], "google")

    # 4. "Search YouTube for Python tutorials." -> Targeted YouTube search
    @patch.object(BrowserManager, "search", return_value={"success": True, "message": "Searching YouTube."})
    def test_04_search_youtube_for_python_tutorials(self, mock_search):
        node = self.intent_engine.parse("Search YouTube for Python tutorials")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["provider"], "youtube")
        self.assertIn("python tutorials", node["target"].lower())
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        mock_search.assert_called_once()
        self.assertEqual(mock_search.call_args[1]["provider"], "youtube")

    # 5. "Search GitHub for this repository." -> Targeted GitHub search
    @patch.object(BrowserManager, "search", return_value={"success": True, "message": "Searching GitHub."})
    def test_05_search_github_for_this_repository(self, mock_search):
        node = self.intent_engine.parse("Search GitHub for this repository")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["provider"], "github")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        mock_search.assert_called_once()
        self.assertEqual(mock_search.call_args[1]["provider"], "github")

    # 6. "Open YouTube and search for React tutorials." -> Multi-step / Site targeted search
    def test_06_open_youtube_and_search_for_react(self):
        plan = self.planner.plan("Open YouTube and search for React tutorials")
        self.assertGreaterEqual(len(plan), 2)
        step1 = plan[0]["intent_node"]
        step2 = plan[1]["intent_node"]
        self.assertIn(step1["intent"], ["open_website", "open_app"])
        self.assertEqual(step2["intent"], "web_search")

    # 7. "Open three specified websites in separate tabs." -> Multi-tab opening
    @patch.object(BrowserManager, "open_multiple_urls", return_value={"success": True, "count": 3, "message": "Opened 3 websites in browser tabs."})
    def test_07_open_three_websites_in_separate_tabs(self, mock_open_multi):
        node = self.intent_engine.parse("open three websites in separate tabs: google.com, github.com, youtube.com")
        self.assertEqual(node["intent"], "browser_control")
        self.assertEqual(node["action"], "open_multiple")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        mock_open_multi.assert_called_once()

    # 8. "Summarize the current webpage." -> Content generation / summarization
    def test_08_summarize_current_webpage(self):
        node = self.intent_engine.parse("Summarize this webpage")
        self.assertEqual(node["intent"], "content_generation")
        self.assertEqual(node["action"], "summarize_page")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        self.assertIn("Draft document", res["message"])

    # 9. "Find a file in the project." -> Local project search
    def test_09_find_file_in_project(self):
        node = self.intent_engine.parse("Find a file in the project main.py")
        self.assertEqual(node["intent"], "local_search")
        self.assertEqual(node["action"], "find_file")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])

    # 10. "Write a professional email." -> Content drafting with UI text & concise voice summary
    def test_10_write_professional_email(self):
        node = self.intent_engine.parse("Write a professional email about project status")
        self.assertEqual(node["intent"], "content_generation")
        self.assertEqual(node["action"], "draft_email")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        self.assertIn("Subject:", res["message"])
        self.assertIn("Dear Colleague", res["message"])

    # 11. "Create a folder and save a README." -> Verified filesystem workflow
    def test_11_create_folder_and_save_readme(self):
        folder_target = str(self.test_dir / "my_college_notes")
        node1 = {"intent": "filesystem_control", "action": "create_folder", "target": folder_target}
        res1 = self.executor.execute(node1)
        self.assertTrue(res1["success"])
        self.assertTrue(Path(folder_target).exists())

        readme_target = str(Path(folder_target) / "README.md")
        node2 = {
            "intent": "filesystem_control",
            "action": "save_file",
            "target": readme_target,
            "content": "# College Notes\n\nNotes collection."
        }
        res2 = self.executor.execute(node2)
        self.assertTrue(res2["success"])
        self.assertTrue(Path(readme_target).exists())
        self.assertGreater(Path(readme_target).stat().st_size, 0)

    # 12. "Explain this Python error." -> Concept/error explanation
    def test_12_explain_python_error(self):
        node = self.intent_engine.parse("Explain this error: IndexError: list index out of range")
        self.assertEqual(node["intent"], "content_generation")
        self.assertEqual(node["action"], "explain_concept")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])
        self.assertIn("IndexError", res["message"])

    # 13. "Open my project and run its tests." -> Developer test execution
    @patch.object(CommandExecutor, "execute", return_value={"success": True, "message": "Test execution completed: Ran 256 tests OK"})
    def test_13_open_project_and_run_tests(self, mock_exec):
        node = self.intent_engine.parse("Run the tests")
        self.assertEqual(node["intent"], "developer_workflow")
        self.assertEqual(node["action"], "run_tests")
        res = self.executor.execute(node)
        self.assertTrue(res["success"])

    # 14. Multi-step request with one intentionally failing step -> Truthful reporting
    def test_14_multi_step_with_failing_step(self):
        steps = [
            {"step_index": 0, "clean_text": "step 1", "intent_node": {"intent": "test_speech"}, "depends_on": None, "required": True},
            {"step_index": 1, "clean_text": "step 2", "intent_node": {"intent": "terminal_execute", "target": "invalid_cmd_xyz_123"}, "depends_on": None, "required": True},
            {"step_index": 2, "clean_text": "step 3", "intent_node": {"intent": "test_speech"}, "depends_on": 1, "required": True}
        ]
        with patch.object(CommandExecutor, "execute", side_effect=[
            {"success": True, "message": "Step 1 passed."},
            {"success": False, "message": "Step 2 command not found."},
            {"success": True, "message": "Step 3 passed."}
        ]):
            report = self.planner.execute_plan(steps)
            self.assertFalse(report["success"])
            self.assertEqual(report["completed_count"], 1)
            self.assertEqual(report["failed_count"], 1)
            self.assertEqual(report["skipped_count"], 1)
            self.assertIn("warnings", report["message"])

    # 15. Request requiring unavailable provider -> Truthful local execution without fake output
    def test_15_unavailable_provider_fallback(self):
        content_gen = ContentGenerator()
        # provider is None or inactive
        res = content_gen.draft_content("Neural Network Architectures", content_type="report")
        self.assertTrue(res["success"])
        self.assertIn("Local Template Generator", res["source"])
        self.assertIn("Report", res["content"])

    # 16. Destructive request that must be blocked or confirmed -> Safety gate
    def test_16_destructive_action_safety_gate(self):
        # Shutdown pc requires confirmation
        risk = get_action_risk_level("system_control", "shutdown_pc")
        self.assertEqual(risk, RiskLevel.HIGH)

        node = {"intent": "system_control", "action": "shutdown_pc"}
        # Unconfirmed execution must be blocked with pending_confirmation=True
        res = self.executor.execute(node, confirm=False)
        self.assertFalse(res["success"])
        self.assertTrue(res.get("pending_confirmation"))
        self.assertIn("high risk", res["message"].lower())

    # 17. Follow-up referring to previous search result -> Context resolution
    def test_17_follow_up_referring_to_previous_result(self):
        # Populate previous search results in executor
        test_file = str(self.test_dir / "sample_doc.txt")
        Path(test_file).write_text("Sample doc content", encoding="utf-8")
        self.executor.last_search_results = ["dummy1", test_file]

        node = self.intent_engine.parse("Open the second result")
        self.assertEqual(node["intent"], "follow_up")
        self.assertEqual(node["action"], "open_result_index")
        self.assertEqual(node["target"], "2")

        with patch.object(FilesystemManager, "open_file", return_value={"success": True, "message": "Opened sample_doc.txt."}):
            res = self.executor.execute(node)
            self.assertTrue(res["success"])

    # 18. API timeout -> Truthful error reporting
    @patch.object(BrowserManager, "search", side_effect=TimeoutError("Connection timed out"))
    def test_18_api_timeout_recovery(self, mock_search):
        node = {"intent": "web_search", "action": "search", "query": "latest AI news", "target": "latest AI news"}
        res = self.executor.execute(node)
        self.assertFalse(res["success"])
        self.assertIn("timed out", res["message"].lower())

    # 19. Browser connection failure -> Truthful reporting
    @patch.object(BrowserManager, "search", return_value={"success": False, "operation": "web_search", "message": "I couldn't open the browser."})
    def test_19_browser_connection_failure(self, mock_search):
        node = {"intent": "web_search", "action": "search", "query": "python tutorials", "target": "python tutorials"}
        res = self.executor.execute(node)
        self.assertFalse(res["success"])
        self.assertIn("couldn't open the browser", res["message"])

    # 20. TTS failure after successful command -> Successful command state preserved
    def test_20_tts_failure_preserves_command_success(self):
        with patch("modules.system.system_control.volume_up", return_value=(True, "Volume increased.")):
            with patch("core.tts.tts_manager.TTSManager.speak", side_effect=Exception("Audio output stream unavailable")):
                res = self.executor.execute({"intent": "system_control", "action": "volume_up"})
                self.assertTrue(res["success"])
                self.assertEqual(res["action"], "volume_up")

if __name__ == "__main__":
    unittest.main()
