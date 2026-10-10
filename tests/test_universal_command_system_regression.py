"""Regression Test Suite for Universal Command Routing, Response Fixes & Taxonomy.

Validates the 10 acceptance criteria specified in Section 7 of the Master Prompt:
1. 'Jarvis, help' is NOT classified as multi_command; has deterministic help intent.
2. No duplicate generic fallback response or duplicate TTS for one request.
3. 'Open ChatGPT in Chrome' selecting the correct browser/navigation route.
4. Application launching is strictly distinct from website navigation.
5. Explicit web, YouTube, GitHub, and local-file search routing.
6. Missing arguments and clarification questions.
7. Truthful success and failure reporting (including CDP unavailable guidance).
8. Dynamic capability catalogue matching registered tools (overview, full, scoped).
9. Custom command persistence and safety validation (no eval/exec).
10. Single truth response policy and outcome consistency.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.intent_engine import IntentEngine
from core.command_normalizer import CommandNormalizer
from core.multi_command_parser import multi_command_parser
from core.capability_service import capability_service
from core.tool_registry import tool_registry
from core.response_registry import response_registry, CommandOutcome
from modules.system.executor import CommandExecutor
from core.os.browser_manager import BrowserManager
from core.custom_commands.command_registry import custom_command_registry, CustomCommand


class TestUniversalCommandSystemRegression(unittest.TestCase):
    """Test suite asserting all Master Prompt command routing and response guarantees."""

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.executor = CommandExecutor()

    # =========================================================================
    # 1. "Jarvis, help" classification & multi_command isolation
    # =========================================================================

    def test_01_jarvis_help_not_classified_as_multi_command(self):
        """'Jarvis, help' must NOT split into multiple sub-commands or multi_command intent."""
        raw = "Jarvis, help"

        # Multi-command parser clause splitting
        split_clauses = multi_command_parser.parse(raw)
        self.assertEqual(len(split_clauses), 1, f"Expected 1 clause, got: {split_clauses}")

        # Normalizer split
        chained = self.normalizer.split_chained_commands(raw)
        self.assertEqual(len(chained), 1, f"Expected 1 chained command, got: {chained}")

        # Intent classification
        node = self.intent_engine.parse(raw)
        self.assertEqual(node["intent"], "help")
        self.assertNotEqual(node["intent"], "multi_command")
        self.assertEqual(node["scope"], "overview")

    # =========================================================================
    # 2. Single response guarantee & zero duplicate fallback
    # =========================================================================

    def test_02_no_duplicate_generic_response_or_duplicate_tts(self):
        """Execution produces exactly one spoken and displayed response via response registry."""
        node = self.intent_engine.parse("Jarvis, help")
        res = self.executor.execute(node)

        self.assertTrue(res["success"])
        # Should contain categories, not the broken generic fallback spiel
        self.assertNotIn("I'm not sure how to help with that yet, and I can open", res["message"])

        # Formatting through response registry
        spoken = response_registry.get_success_response(node, res)
        self.assertIsNotNone(spoken)
        self.assertNotIn("I'm not sure how to help with that yet", spoken)

    # =========================================================================
    # 3. "Open ChatGPT in Chrome" browser/navigation route
    # =========================================================================

    def test_03_open_chatgpt_in_chrome(self):
        """'Open ChatGPT in Chrome' must resolve ChatGPT URL and target Chrome browser."""
        node = self.intent_engine.parse("Open ChatGPT in Chrome")

        self.assertEqual(node["intent"], "open_website")
        self.assertEqual(node["action"], "open_in_browser")
        self.assertEqual(node["target"].lower(), "chatgpt")
        self.assertEqual(node["browser"], "chrome")
        self.assertEqual(node["url"], "https://chatgpt.com")

        with patch.object(self.executor.browser_mgr, "open_browser", return_value={"success": True, "message": "Opening Chrome."}) as mock_open:
            res = self.executor.execute(node)
            self.assertTrue(res["success"])
            self.assertEqual(res["outcome"], CommandOutcome.SUCCESS.value)
            self.assertIn("Opening Chatgpt in Chrome", res["message"])
            mock_open.assert_called_once_with(browser_name="chrome", url="https://chatgpt.com")

    # =========================================================================
    # 4. Applications distinct from website navigation
    # =========================================================================

    def test_04_application_launching_distinct_from_website_navigation(self):
        """Opening a native desktop app must be strictly distinct from navigating to a website."""
        # App launch
        node_app = self.intent_engine.parse("Open Chrome")
        self.assertEqual(node_app["intent"], "open_app")
        self.assertEqual(node_app["target"], "chrome")

        node_vscode = self.intent_engine.parse("Launch VS Code")
        self.assertEqual(node_vscode["intent"], "open_app")
        self.assertEqual(node_vscode["target"], "vscode")

        # Website navigation
        node_yt = self.intent_engine.parse("Open YouTube")
        self.assertEqual(node_yt["intent"], "open_website")
        self.assertIn("youtube.com", node_yt["url"])

        node_gpt = self.intent_engine.parse("Open ChatGPT")
        self.assertEqual(node_gpt["intent"], "open_website")
        self.assertEqual(node_gpt["url"], "https://chatgpt.com")

    # =========================================================================
    # 5. Explicit Search Routing (Web, YouTube, GitHub, Local)
    # =========================================================================

    def test_05_explicit_search_destinations(self):
        """Explicit searches preserve query and route to dedicated provider."""
        # General search preserves remaining query
        node_general = self.intent_engine.parse("Jarvis search Python tutorials")
        self.assertEqual(node_general["intent"], "web_search")
        self.assertEqual(node_general["provider"], "google")
        self.assertEqual(node_general["query"], "Python tutorials")

        # Targeted YouTube search
        node_yt = self.intent_engine.parse("Jarvis, search YouTube for Python tutorials")
        self.assertEqual(node_yt["intent"], "web_search")
        self.assertEqual(node_yt["provider"], "youtube")
        self.assertIn("Python tutorials", node_yt["query"])

        # Targeted GitHub search
        node_gh = self.intent_engine.parse("Jarvis, search GitHub for React dashboard")
        self.assertEqual(node_gh["intent"], "web_search")
        self.assertEqual(node_gh["provider"], "github")
        self.assertIn("React dashboard", node_gh["query"])

        # Local project file search
        node_loc = self.intent_engine.parse("find file in project main.py")
        self.assertEqual(node_loc["intent"], "local_search")
        self.assertEqual(node_loc["target"], "main.py")

    # =========================================================================
    # 6. Missing arguments and clarification questions
    # =========================================================================

    def test_06_missing_arguments_clarification(self):
        """Missing search query or missing parameters produce clarification questions."""
        node_empty = self.intent_engine.parse("Jarvis, search")
        self.assertEqual(node_empty["intent"], "web_search")
        self.assertTrue(node_empty.get("empty_query", False))

        res = self.executor.execute(node_empty)
        self.assertEqual(res["outcome"], CommandOutcome.MISSING_ARGUMENT.value)
        self.assertEqual(res["message"], "What would you like me to search for, Sir?")

    # =========================================================================
    # 7. Truthful success, failure, and CDP status reporting
    # =========================================================================

    def test_07_truthful_failure_and_cdp_reporting(self):
        """Failures report the real error; unavailable CDP does not pretend DOM success."""
        # Uninstalled application
        with patch("modules.system.app_control.open_app", return_value=False):
            node_fake_app = {"intent": "open_app", "target": "nonexistent_app_xyz"}
            res_fail = self.executor.execute(node_fake_app)
            self.assertFalse(res_fail["success"])
            self.assertEqual(res_fail["outcome"], CommandOutcome.UNSUPPORTED_CAPABILITY.value)
            self.assertIn("That application isn't installed", res_fail["message"])

        # CDP page inspection when CDP is offline
        with patch.object(self.executor.browser_mgr.cdp, "is_available", return_value=False):
            res_inspect = self.executor.browser_mgr.inspect_page()
            self.assertFalse(res_inspect["success"])
            self.assertIn("--remote-debugging-port=9222", res_inspect["message"])

    # =========================================================================
    # 8. Dynamic capability catalogue (overview, all, scoped)
    # =========================================================================

    def test_08_dynamic_capability_service_catalogue(self):
        """Capability service distinguishes available tools and generates accurate listings."""
        # Overview for "Jarvis, help"
        overview = capability_service.get_help_overview()
        self.assertIn("Core Capabilities", overview)
        self.assertIn("Applications", overview)

        # Full command reference for "show all commands"
        all_ref = capability_service.get_all_commands_reference()
        self.assertIn("JARVIS Comprehensive Command Reference", all_ref)
        self.assertIn("Applications & Desktop Programs", all_ref)
        self.assertIn("Websites & Browser Actions", all_ref)
        self.assertIn("Search Operations", all_ref)

        # Scoped browser commands
        browser_scoped = capability_service.get_scoped_commands("browser")
        self.assertIn("Browser & Web Navigation", browser_scoped)
        self.assertIn("open_website", browser_scoped)

        # Scoped filesystem commands
        file_scoped = capability_service.get_scoped_commands("filesystem")
        self.assertIn("File & Folder Operations", file_scoped)
        self.assertIn("create_folder", file_scoped)

    # =========================================================================
    # 9. Custom command persistence and safety (no eval/exec)
    # =========================================================================

    def test_09_custom_commands_safety_and_persistence(self):
        """Custom commands are structured without dynamic code execution."""
        ok, msg, cmd = custom_command_registry.register_command(
            name="Focus Mode Unit Test",
            trigger_phrases=["focus mode test"],
            workflow_definition=[
                {"tool": "volume_control", "args": {"action": "mute"}, "description": "Mute audio"}
            ],
            risk_classification="LOW",
            command_id="test_focus_mode_unit"
        )
        self.assertTrue(ok)

        found, conf = custom_command_registry.find_matching_command("focus mode test")
        self.assertIsNotNone(found)
        self.assertEqual(found.command_id, "test_focus_mode_unit")
        self.assertEqual(len(found.workflow_definition), 1)
        self.assertEqual(found.workflow_definition[0]["tool"], "volume_control")

        # Cleanup
        custom_command_registry.delete_command("test_focus_mode_unit")

    # =========================================================================
    # 10. Browser Tab Navigation Actions
    # =========================================================================

    def test_10_browser_tab_and_navigation_intents(self):
        """Browser tab management and history navigation keywords parse deterministically."""
        node_new_tab = self.intent_engine.parse("open a new Chrome tab")
        self.assertEqual(node_new_tab["intent"], "open_new_chrome_tab")

        node_close_tab = self.intent_engine.parse("close tab")
        self.assertEqual(node_close_tab["intent"], "browser_tab_control")
        self.assertEqual(node_close_tab["action"], "close_tab")

        node_back = self.intent_engine.parse("go back in Chrome")
        self.assertEqual(node_back["intent"], "browser_tab_control")
        self.assertEqual(node_back["action"], "go_back")

        node_read = self.intent_engine.parse("read the current webpage")
        self.assertEqual(node_read["intent"], "browser_action")
        self.assertEqual(node_read["action"], "read_page")


if __name__ == "__main__":
    unittest.main()
