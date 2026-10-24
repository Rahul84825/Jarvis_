"""Comprehensive Test Suite for Chrome Page Analysis, CDP Repair,
and Wake-Word State Management (Phase 8 Regression Tests).
Covers:
- Commands without wake word while awake (Standby).
- Wake-word activation while sleeping.
- Wake word plus trailing command.
- Duplicate wake and transcription suppression.
- Chrome already open with CDP available (mocked server).
- Chrome already open without CDP (diagnostics & fallback).
- Port conflicts and stale endpoints.
- Bounded connection timeouts.
- Correct active tab identification, URL, title extraction.
- DOM and accessibility extraction.
- Screenshot/OCR fallback.
- Multi-tier page analysis.
"""

import unittest
from unittest.mock import MagicMock, patch
import time
import json
import http.server
import threading
import socket

from core.os.cdp_client import CDPClient
from core.os.browser_manager import BrowserManager
from core.intent_engine import intent_engine
from core.ai.intelligence_router import intelligence_router
from core.jarvis_runtime import JarvisRuntime


class MockCDPHandler(http.server.BaseHTTPRequestHandler):
    """Mock Chrome DevTools Protocol HTTP server."""
    
    def log_message(self, format, *args):
        pass  # Suppress server logging during tests

    def do_GET(self):
        if self.path == "/json/version":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "Browser": "Chrome/124.0.6367.60",
                "Protocol-Version": "1.3",
                "User-Agent": "Mozilla/5.0 Chrome",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser"
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        elif self.path == "/json/list":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            tabs = [
                {
                    "id": "tab-101",
                    "title": "GitHub - Repository",
                    "url": "https://github.com/Rahul84825/Jarvis_",
                    "type": "page",
                    "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/tab-101"
                },
                {
                    "id": "tab-102",
                    "title": "Python Tutorials",
                    "url": "https://docs.python.org/3/",
                    "type": "page"
                }
            ]
            self.wfile.write(json.dumps(tabs).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class MockNonCDPConflictHandler(http.server.BaseHTTPRequestHandler):
    """Mock non-CDP HTTP server on debugging port simulating port conflict."""
    
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Generic HTTP Server - Not CDP")


class TestCDPRepairAndDiagnostics(unittest.TestCase):
    """Unit tests for CDP client repair, diagnostics, and error handling."""

    @classmethod
    def setUpClass(cls):
        # Pick free ephemeral port for mock CDP server
        cls.mock_port = 9333
        cls.server = http.server.HTTPServer(("127.0.0.1", cls.mock_port), MockCDPHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_cdp_available_when_mock_server_running(self):
        cdp = CDPClient(port=self.mock_port)
        self.assertTrue(cdp.is_available())
        diag = cdp.get_endpoint_diagnostics()
        self.assertTrue(diag["cdp_available"])
        self.assertEqual(diag["status"], "online")
        self.assertIn("Chrome/124", diag["browser_version"])

    def test_cdp_list_tabs_and_active_tab(self):
        cdp = CDPClient(port=self.mock_port)
        tabs = cdp.list_tabs()
        self.assertEqual(len(tabs), 2)
        active = cdp.get_active_tab()
        self.assertIsNotNone(active)
        self.assertEqual(active["title"], "GitHub - Repository")
        self.assertEqual(active["url"], "https://github.com/Rahul84825/Jarvis_")

    def test_cdp_offline_when_port_closed(self):
        # Port 9999 is closed
        cdp = CDPClient(port=9999)
        self.assertFalse(cdp.is_available())
        with patch.object(cdp, "is_chrome_running", return_value=True):
            diag = cdp.get_endpoint_diagnostics()
            self.assertFalse(diag["cdp_available"])
            self.assertTrue(diag["chrome_running"])
            self.assertEqual(diag["status"], "chrome_running_no_cdp")
            self.assertEqual(diag["guidance"], "Chrome is open, but this session does not expose a local debugging endpoint.")

    def test_cdp_port_conflict_detection(self):
        conflict_port = 9334
        conflict_server = http.server.HTTPServer(("127.0.0.1", conflict_port), MockNonCDPConflictHandler)
        t = threading.Thread(target=conflict_server.serve_forever, daemon=True)
        t.start()
        try:
            cdp = CDPClient(port=conflict_port)
            diag = cdp.get_endpoint_diagnostics()
            self.assertFalse(diag["cdp_available"])
            self.assertTrue(diag["port_conflict"])
            self.assertEqual(diag["status"], "port_conflict")
            self.assertEqual(diag["guidance"], "The debugging port is already in use by another process.")
        finally:
            conflict_server.shutdown()
            conflict_server.server_close()

    def test_cdp_bounded_connection_timeout(self):
        cdp = CDPClient(port=9998)
        cdp.timeout = 0.2
        t0 = time.time()
        res = cdp.is_available()
        elapsed = time.time() - t0
        self.assertFalse(res)
        self.assertLess(elapsed, 0.5)


class TestChromePageAnalysisMultiTier(unittest.TestCase):
    """Unit tests for BrowserManager multi-tier page analysis."""

    def setUp(self):
        self.browser_mgr = BrowserManager()

    def test_tier1_cdp_page_analysis(self):
        # Mock CDP returning active page with headings and text
        mock_cdp = MagicMock()
        mock_cdp.inspect_active_page.return_value = {
            "success": True,
            "cdp_available": True,
            "title": "Documentation - Python 3.12",
            "url": "https://docs.python.org/3.12/",
            "headings": ["What's New In Python 3.12", "Tutorial", "Library Reference"],
            "content": "Python is an easy to learn, powerful programming language with efficient high-level data structures.",
            "source": "cdp",
            "message": "Active page inspected."
        }
        self.browser_mgr.cdp = mock_cdp
        res = self.browser_mgr.analyze_active_page()
        self.assertTrue(res["success"])
        self.assertEqual(res["source"], "cdp")
        self.assertEqual(res["title"], "Documentation - Python 3.12")
        self.assertEqual(len(res["headings"]), 3)

    def test_tier2_accessibility_tree_fallback_when_cdp_offline(self):
        # Mock CDP offline
        mock_cdp = MagicMock()
        mock_cdp.inspect_active_page.return_value = {
            "success": False,
            "cdp_available": False,
            "chrome_running": True,
            "message": "Chrome is open, but this session does not expose a local debugging endpoint."
        }
        self.browser_mgr.cdp = mock_cdp

        # Mock desktop context returning accessible Chrome document
        mock_ctrl = MagicMock()
        mock_ctrl.name = "Address and search bar"
        mock_ctrl.current_value = "https://news.ycombinator.com"
        mock_ctrl.control_type = "edit"

        mock_doc = MagicMock()
        mock_doc.name = "Hacker News Content"
        mock_doc.current_value = "Hacker News new | past | comments | ask | show | jobs | submit 1. Show HN: AI Assistant"
        mock_doc.control_type = "document"

        mock_ctx = MagicMock()
        mock_ctx.window_title = "Hacker News - Google Chrome"
        mock_ctx.process_name = "chrome.exe"
        mock_ctx.available_targets = [mock_ctrl, mock_doc]

        with patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context", return_value=mock_ctx):
            res = self.browser_mgr.analyze_active_page()
            self.assertTrue(res["success"])
            self.assertEqual(res["source"], "accessibility")
            self.assertEqual(res["title"], "Hacker News")
            self.assertIn("Hacker News", res["content"])

    def test_tier4_screen_ocr_fallback_when_accessibility_empty(self):
        mock_cdp = MagicMock()
        mock_cdp.inspect_active_page.return_value = {
            "success": False,
            "cdp_available": False,
            "chrome_running": True,
            "message": "Chrome is open, but this session does not expose a local debugging endpoint."
        }
        mock_cdp.get_endpoint_diagnostics.return_value = {
            "cdp_available": False,
            "chrome_running": True,
            "port_conflict": False,
            "status": "chrome_running_no_cdp",
            "guidance": "Chrome is open, but this session does not expose a local debugging endpoint."
        }
        self.browser_mgr.cdp = mock_cdp

        # Empty accessibility context
        mock_ctx = MagicMock()
        mock_ctx.window_title = "Dashboard - Google Chrome"
        mock_ctx.process_name = "chrome.exe"
        mock_ctx.available_targets = []

        # Mock OCR output
        mock_ocr_res = MagicMock()
        mock_ocr_res.success = True
        mock_ocr_res.text = "System Status: Online CPU Load 12% Memory 4.2GB"
        mock_ocr_res.has_meaningful_content.return_value = True

        with patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context", return_value=mock_ctx):
            with patch("core.vision.screen_capture.screen_capture_manager.capture", return_value=(MagicMock(), "test.png")):
                with patch("core.vision.ocr_engine.ocr_engine.extract_text", return_value=mock_ocr_res):
                    res = self.browser_mgr.analyze_active_page()
                    self.assertTrue(res["success"])
                    self.assertEqual(res["source"], "ocr")
                    self.assertEqual(res["title"], "Dashboard")
                    self.assertIn("System Status: Online", res["content"])


class TestWakeWordAndCommandUnderstandingSemantics(unittest.TestCase):
    """Tests awake vs sleeping semantics, wake-word preservation, and latency."""

    def test_commands_without_wake_word_while_awake(self):
        commands = [
            "Open Chrome.",
            "Analyze this page.",
            "Explain what is on this screen.",
            "Search this website for Naruto.",
            "Create a Python file.",
            "Save it in my DSA folder."
        ]
        for cmd in commands:
            req = intelligence_router.route(cmd)
            self.assertEqual(req.layer, 1, f"Command '{cmd}' should route to Layer 1 Fast Local")
            self.assertEqual(req.mode, "FAST_LOCAL")

    def test_wake_acknowledgment_when_name_spoken_alone(self):
        for name_phrase in ["Santra", "hey santra", "samtra"]:
            req = intelligence_router.route(name_phrase)
            self.assertEqual(req.layer, 1, f"Phrase '{name_phrase}' should be fast local layer 1")
            self.assertEqual(req.mode, "FAST_LOCAL")
            self.assertIn(req.intent, ["STATUS_REQUEST", "GREETING"])

    def test_wake_with_trailing_command(self):
        req = intelligence_router.route("Santra, open Chrome.")
        self.assertEqual(req.intent, "OPEN_APP")
        self.assertEqual(req.action, "open")
        self.assertEqual(req.target, "chrome")

    def test_sleep_transition_command(self):
        req = intelligence_router.route("Santra, go to sleep.")
        self.assertEqual(req.intent, "SYSTEM_CONTROL")
        self.assertEqual(req.action, "sleep_assistant")

    def test_sleeping_state_guards_background_speech(self):
        runtime = JarvisRuntime()
        runtime.enter_sleep_mode(speak=False)
        self.assertEqual(runtime.current_status, "SLEEPING")

        # Ordinary speech while sleeping must NOT execute commands
        with patch.object(runtime, "process_command") as mock_proc:
            runtime._process_command_worker("open chrome")
            # Should be rejected
            mock_proc.assert_not_called()
        self.assertEqual(runtime.current_status, "SLEEPING")

        # Wake phrase while sleeping wakes assistant and preserves trailing command
        with patch.object(runtime, "wake_up") as mock_wake:
            with patch.object(runtime, "process_command") as mock_proc:
                runtime._process_command_worker("Santra open Chrome")
                mock_wake.assert_called_once()
                mock_proc.assert_called_once_with("open Chrome")

    def test_duplicate_utterance_suppression(self):
        runtime = JarvisRuntime()
        # First request
        self.assertFalse(runtime._is_duplicate_request("open chrome"))
        # Second immediate duplicate request (< 1.2s)
        self.assertTrue(runtime._is_duplicate_request("open chrome"))


class TestDeterministicCommandLatency(unittest.TestCase):
    """Verifies that all deterministic commands execute in < 25ms."""

    def test_deterministic_routing_latency(self):
        test_commands = [
            "Open Chrome.",
            "Analyze this page.",
            "Explain what is on this screen.",
            "Search this website for Naruto.",
            "Create a Python file.",
            "Save it in my DSA folder.",
            "Santra, open Chrome.",
            "Santra, go to sleep."
        ]
        # Warmup
        intelligence_router.route("warmup")

        latencies = []
        for cmd in test_commands:
            t0 = time.perf_counter()
            req = intelligence_router.route(cmd)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            self.assertEqual(req.layer, 1, f"Command '{cmd}' must execute in Layer 1 Fast Local")
            self.assertLess(elapsed_ms, 25.0, f"Command '{cmd}' took {elapsed_ms:.2f}ms (>25ms)")

        median_ms = sorted(latencies)[len(latencies) // 2]
        self.assertLess(median_ms, 15.0, f"Median latency {median_ms:.2f}ms exceeds 15ms target")


if __name__ == "__main__":
    unittest.main()
