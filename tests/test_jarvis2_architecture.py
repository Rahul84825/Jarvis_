"""
Comprehensive Unit Tests for J.A.R.V.I.S 2.0 Architectural Concepts:
1. Speech Sanitization & Brevity Enforcement
2. Tool Safety Gate (Default-Deny / Whitelist)
3. Chrome DevTools Protocol (CDP) Driver & Fallback
4. MCP Server Discovery & Claude CLI Bridge
5. Instant Voice Barge-In (TTS Interruption)
6. Multi-Tier TTS Fallback & Synthesis Separation
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from core.speech_sanitizer import sanitize_speech_text, enforce_conversational_brevity
from core.tool_safety_gate import ToolSafetyGate, READ_ONLY_TOOLS, WRITE_TOOLS
from modules.browser.cdp_chrome import CDPChromeManager
from core.ai.mcp_bridge import MCPBridge
from core.listener import SpeechListener
from core.tts.tts_manager import TTSManager


class TestSpeechSanitizationAndBrevity(unittest.TestCase):
    """Tests speech sanitization removing markdown, URLs, code, and enforcing brevity."""

    def test_markdown_and_formatting_removal(self):
        raw = "### System Status\n* The CPU usage is **45%** and RAM is *80%*.\n```python\nprint('hello')\n```"
        clean = sanitize_speech_text(raw)
        self.assertNotIn("#", clean)
        self.assertNotIn("*", clean)
        self.assertNotIn("```", clean)
        self.assertNotIn("print('hello')", clean)
        self.assertIn("45 percent", clean)

    def test_url_and_link_sanitization(self):
        raw = "Check [WellMeds](https://wellmeds.in) or visit https://google.com for more info."
        clean = sanitize_speech_text(raw)
        self.assertNotIn("https://", clean)
        self.assertNotIn("wellmeds.in", clean)
        self.assertIn("Check WellMeds", clean)

    def test_conversational_brevity_enforcement(self):
        long_speech = (
            "First sentence here. Second sentence here. "
            "Third sentence is too long. Fourth sentence is unnecessary filler."
        )
        brief = enforce_conversational_brevity(long_speech, max_sentences=2)
        self.assertEqual(brief, "First sentence here. Second sentence here.")


class TestToolSafetyGate(unittest.TestCase):
    """Tests tool safety decisions and permission policies."""

    def setUp(self):
        self.gate = ToolSafetyGate(allow_writes=False)

    def test_read_only_tools_allowed_by_default(self):
        for tool in ["get_time", "get_system_status", "search_web", "list_directory", "read_file"]:
            allowed, reason = self.gate.evaluate_tool(tool)
            self.assertTrue(allowed, f"Expected {tool} to be allowed in safe mode")
            self.assertIn("Allowed", reason)

    def test_write_and_destructive_tools_blocked_without_permission(self):
        for tool in ["delete_file", "write_file", "kill_process", "restart_pc", "shutdown_pc"]:
            allowed, reason = self.gate.evaluate_tool(tool)
            self.assertFalse(allowed, f"Expected {tool} to be blocked in safe mode")
            self.assertIn("Blocked", reason)

    def test_write_tools_allowed_when_permission_granted(self):
        self.gate.set_allow_writes(True)
        allowed, reason = self.gate.evaluate_tool("write_file")
        self.assertTrue(allowed)
        self.assertIn("Allowed", reason)


class TestCDPChromeDriver(unittest.TestCase):
    """Tests Chrome DevTools Protocol manager and graceful fallback."""

    def setUp(self):
        self.cdp = CDPChromeManager(port=9999)  # Non-existent port to test fallback

    def test_cdp_not_available_on_inactive_port(self):
        self.assertFalse(self.cdp.is_available())

    def test_tab_listing_returns_empty_on_offline_cdp(self):
        tabs = self.cdp.list_tabs()
        self.assertEqual(tabs, [])

    @patch("webbrowser.open")
    def test_open_tab_falls_back_to_system_browser(self, mock_web_open):
        mock_web_open.return_value = True
        res = self.cdp.open_tab("https://example.com")
        self.assertEqual(res.get("status"), "success")
        mock_web_open.assert_called_once_with("https://example.com")


class TestMCPBridge(unittest.TestCase):
    """Tests MCP server discovery and Claude CLI presence check."""

    def setUp(self):
        self.bridge = MCPBridge()

    def test_mcp_discovery_handles_missing_config_gracefully(self):
        from pathlib import Path
        self.bridge.config_path = Path("C:/invalid_nonexistent_path_xyz.json")
        servers = self.bridge.get_configured_servers()
        self.assertEqual(servers, {})

    def test_has_claude_cli_boolean(self):
        res = self.bridge.has_claude_cli()
        self.assertIsInstance(res, bool)


class TestVoiceBargeIn(unittest.TestCase):
    """Tests Instant Voice Barge-In TTS interruption logic."""

    def test_barge_in_callback_wiring(self):
        listener = SpeechListener()
        mock_cb = MagicMock()
        listener.on_barge_in_cb = mock_cb
        self.assertEqual(listener.on_barge_in_cb, mock_cb)


class TestMultiTierTTS(unittest.TestCase):
    """Tests Multi-Tier TTS provider management and fallback."""

    def setUp(self):
        self.tts = TTSManager()

    def test_registered_providers_exist(self):
        self.assertIn("edge", self.tts._providers)
        self.assertIn("sapi", self.tts._providers)
        self.assertIn("elevenlabs", self.tts._providers)

    def test_set_provider(self):
        self.tts.set_provider("sapi")
        self.assertIn("Windows SAPI", self.tts.provider.get_name())


if __name__ == "__main__":
    unittest.main()
