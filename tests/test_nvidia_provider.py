"""Comprehensive Unit, Routing, Conversation, and Tool-Calling Tests for NVIDIA Nemotron Integration.

Verifies:
A. Provider Tests (mocked HTTP client, status codes 200, 401, 429, 500, timeouts, redactions)
B. Routing Tests (deterministic Layer 1 preservation, Layer 2 local conversation, Layer 3 Nemotron)
C. Contextual Conversation Tests (multi-turn follow-ups, session memory, history bounds)
D. Controlled Tool-Calling Tests (schema validation, SafetyGate permission checks, ReAct loop)
E. Privacy & Security Tests (STRICT blocks cloud, GUARDED redacts nvapi- keys)
F. Live Integration Smoke Test (executes live query only if NVIDIA_API_KEY is configured in env)
"""

import os
import time
import json
import unittest
from unittest.mock import patch, MagicMock

from config import config
from core.ai.providers.nvidia_provider import NvidiaNemotronProvider
from core.ai.provider_manager import ProviderManager
from core.ai.intelligence_router import IntelligenceRouter, MODE_FAST_LOCAL, MODE_CONTEXT, MODE_REASONING, LAYER_1, LAYER_2, LAYER_3
from core.conversation_manager import ConversationManager
from core.ai.agent_brain import AgentBrain
from core.security.privacy_guard import PrivacyGuard, PrivacyMode
from core.tool_safety_gate import tool_safety_gate


class TestNvidiaNemotronProvider(unittest.TestCase):
    """A. Provider Unit Tests (Fully Mocked)."""

    def setUp(self):
        self.provider = NvidiaNemotronProvider(
            api_key="nvapi-test-dummy-mock-key-for-unit-testing",
            model="nvidia/nemotron-3.5-super-vl-120b-a12b",
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=5.0,
            max_retries=2
        )

    def test_provider_initialization_and_defaults(self):
        self.assertEqual(self.provider.model, "nvidia/nemotron-3.5-super-vl-120b-a12b")
        self.assertEqual(self.provider.base_url, "https://integrate.api.nvidia.com/v1")
        self.assertTrue(self.provider.is_available())
        self.assertIn("Nemotron", self.provider.get_name())

    def test_missing_api_key_handling(self):
        empty_provider = NvidiaNemotronProvider(api_key="")
        with patch.object(config, "nvidia_api_key", ""), patch.dict(os.environ, {"NVIDIA_API_KEY": ""}):
            self.assertFalse(empty_provider.is_available())
            res = empty_provider.generate_response([{"role": "user", "content": "hello"}])
            self.assertIsNone(res)

    @patch("requests.post")
    def test_successful_reasoning_generation(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Binary search has O(log n) time complexity.",
                        "reasoning_content": "User asked for binary search complexity. Drafting answer..."
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        res = self.provider.generate_response([{"role": "user", "content": "What is the complexity of binary search?"}])
        self.assertEqual(res, "Binary search has O(log n) time complexity.")
        self.assertTrue(mock_post.called)

    @patch("requests.post")
    def test_authentication_error_401_no_retry(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized: Invalid API Key"
        mock_post.return_value = mock_resp

        res = self.provider.generate_response([{"role": "user", "content": "test"}])
        self.assertIsNone(res)
        # Should not retry 401
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.post")
    @patch("time.sleep")
    def test_rate_limiting_429_bounded_retry(self, mock_sleep, mock_post):
        resp_429 = MagicMock(status_code=429, text="Rate limit exceeded")
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {
            "choices": [{"message": {"content": "Recovered answer"}}]
        }
        mock_post.side_effect = [resp_429, resp_200]

        res = self.provider.generate_response([{"role": "user", "content": "test"}])
        self.assertEqual(res, "Recovered answer")
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("requests.post")
    @patch("time.sleep")
    def test_timeout_and_network_error_recovery(self, mock_sleep, mock_post):
        import requests
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {
            "choices": [{"message": {"content": "Answer after timeout"}}]
        }
        mock_post.side_effect = [requests.exceptions.Timeout("Read timed out"), resp_200]

        res = self.provider.generate_response([{"role": "user", "content": "test"}])
        self.assertEqual(res, "Answer after timeout")
        self.assertEqual(mock_post.call_count, 2)

    @patch("requests.post")
    def test_tool_calling_openai_format_parsing(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1234",
                                "type": "function",
                                "function": {
                                    "name": "open_application",
                                    "arguments": '{"application": "spotify"}'
                                }
                            }
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        res = self.provider.generate_response([{"role": "user", "content": "Open Spotify"}])
        self.assertIn("Action: open_application", res)
        self.assertIn('"application": "spotify"', res)

    def test_safe_logging_does_not_reveal_keys(self):
        key = "nvapi-secret-private-credential-value"
        p = NvidiaNemotronProvider(api_key=key)
        sanitized = p._sanitize_error_message(f"Connection failed with Bearer {key} to endpoint")
        self.assertNotIn(key, sanitized)
        self.assertIn("[REDACTED_NVIDIA_KEY]", sanitized)


class TestNvidiaRoutingAndIntelligence(unittest.TestCase):
    """B. Routing and Intelligence Router Tests."""

    def setUp(self):
        self.router = IntelligenceRouter()
        self.pm = ProviderManager()

    def test_deterministic_layer1_commands_remain_local(self):
        commands = [
            ("open chrome", "OPEN_APP", LAYER_1),
            ("close spotify", "CLOSE_APP", LAYER_1),
            ("take a screenshot", "SCREENSHOT", LAYER_1),
            ("what time is it", "TIME_QUERY", LAYER_1),
        ]
        for cmd, expected_intent, expected_layer in commands:
            req = self.router.route(cmd)
            self.assertEqual(req.layer, expected_layer, f"Command '{cmd}' failed layer expectation.")
            self.assertEqual(req.intent, expected_intent, f"Command '{cmd}' failed intent expectation.")

    def test_local_conversation_layer2_remains_local(self):
        conversational = [
            ("hello jarvis", "GREETING", LAYER_1),
            ("tell me a joke", "SOCIAL_HUMOR", LAYER_1),
            ("who are you", "IDENTITY", LAYER_1),
        ]
        for query, expected_intent, expected_layer in conversational:
            req = self.router.route(query)
            self.assertEqual(req.layer, expected_layer)

    def test_complex_reasoning_and_dsa_routes_to_layer3(self):
        reasoning_queries = [
            "Explain binary search in C++ with an example",
            "Why does my remove-duplicates algorithm fail",
            "Compare merge sort and quicksort",
            "Explain this error and suggest a fix",
            "What is the time complexity of quicksort",
            "Explain LeetCode 26 in C++",
        ]
        for q in reasoning_queries:
            req = self.router.route(q)
            self.assertEqual(req.layer, LAYER_3, f"Query '{q}' did not route to Layer 3 Reasoning.")

    def test_explicit_nvidia_and_nemotron_prefix_routing(self):
        p1, clean1 = self.pm.extract_model_prefix("nemotron: Explain Dijkstra's algorithm")
        self.assertEqual(p1, "nvidia")
        self.assertEqual(clean1, "Explain Dijkstra's algorithm")

        p2, clean2 = self.pm.extract_model_prefix("nvidia: Compare BFS and DFS")
        self.assertEqual(p2, "nvidia")
        self.assertEqual(clean2, "Compare BFS and DFS")

        req = self.router.route("nemotron: solve two sum in C++")
        self.assertEqual(req.layer, LAYER_3)
        self.assertEqual(req.intent, "NEMOTRON_REASONING")

    def test_active_provider_key_resolves_nvidia(self):
        with patch.object(config, "ai_provider", "nvidia"):
            self.assertEqual(self.pm.active_provider_key, "nvidia")
            prov = self.pm.get_provider("nvidia")
            self.assertIsInstance(prov, NvidiaNemotronProvider)


class TestContextualConversation(unittest.TestCase):
    """C. Contextual Conversation & Follow-up Tests."""

    def setUp(self):
        self.cm = ConversationManager(max_turns=5, session_timeout=60.0)

    def test_multi_turn_history_preservation(self):
        mock_provider = MagicMock()
        mock_provider.generate_response.side_effect = [
            "Binary search repeatedly divides the search interval in half.",
            "Here is the recursive implementation in C++: int binarySearch(int arr[], int l, int r, int x)..."
        ]

        with patch.object(self.cm, "provider_manager", mock_provider):
            res1 = self.cm.process_query("Explain binary search")
            self.assertIn("Binary search", res1["text"])
            self.assertEqual(len(self.cm.history), 2)  # 1 user + 1 assistant

            res2 = self.cm.process_query("Now show the recursive version in C++")
            self.assertIn("recursive implementation in C++", res2["text"])
            self.assertEqual(len(self.cm.history), 4)  # 2 user + 2 assistant

    def test_history_bounds_enforced(self):
        mock_provider = MagicMock()
        mock_provider.generate_response.return_value = "Response content."

        with patch.object(self.cm, "provider_manager", mock_provider):
            for i in range(15):
                self.cm.process_query(f"Question {i}")
            # Max turns is 5 -> history length is at most max_turns * 2 = 10
            self.assertLessEqual(len(self.cm.history), 10)

    def test_session_clear(self):
        self.cm.history.append({"role": "user", "content": "test"})
        self.cm.clear_session()
        self.assertEqual(len(self.cm.history), 0)


class TestControlledToolCalling(unittest.TestCase):
    """D. Safe Tool-Calling and SafetyGate Tests."""

    def setUp(self):
        self.brain = AgentBrain()

    def test_registered_tools_contain_core_capabilities(self):
        self.assertIn("open_application", self.brain.tools)
        self.assertIn("close_application", self.brain.tools)
        self.assertIn("chrome_open_url", self.brain.tools)

    def test_safety_gate_blocks_prohibited_tools(self):
        # Destructive or high-risk actions without approval
        allowed, reason = tool_safety_gate.evaluate_tool("format_hard_drive")
        self.assertFalse(allowed)

    @patch.object(ProviderManager, "generate_response")
    @patch.object(ProviderManager, "is_ai_available", return_value=True)
    def test_brain_react_step_tool_execution(self, mock_avail, mock_gen):
        # Model returns tool call, then final answer
        mock_gen.side_effect = [
            'Action: open_application\nAction Input: {"application": "notepad"}',
            'Final Answer: Notepad has been opened for you, Sir.'
        ]

        with patch.object(tool_safety_gate, "_allow_writes", True):
            with patch.dict(self.brain.tools, {"open_application": {"func": MagicMock(return_value={"success": True, "message": "Opened notepad"}), "description": "test"}}):
                res = self.brain.reason_and_execute("Open Notepad please")
                self.assertEqual(res["text"], "Notepad has been opened for you, Sir.")
                self.assertIn("open_application", res["tools_executed"])


class TestPrivacyAndSecurity(unittest.TestCase):
    """E. Privacy Modes and Secret Redaction Tests."""

    def test_nvidia_api_key_redaction(self):
        guard = PrivacyGuard(mode=PrivacyMode.GUARDED)
        sample = "NVIDIA key: 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 in prompt"
        redacted, count, types = guard.redact_text(sample)
        self.assertNotIn("nvapi-", redacted)
        self.assertIn("[REDACTED_NVIDIA_KEY]", redacted)
        self.assertGreater(count, 0)

    def test_strict_privacy_mode_blocks_nvidia_cloud_request(self):
        pm = ProviderManager()
        with patch("core.security.privacy_guard.privacy_guard.is_cloud_allowed", return_value=False):
            with patch.object(config, "ai_provider", "nvidia"):
                # STRICT mode blocks external cloud calls
                res = pm.generate_response([{"role": "user", "content": "Explain quantum computing"}])
                self.assertIsNone(res)


class TestNvidiaLiveSmokeTest(unittest.TestCase):
    """F. Optional Live Integration Smoke Test (Only runs if real NVIDIA_API_KEY is configured)."""

    def test_live_nemotron_reasoning_if_configured(self):
        key = getattr(config, "nvidia_api_key", "") or os.environ.get("NVIDIA_API_KEY", "")
        if not key or not key.startswith("nvapi-") or len(key) < 20:
            self.skipTest("NVIDIA_API_KEY not configured or placeholder. Skipping live smoke test.")

        provider = NvidiaNemotronProvider(
            api_key=key,
            model=getattr(config, "nvidia_model", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
            base_url=getattr(config, "nvidia_base_url", "https://integrate.api.nvidia.com/v1"),
            timeout=30.0,
            max_retries=2
        )

        # 1. Health check
        healthy = provider.health_check()
        self.assertTrue(healthy, "Live NVIDIA health check failed.")

        # 2. Reasoning query
        t0 = time.time()
        res = provider.generate_response(
            messages=[
                {"role": "user", "content": "In one concise sentence, what is time complexity in computer science?"}
            ]
        )
        duration_s = time.time() - t0

        self.assertIsNotNone(res, "Live response should not be None.")
        self.assertIsInstance(res, str)
        self.assertTrue(len(res.strip()) > 10, "Live response should be non-trivial.")
        print(f"\n[LIVE SMOKE TEST PASSED] Model: {provider.model} | Duration: {duration_s:.2f}s | Output: {res.strip()[:100]}...")


if __name__ == "__main__":
    unittest.main()
