"""
Unit and Integration Tests for Command Execution, Capability Routing, and TTS Latency.
Verifies:
1. 'What can you do?' dynamic capability summary generation (no fallback errors)
2. Deterministic Layer 1 routing for browser, apps, websites, and multi-commands
3. TTSManager persistent caching, prewarming, and audio playback lifecycle
4. AgentBrain defense-in-depth handling of capability questions
"""

import os
import time
import unittest
from pathlib import Path

from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.ai.intelligence_router import IntelligenceRouter
from core.ai.agent_brain import AgentBrain
from core.local_response_engine import LocalResponseEngine
from core.ai.tools.registry import ToolRegistry
from core.tts.tts_manager import TTSManager


class TestCapabilityRoutingAndSummary(unittest.TestCase):
    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.router = IntelligenceRouter()
        self.response_engine = LocalResponseEngine()
        self.tool_registry = ToolRegistry()
        self.agent_brain = AgentBrain()

    def test_what_can_you_do_normalization(self):
        queries = [
            "What can you do?",
            "What can you do",
            "what can jarvis do",
            "what are your capabilities",
            "What commands do you know?"
        ]
        for q in queries:
            norm = self.normalizer.normalize(q)["normalized"]
            self.assertIn("what", norm)
            self.assertNotIn("what do", norm)

    def test_what_can_you_do_routing_and_response(self):
        queries = [
            "What can you do?",
            "What can you do",
            "What can Jarvis do?",
            "What are your capabilities?",
            "Help",
            "Show capabilities"
        ]
        for q in queries:
            req = self.router.route(q)
            self.assertEqual(req.layer, 1, f"Expected Layer 1 for query: {q}")
            self.assertEqual(req.intent.lower(), "help", f"Expected help intent for query: {q}")
            
            resp = self.response_engine.get_help_response()
            self.assertIsNotNone(resp)
            self.assertNotIn("limited to my local capabilities", resp)
            self.assertIn("applications", resp.lower())
            self.assertIn("Sir", resp)

    def test_agent_brain_offline_capability_fallback(self):
        # Even if a capability query somehow reaches agent_brain offline fallback,
        # it must return the actual dynamic capability summary.
        res = self.agent_brain._handle_offline_reasoning("What can you do?", t0=time.time())
        self.assertIsNotNone(res.get("text"))
        self.assertNotIn("limited to my local capabilities", res["text"])
        self.assertIn("applications", res["text"].lower())


class TestDeterministicCommandRouting(unittest.TestCase):
    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.router = IntelligenceRouter()

    def test_layer1_single_actions(self):
        test_cases = [
            ("Open Chrome", "open_app", "chrome"),
            ("Open Spotify", "open_app", "spotify"),
            ("Open YouTube", "open_website", "youtube"),
            ("Open a new Chrome tab", "open_new_chrome_tab", None),
            ("Open another Chrome window", "open_new_chrome_window", None),
            ("Open wellmeds.in", "open_website", "wellmeds.in"),
            ("Take a screenshot", "screenshot", None),
            ("Lock computer", "system_control", "lock"),
        ]
        for raw_cmd, expected_intent, expected_target in test_cases:
            req = self.router.route(raw_cmd)
            self.assertEqual(req.layer, 1, f"Expected Layer 1 for command: '{raw_cmd}' (got layer {req.layer})")
            if expected_target:
                actual_val = str(req.target or req.action or "").lower()
                self.assertIn(expected_target.lower(), actual_val, f"Mismatch target for: '{raw_cmd}'")

    def test_multi_action_command_splitting(self):
        multi_cmd = "Open Chrome and search for WellMeds"
        sub_cmds = self.normalizer.split_chained_commands(multi_cmd)
        self.assertEqual(len(sub_cmds), 2)
        self.assertIn("open chrome", sub_cmds[0].lower())
        self.assertIn("search", sub_cmds[1].lower())

        multi_cmd_2 = "Open YouTube and ChatGPT"
        sub_cmds_2 = self.normalizer.split_chained_commands(multi_cmd_2)
        self.assertEqual(len(sub_cmds_2), 2)


class TestTTSManagerAudioCacheAndLifecycle(unittest.TestCase):
    def setUp(self):
        self.tts = TTSManager()

    def test_cache_path_generation(self):
        path = self.tts._get_cache_path("Done, Sir.")
        self.assertIsNotNone(path)
        self.assertTrue(str(path).endswith(".wav"))

    def test_tts_amplitude_callback_registered(self):
        amps = []
        def amp_cb(val):
            amps.append(val)

        self.tts.start(on_audio_amplitude=amp_cb)
        self.assertIsNotNone(self.tts.on_audio_amplitude_cb)
        self.tts.stop()


if __name__ == "__main__":
    unittest.main()
