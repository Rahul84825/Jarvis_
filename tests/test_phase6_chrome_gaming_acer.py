"""Comprehensive Regression and Integration Test Suite for JARVIS Phase 6:
- Part 1: Specific Chrome Tab Closing & Disambiguation (Tab vs Window vs App)
- Part 2: Gaming Mode Confirmation Lifecycle, Execution Resumption & Idempotency
- Part 3: Valorant Launcher Discovery, Process Verification & State Distinction
- Part 4: Windows Power Schemes (read-back verification) & Acer OEM Truthful Boundaries
"""

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.os.browser_manager import BrowserManager
from core.os.power_manager import PowerManager, AcerOEMAdapter
from core.os.workspace_manager import WorkspaceManager
from core.platform.windows_platform import WindowsPlatform
from memory.persistent_memory import persistent_memory
from modules.system.executor import CommandExecutor


class TestChromeTabClosing(unittest.TestCase):
    """Part 1: Chrome tab closing by active state, unique title, ordinal, and window disambiguation."""

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.browser_mgr = BrowserManager()

    def test_close_current_tab_intent(self):
        """Verifies 'close current chrome tab' routes to browser_tab_control with active tab_target."""
        phrase = "close current chrome tab"
        norm = self.normalizer.normalize(phrase)["normalized"]
        node = self.intent_engine.parse(norm, raw_text=phrase)
        self.assertEqual(node["intent"], "browser_tab_control")
        self.assertEqual(node["action"], "close_tab")
        self.assertEqual(node["tab_target"], "active")

    def test_close_ordinal_tab_intent(self):
        """Verifies 'close the second Chrome tab' routes to browser_tab_control with ordinal position."""
        phrase = "close the second chrome tab"
        norm = self.normalizer.normalize(phrase)["normalized"]
        node = self.intent_engine.parse(norm, raw_text=phrase)
        self.assertEqual(node["intent"], "browser_tab_control")
        self.assertEqual(node["action"], "close_tab")
        self.assertEqual(self.browser_mgr._resolve_ordinal(node["tab_target"]), 1)

    def test_close_named_tab_intent(self):
        """Verifies 'close the YouTube tab' routes to browser_tab_control with tab_target."""
        phrase = "close the YouTube tab"
        norm = self.normalizer.normalize(phrase)["normalized"]
        node = self.intent_engine.parse(norm, raw_text=phrase)
        self.assertEqual(node["intent"], "browser_tab_control")
        self.assertEqual(node["action"], "close_tab")
        self.assertEqual(node["tab_target"].lower(), "youtube")

    def test_close_descriptive_tab_intent(self):
        """Verifies 'close the tab showing my WellMeds dashboard' routes to browser_tab_control."""
        phrase = "close the tab showing my WellMeds dashboard"
        norm = self.normalizer.normalize(phrase)["normalized"]
        node = self.intent_engine.parse(norm, raw_text=phrase)
        self.assertEqual(node["intent"], "browser_tab_control")
        self.assertEqual(node["action"], "close_tab")
        self.assertIn("wellmeds dashboard", node["tab_target"].lower())

    def test_distinguish_tab_vs_window_vs_app(self):
        """Strictly ensures closing a tab, closing a window, and terminating Chrome are distinguished."""
        node_tab = self.intent_engine.parse("close active tab")
        self.assertEqual(node_tab["intent"], "browser_tab_control")

        node_window = self.intent_engine.parse("close the chrome window")
        self.assertEqual(node_window["intent"], "window_control")
        self.assertEqual(node_window["action"], "close")

        node_app = self.intent_engine.parse("close chrome")
        self.assertEqual(node_app["intent"], "close_app")
        self.assertEqual(node_app["target"], "chrome")

    @patch("core.os.browser_manager.CDPClient")
    def test_close_tab_by_unique_title_execution(self, mock_cdp_cls):
        """Verifies closing a specific tab via CDP targets only that tab and verifies closure."""
        mock_cdp = mock_cdp_cls.return_value
        mock_cdp.list_tabs.return_value = [
            {"id": "tab1", "title": "YouTube - Lo-Fi Beats", "url": "https://youtube.com/watch?v=1", "type": "page"},
            {"id": "tab2", "title": "GitHub - Repo", "url": "https://github.com/my-repo", "type": "page"}
        ]
        mock_cdp.close_tab.return_value = True
        mock_cdp.verify_tab_closed.return_value = True

        mgr = BrowserManager()
        mgr.cdp = mock_cdp

        res = mgr.close_tab(target="YouTube")
        self.assertTrue(res["success"])
        self.assertEqual(res["tab_id"], "tab1")
        mock_cdp.close_tab.assert_called_with("tab1")
        mock_cdp.verify_tab_closed.assert_called_with("tab1")

    @patch("core.os.browser_manager.CDPClient")
    def test_close_tab_multiple_matches_disambiguation(self, mock_cdp_cls):
        """Verifies that multiple tabs matching the query prompt for disambiguation."""
        mock_cdp = mock_cdp_cls.return_value
        mock_cdp.list_tabs.return_value = [
            {"id": "tab1", "title": "YouTube - Lo-Fi", "url": "https://youtube.com/1", "type": "page"},
            {"id": "tab2", "title": "YouTube - Gaming", "url": "https://youtube.com/2", "type": "page"}
        ]

        mgr = BrowserManager()
        mgr.cdp = mock_cdp

        res = mgr.close_tab(target="YouTube")
        self.assertFalse(res["success"])
        self.assertTrue(res.get("disambiguation_required"))
        self.assertEqual(len(res.get("candidates", [])), 2)
        mock_cdp.close_tab.assert_not_called()

    @patch("core.os.browser_manager.CDPClient")
    def test_close_tab_missing_reports_truthfully(self, mock_cdp_cls):
        """Verifies that attempting to close a non-existent tab reports no matching tab found."""
        mock_cdp = mock_cdp_cls.return_value
        mock_cdp.list_tabs.return_value = [
            {"id": "tab1", "title": "GitHub - Repo", "url": "https://github.com/my-repo", "type": "page"}
        ]

        mgr = BrowserManager()
        mgr.cdp = mock_cdp

        res = mgr.close_tab(target="WellMeds Dashboard")
        self.assertFalse(res["success"])
        self.assertIn("No tab matching", res["message"])
        mock_cdp.close_tab.assert_not_called()


class TestGamingModeConfirmationAndExecution(unittest.TestCase):
    """Part 2: Gaming mode confirmation lifecycle, resumption, and idempotency."""

    def setUp(self):
        self.ws_mgr = WorkspaceManager()
        # Reset any temporary test preferences
        persistent_memory.set_preference("workspace_gaming_discord", None)

    def tearDown(self):
        persistent_memory.set_preference("workspace_gaming_discord", None)

    def test_start_gaming_mode_prompts_for_discord(self):
        """Verifies 'Start gaming mode' prompts for Discord confirmation when no preference is saved."""
        res = self.ws_mgr.execute_workspace("gaming")
        self.assertTrue(res["success"])
        self.assertTrue(res.get("needs_confirmation"))
        self.assertEqual(res.get("workspace_id"), "gaming")
        self.assertEqual(res.get("optional_id"), "discord")
        self.assertIn("Would you like Discord open", res.get("prompt"))

    @patch("modules.system.executor.CommandExecutor.execute")
    def test_confirm_yes_executes_all_configured_actions(self, mock_exec):
        """Verifies replying 'Yes' resumes execution and runs all steps including Discord."""
        mock_exec.return_value = {"success": True, "message": "OK"}

        res = self.ws_mgr.execute_workspace("gaming", confirmed_optional_ids=["discord"])
        self.assertTrue(res["success"])
        self.assertIn("Open Discord", res["completed_steps"])
        self.assertIn("Launch Valorant", res["completed_steps"])
        self.assertEqual(mock_exec.call_count, 3)  # power_plan, valorant, discord

    @patch("modules.system.executor.CommandExecutor.execute")
    def test_confirm_no_skips_discord_and_executes_workspace(self, mock_exec):
        """Verifies replying 'No' skips Discord and executes remaining workspace steps."""
        mock_exec.return_value = {"success": True, "message": "OK"}

        res = self.ws_mgr.execute_workspace("gaming", declined_optional_ids=["discord"])
        self.assertTrue(res["success"])
        self.assertNotIn("Open Discord", res["completed_steps"])
        self.assertIn("Launch Valorant", res["completed_steps"])
        self.assertEqual(mock_exec.call_count, 2)  # power_plan, valorant

    @patch("modules.system.executor.CommandExecutor.execute")
    def test_always_preference_persists_and_auto_runs(self, mock_exec):
        """Verifies 'always' persists preference to persistent_memory and subsequent runs execute Discord without prompting."""
        mock_exec.return_value = {"success": True, "message": "OK"}

        # 1. User says always
        res = self.ws_mgr.execute_workspace("gaming", always_optional_ids=["discord"])
        self.assertTrue(res["success"])
        self.assertFalse(res.get("needs_confirmation", False))
        self.assertIn("Open Discord", res["completed_steps"])

        # Verify persistent memory
        pref = persistent_memory.get_preference("workspace_gaming_discord")
        self.assertEqual(pref, "true")

        # 2. Subsequent launch automatically includes Discord without prompt
        res2 = self.ws_mgr.execute_workspace("gaming")
        self.assertTrue(res2["success"])
        self.assertFalse(res2.get("needs_confirmation", False))
        self.assertIn("Open Discord", res2["completed_steps"])

    @patch("modules.system.executor.CommandExecutor.execute")
    def test_never_preference_persists_and_auto_skips(self, mock_exec):
        """Verifies 'never' persists preference and subsequent runs skip Discord without prompting."""
        mock_exec.return_value = {"success": True, "message": "OK"}

        res = self.ws_mgr.execute_workspace("gaming", never_optional_ids=["discord"])
        self.assertTrue(res["success"])
        self.assertFalse(res.get("needs_confirmation", False))
        self.assertNotIn("Open Discord", res["completed_steps"])

        pref = persistent_memory.get_preference("workspace_gaming_discord")
        self.assertEqual(pref, "false")

        res2 = self.ws_mgr.execute_workspace("gaming")
        self.assertTrue(res2["success"])
        self.assertFalse(res2.get("needs_confirmation", False))
        self.assertNotIn("Open Discord", res2["completed_steps"])

    @patch("modules.system.executor.CommandExecutor.execute")
    def test_idempotency_prevents_duplicate_step_execution(self, mock_exec):
        """Verifies that completed steps are skipped upon resumption."""
        mock_exec.return_value = {"success": True, "message": "OK"}

        # Simulate resume where power_plan was already completed
        res = self.ws_mgr.execute_workspace(
            "gaming",
            confirmed_optional_ids=["discord"],
            completed_step_ids=["power_plan"]
        )
        self.assertTrue(res["success"])
        # Should have executed only valorant and discord
        self.assertEqual(mock_exec.call_count, 2)
        self.assertIn("Set Gaming Power Scheme", res["completed_steps"])
        self.assertIn("Launch Valorant", res["completed_steps"])
        self.assertIn("Open Discord", res["completed_steps"])

    @patch("modules.system.executor.CommandExecutor.execute")
    def test_truthful_partial_success_reporting(self, mock_exec):
        """Verifies that non-critical failures (like Modern Standby power plan) are reported truthfully without failing workspace."""
        def side_effect(node, confirm=False):
            if node["intent"] == "power.scheme":
                return {"success": False, "message": "Windows power scheme 'High Performance' is not available."}
            return {"success": True, "message": "OK"}

        mock_exec.side_effect = side_effect

        res = self.ws_mgr.execute_workspace("gaming", confirmed_optional_ids=["discord"])
        self.assertTrue(res["success"])
        self.assertIn("Launch Valorant", res["completed_steps"])
        self.assertIn("Open Discord", res["completed_steps"])
        self.assertEqual(len(res["failed_steps"]), 1)
        self.assertIn("Optional items skipped", res["message"])
        self.assertIn("High Performance", res["message"])


class TestValorantAndApplications(unittest.TestCase):
    """Part 3: Valorant application discovery, launching, and process verification."""

    def setUp(self):
        self.platform = WindowsPlatform()

    def test_valorant_discovery_finds_official_launcher(self):
        """Verifies ApplicationDiscovery discovers Valorant via official Riot Client path and arguments."""
        from core.apps.application_discovery import app_discovery
        app, cands = app_discovery.find_application("valorant")
        self.assertIsNotNone(app)
        self.assertEqual(app.app_id, "valorant")
        self.assertTrue(app.executable_path.lower().endswith(".exe"))
        self.assertIn("--launch-product=valorant", app.arguments)
        self.assertIn("--launch-patchline=live", app.arguments)

    @patch("psutil.process_iter")
    def test_valorant_already_running_focuses_without_spawning(self, mock_procs):
        """Verifies that if VALORANT is already running, launch_valorant reports running and does not spawn new process."""
        mock_proc = MagicMock()
        mock_proc.info = {"name": "VALORANT-Win64-Shipping.exe"}
        mock_procs.return_value = [mock_proc]

        with patch.object(self.platform, "focus_application", return_value=True) as mock_focus:
            res = self.platform.launch_valorant()
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "running")
            self.assertIn("already running", res["message"])
            mock_focus.assert_called_with("valorant")

    @patch("subprocess.Popen")
    @patch("psutil.process_iter")
    def test_valorant_distinguishes_launcher_vs_game(self, mock_procs, mock_popen):
        """Verifies distinguishing between Riot Client started and game client running."""
        # Scenario A: Riot Client started but game not yet loaded
        proc_rc = MagicMock()
        proc_rc.info = {"name": "RiotClientServices.exe"}
        mock_procs.return_value = [proc_rc]

        res = self.platform.launch_valorant()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "launcher_started")
        self.assertIn("Riot Client started", res["message"])

        # Scenario B: Game client running
        proc_val = MagicMock()
        proc_val.info = {"name": "VALORANT.exe"}
        mock_procs.return_value = [proc_val]

        res2 = self.platform.launch_valorant()
        self.assertTrue(res2["success"])
        self.assertEqual(res2["status"], "running")

    def test_unavailable_app_reports_precise_limitation(self):
        """Verifies that launching a non-existent app reports truthful limitation without false success."""
        from modules.system.app_control import launch_application
        res = launch_application("non_existent_fake_app_xyz")
        self.assertFalse(res["success"])
        self.assertEqual(res["outcome"], "UNSUPPORTED_CAPABILITY")
        self.assertIn("couldn't find an application", res["message"])


class TestPowerAndAcerOEMControls(unittest.TestCase):
    """Part 4: Windows power schemes, Acer OEM profile boundaries, and battery telemetry."""

    def setUp(self):
        self.power_mgr = PowerManager()
        self.acer_adapter = AcerOEMAdapter()

    def test_windows_power_schemes_list(self):
        """Queries actual power schemes via powercfg."""
        schemes = self.power_mgr.list_power_schemes()
        self.assertIsInstance(schemes, list)
        self.assertGreater(len(schemes), 0)
        self.assertTrue(any(s["is_active"] for s in schemes))

    def test_windows_power_scheme_read_back_verification(self):
        """Verifies that setting a scheme verifies read-back GUID."""
        active = self.power_mgr.get_active_scheme()
        self.assertIsNotNone(active)

        # Set currently active scheme by name
        res = self.power_mgr.set_power_scheme(active["name"])
        self.assertTrue(res["success"])
        self.assertTrue(res.get("verified"))
        self.assertEqual(res["guid"].lower(), active["guid"].lower())

    def test_windows_power_scheme_unavailable_reports_schemes(self):
        """Verifies that requesting an unavailable scheme reports available schemes and keeps active plan."""
        res = self.power_mgr.set_power_scheme("Ultra Extreme Nonexistent Scheme")
        self.assertFalse(res["success"])
        self.assertFalse(res.get("verified"))
        self.assertIn("Available schemes", res["message"])
        self.assertIn("Balanced", res["message"])

    def test_acer_oem_adapter_supported_is_false(self):
        """Confirms honest hardware boundary: public APIs do not support direct ACPI writes."""
        self.assertFalse(self.acer_adapter.is_supported())

    def test_acer_oem_profile_setting_boundary(self):
        """Verifies attempting to set an Acer OEM profile explains that direct ACPI writes are not supported."""
        res = self.acer_adapter.set_oem_profile("Performance")
        self.assertFalse(res["success"])
        self.assertFalse(res["supported"])
        self.assertIn("Direct switching to Acer OEM 'Performance' profile is not supported", res["message"])
        self.assertEqual(res["recommended_action"], "launch_control_center")

    def test_acer_oem_invalid_profile(self):
        """Verifies invalid profile names are caught and supported profiles are listed."""
        res = self.acer_adapter.set_oem_profile("TurboOverclock")
        self.assertFalse(res["success"])
        self.assertIn("Supported profiles: Performance, Entertainment, Quiet, Power-saving", res["message"])

    def test_battery_threshold_setting_boundary(self):
        """Verifies attempting to set battery threshold to 80% reports unchanged and directs to OEM app."""
        res = self.acer_adapter.set_battery_threshold(80)
        self.assertFalse(res["success"])
        self.assertFalse(res["supported"])
        self.assertEqual(res["threshold"], "Unchanged")
        self.assertIn("80%", res["message"])
        self.assertIn("remains unchanged", res["message"])

    def test_comprehensive_status_discrete_fields(self):
        """Verifies get_comprehensive_status returns distinct truthful fields."""
        status = self.power_mgr.get_comprehensive_status(app_states={"valorant": "Running", "discord": "Not Running"})
        self.assertIn("active_windows_power_plan", status)
        self.assertIn("active_acer_oem_profile", status)
        self.assertIn("battery_percentage", status)
        self.assertIn("battery_charging_status", status)
        self.assertIn("configured_battery_charging_threshold", status)
        self.assertIn("valorant_launch_status", status)
        self.assertIn("discord_launch_status", status)

        self.assertEqual(status["active_acer_oem_profile"], "Unknown / Unverified (OEM only)")
        self.assertEqual(status["configured_battery_charging_threshold"], "Unknown / Unverified (OEM only)")
        self.assertEqual(status["valorant_launch_status"], "Running")
        self.assertEqual(status["discord_launch_status"], "Not Running")


if __name__ == "__main__":
    unittest.main()
