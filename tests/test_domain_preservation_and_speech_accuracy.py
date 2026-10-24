import unittest
from unittest.mock import patch, MagicMock

from core.os.domain_manager import domain_manager, DomainEntry
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.os.browser_intent import BrowserIntentParser, BrowserActionType, SearchScope
from core.conversation_manager import ConversationManager, PendingActionContext


class TestDomainPreservationAndSpeechAccuracy(unittest.TestCase):
    """Regression test suite for Domain Preservation & Speech-to-URL Accuracy (Phase 8 Fixes)."""

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.parser = BrowserIntentParser()
        self.conv_mgr = ConversationManager()

    def test_1_user_says_open_hianime_at(self):
        """Case 1: User says 'Open hianime.at.' -> Expected hostname: hianime.at."""
        intent = self.parser.parse("Open hianime.at.")
        self.assertEqual(intent.action_type, BrowserActionType.OPEN_URL)
        self.assertEqual(intent.domain, "hianime.at")
        self.assertEqual(intent.site_name, "hianime.at")
        self.assertEqual(intent.url, "https://hianime.at")

    def test_2_stt_returns_high_anime_at_low_confidence_confirmation_required(self):
        """Case 2: STT returns 'high-anime.at' with low confidence / uncertainty.
        Expected: ask for confirmation instead of navigating to a guessed domain.
        """
        # Test directly via domain_manager
        res = domain_manager.resolve_domain("high-anime.at", confidence=0.75, is_spoken=True)
        self.assertEqual(res.status, "CONFIRMATION_REQUIRED")
        self.assertEqual(res.canonical_hostname, "hianime.at")
        self.assertIn("Did you mean 'hianime.at' or 'high-anime.at'?", res.clarification_prompt)
        self.assertFalse(res.is_navigable)

        # Test through real production BrowserIntentParser
        intent = self.parser.parse("Open high-anime.at.")
        self.assertEqual(intent.action_type, BrowserActionType.CLARIFICATION_NEEDED)
        self.assertIn("hianime.at", intent.clarification_prompt)
        self.assertIn("high-anime.at", intent.clarification_prompt)
        # Verify it did NOT navigate directly to guessed domain
        self.assertIsNone(intent.url)

    def test_3_user_types_exact_hianime_at(self):
        """Case 3: User types 'hianime.at'. Expected: preserve the exact hostname."""
        norm_res = self.normalizer.normalize("hianime.at")
        self.assertEqual(norm_res["normalized"], "hianime.at")

        intent = self.parser.parse("hianime.at")
        self.assertEqual(intent.action_type, BrowserActionType.OPEN_URL)
        self.assertEqual(intent.domain, "hianime.at")
        self.assertEqual(intent.url, "https://hianime.at")

    def test_4_user_says_open_example_com(self):
        """Case 4: User says 'Open example.com.' Expected hostname: example.com."""
        intent = self.parser.parse("Open example.com.")
        self.assertEqual(intent.action_type, BrowserActionType.OPEN_URL)
        self.assertEqual(intent.domain, "example.com")
        self.assertEqual(intent.site_name, "example.com")
        self.assertEqual(intent.url, "https://example.com")

    def test_5_user_says_search_google_for_python(self):
        """Case 5: User says 'Search Google for Python.'
        Expected: Google search, not domain navigation.
        """
        intent = self.parser.parse("Search Google for Python.")
        self.assertEqual(intent.action_type, BrowserActionType.SEARCH_WEB)
        d = intent.to_dict()
        self.assertEqual(d["intent"], "web_search")
        self.assertEqual(d["provider"], "google")
        self.assertEqual(d["query"].lower(), "python")
        self.assertIn("google.com/search?q=python", intent.url)

    def test_6_user_says_search_hianime_for_naruto(self):
        """Case 6: User says 'Search HiAnime for Naruto.'
        Expected: retain the website target and the query as separate fields.
        """
        intent = self.parser.parse("Search HiAnime for Naruto.")
        self.assertEqual(intent.action_type, BrowserActionType.SEARCH_WEBSITE)
        self.assertEqual(intent.site_name, "hianime")
        self.assertEqual(intent.search_query.lower(), "naruto")
        self.assertEqual(intent.search_scope, SearchScope.WEBSITE)

        # Also test via full IntentEngine.parse()
        node = self.intent_engine.parse("Search HiAnime for Naruto.")
        self.assertEqual(node["intent"], "browser_action")
        self.assertEqual(node["action"], "search_website")
        self.assertEqual(node["target"], "hianime")
        self.assertEqual(node["search_query"].lower(), "naruto")

    def test_7_user_explicitly_requests_different_hostname(self):
        """Case 7: User explicitly requests a different hostname.
        Expected: preserve the new requested hostname rather than forcing the old one.
        """
        for custom_domain in ["custom-anime.org", "my-portfolio.dev", "sub.example.net"]:
            intent = self.parser.parse(f"Open {custom_domain}.")
            self.assertEqual(intent.action_type, BrowserActionType.OPEN_URL)
            self.assertEqual(intent.domain, custom_domain)
            self.assertEqual(intent.url, f"https://{custom_domain}")

    def test_8_domain_normalization_must_not_alter_unrelated_words(self):
        """Case 8: Domain normalization must not alter unrelated words or ordinary conversation."""
        sentences = [
            "We observed high anime interest among students yesterday",
            "This project requires high performance and low latency",
            "The high altitude mountain pass was closed for winter",
            "What is Python programming language",
        ]
        for s in sentences:
            norm_res = self.normalizer.normalize(s)
            # Must NOT insert hianime or domains into non-domain sentences
            self.assertNotIn("hianime", norm_res["normalized"])
            self.assertNotIn(".at", norm_res["normalized"])

    def test_9_followup_open_domain_then_chrome(self):
        """Case 9: Follow-up: 'Open hianime.at', then 'Chrome.'
        Expected: retain the original hostname and resolve the browser choice.
        """
        pending = PendingActionContext(
            original_request="Open hianime.at.",
            intent="browser_action",
            action="open_url",
            target="hianime.at",
            target_url="https://hianime.at",
            target_domain="hianime.at",
            clarification_question="Which browser should I use to open hianime.at?",
            clarification_type="browser_selection",
            valid_options=["chrome", "edge", "firefox", "brave"]
        )
        self.conv_mgr.set_pending_action(pending)

        # User responds with "Chrome."
        self.assertTrue(self.conv_mgr.get_pending_action().can_resolve("Chrome."))
        resolved = self.conv_mgr.get_pending_action().resolve_action("Chrome.")

        self.assertEqual(resolved["action"], "open_url")
        self.assertEqual(resolved["url"], "https://hianime.at")
        self.assertEqual(resolved["target"], "hianime.at")
        self.assertEqual(resolved["browser"], "chrome")

    def test_10_invalid_or_malformed_domains_produce_safe_clarification(self):
        """Case 10: Invalid or malformed domains must produce a safe, actionable clarification."""
        malformed_inputs = [
            "Open http://",
            "Open foo..com",
            "Open .com",
            "Navigate to -invalid-.at",
        ]
        for mal in malformed_inputs:
            intent = self.parser.parse(mal)
            # Must produce clarification rather than navigating or crashing
            self.assertEqual(
                intent.action_type,
                BrowserActionType.CLARIFICATION_NEEDED,
                f"Expected clarification for malformed input: {mal}"
            )
            self.assertIn("Which website would you like me to open", intent.clarification_prompt)
            self.assertIsNone(intent.url)


if __name__ == "__main__":
    unittest.main()
