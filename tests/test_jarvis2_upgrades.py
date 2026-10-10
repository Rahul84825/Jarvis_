from pathlib import Path
import unittest
import os
import sys

# Ensure jarvis root is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.speech_sanitizer import sanitize_speech_text, enforce_conversational_brevity
from core.tool_safety_gate import ToolSafetyGate, tool_safety_gate
from core.ai.mcp_bridge import MCPBridge, mcp_bridge
from modules.browser.cdp_chrome import CDPChromeManager, cdp_chrome
from core.tts.providers.elevenlabs_provider import ElevenLabsProvider
from core.tts.tts_manager import TTSManager


class TestJarvis2Upgrades(unittest.TestCase):

    def test_speech_sanitizer_markdown_and_urls(self):
        raw = """### Latest News
- [BBC News](https://www.bbc.com): Market is up by 5% today!
Check `code snippet` and https://example.com for more details."""
        clean = sanitize_speech_text(raw)
        self.assertNotIn("https://", clean)
        self.assertNotIn("###", clean)
        self.assertNotIn("`", clean)
        self.assertIn("BBC News", clean)
        self.assertIn("5 percent", clean)

    def test_speech_sanitizer_brevity(self):
        long_text = "Sentence one. Sentence two! Sentence three? Sentence four."
        brev = enforce_conversational_brevity(long_text, max_sentences=2)
        self.assertEqual(brev, "Sentence one. Sentence two!")

    def test_tool_safety_gate_safe_mode(self):
        gate = ToolSafetyGate(allow_writes=False)
        self.assertTrue(gate.decide_tool("search_web"))
        self.assertTrue(gate.decide_tool("get_weather"))
        self.assertTrue(gate.decide_tool("get_system_status"))
        self.assertTrue(gate.decide_tool("list_directory"))

        self.assertFalse(gate.decide_tool("send_email"))
        self.assertFalse(gate.decide_tool("run_terminal_command"))
        self.assertFalse(gate.decide_tool("delete_file"))

    def test_tool_safety_gate_write_mode(self):
        gate = ToolSafetyGate(allow_writes=True)
        self.assertTrue(gate.decide_tool("send_email"))
        self.assertTrue(gate.decide_tool("run_terminal_command"))
        self.assertTrue(gate.decide_tool("delete_file"))

    def test_mcp_bridge_loading(self):
        bridge = MCPBridge()
        servers = bridge.get_configured_servers()
        self.assertIsInstance(servers, dict)
        self.assertIn(bridge.has_claude_cli(), (True, False))

    def test_cdp_chrome_manager(self):
        mgr = CDPChromeManager(port=9222)
        self.assertIn(mgr.is_available(), (True, False))
        tabs = mgr.list_tabs()
        self.assertIsInstance(tabs, list)

    def test_elevenlabs_provider_registered_in_tts_manager(self):
        tts = TTSManager()
        self.assertIn("elevenlabs", tts._providers)
        self.assertIsInstance(tts._providers["elevenlabs"], ElevenLabsProvider)


if __name__ == "__main__":
    unittest.main()
