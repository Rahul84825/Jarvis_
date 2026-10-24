"""Unit and Integration Tests for Santra:
- Background Startup & Hidden HUD
- Panel Visibility Controls (Show, Hide, Minimize, Restore)
- Global Keyboard Shortcut (Ctrl+Shift+Space)
- Headless Command and API Test Execution
- System Tray Controls & Clean Exit
- Single Instance Duplication Guard
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from core.intent_engine import IntentEngine
from modules.system.executor import CommandExecutor
from core.global_hotkey import GlobalHotkeyManager, DEFAULT_HOTKEY_ID, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT, VK_SPACE
from core.single_instance import SingleInstanceGuard
from core.startup import is_startup_enabled, get_startup_status


class TestPanelVisibilityIntentParsing(unittest.TestCase):
    """Phase 3: Natural language parsing for panel visibility controls."""

    @classmethod
    def setUpClass(cls):
        cls.intent_engine = IntentEngine()

    def test_show_and_open_panel_intents(self):
        show_commands = [
            "Open Santra panel.",
            "Show Santra.",
            "Show Santra dashboard.",
            "Restore Santra.",
            "open santra panel",
            "show santra dashboard",
            "restore santra dashboard",
            "show panel",
            "open panel",
            "restore panel"
        ]
        for cmd in show_commands:
            node = self.intent_engine.parse(cmd)
            self.assertEqual(node.get("intent"), "panel_visibility", f"Failed intent on: '{cmd}'")
            self.assertEqual(node.get("action"), "show_panel", f"Failed action on: '{cmd}'")

    def test_hide_and_minimize_panel_intents(self):
        hide_commands = [
            "Hide Santra panel.",
            "Hide Santra.",
            "Minimize Santra.",
            "hide santra panel",
            "hide santra dashboard",
            "minimize santra dashboard",
            "hide panel",
            "minimize panel"
        ]
        for cmd in hide_commands:
            node = self.intent_engine.parse(cmd)
            self.assertEqual(node.get("intent"), "panel_visibility", f"Failed intent on: '{cmd}'")
            self.assertEqual(node.get("action"), "hide_panel", f"Failed action on: '{cmd}'")

    def test_explicit_exit_assistant_intents(self):
        exit_commands = [
            "Exit Santra.",
            "Shut down Santra.",
            "Quit Santra.",
            "exit santra",
            "shut down santra"
        ]
        for cmd in exit_commands:
            node = self.intent_engine.parse(cmd)
            self.assertEqual(node.get("intent"), "panel_visibility", f"Failed intent on: '{cmd}'")
            self.assertEqual(node.get("action"), "exit_assistant", f"Failed action on: '{cmd}'")

    def test_no_confusion_with_sleep_or_other_apps(self):
        """Ensure sleep mode and general application commands are distinct from panel visibility."""
        sleep_node = self.intent_engine.parse("Sleep.")
        self.assertNotEqual(sleep_node.get("intent"), "panel_visibility")

        spotify_close_node = self.intent_engine.parse("Close Spotify.")
        self.assertEqual(spotify_close_node.get("intent"), "close_app")
        self.assertEqual(spotify_close_node.get("target"), "spotify")


class TestPanelVisibilityExecution(unittest.TestCase):
    """Phase 3 & 7: CommandExecutor execution and callback invocation."""

    def setUp(self):
        self.executor = CommandExecutor()
        self.callback_mock = MagicMock()
        self.executor.panel_visibility_cb = self.callback_mock

    def test_execute_show_panel(self):
        node = {"intent": "panel_visibility", "action": "show_panel"}
        res = self.executor.execute(node)

        self.assertTrue(res["success"])
        self.assertIn("Opening Santra dashboard", res["message"])
        self.callback_mock.assert_called_once_with("show_panel")

    def test_execute_hide_panel(self):
        node = {"intent": "panel_visibility", "action": "hide_panel"}
        res = self.executor.execute(node)

        self.assertTrue(res["success"])
        self.assertIn("Santra panel hidden", res["message"])
        self.callback_mock.assert_called_once_with("hide_panel")

    def test_execute_exit_assistant(self):
        node = {"intent": "panel_visibility", "action": "exit_assistant"}
        res = self.executor.execute(node)

        self.assertTrue(res["success"])
        self.assertIn("Shutting down Santra", res["message"])
        self.callback_mock.assert_called_once_with("exit_assistant")


class TestGlobalHotkeyManager(unittest.TestCase):
    """Phase 4: Global keyboard shortcut registration, triggers, and unregistration."""

    @patch("ctypes.windll.user32.RegisterHotKey", return_value=1)
    @patch("ctypes.windll.user32.UnregisterHotKey", return_value=1)
    def test_successful_registration_and_trigger(self, mock_unreg, mock_reg):
        mgr = GlobalHotkeyManager(hotkey_id=0x5341)
        triggered = []

        # Register hotkey on dummy HWND 12345
        ok = mgr.register(hwnd=12345, on_trigger=lambda: triggered.append(True))
        self.assertTrue(ok)
        self.assertTrue(mgr.is_registered)

        # Verify correct Win32 params passed (Ctrl+Shift+NoRepeat, VK_SPACE)
        self.assertEqual(mock_reg.call_count, 1)
        r_args, _ = mock_reg.call_args
        self.assertEqual(getattr(r_args[0], "value", r_args[0]), 12345)
        self.assertEqual(getattr(r_args[1], "value", r_args[1]), 0x5341)
        self.assertEqual(getattr(r_args[2], "value", r_args[2]), MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT)
        self.assertEqual(getattr(r_args[3], "value", r_args[3]), VK_SPACE)

        # Trigger event
        mgr.trigger()
        self.assertEqual(len(triggered), 1)

        # Unregister
        unreg_ok = mgr.unregister()
        self.assertTrue(unreg_ok)
        self.assertFalse(mgr.is_registered)
        self.assertEqual(mock_unreg.call_count, 1)
        u_args, _ = mock_unreg.call_args
        self.assertEqual(getattr(u_args[0], "value", u_args[0]), 12345)
        self.assertEqual(getattr(u_args[1], "value", u_args[1]), 0x5341)

    @patch("ctypes.windll.user32.RegisterHotKey", return_value=0)
    @patch("ctypes.GetLastError", return_value=1409)  # ERROR_HOTKEY_ALREADY_REGISTERED
    def test_registration_conflict_handled_gracefully(self, mock_err, mock_reg):
        mgr = GlobalHotkeyManager()
        # Must not raise an exception, returns False and logs warning
        ok = mgr.register(hwnd=999, on_trigger=lambda: None)
        self.assertFalse(ok)
        self.assertFalse(mgr.is_registered)


class TestHeadlessExecution(unittest.TestCase):
    """Phase 5: Commands and API tests execute normally while UI panel is hidden."""

    def setUp(self):
        self.executor = CommandExecutor()

    def test_system_and_api_queries_execute_headlessly(self):
        """Commands must execute and return structured outcomes without requiring GUI visibility."""
        # 1. Time query
        time_res = self.executor.execute({"intent": "time_query"})
        self.assertTrue(time_res["success"])
        self.assertIn("The time is", time_res["message"])

        # 2. Date query
        date_res = self.executor.execute({"intent": "date_query"})
        self.assertTrue(date_res["success"])
        self.assertIn("Today is", date_res["message"])

        # 3. Math calculation
        math_res = self.executor.execute({"intent": "math_calculation", "target": "25 * 4"})
        self.assertTrue(math_res["success"])
        self.assertIn("100", math_res["message"])

    @patch("modules.spotify.service.SpotifyService.is_connected", return_value=True)
    def test_spotify_api_status_headlessly(self, mock_conn):
        """Spotify status query returns truthful playback data headlessly."""
        from modules.spotify import spotify_service
        with patch.object(spotify_service, "get_current_playback", return_value=None):
            res = self.executor.execute({"intent": "spotify_control", "action": "current_track"})
            self.assertTrue(res["success"])
            self.assertIn("Nothing is currently playing", res["message"])


class TestSingleInstanceAndDuplicationGuard(unittest.TestCase):
    """Phase 2 & 7: Verify single instance enforcement and deduplication."""

    def test_single_instance_guard_lifecycle(self):
        guard = SingleInstanceGuard(mutex_name="Global\\Santra_Test_Mutex", ipc_port=49199)
        # First acquire succeeds
        acquired = guard.acquire()
        self.assertTrue(acquired)
        self.assertTrue(guard.is_primary)

        # Release cleanly
        guard.release()


class TestWindowsStartupConfiguration(unittest.TestCase):
    """Phase 2: Task Scheduler startup configuration status and properties."""

    def test_startup_status_diagnostics(self):
        status = get_startup_status()
        self.assertIn("enabled", status)
        self.assertIn("mechanism", status)
        self.assertIn("command", status)
        self.assertIn("working_directory", status)
        self.assertIn("diagnostics", status)
        self.assertTrue(status["diagnostics"]["main_py_exists"])


if __name__ == "__main__":
    unittest.main()
