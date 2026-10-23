"""Automated Test Suite for Natural Language Intent Routing of Desktop Intelligence & File Creation."""

import unittest
from core.intent_engine import IntentEngine
from core.ai.intelligence_router import IntelligenceRouter, LAYER_1


class TestDesktopIntelligenceIntentRouting(unittest.TestCase):
    """Validates deterministic parsing and Layer 1 Fast Local routing for screen, file, and provider commands."""

    def setUp(self):
        self.intent_engine = IntentEngine()
        self.router = IntelligenceRouter()

    def test_screen_understanding_and_explanation_intents(self):
        """Verify all Phase 1 and 2 screen understanding commands parse deterministically."""
        cases = [
            ("Explain my screen", "screen_understanding.explain"),
            ("Explain this page in simple language", "screen_understanding.explain"),
            ("What are the important points here?", "screen_understanding.explain"),
            ("Explain the highlighted section", "screen_understanding.explain"),
            ("What does this error mean", "screen_understanding.explain"),
            ("Explain this code line by line", "screen_understanding.explain"),
            ("Summarize this PDF page", "screen_understanding.explain"),
            ("Explain this graph", "screen_understanding.explain"),
            ("What is this button used for", "screen_understanding.explain"),
            ("Compare these two visible sections", "screen_understanding.explain"),
            ("Explain point 3 again", "screen_understanding.explain"),
            ("Explain the second point", "screen_understanding.explain"),
            ("I still don't understand. Explain it with an example", "screen_understanding.explain"),
            ("Give me a short answer first, then explain in detail", "screen_understanding.explain"),
            ("Explain this like I'm a beginner", "screen_understanding.explain"),
            ("Analyze my screen", "screen_understanding.analyze"),
            ("What is on my screen", "screen_understanding.analyze")
        ]

        for phrase, expected_intent in cases:
            with self.subTest(phrase=phrase):
                res = self.intent_engine.parse(phrase)
                self.assertEqual(res["intent"], expected_intent, f"Failed intent for '{phrase}'")

    def test_file_creation_and_search_intents(self):
        """Verify all Phase 4 and 5 file creation and search commands parse deterministically."""
        cases = [
            ("Create a Python program for binary search", "file_management.create_file"),
            ("Write a C++ program for quicksort", "file_management.create_file"),
            ("Create a Python script that reads a CSV", "file_management.create_file"),
            ("Create a React component for this design", "file_management.create_file"),
            ("Generate a Node.js API route", "file_management.create_file"),
            ("Create a SQL schema for my project", "file_management.create_file"),
            ("Save this explanation as a Markdown file", "file_management.create_file"),
            ("Create a README for this folder", "file_management.create_file"),
            ("Where did I save my binary search program?", "file_management.search"),
            ("Find the README I created yesterday", "file_management.search"),
            ("Where is my JARVIS repository?", "file_management.search"),
            ("List AI providers", "ai_management.list_providers"),
            ("AI provider settings", "ai_management.list_providers")
        ]

        for phrase, expected_intent in cases:
            with self.subTest(phrase=phrase):
                res = self.intent_engine.parse(phrase)
                self.assertEqual(res["intent"], expected_intent, f"Failed intent for '{phrase}'")

    def test_intelligence_router_classifies_as_layer_1(self):
        """Verify IntelligenceRouter routes deterministic desktop commands via Layer 1 Fast Local (<5ms)."""
        test_commands = [
            "Explain my screen",
            "What are the important points here?",
            "Explain point 3 again",
            "Where did I save my binary search program?",
            "List AI providers"
        ]

        for cmd in test_commands:
            with self.subTest(cmd=cmd):
                req = self.router.classify(cmd)
                self.assertEqual(req.layer, LAYER_1, f"Expected Layer 1 for '{cmd}', got Layer {req.layer}")


if __name__ == "__main__":
    unittest.main()
