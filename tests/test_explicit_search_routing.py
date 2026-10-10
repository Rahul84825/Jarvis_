import unittest
from unittest.mock import patch, MagicMock
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.jarvis_runtime import JarvisRuntime
from modules.system.executor import CommandExecutor
from core.os.browser_manager import BrowserManager
from config import config

class TestExplicitSearchRouting(unittest.TestCase):
    """Exhaustive test suite for explicit search keyword routing and API integration."""

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()

    # ==========================================
    # 1. PREFIX DETECTION & NORMALIZATION
    # ==========================================
    def test_prefix_detection_variations(self):
        """Verifies explicit search prefix detection across wake words, greetings, punctuation, and capitalization."""
        positive_cases = [
            ("Jarvis search AI news", "AI news"),
            ("Jarvis, search AI news", "AI news"),
            ("Hey Jarvis search React documentation", "React documentation"),
            ("search AI news", "AI news"),
            ("SEARCH AI NEWS", "AI NEWS"),
            ("jarvis search AI news", "AI news"),
            ("Hello Jarvis, search the official React documentation", "the official React documentation"),
            ("Hey Jarvis, search how does CPU beam size affect Whisper transcription?", "how does CPU beam size affect Whisper transcription?"),
            ("Please search latest Python releases", "latest Python releases"),
            ("Jarvis: search weather in Tokyo", "weather in Tokyo"),
        ]

        for raw_input, expected_query in positive_cases:
            with self.subTest(raw_input=raw_input):
                is_search, extracted_q = self.normalizer.extract_explicit_search(raw_input)
                self.assertTrue(is_search, f"Failed to detect search in '{raw_input}'")
                self.assertEqual(extracted_q, expected_query)

                # Intent engine parsing
                node = self.intent_engine.parse(raw_input)
                self.assertEqual(node["intent"], "web_search")
                self.assertEqual(node["action"], "search")
                self.assertTrue(node.get("is_explicit_search"))

    # ==========================================
    # 2. QUERY EXTRACTION (TECHNICAL TERMS & PUNCTUATION)
    # ==========================================
    def test_query_extraction_preserves_technical_terms(self):
        """Verify that 'Jarvis search React 19 migration guide' produces exactly 'React 19 migration guide'."""
        node = self.intent_engine.parse("Jarvis search React 19 migration guide")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["query"], "React 19 migration guide")
        self.assertEqual(node["target"], "React 19 migration guide")

    def test_query_extraction_preserves_casing_and_punctuation(self):
        """Verify that casing, technical acronyms, and punctuation are preserved."""
        raw = "Hey Jarvis, search how does CPU beam size affect Whisper transcription?"
        node = self.intent_engine.parse(raw)
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["query"], "how does CPU beam size affect Whisper transcription?")
        self.assertIn("CPU", node["query"])
        self.assertIn("Whisper", node["query"])
        self.assertTrue(node["query"].endswith("?"))

    # ==========================================
    # 3. NEGATIVE CASES
    # ==========================================
    def test_negative_cases_do_not_trigger_explicit_search(self):
        """Negative cases must not trigger explicit search routing."""
        negative_cases = [
            "research AI safety",
            "searching for AI news",
            "I want to search my local files",
            "can we do research on quantum computing",
        ]

        for neg in negative_cases:
            with self.subTest(neg=neg):
                is_search, _ = self.normalizer.extract_explicit_search(neg)
                self.assertFalse(is_search, f"Should not match explicit search: '{neg}'")

                node = self.intent_engine.parse(neg)
                self.assertNotEqual(node.get("intent"), "web_search")

    # ==========================================
    # 4. EMPTY SEARCH QUERY HANDLING
    # ==========================================
    def test_empty_search_query_prompts_clarification_without_calling_provider(self):
        """Empty search query ('Jarvis search') must prompt clarification and NOT invoke the browser."""
        node = self.intent_engine.parse("Jarvis search")
        self.assertEqual(node["intent"], "web_search")
        self.assertTrue(node.get("empty_query"))
        self.assertEqual(node.get("query"), "")

        executor = CommandExecutor()
        with patch.object(executor.browser_mgr, "search") as mock_search:
            res = executor.execute(node)
            mock_search.assert_not_called()
            self.assertTrue(res["success"])
            self.assertEqual(res["message"], "What would you like me to search for, Sir?")

    def test_empty_search_query_standalone_keyword(self):
        """Standalone 'search' keyword with trailing spaces must also prompt clarification."""
        node = self.intent_engine.parse("search   ")
        self.assertEqual(node["intent"], "web_search")
        self.assertTrue(node.get("empty_query"))

    # ==========================================
    # 5. ROUTING PRIORITY (BEFORE QUESTIONS & FALLBACK)
    # ==========================================
    def test_routing_priority_over_generic_question(self):
        """Explicit search with question starter ('what is') must reach search BEFORE question fallback."""
        # Unprefixed question routes to conversation/question
        unprefixed_node = self.intent_engine.parse("What is quantum computing?")
        self.assertEqual(unprefixed_node["intent"], "question")

        # Prefixed search MUST route to web_search
        prefixed_node = self.intent_engine.parse("Jarvis search what is quantum computing")
        self.assertEqual(prefixed_node["intent"], "web_search")
        self.assertEqual(prefixed_node["query"], "what is quantum computing")

    # ==========================================
    # 6. INTEGRATION-STYLE ROUTING (RUNTIME PIPELINE)
    # ==========================================
    @patch("core.jarvis_runtime.SpeechListener")
    @patch("core.jarvis_runtime.SpeechTranscriber")
    @patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector")
    def test_runtime_pipeline_integration_exercises_real_normalizer_and_router(self, mock_ww, mock_trans, mock_list):
        """Integration test executing real normalizer, intent engine, and executor together."""
        runtime = JarvisRuntime()

        with patch.object(runtime.executor.browser_mgr, "search") as mock_search, \
             patch.object(runtime.conversation_manager, "process_query") as mock_cm:
            mock_search.return_value = {"success": True, "message": "Searching Google."}

            res = runtime._process_single_command("Jarvis search latest AI news", speak=False)

            mock_search.assert_called_once_with("latest AI news", provider="google")
            mock_cm.assert_not_called()
            self.assertEqual(res["action"], "search")
            self.assertEqual(res["message"], "Searching Google.")

    # ==========================================
    # 7. PROVIDER EXECUTION & ARGUMENT MAPPING
    # ==========================================
    def test_provider_execution_passes_query_correctly(self):
        """Verify executor passes extracted query and resolved provider correctly."""
        executor = CommandExecutor()
        node = {
            "intent": "web_search",
            "action": "search",
            "provider": "google",
            "target": "official React documentation",
            "query": "official React documentation",
            "empty_query": False,
            "is_explicit_search": True
        }

        with patch.object(executor.browser_mgr, "search") as mock_search:
            mock_search.return_value = {"success": True, "message": "Searching Google."}
            res = executor.execute(node)

            mock_search.assert_called_once_with("official React documentation", provider="google")
            self.assertTrue(res["success"])
            self.assertEqual(res["message"], "Searching Google.")

    # ==========================================
    # 8. FAILURE MODES
    # ==========================================
    def test_failure_provider_unavailable(self):
        """When browser/search service is unavailable, honest error is reported."""
        executor = CommandExecutor()
        node = {
            "intent": "web_search",
            "action": "search",
            "provider": "google",
            "target": "Python 3.14",
            "query": "Python 3.14",
            "empty_query": False
        }

        with patch.object(executor.browser_mgr, "resolve_target_browser", return_value=(None, "No supported browser installed.")):
            res = executor.execute(node)
            self.assertFalse(res["success"])
            self.assertIn("No supported browser installed", res["message"])
            self.assertNotIn("limited to my local capabilities", res["message"])

    def test_failure_timeout(self):
        """When search API/operation times out, report timeout error."""
        executor = CommandExecutor()
        node = {
            "intent": "web_search",
            "action": "search",
            "provider": "google",
            "target": "weather in Pune",
            "query": "weather in Pune",
            "empty_query": False
        }

        with patch.object(executor.browser_mgr, "search", side_effect=TimeoutError("Request timed out")):
            res = executor.execute(node)
            self.assertFalse(res["success"])
            self.assertIn("timed out", res["message"].lower())
            self.assertNotIn("limited to my local capabilities", res["message"])

    def test_failure_missing_configuration(self):
        """When an unconfigured search provider is requested, report configuration error."""
        bm = BrowserManager()
        res = bm.search("test query", provider="non_existent_provider")
        self.assertFalse(res["success"])
        self.assertIn("not configured", res["message"])

    def test_failure_unexpected_exception(self):
        """When an unexpected exception occurs, return failure without crashing."""
        executor = CommandExecutor()
        node = {
            "intent": "web_search",
            "action": "search",
            "provider": "google",
            "target": "test",
            "query": "test",
            "empty_query": False
        }

        with patch.object(executor.browser_mgr, "search", side_effect=RuntimeError("Unexpected OS bus error")):
            res = executor.execute(node)
            self.assertFalse(res["success"])
            self.assertIn("unexpected error", res["message"].lower())
            self.assertNotIn("limited to my local capabilities", res["message"])

if __name__ == "__main__":
    unittest.main()
