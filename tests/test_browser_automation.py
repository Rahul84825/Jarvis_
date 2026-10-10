import unittest
from unittest.mock import patch, MagicMock
from core.os.browser_manager import BrowserManager
from core.os.cdp_client import CDPClient

class TestBrowserAutomationReliability(unittest.TestCase):
    """Test suite verifying browser automation reliability, CDP availability detection,
    truthful success/failure reporting, and window focus verification before shortcuts.
    """

    def setUp(self):
        self.bm = BrowserManager()
        self.cdp = CDPClient()

    def test_cdp_security_restriction_to_localhost(self):
        """Verifies that CDPClient restricts remote host attempts to loopback (127.0.0.1)."""
        client = CDPClient(host="192.168.1.100")
        self.assertEqual(client.host, "127.0.0.1")
        self.assertEqual(client.base_url, "http://127.0.0.1:9222")

    def test_inspect_page_cdp_offline_returns_actionable_guidance(self):
        """Verifies that inspect_page reports truthful failure with launch guidance when CDP is offline."""
        with patch.object(self.bm.cdp, "is_available", return_value=False):
            res = self.bm.inspect_page()
            self.assertFalse(res["success"])
            self.assertFalse(res["cdp_available"])
            self.assertIn("--remote-debugging-port=9222", res["message"])

    def test_click_element_cdp_offline_does_not_falsely_report_success(self):
        """Verifies that clicking DOM elements reports failure truthfully when CDP is not active."""
        with patch.object(self.bm.cdp, "is_available", return_value=False):
            res = self.bm.click_element("#submit-button")
            self.assertFalse(res["success"])
            self.assertFalse(res["cdp_available"])
            self.assertIn("DOM element interaction requires", res["message"])

    def test_tab_actions_fail_gracefully_when_browser_cannot_be_focused(self):
        """Verifies that shortcut-based tab operations do NOT send blind global keystrokes
        if no browser window can be focused.
        """
        with patch.object(self.bm.cdp, "is_available", return_value=False), \
             patch.object(self.bm, "focus_browser", return_value=False), \
             patch.object(self.bm, "_send_shortcut") as mock_shortcut:

            res_new = self.bm.new_tab()
            self.assertFalse(res_new["success"])
            self.assertIn("No active browser window", res_new["message"])
            mock_shortcut.assert_not_called()

            res_close = self.bm.close_tab()
            self.assertFalse(res_close["success"])
            mock_shortcut.assert_not_called()

            res_reopen = self.bm.reopen_closed_tab()
            self.assertFalse(res_reopen["success"])
            mock_shortcut.assert_not_called()

            res_next = self.bm.next_tab()
            self.assertFalse(res_next["success"])
            mock_shortcut.assert_not_called()

    def test_youtube_control_fails_safely_when_unfocused(self):
        """Verifies that YouTube media control aborts safely if browser is not focused."""
        with patch.object(self.bm, "focus_browser", return_value=False), \
             patch.object(self.bm, "_send_shortcut") as mock_shortcut:

            res = self.bm.youtube_control("pause")
            self.assertFalse(res["success"])
            self.assertIn("No active browser window found", res["message"])
            mock_shortcut.assert_not_called()

    def test_cdp_when_available_handles_tabs(self):
        """Verifies that when CDP is responding, tab listing and inspection succeed."""
        mock_tabs = [
            {"id": "tab-1", "title": "GitHub", "url": "https://github.com", "type": "page"},
            {"id": "tab-2", "title": "YouTube", "url": "https://youtube.com", "type": "page"}
        ]
        with patch.object(self.bm.cdp, "is_available", return_value=True), \
             patch.object(self.bm.cdp, "list_tabs", return_value=mock_tabs):

            res = self.bm.list_tabs()
            self.assertTrue(res["success"])
            self.assertEqual(res["count"], 2)
            self.assertIn("GitHub", res["message"])

if __name__ == "__main__":
    unittest.main()
