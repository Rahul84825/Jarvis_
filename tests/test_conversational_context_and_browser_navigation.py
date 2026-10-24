import unittest
from unittest.mock import patch, MagicMock
from core.os.browser_intent import BrowserIntentParser, BrowserActionType, SearchScope
from core.conversation_manager import ConversationManager, PendingActionContext
from core.intent_engine import IntentEngine


class TestConversationalContextAndBrowserNavigation(unittest.TestCase):
    """Deterministic regression test suite covering Phase 6 conversational context retention,
    pending clarification resolution, and website navigation.
    """

    def setUp(self):
        self.parser = BrowserIntentParser()
        self.conv_mgr = ConversationManager(db_path=":memory:")
        self.intent_engine = IntentEngine()

    def test_a_open_domain_navigates_directly_without_search_clarification(self):
        """TEST A: 'Open hianime.at.' -> Website navigation intent; no unnecessary search-engine clarification."""
        intent = self.parser.parse("Open hianime.at.")
        self.assertEqual(intent.action_type, BrowserActionType.OPEN_URL)
        self.assertEqual(intent.url, "https://hianime.at")
        self.assertEqual(intent.domain, "hianime.at")
        self.assertIsNone(intent.clarification_prompt)

        # Also test "Search HiAnime.at." -> Should recognize domain and navigate directly
        intent_search = self.parser.parse("Search HiAnime.at.")
        self.assertEqual(intent_search.action_type, BrowserActionType.OPEN_URL)
        self.assertEqual(intent_search.url, "https://hianime.at")

    def test_b_pending_clarification_browser_resolved_by_chrome(self):
        """TEST B: User asks to open site, assistant asks which browser, user replies 'Chrome'."""
        pending = PendingActionContext(
            original_request="Open HiAnime.at.",
            intent="browser_action",
            action="open_url",
            target="hianime.at",
            target_url="https://hianime.at",
            target_domain="hianime.at",
            clarification_question="Which browser should I use to open HiAnime.at?",
            clarification_type="browser_selection",
            valid_options=["chrome", "edge", "brave", "firefox"]
        )
        self.conv_mgr.set_pending_action(pending)
        self.assertTrue(self.conv_mgr.get_pending_action().can_resolve("Chrome."))

        resolved = self.conv_mgr.get_pending_action().resolve_action("Chrome.")
        self.assertEqual(resolved["intent"], "browser_action")
        self.assertEqual(resolved["action"], "open_url")
        self.assertEqual(resolved["browser"], "chrome")
        self.assertEqual(resolved["url"], "https://hianime.at")
        self.assertEqual(resolved["target"], "hianime.at")

    def test_c_search_site_for_query(self):
        """TEST C: 'Search HiAnime for Naruto.' -> Website search intent, website target HiAnime, query Naruto."""
        intent = self.parser.parse("Search HiAnime for Naruto.")
        self.assertEqual(intent.action_type, BrowserActionType.SEARCH_WEBSITE)
        self.assertEqual(intent.site_name, "hianime")
        self.assertEqual(intent.search_query.lower(), "naruto")
        self.assertEqual(intent.search_scope, SearchScope.WEBSITE)

    def test_d_search_this_website_contextual_reuse_and_clarification(self):
        """TEST D: 'Search this website for Naruto.' -> Reuses active website when known; otherwise requests clarification."""
        # 1. Without active website in context -> triggers clarification
        intent_no_ctx = self.parser.parse("Search this website for Naruto.", session_context={})
        self.assertEqual(intent_no_ctx.action_type, BrowserActionType.CLARIFICATION_NEEDED)
        self.assertIn("Which website would you like me to search", intent_no_ctx.clarification_prompt)

        # 2. With active website in context -> reuses website
        ctx = {"active_site": "hianime", "active_url": "https://hianime.to"}
        intent_ctx = self.parser.parse("Search this website for Naruto.", session_context=ctx)
        self.assertEqual(intent_ctx.action_type, BrowserActionType.SEARCH_WEBSITE)
        self.assertEqual(intent_ctx.site_name, "hianime")
        self.assertEqual(intent_ctx.url, "https://hianime.to")
        self.assertEqual(intent_ctx.search_query.lower(), "naruto")

    def test_e_search_google_for_query(self):
        """TEST E: 'Search Google for Naruto.' -> Google search; no accidental HiAnime navigation."""
        intent = self.parser.parse("Search Google for Naruto.")
        d = intent.to_dict()
        self.assertEqual(d["intent"], "web_search")
        self.assertEqual(d["provider"], "google")
        self.assertEqual(d["query"].lower(), "naruto")

    def test_f_clarification_destination_override(self):
        """TEST F: Assistant asks clarification; user replies 'No, YouTube instead' -> updates destination."""
        pending = PendingActionContext(
            original_request="Open hianime.at.",
            intent="browser_action",
            action="open_url",
            target="hianime.at",
            target_url="https://hianime.at",
            clarification_question="Which browser should I use?",
            clarification_type="browser_selection"
        )
        self.conv_mgr.set_pending_action(pending)
        self.assertTrue(self.conv_mgr.get_pending_action().can_resolve("No, YouTube instead"))

        resolved = self.conv_mgr.get_pending_action().resolve_action("No, YouTube instead")
        self.assertEqual(resolved["action"], "open_url")
        self.assertEqual(resolved["target"], "youtube")
        self.assertEqual(resolved["url"], "https://www.youtube.com")

    def test_g_clarification_cancellation(self):
        """TEST G: Assistant asks clarification; user replies 'Cancel that.' -> cancels cleanly."""
        pending = PendingActionContext(
            original_request="Open hianime.at.",
            intent="browser_action",
            action="open_url",
            target="hianime.at",
            target_url="https://hianime.at",
            clarification_question="Which browser should I use?"
        )
        self.conv_mgr.set_pending_action(pending)
        self.assertTrue(self.conv_mgr.get_pending_action().can_resolve("Cancel that."))

        resolved = self.conv_mgr.get_pending_action().resolve_action("Cancel that.")
        self.assertTrue(resolved.get("cancelled"))
        self.assertIn("Action cancelled", resolved.get("message"))

    def test_h_open_domain_does_not_ask_what_to_do_with_chrome(self):
        """TEST H: When clarification is pending, 'Chrome.' resolves to opening the domain, NOT standalone open_app."""
        pending = PendingActionContext(
            original_request="Open hianime.at.",
            intent="browser_action",
            action="open_url",
            target="hianime.at",
            target_url="https://hianime.at",
            target_domain="hianime.at",
            clarification_question="Which browser should I use?"
        )
        self.conv_mgr.set_pending_action(pending)
        resolved = self.conv_mgr.get_pending_action().resolve_action("Chrome")
        self.assertEqual(resolved["intent"], "browser_action")
        self.assertEqual(resolved["action"], "open_url")
        self.assertEqual(resolved["url"], "https://hianime.at")
        self.assertEqual(resolved["browser"], "chrome")

    def test_i_topic_change_supersedes_pending_action_safely(self):
        """TEST I: User asks to open site, then changes topic to 'What is Python?'.
        Pending action must NOT match, allowing normal topic handling.
        """
        pending = PendingActionContext(
            original_request="Open hianime.at.",
            intent="browser_action",
            action="open_url",
            target="hianime.at",
            target_url="https://hianime.at",
            clarification_question="Which browser should I use?"
        )
        self.conv_mgr.set_pending_action(pending)
        # "What is Python?" is an unrelated topic question
        self.assertFalse(self.conv_mgr.get_pending_action().can_resolve("What is Python?"))

    def test_j_followup_search_there_preserves_query_and_website_context(self):
        """TEST J: Follow-up 'Search for Naruto there.' -> reuses active site and cleans query to 'Naruto'."""
        ctx = {"active_site": "hianime", "active_url": "https://hianime.to"}
        intent = self.parser.parse("Search for Naruto there.", session_context=ctx)
        self.assertEqual(intent.action_type, BrowserActionType.SEARCH_WEBSITE)
        self.assertEqual(intent.site_name, "hianime")
        self.assertEqual(intent.url, "https://hianime.to")
        # Ensure 'there' was removed from the query
        self.assertEqual(intent.search_query.lower(), "naruto")

    def test_prefix_browser_with_destination(self):
        """Verifies 'Open Chrome and go to hianime.at' correctly resolves browser and destination."""
        intent = self.parser.parse("Open Chrome and go to hianime.at")
        self.assertEqual(intent.action_type, BrowserActionType.OPEN_URL)
        self.assertEqual(intent.target_browser, "chrome")

    def test_runtime_e2e_clarification_and_followup_resolution(self):
        """Simulates full conversational sequence through JarvisRuntime command handler."""
        from core.jarvis_runtime import JarvisRuntime
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber"), \
             patch("core.jarvis_runtime.TTSManager"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory"):
            runtime = JarvisRuntime()

            # Set up pending action as if Turn 1 asked "Which browser should I use to open HiAnime.at?"
            pending = PendingActionContext(
                original_request="Open HiAnime.at.",
                intent="browser_action",
                action="open_url",
                target="hianime.at",
                target_url="https://hianime.at",
                target_domain="hianime.at",
                clarification_question="Which browser should I use to open HiAnime.at?",
                clarification_type="browser_selection",
                valid_options=["chrome", "edge", "brave", "firefox"]
            )
            runtime.conversation_manager.set_pending_action(pending)

            # Turn 2: User says "Chrome."
            with patch.object(runtime.executor, "execute", return_value={"success": True, "action": "open_url", "message": "Opened hianime.at."}) as mock_exec:
                # Execute worker logic with input "Chrome."
                runtime._process_command_worker("Chrome.", "test-utterance-1")

                # Verify executor was called with the resolved intent
                mock_exec.assert_called_once()
                exec_arg = mock_exec.call_args[0][0]
                self.assertEqual(exec_arg["action"], "open_url")
                self.assertEqual(exec_arg["url"], "https://hianime.at")
                self.assertEqual(exec_arg["browser"], "chrome")

                # Verify pending action was cleared after resolution
                self.assertIsNone(runtime.conversation_manager.get_pending_action())


if __name__ == "__main__":
    unittest.main()
