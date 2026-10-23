"""JARVIS Phase 5 Comprehensive Regression & Routing Verification Suite.
Validates:
1. Fix for repeated generic capability response (time/date/help disambiguation).
2. Command routing across Layer 1, Layer 2, and Layer 3.
3. Chrome vs Brave browser selection and YouTube vs general search.
4. AI reasoning vs web search vs Nemotron explicit provider routing.
5. Conversational workspace confirmation for Gaming Mode (yes/no/always/never/cancel/timeout).
6. Security preservation: no popup for conversational confirmation, popup retained for high-risk actions.
7. Spotify launch vs media playback controls.
8. Truthful offline and provider fallback behavior.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.ai.intelligence_router import (
    IntelligenceRouter,
    MODE_FAST_LOCAL,
    MODE_CONTEXT,
    MODE_REASONING,
    LAYER_1,
    LAYER_2,
    LAYER_3
)
from core.ai.provider_manager import ProviderManager
from core.ai.agent_brain import AgentBrain
from core.conversation_manager import ConversationManager
from core.os.workspace_manager import WorkspaceManager
from modules.system.executor import CommandExecutor
from core.jarvis_runtime import JarvisRuntime
from memory.persistent_memory import persistent_memory


class TestPhase5RoutingAndConfirmations(unittest.TestCase):
    """Phase 5 verification test suite."""

    @classmethod
    def setUpClass(cls):
        cls.normalizer = CommandNormalizer()
        cls.intent_engine = IntentEngine()
        cls.router = IntelligenceRouter()
        cls.workspace_mgr = WorkspaceManager()
        cls.executor = CommandExecutor()

    # =========================================================================
    # 1. FIX THE REPEATED GENERIC CAPABILITIES RESPONSE
    # =========================================================================
    def test_time_queries_route_deterministically_to_time_query(self):
        """Verify time queries never get misclassified as help or generic capabilities."""
        time_inputs = [
            "what time is it",
            "Jarvis, what time is it?",
            "tell me what time it is",
            "what time do you have",
            "what is the time",
            "current time",
            "time now"
        ]
        for inp in time_inputs:
            node = self.intent_engine.parse(inp)
            self.assertEqual(node["intent"], "time_query", f"Failed for input: '{inp}'")
            req = self.router.route(inp)
            self.assertEqual(req.layer, LAYER_1, f"Expected Layer 1 for '{inp}'")
            self.assertEqual(req.intent, "TIME_QUERY", f"Expected TIME_QUERY for '{inp}'")

    def test_date_queries_route_deterministically_to_date_query(self):
        """Verify date queries route to date_query in Layer 1."""
        date_inputs = [
            "what is today's date",
            "what date is it",
            "tell me the date",
            "today's date",
            "what day is it"
        ]
        for inp in date_inputs:
            node = self.intent_engine.parse(inp)
            self.assertEqual(node["intent"], "date_query", f"Failed for input: '{inp}'")
            req = self.router.route(inp)
            self.assertEqual(req.layer, LAYER_1, f"Expected Layer 1 for '{inp}'")
            self.assertEqual(req.intent, "DATE_QUERY", f"Expected DATE_QUERY for '{inp}'")

    def test_conversational_questions_not_hijacked_as_help(self):
        """Verify questions starting with 'what do' are not hijacked into help capabilities overview."""
        questions = [
            "what do you think about AI",
            "what do cats eat",
            "what do computers do in sleep mode"
        ]
        for q in questions:
            node = self.intent_engine.parse(q)
            self.assertNotEqual(node["intent"], "help", f"Query '{q}' was hijacked as help intent!")

    def test_explicit_help_queries_trigger_help(self):
        """Verify explicit capability discovery still routes to help."""
        help_inputs = [
            "what can you do",
            "what are your capabilities",
            "show commands",
            "list commands",
            "help"
        ]
        for h in help_inputs:
            node = self.intent_engine.parse(h)
            self.assertEqual(node["intent"], "help", f"Failed for help query: '{h}'")

    def test_offline_reasoning_returns_truthful_message(self):
        """Verify offline reasoning returns truthful status instead of generic capabilities dump."""
        brain = AgentBrain()
        res = brain._handle_offline_reasoning("Explain quantum physics", time.time())
        self.assertNotIn("I can control applications, Chrome, files", res["text"])
        self.assertIn("cannot perform AI reasoning while offline", res["text"])

    # =========================================================================
    # 2. COMMAND ROUTING: APP vs WEB SEARCH vs BROWSER-SPECIFIC vs YOUTUBE
    # =========================================================================
    def test_open_applications(self):
        """Verify explicit application launches resolve to open_app with exact target."""
        test_apps = [
            ("Open Chrome", "chrome"),
            ("Open Brave", "brave"),
            ("Open Spotify", "spotify"),
            ("Open Visual Studio Code", "vscode")
        ]
        for inp, expected_target in test_apps:
            node = self.intent_engine.parse(inp)
            self.assertEqual(node["intent"], "open_app")
            self.assertEqual(node["target"], expected_target)
            req = self.router.route(inp)
            self.assertEqual(req.layer, LAYER_1)
            self.assertEqual(req.mode, MODE_FAST_LOCAL)

    def test_general_web_search(self):
        """Verify general web search routes to Layer 1 web_search with default browser."""
        inp = "Search the web for React hooks"
        node = self.intent_engine.parse(inp)
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node.get("provider"), "google")
        self.assertEqual(node.get("browser"), "default")
        self.assertEqual(node.get("query"), "React hooks")

        req = self.router.route(inp)
        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "WEB_SEARCH")

    def test_browser_specific_search_brave(self):
        """Verify search with explicit browser directs query to requested browser."""
        inp = "Search Brave for NVIDIA news"
        node = self.intent_engine.parse(inp)
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node.get("browser"), "brave")
        self.assertEqual(node.get("query"), "NVIDIA news")

        req = self.router.route(inp)
        self.assertEqual(req.layer, LAYER_1)

    def test_youtube_search_in_specific_browser(self):
        """Verify YouTube search in Chrome selects youtube provider and chrome browser."""
        inp = "Search YouTube for Python tutorials in Chrome"
        node = self.intent_engine.parse(inp)
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node.get("provider"), "youtube")
        self.assertEqual(node.get("browser"), "chrome")
        self.assertEqual(node.get("query"), "Python tutorials")

        req = self.router.route(inp)
        self.assertEqual(req.layer, LAYER_1)

    # =========================================================================
    # 3. AI REASONING vs NEMOTRON vs RESEARCH & EXPLAIN
    # =========================================================================
    def test_ai_reasoning_routes_to_layer_3(self):
        """Verify complex coding / DSA prompt routes to Layer 3 Reasoning."""
        inp = "Explain binary search in C++"
        req = self.router.route(inp)
        self.assertEqual(req.layer, LAYER_3)
        self.assertEqual(req.mode, MODE_REASONING)
        self.assertEqual(req.intent, "COMPLEX_TASK")

    def test_explicit_nemotron_routing(self):
        """Verify 'Ask Nemotron to...' routes to Layer 3 NEMOTRON_REASONING."""
        inp = "Ask Nemotron to explain this algorithm"
        req = self.router.route(inp)
        self.assertEqual(req.layer, LAYER_3)
        self.assertEqual(req.mode, MODE_REASONING)
        self.assertEqual(req.intent, "NEMOTRON_REASONING")
        self.assertEqual(req.entities.get("provider"), "nvidia")

    def test_research_and_explain_not_split_on_and(self):
        """Verify compound research and explain commands are preserved as Layer 3 requests."""
        inp = "Find the latest NVIDIA news online and explain it"
        # Verify multi-command parser does not split into disjoint commands
        chained = self.normalizer.split_chained_commands(inp)
        self.assertEqual(len(chained), 1, f"Query '{inp}' should not be split on 'and'!")

        req = self.router.route(inp)
        self.assertEqual(req.layer, LAYER_3)
        self.assertEqual(req.mode, MODE_REASONING)

    # =========================================================================
    # 4. GAMING MODE CONVERSATIONAL CONFIRMATION & LIFECYCLE
    # =========================================================================
    def test_gaming_mode_prompt_text(self):
        """Verify gaming workspace prompts with exact conversational text."""
        persistent_memory.delete_preference("workspace_gaming_discord")
        res = self.workspace_mgr.execute_workspace("gaming")
        self.assertTrue(res.get("needs_confirmation"))
        self.assertTrue(res.get("is_conversational_confirmation"))
        self.assertEqual(res.get("prompt"), "I'll prepare your gaming setup. Would you like Discord open as well?")

    def test_gaming_mode_no_duplicate_security_dialog(self):
        """Verify conversational confirmation does NOT trigger on_permission_dialog_cb modal popup."""
        persistent_memory.delete_preference("workspace_gaming_discord")
        runtime = JarvisRuntime()

        dialog_mock = MagicMock()
        runtime.on_permission_dialog_cb = dialog_mock

        intent_node = {
            "intent": "workspace.launch",
            "action": "launch",
            "target": "gaming"
        }
        res = runtime._execute_intent(intent_node, confirm=False, speak=False)

        self.assertTrue(res.get("pending_confirmation"))
        self.assertTrue(res.get("is_conversational_confirmation"))
        # Crucial security assertion: dialog MUST NOT be called for conversational confirmation
        dialog_mock.assert_not_called()
        self.assertIsNotNone(runtime.pending_intent)
        self.assertEqual(runtime.pending_intent.get("intent"), "workspace_optional_confirmation")

    def test_genuine_security_action_still_triggers_permission_dialog(self):
        """Verify security-sensitive actions still trigger native modal authorization dialog."""
        runtime = JarvisRuntime()
        dialog_mock = MagicMock()
        runtime.on_permission_dialog_cb = dialog_mock

        # High risk action (e.g. shutdown / command management deletion)
        high_risk_node = {
            "intent": "system_control",
            "action": "shutdown",
            "target": "computer"
        }
        res = runtime._execute_intent(high_risk_node, confirm=False, speak=False)
        self.assertTrue(res.get("pending_confirmation"))
        self.assertFalse(res.get("is_conversational_confirmation", False))
        dialog_mock.assert_called_once()

    def test_gaming_mode_confirmation_flow_yes(self):
        """Verify answering 'yes' confirms Discord and completes gaming workspace."""
        persistent_memory.delete_preference("workspace_gaming_discord")
        runtime = JarvisRuntime()

        # Step 1: Start gaming mode
        intent_node = {"intent": "workspace.launch", "target": "gaming", "action": "launch"}
        runtime._execute_intent(intent_node, confirm=False, speak=False)
        self.assertIsNotNone(runtime.pending_intent)

        # Step 2: User responds "yes"
        with patch("core.os.workspace_manager.workspace_manager.execute_workspace", return_value={"success": True, "message": "Gaming workspace is ready."}) as mock_exec:
            runtime._process_command_worker("yes")
            mock_exec.assert_called_once_with("gaming", confirmed_optional_ids=["discord"])
            self.assertIsNone(runtime.pending_intent)

    def test_gaming_mode_confirmation_flow_no(self):
        """Verify answering 'no' declines Discord and completes gaming workspace."""
        persistent_memory.delete_preference("workspace_gaming_discord")
        runtime = JarvisRuntime()

        intent_node = {"intent": "workspace.launch", "target": "gaming", "action": "launch"}
        runtime._execute_intent(intent_node, confirm=False, speak=False)
        self.assertIsNotNone(runtime.pending_intent)

        with patch("core.os.workspace_manager.workspace_manager.execute_workspace", return_value={"success": True, "message": "Gaming workspace is ready."}) as mock_exec:
            runtime._process_command_worker("no")
            mock_exec.assert_called_once_with("gaming", declined_optional_ids=["discord"])
            self.assertIsNone(runtime.pending_intent)

    def test_gaming_mode_confirmation_flow_always(self):
        """Verify answering 'always' persists preference to persistent_memory."""
        persistent_memory.delete_preference("workspace_gaming_discord")
        runtime = JarvisRuntime()

        intent_node = {"intent": "workspace.launch", "target": "gaming", "action": "launch"}
        runtime._execute_intent(intent_node, confirm=False, speak=False)

        with patch("core.os.workspace_manager.workspace_manager.execute_workspace", return_value={"success": True, "message": "Gaming workspace is ready."}) as mock_exec:
            runtime._process_command_worker("always")
            mock_exec.assert_called_once_with("gaming", always_optional_ids=["discord"])
            self.assertIsNone(runtime.pending_intent)

    def test_gaming_mode_confirmation_flow_never(self):
        """Verify answering 'never' persists preference to persistent_memory."""
        persistent_memory.delete_preference("workspace_gaming_discord")
        runtime = JarvisRuntime()

        intent_node = {"intent": "workspace.launch", "target": "gaming", "action": "launch"}
        runtime._execute_intent(intent_node, confirm=False, speak=False)

        with patch("core.os.workspace_manager.workspace_manager.execute_workspace", return_value={"success": True, "message": "Gaming workspace is ready."}) as mock_exec:
            runtime._process_command_worker("never")
            mock_exec.assert_called_once_with("gaming", never_optional_ids=["discord"])
            self.assertIsNone(runtime.pending_intent)

    def test_gaming_mode_confirmation_cancellation(self):
        """Verify answering 'cancel' aborts workspace execution cleanly."""
        persistent_memory.delete_preference("workspace_gaming_discord")
        runtime = JarvisRuntime()

        intent_node = {"intent": "workspace.launch", "target": "gaming", "action": "launch"}
        runtime._execute_intent(intent_node, confirm=False, speak=False)
        self.assertIsNotNone(runtime.pending_intent)

        runtime._process_command_worker("cancel")
        self.assertIsNone(runtime.pending_intent)
        self.assertIn("cancelled", runtime.current_speech_text.lower())

    def test_gaming_mode_confirmation_ambiguous_reply(self):
        """Verify ambiguous reply prompts short clarification without discarding pending state."""
        persistent_memory.delete_preference("workspace_gaming_discord")
        runtime = JarvisRuntime()

        intent_node = {"intent": "workspace.launch", "target": "gaming", "action": "launch"}
        runtime._execute_intent(intent_node, confirm=False, speak=False)
        self.assertIsNotNone(runtime.pending_intent)

        runtime._process_command_worker("maybe later today")
        self.assertIsNotNone(runtime.pending_intent)
        self.assertIn("reply with yes, no, always, or never", runtime.current_speech_text)

    def test_gaming_mode_confirmation_timeout(self):
        """Verify pending confirmation expires after 60 seconds timeout."""
        runtime = JarvisRuntime()
        runtime.pending_intent = {
            "intent": "workspace_optional_confirmation",
            "workspace_id": "gaming",
            "optional_id": "discord",
            "timestamp": time.time() - 65.0  # 65 seconds ago
        }
        # Subsequent command should detect timeout and discard stale pending intent
        runtime._process_command_worker("what time is it")
        self.assertIsNone(runtime.pending_intent)

    # =========================================================================
    # 5. SPOTIFY LAUNCH vs PLAYBACK MEDIA CONTROL
    # =========================================================================
    def test_spotify_launch_distinguished_from_playback(self):
        """Verify launching Spotify is distinct from media playback controls."""
        launch_node = self.intent_engine.parse("Open Spotify")
        self.assertEqual(launch_node["intent"], "open_app")
        self.assertEqual(launch_node["target"], "spotify")

        play_node1 = self.intent_engine.parse("Play music")
        self.assertEqual(play_node1["intent"], "media_control")
        self.assertEqual(play_node1["action"], "play_pause")

        play_node2 = self.intent_engine.parse("Play Spotify")
        self.assertEqual(play_node2["intent"], "media_control")
        self.assertEqual(play_node2["action"], "play_pause")

        next_node = self.intent_engine.parse("Next song")
        self.assertEqual(next_node["intent"], "media_control")
        self.assertEqual(next_node["action"], "next_track")


if __name__ == "__main__":
    unittest.main()
