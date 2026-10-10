import unittest
from core.ai.tools.registry import tool_registry
from core.local_response_engine import local_response_engine
from core.intent_engine import intent_engine

class TestCapabilityRegistry(unittest.TestCase):
    def test_tool_registry_categories_and_examples(self):
        categories = tool_registry.get_categories()
        self.assertTrue(len(categories) > 0)
        self.assertIn("Applications", categories)
        self.assertIn("Browser", categories)
        self.assertIn("System", categories)

        by_cat = tool_registry.get_capabilities_by_category()
        for cat, tools in by_cat.items():
            self.assertTrue(len(tools) > 0)
            for t in tools:
                self.assertTrue("name" in t)
                self.assertTrue("description" in t)
                self.assertTrue("examples" in t)

    def test_dynamic_capability_summary_not_empty(self):
        summary = tool_registry.get_capability_summary()
        self.assertIsNotNone(summary)
        self.assertTrue(len(summary) > 30)
        self.assertIn("applications", summary.lower())
        self.assertIn("browser", summary.lower())

    def test_help_intent_classification(self):
        queries = [
            "What can you do?",
            "What can Jarvis do?",
            "What are your capabilities?",
            "What commands do you know?",
            "Help",
            "Show me your capabilities.",
            "How can you help me?"
        ]
        for q in queries:
            intent, target = intent_engine.classify_intent(q)
            self.assertEqual(intent, "help", f"Failed for query: {q}")

    def test_help_response_generation(self):
        resp = local_response_engine.get_help_response()
        self.assertIsNotNone(resp)
        self.assertTrue(len(resp) > 30)
        self.assertNotIn("I'm currently limited", resp)
        self.assertIn("applications", resp.lower())

if __name__ == "__main__":
    unittest.main()
