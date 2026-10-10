import unittest
import time
import os
import shutil
from pathlib import Path

from core.ai.intelligence_router import (
    IntelligenceRouter,
    StructuredRequest,
    MODE_FAST_LOCAL,
    MODE_CONTEXT,
    MODE_REASONING,
    MODE_QUESTION,
    LAYER_1,
    LAYER_2,
    LAYER_3
)
from core.ai.tools.registry import ToolRegistry, tool_registry
from core.ai.agent_brain import AgentBrain, agent_brain
from core.conversation_manager import ConversationManager
from memory.persistent_memory import PersistentMemory, persistent_memory
from core.jarvis_runtime import JarvisRuntime
from config import config

class TestIntelligenceSystem(unittest.TestCase):
    """Unit and Integration Tests for the 3-Layer Jarvis Intelligence Brain."""

    @classmethod
    def setUpClass(cls):
        cls.test_db_path = str(Path(__file__).parent / "test_memory.db")
        cls.memory = PersistentMemory(db_path=cls.test_db_path)
        cls.router = IntelligenceRouter()
        cls.tool_registry = tool_registry
        cls.agent = AgentBrain()
        cls.conv_manager = ConversationManager()
        # Warm-up call
        cls.router.route("warm up jarvis")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def setUp(self):
        self.conv_manager.clear_session()

    # =========================================================================
    # 1. LAYER 1 — REFLEX / FAST LOCAL TESTS
    # =========================================================================
    def test_layer1_fast_local_commands(self):
        test_cases = [
            ("Open Chrome", "OPEN_APP", "chrome"),
            ("Hey Jarvis, open Chrome", "OPEN_APP", "chrome"),
            ("Could you please open Chrome for me?", "OPEN_APP", "chrome"),
            ("Launch VS Code", "OPEN_APP", "vscode"),
            ("Close Chrome", "CLOSE_APP", "chrome"),
            ("Open Downloads", "OPEN_FOLDER", "downloads"),
            ("Take a screenshot", "SCREENSHOT", "screenshot"),
            ("Lock my laptop", "SYSTEM_CONTROL", "lock"),
            ("Put my computer to sleep", "SYSTEM_CONTROL", "sleep"),
            ("Open a new Chrome tab", "WINDOW_CONTROL", "new_tab"),
            ("Open another Chrome window", "WINDOW_CONTROL", "new_window"),
            ("Open the terminal", "OPEN_APP", "terminal"),
            ("What is 25 times 48?", "MATH_CALCULATION", "math"),
            ("What time is it?", "TIME_QUERY", "time"),
        ]

        for phrase, expected_intent, expected_target_sub in test_cases:
            with self.subTest(phrase=phrase):
                t0 = time.perf_counter()
                req = self.router.route(phrase)
                elapsed_ms = (time.perf_counter() - t0) * 1000

                self.assertEqual(req.layer, LAYER_1, f"Expected Layer 1 for '{phrase}', got Layer {req.layer}")
                self.assertEqual(req.mode, MODE_FAST_LOCAL)
                self.assertFalse(req.planning_required)
                self.assertLess(elapsed_ms, 50.0, f"Layer 1 parse exceeded 50ms latency ({elapsed_ms:.2f}ms) for '{phrase}'")

    # =========================================================================
    # 2. LAYER 2 — CONTEXT & UNDERSTANDING TESTS
    # =========================================================================
    def test_layer2_pronominal_close_it(self):
        # Setup context where last opened app was 'chrome'
        context = {"last_target": "chrome", "last_action": "open_application"}
        req = self.router.route("Close it", session_context=context)

        self.assertEqual(req.layer, LAYER_2)
        self.assertEqual(req.mode, MODE_CONTEXT)
        self.assertEqual(req.intent, "CLOSE_APP")
        self.assertEqual(req.target, "chrome")

    def test_layer2_pronominal_minimize_it(self):
        context = {"last_target": "vscode", "last_action": "open_application"}
        req = self.router.route("Minimize it", session_context=context)

        self.assertEqual(req.layer, LAYER_2)
        self.assertEqual(req.mode, MODE_CONTEXT)
        self.assertEqual(req.target, "vscode")
        self.assertEqual(req.action, "minimize_application")

    def test_layer2_preference_lookup(self):
        # Set preference in memory
        persistent_memory.set_preference("default_browser", "firefox")
        req = self.router.route("Open the browser I usually use")

        self.assertEqual(req.layer, LAYER_2)
        self.assertEqual(req.mode, MODE_CONTEXT)
        self.assertEqual(req.intent, "OPEN_APP")
        self.assertEqual(req.target, "firefox")

    def test_layer2_project_context_switch(self):
        req = self.router.route("Work on Jarvis")
        self.assertEqual(req.layer, LAYER_2)
        self.assertEqual(req.mode, MODE_CONTEXT)
        self.assertEqual(req.intent, "PROJECT_CONTROL")
        self.assertEqual(req.target, "jarvis")

    def test_layer2_ambiguity_clarification(self):
        # Register 2 projects
        persistent_memory.register_project("jarvis", "Jarvis Assistant", "C:/jarvis")
        persistent_memory.register_project("wellmeds", "WellMeds Healthcare", "C:/wellmeds")

        # When asking "Open my project" without explicit active project
        req = self.router.route("Open my project", session_context={"explicit_project": False})
        self.assertEqual(req.layer, LAYER_2)
        self.assertEqual(req.intent, "CLARIFICATION_REQUIRED")
        self.assertIn("Which project do you want", req.clarification_prompt)

    # =========================================================================
    # 3. LAYER 3 — REASONING & AGENTIC PATH TESTS
    # =========================================================================
    def test_layer3_reasoning_routing(self):
        complex_phrases = [
            "Prepare my development environment",
            "Get my dev environment ready",
            "Check why my backend isn't working",
            "Run the tests and tell me what failed",
            "Search the internet for quantum computing and summarize",
            "Find the file where I implemented authentication",
            "Compare these two project architectures"
        ]

        for phrase in complex_phrases:
            with self.subTest(phrase=phrase):
                req = self.router.route(phrase)
                self.assertEqual(req.layer, LAYER_3, f"Expected Layer 3 for '{phrase}', got Layer {req.layer}")
                self.assertEqual(req.mode, MODE_REASONING)
                self.assertTrue(req.planning_required)

    def test_agent_brain_deterministic_local_plan(self):
        # Test offline dev environment preparation plan
        res = self.agent.reason_and_execute("Prepare my development environment")
        self.assertIn("text", res)
        self.assertIn("tools_executed", res)
        self.assertIn("open_application", res["tools_executed"])
        self.assertIn("run_tests", res["tools_executed"])

    def test_agent_brain_backend_diagnosis_plan(self):
        res = self.agent.reason_and_execute("Check why my backend isn't working")
        self.assertIn("text", res)
        self.assertIn("get_system_info", res["tools_executed"])

    # =========================================================================
    # 4. NEGATIVE CASES — QUESTIONS VS COMMANDS
    # =========================================================================
    def test_negative_informational_questions(self):
        questions = [
            "What is Chrome?",
            "How do I lock my laptop?",
            "Why does VS Code crash?",
            "Tell me about sleep mode",
            "Can you explain how the terminal works?",
            "Should I shut down or sleep my laptop?"
        ]

        for q in questions:
            with self.subTest(question=q):
                req = self.router.route(q)
                self.assertEqual(req.mode, MODE_QUESTION, f"'{q}' should be classified as QUESTION")
                self.assertFalse(req.planning_required)
                self.assertNotEqual(req.mode, MODE_FAST_LOCAL, f"'{q}' should not trigger fast local execution")

    # =========================================================================
    # 5. STRUCTURED TOOL REGISTRY TESTS
    # =========================================================================
    def test_tool_registry_execution(self):
        # System info tool
        res_info = self.tool_registry.execute("get_system_info")
        self.assertTrue(res_info["success"])
        self.assertEqual(res_info["tool"], "get_system_info")
        self.assertIn("data", res_info)

        # Recall memory tool
        self.tool_registry.execute("remember", {"key": "favorite_editor", "value": "vscode", "category": "preferences"})
        res_recall = self.tool_registry.execute("recall", {"key": "favorite_editor"})
        self.assertTrue(res_recall["success"])
        self.assertEqual(res_recall["data"], "vscode")

        # Non-existent tool
        res_none = self.tool_registry.execute("non_existent_tool_123")
        self.assertFalse(res_none["success"])

    # =========================================================================
    # 6. SQLITE MEMORY PERSISTENCE TESTS
    # =========================================================================
    def test_sqlite_memory_persistence(self):
        # Preferences
        self.memory.set_preference("theme", "dark", category="ui")
        self.assertEqual(self.memory.get_preference("theme"), "dark")

        # Categorized memories
        self.memory.remember("projects", "jarvis_lang", "Python")
        self.assertEqual(self.memory.recall("jarvis_lang", category="projects"), "Python")

        # Project registry
        self.memory.register_project("testproj", "Test Project", "C:/testproj", framework="React", backend_port=3000)
        proj = self.memory.get_project("testproj")
        self.assertIsNotNone(proj)
        self.assertEqual(proj["framework"], "React")
        self.assertEqual(proj["backend_port"], 3000)

        # Search memories
        matches = self.memory.search_memories("Python")
        self.assertTrue(len(matches) > 0)

    # =========================================================================
    # 7. CONVERSATION MANAGER MULTI-TURN TRACKING
    # =========================================================================
    def test_conversation_manager_context_update(self):
        self.conv_manager.update_context("open_application", "vscode")
        ctx = self.conv_manager.get_context()
        self.assertEqual(ctx["last_target"], "vscode")
        self.assertEqual(ctx["last_action"], "open_application")

if __name__ == "__main__":
    unittest.main()
