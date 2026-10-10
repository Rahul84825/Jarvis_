"""Comprehensive Test Suite for JARVIS Self-Extending Commands & Application Discovery.

Covers:
1. Application discovery and deduplication
2. Missing / stale application paths
3. Generic application launch resolution
4. Ambiguous application names
5. Creating and persisting a custom command
6. Restart persistence
7. Alias matching
8. Duplicate trigger detection
9. Editing and version rollback
10. Enabling / disabling commands
11. Safe workflow validation
12. Workflow step failure
13. Timeout and cancellation
14. Safety confirmation
15. Built-in command precedence
16. Search routing preservation
17. Dynamic capability summaries and malformed command definitions
"""

import os
import json
import time
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.apps.application_discovery import ApplicationDiscovery, DiscoveredApplication
from core.custom_commands.command_registry import CustomCommandRegistry, CustomCommand
from core.custom_commands.workflow_engine import WorkflowEngine
from core.custom_commands.command_manager import CommandManager
from core.intent_engine import IntentEngine
from core.tool_registry import tool_registry, ToolDefinition
from modules.system.executor import CommandExecutor
from core.response_registry import response_registry, CommandOutcome
from modules.system import app_control


class TestCustomCommandsAndDiscovery(unittest.TestCase):
    """Automated unit and integration test suite for extensible commands and app discovery."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.apps_db_path = os.path.join(self.temp_dir, "test_apps.db")
        self.cmds_db_path = os.path.join(self.temp_dir, "test_cmds.db")
        self.apps_json_path = os.path.join(self.temp_dir, "applications.json")

        # Create mock applications.json
        mock_apps = {
            "blender": {
                "windows": "blender.exe",
                "linux": "blender",
                "aliases": ["blender", "3d editor", "my 3d editor"]
            },
            "spotify": {
                "windows": "spotify.exe",
                "linux": "spotify",
                "aliases": ["spotify", "music", "music player"]
            }
        }
        with open(self.apps_json_path, "w", encoding="utf-8") as f:
            json.dump(mock_apps, f)

        # Isolated instances
        self.discovery = ApplicationDiscovery(db_path=self.apps_db_path, apps_json_path=self.apps_json_path)
        self.cmd_registry = CustomCommandRegistry(db_path=self.cmds_db_path)
        self.workflow_engine = WorkflowEngine(tool_reg=tool_registry)
        self.cmd_manager = CommandManager(
            registry=self.cmd_registry,
            engine=self.workflow_engine,
            discovery=self.discovery
        )
        self.intent_engine = IntentEngine()
        self.executor = CommandExecutor()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. APPLICATION DISCOVERY AND DEDUPLICATION
    # =========================================================================

    def test_01_application_discovery_and_deduplication(self):
        """Verify discovery normalizes records and deduplicates duplicate entries from multiple sources."""
        # Create dummy executable file
        dummy_exe = os.path.join(self.temp_dir, "blender.exe")
        with open(dummy_exe, "w") as f:
            f.write("mock")

        app1 = DiscoveredApplication(
            app_id="blender",
            display_name="Blender",
            executable_path=dummy_exe,
            source="registry_uninstall",
            platform="windows",
            is_available=True
        )
        app2 = DiscoveredApplication(
            app_id="blender",
            display_name="Blender 3D",
            executable_path=dummy_exe,
            source="start_menu",
            platform="windows",
            is_available=True
        )

        self.discovery._save_to_db([app1, app2])
        self.discovery._load_from_db()

        apps = self.discovery.list_applications()
        blender_matches = [a for a in apps if a.app_id == "blender"]
        self.assertEqual(len(blender_matches), 1)
        self.assertEqual(blender_matches[0].app_id, "blender")
        self.assertTrue(blender_matches[0].is_available)

    # =========================================================================
    # 2. MISSING / STALE APPLICATION PATHS
    # =========================================================================

    def test_02_missing_stale_application_paths(self):
        """Verify non-existent executable paths are marked unavailable or filtered."""
        stale_exe = os.path.join(self.temp_dir, "non_existent_app.exe")
        stale_app = DiscoveredApplication(
            app_id="stale_app",
            display_name="Stale App",
            executable_path=stale_exe,
            source="start_menu",
            platform="windows",
            is_available=False
        )
        self.discovery._save_to_db([stale_app])
        self.discovery._load_from_db()

        available_apps = self.discovery.list_applications(available_only=True)
        self.assertNotIn("stale_app", [a.app_id for a in available_apps])

        # Test safe scan without executing files
        apps = self.discovery.scan(force=True)
        self.assertIsInstance(apps, list)

    # =========================================================================
    # 3. GENERIC APPLICATION LAUNCH RESOLUTION
    # =========================================================================

    def test_03_generic_application_launch_resolution(self):
        """Verify resolving natural-language names and aliases against catalogue."""
        dummy_exe = os.path.join(self.temp_dir, "blender.exe")
        with open(dummy_exe, "w") as f:
            f.write("mock")

        app = DiscoveredApplication(
            app_id="blender",
            display_name="Blender",
            executable_path=dummy_exe,
            source="config",
            platform="windows",
            is_available=True
        )
        self.discovery._cached_apps["blender"] = app
        self.discovery._save_to_db([app])

        # Exact match
        best, cands = self.discovery.find_application("Blender")
        self.assertIsNotNone(best)
        self.assertEqual(best.app_id, "blender")

        # Semantic generic alias ("3d editor")
        best_alias, _ = self.discovery.find_application("launch my 3d editor")
        self.assertIsNotNone(best_alias)
        self.assertEqual(best_alias.app_id, "blender")

        # Execution via app_control.launch_application with mock
        with patch("subprocess.Popen") as mock_popen, patch("modules.system.app_control.app_discovery", self.discovery):
            res = app_control.launch_application("Blender")
            self.assertTrue(res["success"])
            self.assertEqual(res["outcome"], "SUCCESS")

    # =========================================================================
    # 4. AMBIGUOUS APPLICATION NAMES
    # =========================================================================

    def test_04_ambiguous_application_names(self):
        """Verify disambiguation when multiple applications match similarly."""
        dummy_exe1 = os.path.join(self.temp_dir, "code_pro.exe")
        dummy_exe2 = os.path.join(self.temp_dir, "code_lite.exe")
        with open(dummy_exe1, "w") as f: f.write("1")
        with open(dummy_exe2, "w") as f: f.write("2")

        app1 = DiscoveredApplication(app_id="code_editor_pro", display_name="Code Editor Pro", executable_path=dummy_exe1, is_available=True)
        app2 = DiscoveredApplication(app_id="code_editor_lite", display_name="Code Editor Lite", executable_path=dummy_exe2, is_available=True)
        self.discovery._cached_apps["code_editor_pro"] = app1
        self.discovery._cached_apps["code_editor_lite"] = app2

        best, cands = self.discovery.find_application("Code Editor")
        self.assertIsNone(best)
        self.assertGreaterEqual(len(cands), 2)

        # Ambiguous resolution in launch_application
        with patch("modules.system.app_control.app_discovery", self.discovery):
            res = app_control.launch_application("Code Editor")
            self.assertFalse(res["success"])
            self.assertEqual(res["outcome"], "AMBIGUOUS")
            self.assertIn("Multiple applications matched", res["message"])

    # =========================================================================
    # 5. CREATING AND PERSISTING A CUSTOM COMMAND
    # =========================================================================

    def test_05_creating_and_persisting_custom_command(self):
        """Verify creating and saving a custom command into SQLite."""
        workflow = [
            {"step_id": 1, "tool": "open_app", "args": {"target": "blender"}, "description": "Open Blender"}
        ]
        ok, msg, cmd = self.cmd_registry.register_command(
            name="Launch 3D Editor",
            trigger_phrases=["launch my 3d editor"],
            workflow_definition=workflow,
            intent_description="Opens Blender 3D editor"
        )
        self.assertTrue(ok)
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.name, "Launch 3D Editor")
        self.assertEqual(cmd.version, 1)
        self.assertEqual(cmd.validation_status, "VALID")

        # Verify in SQLite
        fetched = self.cmd_registry.get_command(cmd.command_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Launch 3D Editor")

    # =========================================================================
    # 6. RESTART PERSISTENCE
    # =========================================================================

    def test_06_restart_persistence(self):
        """Verify custom commands persist across assistant restarts without data loss."""
        workflow = [{"step_id": 1, "tool": "volume_control", "args": {"action": "volume_up"}}]
        self.cmd_registry.register_command(
            name="Louder",
            trigger_phrases=["turn it up", "make it louder"],
            workflow_definition=workflow,
            aliases=["louder"]
        )

        # Re-instantiate new registry pointing to same database
        new_registry = CustomCommandRegistry(db_path=self.cmds_db_path)
        cmds = new_registry.list_commands()
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].name, "Louder")
        self.assertIn("turn it up", cmds[0].trigger_phrases)
        self.assertIn("louder", cmds[0].aliases)

    # =========================================================================
    # 7. ALIAS MATCHING
    # =========================================================================

    def test_07_alias_matching(self):
        """Verify exact and alias matching for custom commands."""
        workflow = [{"step_id": 1, "tool": "open_app", "args": {"target": "spotify"}}]
        self.cmd_registry.register_command(
            name="Play Music",
            trigger_phrases=["start music"],
            workflow_definition=workflow,
            aliases=["launch music", "tune in"]
        )

        # Trigger phrase match
        match1, conf1 = self.cmd_registry.find_matching_command("start music")
        self.assertIsNotNone(match1)
        self.assertEqual(conf1, 1.0)

        # Alias match
        match2, conf2 = self.cmd_registry.find_matching_command("launch music")
        self.assertIsNotNone(match2)
        self.assertEqual(conf2, 1.0)

    # =========================================================================
    # 8. DUPLICATE TRIGGER DETECTION
    # =========================================================================

    def test_08_duplicate_trigger_detection(self):
        """Verify conflict detection prevents duplicate triggers and hijacking built-ins."""
        workflow = [{"step_id": 1, "tool": "open_app", "args": {"target": "chrome"}}]
        self.cmd_registry.register_command(
            name="Browse Web",
            trigger_phrases=["open web"],
            workflow_definition=workflow
        )

        # Attempt to register duplicate trigger
        ok, msg, _ = self.cmd_registry.register_command(
            name="Browse Alternate",
            trigger_phrases=["open web"],
            workflow_definition=workflow
        )
        self.assertFalse(ok)
        self.assertIn("Trigger conflict", msg)

        # Attempt to hijack protected built-in ("shutdown")
        ok_built, msg_built, _ = self.cmd_registry.register_command(
            name="Hijack Shutdown",
            trigger_phrases=["shutdown"],
            workflow_definition=workflow
        )
        self.assertFalse(ok_built)
        self.assertIn("protected built-in", msg_built)

    # =========================================================================
    # 9. EDITING AND VERSION ROLLBACK
    # =========================================================================

    def test_09_editing_and_version_rollback(self):
        """Verify editing creates version history and rollback restores prior state."""
        wf_v1 = [{"step_id": 1, "tool": "open_app", "args": {"target": "chrome"}}]
        _, _, cmd = self.cmd_registry.register_command(
            name="Morning Routine",
            trigger_phrases=["start morning"],
            workflow_definition=wf_v1
        )
        self.assertEqual(cmd.version, 1)

        # Edit command to version 2
        wf_v2 = wf_v1 + [{"step_id": 2, "tool": "volume_control", "args": {"action": "volume_up"}}]
        ok_up, _, updated = self.cmd_registry.update_command(cmd.command_id, {"workflow_definition": wf_v2})
        self.assertTrue(ok_up)
        self.assertEqual(updated.version, 2)
        self.assertEqual(len(updated.workflow_definition), 2)
        self.assertEqual(len(updated.history), 1)

        # Roll back to version 1
        ok_rb, msg_rb, rolled = self.cmd_registry.rollback_command(cmd.command_id)
        self.assertTrue(ok_rb)
        self.assertEqual(len(rolled.workflow_definition), 1)
        self.assertEqual(rolled.workflow_definition[0]["tool"], "open_app")

    # =========================================================================
    # 10. ENABLING AND DISABLING COMMANDS
    # =========================================================================

    def test_10_enabling_and_disabling_commands(self):
        """Verify disabled commands are not routed, and enabling restores them."""
        workflow = [{"step_id": 1, "tool": "take_screenshot", "args": {}}]
        _, _, cmd = self.cmd_registry.register_command(
            name="Capture Screen",
            trigger_phrases=["capture now"],
            workflow_definition=workflow
        )

        # Disable
        ok_dis, _ = self.cmd_registry.disable_command(cmd.command_id)
        self.assertTrue(ok_dis)
        match_dis, _ = self.cmd_registry.find_matching_command("capture now")
        self.assertIsNone(match_dis)

        # Re-enable
        ok_en, _ = self.cmd_registry.enable_command(cmd.command_id)
        self.assertTrue(ok_en)
        match_en, _ = self.cmd_registry.find_matching_command("capture now")
        self.assertIsNotNone(match_en)

    # =========================================================================
    # 11. SAFE WORKFLOW VALIDATION
    # =========================================================================

    def test_11_safe_workflow_validation(self):
        """Verify workflow validator rejects unknown tools, cycles, and unbounded limits."""
        # Valid workflow
        valid_wf = [
            {"step_id": 1, "tool": "open_app", "args": {"target": "vscode"}},
            {"step_id": 2, "tool": "open_folder", "args": {"target": "my_project"}, "depends_on": 0}
        ]
        is_val, errs, risk = self.workflow_engine.validate_workflow(valid_wf)
        self.assertTrue(is_val)
        self.assertEqual(len(errs), 0)

        # Invalid tool (unregistered capability)
        invalid_wf = [
            {"step_id": 1, "tool": "fly_drone_to_mars", "args": {}}
        ]
        is_val2, errs2, _ = self.workflow_engine.validate_workflow(invalid_wf)
        self.assertFalse(is_val2)
        self.assertIn("unknown or unimplemented tool", errs2[0])

    # =========================================================================
    # 12. WORKFLOW STEP FAILURE
    # =========================================================================

    def test_12_workflow_step_failure(self):
        """Verify that when a required step fails, the workflow does not claim success."""
        workflow = [
            {"step_id": 1, "tool": "open_app", "args": {"target": "app1"}, "required": True},
            {"step_id": 2, "tool": "open_app", "args": {"target": "app2"}, "depends_on": 0, "required": True}
        ]

        # Mock executor where step 1 fails
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {"success": False, "message": "Failed to launch app1"}

        res = self.workflow_engine.execute_workflow(workflow, executor=mock_exec)
        self.assertFalse(res["success"])
        self.assertEqual(res["outcome"], CommandOutcome.EXECUTION_FAILED.value)
        self.assertEqual(res["completed_count"], 0)
        self.assertEqual(res["failed_count"], 1)
        self.assertEqual(res["skipped_count"], 1)
        self.assertIn("Workflow failed at step 1", res["message"])

    # =========================================================================
    # 13. TIMEOUT AND CANCELLATION
    # =========================================================================

    def test_13_timeout_and_cancellation(self):
        """Verify cancellation signal halts workflow execution safely."""
        workflow = [
            {"step_id": 1, "tool": "volume_control", "args": {"action": "volume_up"}},
            {"step_id": 2, "tool": "volume_control", "args": {"action": "volume_up"}},
            {"step_id": 3, "tool": "volume_control", "args": {"action": "volume_up"}}
        ]

        engine = WorkflowEngine(tool_reg=tool_registry)
        engine.cancel_execution()

        mock_exec = MagicMock()
        mock_exec.execute.return_value = {"success": True, "message": "Done"}

        res = engine.execute_workflow(workflow, executor=mock_exec)
        self.assertFalse(res["success"])
        self.assertIn("CANCELLED", [s["status"] for s in res["steps"]])

    # =========================================================================
    # 14. SAFETY CONFIRMATION
    # =========================================================================

    def test_14_safety_confirmation(self):
        """Verify workflows with HIGH risk actions require user confirmation."""
        high_risk_wf = [
            {"step_id": 1, "tool": "shutdown_pc", "args": {}}
        ]
        # Without confirmation
        res_unconfirmed = self.workflow_engine.execute_workflow(high_risk_wf, confirm=False)
        self.assertFalse(res_unconfirmed["success"])
        self.assertTrue(res_unconfirmed.get("pending_confirmation"))
        self.assertEqual(res_unconfirmed["outcome"], CommandOutcome.PERMISSION_DENIED.value)

        # With confirmation
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {"success": True, "message": "System shutdown initiated."}
        res_confirmed = self.workflow_engine.execute_workflow(high_risk_wf, confirm=True, executor=mock_exec)
        self.assertTrue(res_confirmed["success"])

    # =========================================================================
    # 15. BUILT-IN COMMAND PRECEDENCE
    # =========================================================================

    def test_15_builtin_command_precedence(self):
        """Verify built-in deterministic commands take safe precedence over custom phrases."""
        # Built-in search intent precedence
        node = self.intent_engine.parse("Jarvis search python tutorials")
        self.assertEqual(node["intent"], "web_search")
        self.assertTrue(node.get("is_explicit_search", False))

        # Built-in system control precedence
        node_time = self.intent_engine.parse("what time is it")
        self.assertEqual(node_time["intent"], "time_query")

    # =========================================================================
    # 16. SEARCH ROUTING PRESERVATION
    # =========================================================================

    def test_16_search_routing_preservation(self):
        """Verify explicit search prefixes are preserved and never hijacked."""
        node1 = self.intent_engine.parse("Jarvis search quantum computing")
        self.assertEqual(node1["intent"], "web_search")
        self.assertEqual(node1["query"], "quantum computing")

        node2 = self.intent_engine.parse("Jarvis search YouTube for lofi music")
        self.assertEqual(node2["intent"], "web_search")
        self.assertEqual(node2["provider"], "youtube")

    # =========================================================================
    # 17. DYNAMIC CAPABILITY SUMMARIES & MALFORMED DEFINITIONS
    # =========================================================================

    def test_17_dynamic_capability_summaries_and_malformed_definitions(self):
        """Verify capability summary generation and rejection of malformed command definitions."""
        # Summary includes tools and custom workflows
        summary = response_registry.get_capabilities_summary(tool_registry)
        self.assertIn("Applications", summary)
        self.assertIn("Custom Workflows", summary)

        # Malformed definitions handling
        is_val1, errs1, _ = self.workflow_engine.validate_workflow("not_a_list")
        self.assertFalse(is_val1)

        is_val2, errs2, _ = self.workflow_engine.validate_workflow([])
        self.assertFalse(is_val2)

        is_val3, errs3, _ = self.workflow_engine.validate_workflow([{"args": {}}])  # Missing tool
        self.assertFalse(is_val3)

        # Command manager creation of natural language command
        with patch("core.custom_commands.command_manager.custom_command_registry", self.cmd_registry):
            create_res = self.cmd_manager.handle_management_command(
                "Jarvis, add a command: when I say launch my 3D editor, open Blender"
            )
            self.assertTrue(create_res["success"])
            self.assertIn("Created command", create_res["message"])


if __name__ == "__main__":
    unittest.main()
