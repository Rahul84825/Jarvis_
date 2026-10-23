"""Comprehensive Acceptance Tests for JARVIS Phase 8:
Universal Intent-Based Browser, Website Navigation & Search Automation.
Covers all 15 required acceptance criteria using isolated unit tests and mocked browser sessions.
"""

import unittest
from unittest.mock import patch, MagicMock

from core.os.browser_intent import BrowserIntentParser, BrowserIntent, BrowserActionType, SearchScope, TabPreference
from core.os.website_adapters import website_adapter_registry, GenericWebsiteAdapter, HiAnimeAdapter, YouTubeAdapter
from core.os.browser_session import BrowserSessionManager, BrowserSessionState
from core.os.browser_automation import BrowserAutomationEngine, CandidateInputField
from core.intent_engine import IntentEngine
from modules.system.executor import CommandExecutor


class TestBrowserIntentAutomation(unittest.TestCase):
    """Systematic test suite validating all 15 Phase 8 criteria."""

    def setUp(self):
        self.parser = BrowserIntentParser()
        self.session_mgr = BrowserSessionManager()
        self.automation_engine = BrowserAutomationEngine()
        self.intent_engine = IntentEngine()

    # -------------------------------------------------------------------------
    # Criterion 1: Explicit URL opens requested domain rather than search engine
    # -------------------------------------------------------------------------
    def test_1_explicit_url_opens_requested_domain_not_search_engine(self):
        """Explicit URL commands must navigate to the domain and never convert to a web search."""
        intent = self.parser.parse("Open hianime.at on Chrome.")
        self.assertEqual(intent.action_type, BrowserActionType.OPEN_URL)
        self.assertEqual(intent.target_browser, "chrome")
        self.assertEqual(intent.url, "https://hianime.at")
        self.assertEqual(intent.domain, "hianime.at")
        self.assertEqual(intent.search_query, "")

        # Verify execution does not perform a search
        with patch.object(self.automation_engine.browser_mgr, "open_browser", return_value={"success": True}) as mock_open:
            with patch.object(self.automation_engine, "_verify_navigation", return_value=(True, "https://hianime.at")):
                res = self.automation_engine.execute_intent(intent)
                self.assertTrue(res["success"])
                self.assertEqual(res["action"], "open_url")
                mock_open.assert_called_once_with(browser_name="chrome", url="https://hianime.at")

    # -------------------------------------------------------------------------
    # Criterion 2: Named website search targets that site's search interface
    # -------------------------------------------------------------------------
    def test_2_named_website_search_targets_site_search_interface(self):
        """Website-specific search commands must target the named site and query."""
        # Test 2A: HiAnime
        intent_hianime = self.parser.parse("Search for Naruto on HiAnime.")
        self.assertEqual(intent_hianime.action_type, BrowserActionType.SEARCH_WEBSITE)
        self.assertEqual(intent_hianime.site_name, "hianime")
        self.assertEqual(intent_hianime.search_query, "naruto")

        with patch.object(self.automation_engine.browser_mgr, "open_browser", return_value={"success": True}) as mock_open:
            with patch.object(self.automation_engine, "_verify_navigation", return_value=(True, "https://hianime.to/search?keyword=naruto")):
                res = self.automation_engine.execute_intent(intent_hianime)
                self.assertTrue(res["success"])
                self.assertIn("naruto", res["url"].lower())
                self.assertIn("hianime", res["url"].lower())

        # Test 2B: YouTube
        intent_yt = self.parser.parse("Search YouTube for Valorant highlights.")
        self.assertEqual(intent_yt.action_type, BrowserActionType.SEARCH_WEBSITE)
        self.assertEqual(intent_yt.site_name, "youtube")
        self.assertEqual(intent_yt.search_query, "valorant highlights")

    # -------------------------------------------------------------------------
    # Criterion 3: General web search uses configured search engine
    # -------------------------------------------------------------------------
    def test_3_general_web_search_uses_configured_engine(self):
        """Requesting a general web search uses the configured search engine."""
        intent = self.parser.parse("Search the web for python async tutorials.")
        self.assertEqual(intent.action_type, BrowserActionType.SEARCH_WEB)
        self.assertEqual(intent.search_scope, SearchScope.WEB_SEARCH)
        self.assertEqual(intent.search_query, "python async tutorials")

        with patch.object(self.automation_engine.browser_mgr, "search", return_value={"success": True, "message": "Search launched"}) as mock_search:
            res = self.automation_engine.execute_intent(intent)
            self.assertTrue(res["success"])
            mock_search.assert_called_once_with(query="python async tutorials", provider="google", browser_name="chrome")

    # -------------------------------------------------------------------------
    # Criterion 4: Opening a browser does not trigger an unintended search
    # -------------------------------------------------------------------------
    def test_4_opening_browser_does_not_trigger_unintended_search(self):
        """Commands like 'Open Chrome' should launch or focus Chrome, not search."""
        intent = self.parser.parse("Open Chrome.")
        self.assertEqual(intent.action_type, BrowserActionType.OPEN_BROWSER)
        self.assertEqual(intent.target_browser, "chrome")
        self.assertEqual(intent.search_query, "")
        self.assertIsNone(intent.url)

        with patch.object(self.automation_engine.browser_mgr, "open_browser", return_value={"success": True}) as mock_open:
            res = self.automation_engine.execute_intent(intent)
            self.assertTrue(res["success"])
            self.assertEqual(res["action"], "open_browser")
            mock_open.assert_called_once_with(browser_name="chrome", url=None)

    # -------------------------------------------------------------------------
    # Criterion 5: Current-tab request reuses the correct tab
    # -------------------------------------------------------------------------
    def test_5_current_tab_request_reuses_correct_tab(self):
        """'Search for this anime on the website already open' reuses current tab context."""
        context = {
            "active_url": "https://hianime.to/watch/naruto-20",
            "active_site": "hianime",
            "last_site": "hianime"
        }
        intent = self.parser.parse("Search for this anime on the website already open.", session_context=context)
        self.assertEqual(intent.action_type, BrowserActionType.SEARCH_WEBSITE)
        self.assertEqual(intent.site_name, "hianime")
        self.assertEqual(intent.tab_preference, TabPreference.CURRENT_TAB)

    # -------------------------------------------------------------------------
    # Criterion 6: New-tab request opens a new tab
    # -------------------------------------------------------------------------
    def test_6_new_tab_request_opens_new_tab(self):
        """Commands specifying a new tab must set TabPreference.NEW_TAB."""
        intent = self.parser.parse("Open hianime.at in a new tab.")
        self.assertEqual(intent.action_type, BrowserActionType.OPEN_URL)
        self.assertEqual(intent.tab_preference, TabPreference.NEW_TAB)

        # Execution via CDP creates a new tab
        with patch.object(self.automation_engine.cdp, "is_available", return_value=True), \
             patch.object(self.automation_engine.cdp, "new_tab", return_value={"id": "tab123"}) as mock_new_tab:
            res = self.automation_engine.execute_intent(intent)
            self.assertTrue(res["success"])
            self.assertEqual(res["action"], "open_new_tab")
            mock_new_tab.assert_called_once_with(url="https://hianime.at")

    # -------------------------------------------------------------------------
    # Criterion 7: Multiple plausible input fields trigger clarification
    # -------------------------------------------------------------------------
    def test_7_multiple_plausible_input_fields_trigger_clarification(self):
        """When multiple search/filter inputs are plausible, ask the user to clarify."""
        c1 = CandidateInputField(
            element_id="global-search",
            selector="input#global-search",
            name="q",
            placeholder="Search anime",
            field_purpose="search_box",
            score=45.0
        )
        c2 = CandidateInputField(
            element_id="genre-filter",
            selector="input#genre-filter",
            name="filter",
            placeholder="Filter list",
            field_purpose="filter",
            score=42.0
        )

        with patch.object(self.automation_engine, "_discover_search_fields", return_value=[c1, c2]):
            intent = BrowserIntent(
                action_type=BrowserActionType.SEARCH_WEBSITE,
                site_name="example_site",
                search_query="action"
            )
            res = self.automation_engine._handle_search_website(intent)
            self.assertTrue(res.get("requires_clarification"))
            self.assertIn("website search box and the page's filter field", res["message"])

    # -------------------------------------------------------------------------
    # Criterion 8: No suitable input field triggers a safe fallback
    # -------------------------------------------------------------------------
    def test_8_no_suitable_input_field_triggers_safe_fallback(self):
        """When no suitable DOM input exists, fallback safely without typing into random fields."""
        with patch.object(self.automation_engine, "_discover_search_fields", return_value=[]), \
             patch("core.os.website_adapters.GenericWebsiteAdapter.build_search_url", return_value=None), \
             patch.object(self.automation_engine.browser_mgr, "open_browser", return_value={"success": True}):
            intent = BrowserIntent(
                action_type=BrowserActionType.SEARCH_WEBSITE,
                site_name="somewebsite",
                url="https://somewebsite.com",
                search_query="test query"
            )
            res = self.automation_engine._handle_search_website(intent)
            self.assertTrue(res["success"])
            self.assertEqual(res["action"], "search_website_fallback")

    # -------------------------------------------------------------------------
    # Criterion 9: Failed or redirected navigation is detected
    # -------------------------------------------------------------------------
    def test_9_failed_or_redirected_navigation_is_detected(self):
        """Navigation verification returns unverified when page fails to load expected domain."""
        intent = BrowserIntent(
            action_type=BrowserActionType.OPEN_URL,
            url="https://unreachable-domain-12345.com",
            site_name="unreachable"
        )
        with patch.object(self.automation_engine.browser_mgr, "open_browser", return_value={"success": True}):
            with patch.object(self.automation_engine, "_verify_navigation", return_value=(False, None)):
                res = self.automation_engine.execute_intent(intent)
                self.assertFalse(res["verified"])

    # -------------------------------------------------------------------------
    # Criterion 10: Speech-recognition ambiguity in a domain triggers clarification
    # -------------------------------------------------------------------------
    def test_10_speech_recognition_ambiguity_in_domain_triggers_clarification(self):
        """Ambiguous domain spoken inputs trigger clarification rather than guessing."""
        intent = self.parser.parse("Open hianime dot")
        self.assertEqual(intent.action_type, BrowserActionType.CLARIFICATION_NEEDED)
        self.assertIn("Which website extension did you mean", intent.clarification_prompt)

    # -------------------------------------------------------------------------
    # Criterion 11: Follow-up queries preserve the correct website context
    # -------------------------------------------------------------------------
    def test_11_follow_up_queries_preserve_correct_website_context(self):
        """'Now search for One Piece' reuses the remembered website from the previous turn."""
        session_context = {
            "last_site": "hianime",
            "last_url": "https://hianime.to",
            "last_domain": "hianime.to"
        }
        intent = self.parser.parse("Now search for One Piece.", session_context=session_context)
        self.assertEqual(intent.action_type, BrowserActionType.SEARCH_WEBSITE)
        self.assertEqual(intent.site_name, "hianime")
        self.assertEqual(intent.url, "https://hianime.to")
        self.assertEqual(intent.search_query, "one piece")

    # -------------------------------------------------------------------------
    # Criterion 12: Browser switching and cancellation are handled safely
    # -------------------------------------------------------------------------
    def test_12_browser_switching_and_cancellation_are_handled_safely(self):
        """'Stop' cancels active operations; explicit browser targeting is honored."""
        # Cancellation
        stop_intent = self.parser.parse("Stop.")
        self.assertEqual(stop_intent.action_type, BrowserActionType.BROWSER_CONTROL)
        self.assertEqual(stop_intent.metadata.get("control_action"), "stop")
        res_stop = self.automation_engine.execute_intent(stop_intent)
        self.assertTrue(res_stop["cancelled"])

        # Browser targeting
        brave_intent = self.parser.parse("Open hianime.at on Brave.")
        self.assertEqual(brave_intent.target_browser, "brave")

    # -------------------------------------------------------------------------
    # Criterion 13: Consequential form submissions respect confirmation rules
    # -------------------------------------------------------------------------
    def test_13_consequential_form_submissions_respect_confirmation_rules(self):
        """Consequential prompts or actions marked for confirmation yield pending_confirmation."""
        intent = BrowserIntent(
            action_type=BrowserActionType.INTERACT_PROMPT,
            site_name="chatgpt",
            prompt_query="Delete all my files",
            requires_confirmation=True
        )
        res = self.automation_engine.execute_intent(intent)
        self.assertFalse(res["success"])
        self.assertTrue(res.get("pending_confirmation"))

    # -------------------------------------------------------------------------
    # Criterion 14: Generic website interaction works without custom domain adapter
    # -------------------------------------------------------------------------
    def test_14_generic_website_interaction_works_without_custom_domain_adapter(self):
        """Arbitrary sites without custom adapters fall back gracefully to GenericWebsiteAdapter."""
        adapter = website_adapter_registry.get_adapter("unknown-tech-blog.org")
        self.assertIsInstance(adapter, GenericWebsiteAdapter)
        self.assertEqual(adapter.name, "generic")
        selectors = adapter.get_search_selectors()
        self.assertTrue(len(selectors) > 0)
        self.assertIn("input[type='search']", selectors)

    # -------------------------------------------------------------------------
    # Criterion 15: End-to-end Intent Engine and Executor Integration
    # -------------------------------------------------------------------------
    def test_15_end_to_end_intent_engine_and_executor_integration(self):
        """Validates end-to-end integration through IntentEngine and CommandExecutor."""
        executor = CommandExecutor()

        # Parse via IntentEngine
        parsed_node = self.intent_engine.parse("Search for Naruto on HiAnime.")
        self.assertEqual(parsed_node["intent"], "browser_action")
        self.assertEqual(parsed_node["action_type"], "search_website")
        self.assertEqual(parsed_node["search_query"], "naruto")

        # Execute via CommandExecutor
        with patch.object(executor.browser_mgr, "open_browser", return_value={"success": True}):
            with patch.object(self.automation_engine, "_verify_navigation", return_value=(True, "https://hianime.to/search?keyword=naruto")):
                exec_result = executor.execute(parsed_node)
                self.assertTrue(exec_result["success"])
                self.assertIn("searched hianime for 'naruto'", exec_result["message"].lower())


if __name__ == "__main__":
    unittest.main()
