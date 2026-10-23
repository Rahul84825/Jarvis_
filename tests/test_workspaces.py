"""Tests for Track 4 & Track 5 Personal Workspaces and Windows/Acer Laptop Power Controls.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.os.workspace_manager import WorkspaceManager
from core.os.power_manager import PowerManager
from modules.system.executor import CommandExecutor
from memory.persistent_memory import persistent_memory


class TestWorkspacesAndPower(unittest.TestCase):
    """Test suite for declarative workspaces, interactive optional actions,
    and truthful Windows/Acer power controls.
    """

    def setUp(self):
        self.workspace_mgr = WorkspaceManager()
        self.power_mgr = PowerManager()
        self.executor = CommandExecutor()

    # =========================================================================
    # 1. WORKSPACE DECLARATION & RESOLUTION
    # =========================================================================
    def test_all_five_workspaces_loaded(self):
        """Verify all 5 required personal workspaces are loaded from config."""
        workspaces = self.workspace_mgr.list_workspaces()
        ids = [ws["id"] for ws in workspaces]
        expected = ["development", "gaming", "study", "research", "excel"]
        for exp in expected:
            self.assertIn(exp, ids, f"Expected workspace '{exp}' was not loaded.")

    def test_workspace_alias_resolution(self):
        """Verify natural language aliases resolve to canonical workspaces."""
        aliases_map = {
            "gaming mode": "gaming",
            "start gaming mode": "gaming",
            "game setup": "gaming",
            "dev setup": "development",
            "coding mode": "development",
            "study workspace": "study",
            "learning mode": "study",
            "finance setup": "excel",
            "spreadsheet mode": "excel",
            "research mode": "research"
        }
        for alias, expected_id in aliases_map.items():
            match = self.workspace_mgr.get_workspace(alias)
            self.assertIsNotNone(match, f"Failed to resolve alias '{alias}'")
            self.assertEqual(match[0], expected_id, f"Alias '{alias}' resolved to {match[0]}, expected {expected_id}")

    # =========================================================================
    # 2. INTERACTIVE OPTIONAL ACTIONS (DISCORD IN GAMING)
    # =========================================================================
    def test_gaming_workspace_prompts_for_discord_when_unconfirmed(self):
        """Verify gaming workspace pauses and prompts user for Discord before launching."""
        # Clear any saved preference for testing
        persistent_memory.delete_preference("workspace_gaming_discord")

        res = self.workspace_mgr.execute_workspace("gaming")
        self.assertTrue(res.get("needs_confirmation"))
        self.assertEqual(res.get("optional_id"), "discord")
        self.assertIn("Discord", res.get("prompt", ""))

    def test_gaming_workspace_executes_discord_when_confirmed(self):
        """Verify gaming workspace includes Discord when user confirms."""
        with patch.object(self.workspace_mgr.executor, "execute", return_value={"success": True, "message": "App launched."}) as mock_exec:
            res = self.workspace_mgr.execute_workspace("gaming", confirmed_optional_ids=["discord"])
            self.assertTrue(res.get("success"))
            # Ensure open_app was called for discord
            called_targets = [call.args[0].get("target") for call in mock_exec.call_args_list if "target" in call.args[0]]
            self.assertIn("discord", called_targets)

    def test_gaming_workspace_skips_discord_when_declined(self):
        """Verify gaming workspace skips Discord when user declines."""
        with patch.object(self.workspace_mgr.executor, "execute", return_value={"success": True, "message": "App launched."}) as mock_exec:
            res = self.workspace_mgr.execute_workspace("gaming", declined_optional_ids=["discord"])
            self.assertTrue(res.get("success"))
            # Ensure open_app was NOT called for discord
            called_targets = [call.args[0].get("target") for call in mock_exec.call_args_list if "target" in call.args[0]]
            self.assertNotIn("discord", called_targets)

    def test_saved_preference_skips_interactive_prompt(self):
        """Verify explicitly saved preference skips repetitive confirmation."""
        try:
            persistent_memory.set_preference("workspace_gaming_discord", "false")
            with patch.object(self.workspace_mgr.executor, "execute", return_value={"success": True, "message": "Telemetry checked."}):
                res = self.workspace_mgr.execute_workspace("gaming")
                self.assertFalse(res.get("needs_confirmation", False))
                self.assertTrue(res.get("success"))
        finally:
            persistent_memory.delete_preference("workspace_gaming_discord")

    # =========================================================================
    # 3. STEP EXECUTION & FAILURE RECOVERY
    # =========================================================================
    def test_step_failure_recovery_preserves_completed(self):
        """Verify completed steps are preserved and failure is accurately reported."""
        call_count = [0]
        def mock_step_execute(intent_node, confirm=False):
            call_count[0] += 1
            if intent_node.get("target") == "vscode":
                return {"success": True, "message": "VS Code launched."}
            return {"success": False, "message": "Network error reaching GitHub."}

        with patch.object(self.workspace_mgr.executor, "execute", side_effect=mock_step_execute):
            res = self.workspace_mgr.execute_workspace("development")
            self.assertIn("Development workspace prepared", res.get("message"))
            self.assertIn("Launch VS Code", res.get("message"))
            self.assertEqual(len(res.get("completed_steps")), 1)
            self.assertEqual(len(res.get("failed_steps")), 1)

    # =========================================================================
    # 4. TRUTHFUL WINDOWS & ACER POWER CONTROLS
    # =========================================================================
    def test_power_manager_battery_telemetry(self):
        """Verify battery telemetry query returns structured metrics."""
        telemetry = self.power_mgr.get_battery_telemetry()
        self.assertIn("success", telemetry)
        self.assertIn("message", telemetry)
        self.assertIn("percentage", telemetry)
        self.assertIn("is_charging", telemetry)

    def test_power_manager_truthful_acer_oem_report(self):
        """Verify OEM report truthfully documents Acer hardware and driver interface status."""
        report = self.power_mgr.get_acer_oem_report()
        self.assertIn("AELEN15G52", report["laptop_model"])
        self.assertIn("CCDCHUService", report["integration_status"])
        self.assertIn("Acer Control Center", report["integration_status"])

    def test_executor_handles_workspace_intent(self):
        """Verify CommandExecutor routes workspace.launch correctly."""
        with patch("core.os.workspace_manager.workspace_manager.execute_workspace", return_value={"success": True, "message": "Development workspace launched."}):
            res = self.executor.execute({
                "intent": "workspace.launch",
                "target": "development"
            })
            self.assertTrue(res.get("success"))


if __name__ == "__main__":
    unittest.main()
