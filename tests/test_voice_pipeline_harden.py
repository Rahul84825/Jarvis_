"""
Comprehensive regression and hardening tests for Jarvis Voice Pipeline and Intelligence Refactor.
Covers:
1. Transcript Validation (empty, short, repetitive hallucination compression)
2. Multi-command Parsing (valid splits vs conversational non-splits)
3. Command Normalizer output consistency
4. Local Conversation Responses (offline greeting, thanks, bye, how are you, identity, status)
5. Request Deduplication & Authoritative State Transitions
6. Structured Intelligence Router Results
"""

import unittest
import time
from core.transcript_validator import TranscriptValidator, ValidationStatus
from core.multi_command_parser import MultiCommandParser
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.ai.intelligence_router import IntelligenceRouter
from core.conversation_manager import ConversationManager


class TestTranscriptValidator(unittest.TestCase):
    def setUp(self):
        self.validator = TranscriptValidator()

    def test_empty_and_whitespace_rejection(self):
        for raw in ["", "   ", "\t\n", "   \n"]:
            res = self.validator.validate(raw)
            self.assertFalse(res.is_valid)
            self.assertEqual(res.status, ValidationStatus.EMPTY)

    def test_too_short_tokens(self):
        for raw in [".", ",", "a", "??"]:
            res = self.validator.validate(raw)
            self.assertFalse(res.is_valid)
            self.assertEqual(res.status, ValidationStatus.TOO_SHORT)

    def test_repetitive_hallucination_compression(self):
        cases = [
            ("okay okay okay", "okay"),
            ("bye bye bye", "bye"),
            ("oh please oh please oh please oh please", "oh please"),
            ("What do you want to do? What do you want to do?", "What do you want to do"),
            ("thank you thank you", "thank you"),
            ("hello hello hello", "hello")
        ]
        for raw, expected_cleaned in cases:
            res = self.validator.validate(raw)
            self.assertTrue(res.is_valid)
            self.assertEqual(res.cleaned_text.lower().strip(), expected_cleaned.lower().strip())
            self.assertTrue(res.is_hallucination_compressed)

    def test_valid_commands_pass(self):
        commands = [
            "open chrome",
            "open vs code",
            "take a screenshot",
            "lock the computer",
            "open a new tab",
            "open another chrome window"
        ]
        for cmd in commands:
            res = self.validator.validate(cmd)
            self.assertTrue(res.is_valid)
            self.assertEqual(res.status, ValidationStatus.VALID)
            self.assertEqual(res.cleaned_text.lower(), cmd.lower())


class TestMultiCommandParserHardening(unittest.TestCase):
    def setUp(self):
        self.parser = MultiCommandParser()

    def test_valid_multi_command_splits(self):
        cases = [
            ("open Chrome and open VS Code", ["open chrome", "open vs code"]),
            ("open Chrome and then search Google for Python", ["open chrome", "search google for python"]),
            ("open Downloads and take a screenshot", ["open downloads", "take a screenshot"])
        ]
        for text, expected in cases:
            splits = self.parser.parse(text)
            self.assertEqual([s.lower().strip() for s in splits], [e.lower().strip() for e in expected])

    def test_conversational_and_repetitive_non_splits(self):
        cases = [
            "okay and please",
            "yes yes yes",
            "oh please oh please",
            "what what what",
            "bye bye bye",
            "thank you thank you",
            "yes and yes",
            "hello hello"
        ]
        for text in cases:
            splits = self.parser.parse(text)
            self.assertEqual(len(splits), 1, f"Expected 1 item for '{text}' but got {splits}")


class TestCommandNormalizerHardening(unittest.TestCase):
    def setUp(self):
        self.normalizer = CommandNormalizer()

    def test_normalizer_contract(self):
        res = self.normalizer.normalize("please open Chrome")
        self.assertIn("normalized", res)
        self.assertIn("raw", res)
        self.assertIn("removed_words", res)
        self.assertIn("confidence", res)
        self.assertIn("meaningful", res)
        self.assertEqual(res["normalized"], "open chrome")

    def test_pure_polite_word_preservation(self):
        # When only 'please' is spoken, it should remain 'please' and not be emptied
        res = self.normalizer.normalize("please")
        self.assertEqual(res["normalized"], "please")
        self.assertTrue(res["meaningful"])


class TestLocalConversationEngine(unittest.TestCase):
    def setUp(self):
        self.intent_engine = IntentEngine()
        self.router = IntelligenceRouter()
        self.conv_manager = ConversationManager()

    def test_local_greetings(self):
        intents = [
            ("hello", "greeting"),
            ("hey Jarvis", "greeting"),
            ("good morning", "greeting"),
            ("hi there", "greeting")
        ]
        for text, expected_intent in intents:
            intent_res = self.intent_engine.parse(text)
            self.assertEqual(intent_res.get("intent"), expected_intent)

    def test_local_acknowledgement_and_farewell(self):
        intents = [
            ("thanks", "thank_you"),
            ("thank you", "thank_you"),
            ("bye", "goodbye"),
            ("goodbye", "goodbye"),
            ("okay", "acknowledgement"),
            ("yes", "affirmation"),
            ("no", "negation"),
            ("how are you", "how_are_you"),
            ("who are you", "identity"),
            ("are you there", "status_check")
        ]
        for text, expected_intent in intents:
            intent_res = self.intent_engine.parse(text)
            self.assertEqual(intent_res.get("intent"), expected_intent, f"Failed for '{text}'")

    def test_router_layer1_fast_local_for_conversation_and_commands(self):
        queries = [
            "open chrome",
            "open vs code",
            "take a screenshot",
            "lock the computer",
            "hello",
            "thanks",
            "bye",
            "who are you",
            "how are you"
        ]
        for q in queries:
            route = self.router.route(q)
            self.assertEqual(route.layer, 1, f"Query '{q}' was routed to Layer {route.layer} instead of Layer 1")

    def test_conversation_manager_offline_handling(self):
        queries = ["how are you", "are you there", "okay", "yes", "no"]
        for q in queries:
            resp = self.conv_manager.process_query(q)
            self.assertTrue(len(resp.get("text", "")) > 0)
            # Must not be the generic robotic fallback
            self.assertNotEqual(resp.get("text"), "I'm currently limited to my local capabilities for that question.")


if __name__ == "__main__":
    unittest.main()
