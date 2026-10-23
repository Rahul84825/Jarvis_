"""Automated regression test suite for JARVIS Track B:
Social Intelligence, Natural Conversation, Personality Engine & Dynamic Help.
"""

import unittest
from unittest.mock import MagicMock, patch

from config import config, Config
from core.social_engine import social_engine
from core.intent_engine import IntentEngine
from core.ai.intelligence_router import intelligence_router, MODE_FAST_LOCAL, MODE_CONTEXT
from core.capability_service import capability_service
from core.tool_registry import tool_registry
from core.command_normalizer import CommandNormalizer


class TestIdentityAndSelfAwareness(unittest.TestCase):
    """Verifies truthful, honest identity and self-awareness responses without hallucinations."""

    def setUp(self):
        self.original_creator = config.creator_name
        self.original_name = config.assistant_name

    def tearDown(self):
        config.creator_name = self.original_creator
        config.assistant_name = self.original_name

    def test_configured_assistant_name(self):
        config.assistant_name = "JARVIS"
        res = social_engine.get_identity_response("name")
        self.assertIn("JARVIS", res)

    def test_acronym_stands_for(self):
        res = social_engine.get_identity_response("acronym")
        self.assertIn("Just A Rather Very Intelligent System", res)

    def test_configured_creator_identity(self):
        config.creator_name = "Rahul"
        res = social_engine.get_identity_response("creator")
        self.assertIn("Rahul", res)

    def test_missing_creator_identity_honest_fallback(self):
        config.creator_name = ""
        res = social_engine.get_identity_response("creator")
        self.assertIn("not been configured", res.lower())
        self.assertNotIn("Tony Stark", res)
        self.assertNotIn("OpenAI", res)

    def test_ai_nature_truthful(self):
        res = social_engine.get_identity_response("ai_nature")
        self.assertIn("artificial intelligence", res.lower())
        self.assertIn("not a real human", res.lower())

    def test_chatgpt_difference(self):
        res = social_engine.get_identity_response("chatgpt_comparison")
        self.assertIn("desktop assistant", res.lower())
        self.assertIn("operating system", res.lower())

    def test_truthful_microphone_privacy(self):
        res = social_engine.get_identity_response("listening_privacy")
        self.assertIn("wake-word", res.lower())
        self.assertIn("never streamed or uploaded to the cloud", res.lower())

    def test_truthful_offline_work(self):
        res = social_engine.get_identity_response("offline_work")
        self.assertIn("offline", res.lower())
        self.assertIn("internet", res.lower())

    def test_computer_control_truthful(self):
        res = social_engine.get_identity_response("computer_control")
        self.assertIn("control applications", res.lower())


class TestSocialConversationAndHumor(unittest.TestCase):
    """Verifies greetings, jokes, fun facts, roasts, and casual chit-chat."""

    def setUp(self):
        self.original_tone = config.personality_tone
        self.original_humor = config.humor_enabled
        config.personality_tone = "normal"
        config.humor_enabled = True

    def tearDown(self):
        config.personality_tone = self.original_tone
        config.humor_enabled = self.original_humor

    def test_greetings_variations(self):
        morning = social_engine.get_greeting("morning")
        self.assertIn("morning", morning.lower())

        evening = social_engine.get_greeting("evening")
        self.assertIn("evening", evening.lower())

        how_are_you = social_engine.get_greeting("how_are_you")
        self.assertTrue(len(how_are_you) > 5)

    def test_jokes_categories_and_anti_repetition(self):
        joke1 = social_engine.get_joke("programming")
        self.assertTrue(len(joke1) > 10)

        joke2 = social_engine.get_joke("programming")
        self.assertTrue(len(joke2) > 10)
        # Verify anti-repetition doesn't immediately repeat the exact same joke if pool > 1
        if len(social_engine.jokes["programming"]) > 1:
            self.assertNotEqual(joke1, joke2)

    def test_dark_joke_restrained(self):
        joke = social_engine.get_joke("dark")
        self.assertTrue(len(joke) > 5)
        # Should be restrained, non-graphic
        self.assertNotIn("kill", joke.lower())

    def test_fun_facts(self):
        fact = social_engine.get_fun_fact()
        self.assertIn("fact", fact.lower())
        self.assertTrue(len(fact) > 20)

    def test_playful_roast(self):
        roast = social_engine.get_roast("user")
        self.assertTrue(len(roast) > 10)

    def test_roast_my_code_prompts_for_code(self):
        roast_code = social_engine.get_roast("code")
        self.assertIn("code", roast_code.lower())
        self.assertIn("snippet", roast_code.lower())

    def test_casual_bored_prompt(self):
        reply = social_engine.get_casual_reply("bored")
        self.assertTrue("joke" in reply.lower() or "fact" in reply.lower() or "bored" in reply.lower())

    def test_can_you_hear_me(self):
        reply = social_engine.get_casual_reply("can_you_hear_me")
        self.assertIn("hear you", reply.lower())


class TestPersonalityAndTone(unittest.TestCase):
    """Verifies personality tone changes, response length, and humor toggles."""

    def setUp(self):
        self.original_tone = config.personality_tone
        self.original_length = config.response_length
        self.original_humor = config.humor_enabled

    def tearDown(self):
        config.personality_tone = self.original_tone
        config.response_length = self.original_length
        config.humor_enabled = self.original_humor

    def test_update_tone_modes(self):
        msg_prof = social_engine.update_tone("professional")
        self.assertEqual(config.personality_tone, "professional")
        self.assertIn("professional", msg_prof.lower())

        msg_funny = social_engine.update_tone("funny")
        self.assertEqual(config.personality_tone, "funny")
        self.assertIn("funny", msg_funny.lower())

        msg_dramatic = social_engine.update_tone("dramatic")
        self.assertEqual(config.personality_tone, "dramatic")
        self.assertIn("dramatic", msg_dramatic.lower())

        msg_normal = social_engine.update_tone("normal")
        self.assertEqual(config.personality_tone, "normal")
        self.assertIn("normal", msg_normal.lower())

    def test_update_length(self):
        msg_concise = social_engine.update_response_length("concise")
        self.assertEqual(config.response_length, "concise")
        self.assertIn("short", msg_concise.lower())

        msg_detailed = social_engine.update_response_length("detailed")
        self.assertEqual(config.response_length, "detailed")
        self.assertIn("detailed", msg_detailed.lower())

    def test_disable_and_enable_humor(self):
        social_engine.toggle_humor(False)
        self.assertFalse(config.humor_enabled)
        # Asking for a joke when disabled returns polite notice
        refusal = social_engine.get_joke()
        self.assertIn("disabled", refusal.lower())

        social_engine.toggle_humor(True)
        self.assertTrue(config.humor_enabled)
        joke = social_engine.get_joke()
        self.assertNotIn("disabled", joke.lower())


class TestDynamicHelpAndCapabilities(unittest.TestCase):
    """Verifies dynamic capability introspection and dynamic help output."""

    def test_dynamic_help_overview(self):
        overview = capability_service.get_help_overview()
        self.assertIn("Core Capabilities", overview)
        self.assertIn("Applications", overview)

    def test_dynamic_help_all_commands_reference(self):
        full_ref = capability_service.get_all_commands_reference()
        self.assertIn("Applications & Desktop Programs", full_ref)
        self.assertIn("Websites & Browser Actions", full_ref)
        self.assertIn("Social Intelligence & Humor", full_ref)
        self.assertIn("Personality & Tone Settings", full_ref)

    def test_scoped_commands(self):
        browser_help = capability_service.get_scoped_commands("browser")
        self.assertIn("Browser", browser_help)

        system_help = capability_service.get_scoped_commands("system")
        self.assertIn("System", system_help)

        social_help = capability_service.get_scoped_commands("social")
        self.assertIn("Social", social_help)

    def test_offline_capabilities(self):
        offline = capability_service.get_offline_capabilities()
        self.assertIn("completely offline", offline.lower())
        self.assertIn("application control", offline.lower())
        self.assertIn("social & personality", offline.lower())
        self.assertIn("web searches", offline.lower())

    def test_specific_capability_explainers(self):
        yt_expl = capability_service.explain_capability("can you search youtube")
        self.assertIn("search youtube", yt_expl.lower())

        app_expl = capability_service.explain_capability("can you open applications")
        self.assertIn("desktop applications", app_expl.lower())

        sys_expl = capability_service.explain_capability("can you control my computer")
        self.assertIn("system volume", sys_expl.lower())

    def test_new_tools_in_registry(self):
        self.assertIsNotNone(tool_registry.get_tool("tell_joke"))
        self.assertIsNotNone(tool_registry.get_tool("fun_fact"))
        self.assertIsNotNone(tool_registry.get_tool("playful_roast"))
        self.assertIsNotNone(tool_registry.get_tool("set_personality"))
        self.assertIsNotNone(tool_registry.get_tool("dynamic_help"))


class TestIntentClassificationAndRoutingPrecedence(unittest.TestCase):
    """Verifies intent engine and 3-layer router classification and command precedence."""

    def setUp(self):
        self.intent_engine = IntentEngine()
        self.normalizer = CommandNormalizer()

    def test_identity_queries_parsed(self):
        res1 = self.intent_engine.parse("who are you")
        self.assertEqual(res1["intent"], "identity")

        res2 = self.intent_engine.parse("what does jarvis stand for")
        self.assertEqual(res2["intent"], "identity")
        self.assertEqual(res2["sub_type"], "acronym")

        res3 = self.intent_engine.parse("who built you")
        self.assertEqual(res3["intent"], "identity")
        self.assertEqual(res3["sub_type"], "creator")

        res4 = self.intent_engine.parse("are you a real person")
        self.assertEqual(res4["intent"], "identity")
        self.assertEqual(res4["sub_type"], "ai_nature")

    def test_humor_queries_parsed(self):
        res1 = self.intent_engine.parse("tell me a programming joke")
        self.assertEqual(res1["intent"], "social_humor")
        self.assertEqual(res1["action"], "tell_joke")
        self.assertEqual(res1["category"], "programming")

        res2 = self.intent_engine.parse("roast me")
        self.assertEqual(res2["intent"], "social_humor")
        self.assertEqual(res2["action"], "roast")

        res3 = self.intent_engine.parse("tell me a fun fact")
        self.assertEqual(res3["intent"], "social_humor")
        self.assertEqual(res3["action"], "fun_fact")

    def test_personality_queries_parsed(self):
        res1 = self.intent_engine.parse("be more funny")
        self.assertEqual(res1["intent"], "social_personality")
        self.assertEqual(res1["action"], "set_tone")
        self.assertEqual(res1["tone"], "funny")

        res2 = self.intent_engine.parse("be professional")
        self.assertEqual(res2["intent"], "social_personality")
        self.assertEqual(res2["action"], "set_tone")
        self.assertEqual(res2["tone"], "professional")

        res3 = self.intent_engine.parse("keep it short")
        self.assertEqual(res3["intent"], "social_personality")
        self.assertEqual(res3["action"], "set_length")
        self.assertEqual(res3["length"], "concise")

        res4 = self.intent_engine.parse("don't tell jokes for now")
        self.assertEqual(res4["intent"], "social_personality")
        self.assertEqual(res4["action"], "toggle_humor")
        self.assertFalse(res4["humor"])

    def test_explicit_commands_retain_precedence(self):
        # Explicit app command must NOT be treated as social
        res = self.intent_engine.parse("open chrome")
        self.assertEqual(res["intent"], "open_app")
        self.assertEqual(res["target"], "chrome")

        # Explicit search must NOT be treated as social
        res2 = self.intent_engine.parse("search youtube for react tutorials")
        self.assertEqual(res2["intent"], "web_search")
        self.assertEqual(res2["provider"], "youtube")

        # Greeting with action verb must NOT be swallowed as pure greeting
        res3 = self.intent_engine.parse("hello open chrome")
        self.assertNotEqual(res3["intent"], "greeting")

    def test_router_classifies_social_as_fast_local(self):
        # Social requests route to Layer 1 Fast Local (0 LLM overhead)
        req = intelligence_router.route("who are you")
        self.assertEqual(req.mode, MODE_FAST_LOCAL)
        self.assertEqual(req.intent, "IDENTITY")

        req2 = intelligence_router.route("tell me a joke")
        self.assertEqual(req2.mode, MODE_FAST_LOCAL)
        self.assertEqual(req2.intent, "SOCIAL_HUMOR")

        req3 = intelligence_router.route("what can you do offline")
        self.assertEqual(req3.mode, MODE_FAST_LOCAL)
        self.assertEqual(req3.intent, "HELP")

    def test_contextual_followups(self):
        # "Another one" routes to Layer 2 Context with last_social_type
        req = intelligence_router.route("another one", session_context={"last_action": "joke"})
        self.assertEqual(req.mode, MODE_CONTEXT)
        self.assertEqual(req.intent, "SOCIAL_HUMOR")

        # Contextual YouTube follow-up
        req2 = intelligence_router.route("find react tutorials", session_context={"last_target": "youtube"})
        self.assertEqual(req2.mode, MODE_CONTEXT)
        self.assertEqual(req2.intent, "WEB_SEARCH")
        self.assertEqual(req2.entities.get("provider"), "youtube")


class TestOfflineIndependence(unittest.TestCase):
    """Verifies that all social, identity, humor, and help features execute without AI keys or network."""

    def test_social_works_with_no_ai_provider(self):
        orig = config.ai_provider
        config.ai_provider = "none"
        try:
            # Identity
            self.assertTrue(len(social_engine.get_identity_response("name")) > 0)
            self.assertTrue(len(social_engine.get_identity_response("creator")) > 0)
            # Greetings
            self.assertTrue(len(social_engine.get_greeting()) > 0)
            # Humor
            self.assertTrue(len(social_engine.get_joke()) > 0)
            self.assertTrue(len(social_engine.get_fun_fact()) > 0)
            self.assertTrue(len(social_engine.get_roast()) > 0)
            # Dynamic Help
            self.assertTrue(len(capability_service.get_help_overview()) > 0)
            self.assertTrue(len(capability_service.get_offline_capabilities()) > 0)
        finally:
            config.ai_provider = orig


class TestRuntimeExecutionAndMultiCommandIntegration(unittest.TestCase):
    """Verifies end-to-end runtime dispatch for social, identity, and chained commands."""

    def test_single_command_identity_dispatch(self):
        from core.jarvis_runtime import JarvisRuntime
        runtime = JarvisRuntime.__new__(JarvisRuntime)
        runtime.response_manager = MagicMock()
        runtime.conversation_manager = MagicMock()
        runtime.conversation_manager.get_context.return_value = {}
        runtime.tts_manager = MagicMock()
        runtime._notify_pipeline_stage = MagicMock()

        # Execute single identity command
        res = runtime._process_single_command("who are you", speak=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "identity")
        runtime.response_manager.conversation.assert_called()

    def test_single_command_joke_dispatch(self):
        from core.jarvis_runtime import JarvisRuntime
        runtime = JarvisRuntime.__new__(JarvisRuntime)
        runtime.response_manager = MagicMock()
        runtime.conversation_manager = MagicMock()
        runtime.conversation_manager.get_context.return_value = {}
        runtime.tts_manager = MagicMock()
        runtime._notify_pipeline_stage = MagicMock()

        res = runtime._process_single_command("tell me a programming joke", speak=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "social_humor")
        runtime.response_manager.conversation.assert_called()

    def test_single_command_personality_dispatch(self):
        from core.jarvis_runtime import JarvisRuntime
        runtime = JarvisRuntime.__new__(JarvisRuntime)
        runtime.response_manager = MagicMock()
        runtime.conversation_manager = MagicMock()
        runtime.conversation_manager.get_context.return_value = {}
        runtime.tts_manager = MagicMock()
        runtime._notify_pipeline_stage = MagicMock()

        res = runtime._process_single_command("be more dramatic", speak=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "social_personality")
        self.assertEqual(config.personality_tone, "dramatic")

    def test_multi_command_be_funny_and_open_chrome(self):
        normalizer = CommandNormalizer()
        chained = normalizer.split_chained_commands("be funny and open chrome")
        self.assertEqual(len(chained), 2)
        self.assertEqual(chained[0], "be funny")
        self.assertEqual(chained[1], "open chrome")


if __name__ == "__main__":
    unittest.main()

