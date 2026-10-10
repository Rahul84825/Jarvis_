"""Tests for Centralized Command Response Registry and Invalid-Command Handling.

Covers all 14 required test areas:
1. Valid command acknowledgment
2. Successful execution response
3. Invalid command fallback
4. Missing argument clarification
5. Unsupported capability
6. Provider unavailable
7. Permission denied
8. Tool timeout
9. Execution failure
10. Search prefix routing
11. Targeted YouTube search
12. Capability summary generation
13. Consistent UI and voice result states
14. TTS failure after successful command execution
"""

import unittest
from unittest.mock import MagicMock, patch

from core.response_registry import (
    CommandResponseRegistry,
    CommandOutcome,
    response_registry
)
from core.speech_sanitizer import speech_sanitizer
from core.tool_registry import tool_registry
from core.jarvis_runtime import JarvisRuntime
from modules.system.executor import CommandExecutor
from core.os.browser_manager import BrowserManager


class TestCommandResponseRegistry(unittest.TestCase):
    """Automated test suite validating JARVIS response registry and state consistency."""

    def setUp(self):
        self.registry = response_registry
        self.executor = CommandExecutor()

    # ==========================================
    # 1. Valid command acknowledgment
    # ==========================================
    def test_01_valid_command_acknowledgment(self):
        """Verify brief, natural acknowledgments before longer operations."""
        # Open Chrome
        ack_chrome = self.registry.get_acknowledgment({"intent": "open_app", "target": "chrome"})
        self.assertEqual(ack_chrome, "Opening Chrome, Sir.")

        # Search YouTube
        ack_yt = self.registry.get_acknowledgment({"intent": "web_search", "provider": "youtube", "target": "python tutorials"})
        self.assertEqual(ack_yt, "Searching YouTube, Sir.")

        # General web search
        ack_search = self.registry.get_acknowledgment({"intent": "web_search", "provider": "google", "target": "latest news"})
        self.assertEqual(ack_search, "Searching the web now, Sir.")

        # Content writing
        ack_write = self.registry.get_acknowledgment({"intent": "content_generation", "target": "essay"})
        self.assertEqual(ack_write, "Certainly, Sir. I'll prepare that.")

        # Create folder
        ack_folder = self.registry.get_acknowledgment({"intent": "filesystem_control", "action": "create_folder", "target": "Projects"})
        self.assertEqual(ack_folder, "Creating the folder, Sir.")

        # Instant operations should NOT require acknowledgment
        ack_time = self.registry.get_acknowledgment({"intent": "time_query"})
        self.assertIsNone(ack_time)

    # ==========================================
    # 2. Successful execution response
    # ==========================================
    def test_02_successful_execution_response(self):
        """Verify confirmed success responses backed by execution evidence."""
        # App open success
        resp_chrome = self.registry.get_success_response({"intent": "open_app", "target": "chrome"}, {"success": True})
        self.assertEqual(resp_chrome, "Chrome is open, Sir.")

        # Search results
        resp_search = self.registry.get_success_response({"intent": "web_search"}, {"success": True})
        self.assertEqual(resp_search, "Here are the search results, Sir.")

        # Folder created
        resp_folder = self.registry.get_success_response({"intent": "filesystem_control", "action": "create_folder", "target": "MyFolder"}, {"success": True})
        self.assertEqual(resp_folder, "The folder has been created, Sir.")

        # Document saved
        resp_doc = self.registry.get_success_response({"intent": "content_generation", "target": "report"}, {"success": True})
        self.assertEqual(resp_doc, "The document has been saved, Sir.")

    # ==========================================
    # 3. Invalid command fallback
    # ==========================================
    def test_03_invalid_command_fallback(self):
        """Verify short default fallback for invalid commands."""
        # Outcome mapping
        resp = self.registry.get_outcome_response(CommandOutcome.INVALID_COMMAND)
        self.assertEqual(resp, "I couldn't complete that request, Sir. Try another command.")

        # Executor execution of invalid command
        res = self.executor.execute({"intent": "invalid_command", "target": "xyz_nonsense_command"})
        self.assertFalse(res["success"])
        self.assertEqual(res["outcome"], CommandOutcome.INVALID_COMMAND.value)
        self.assertEqual(res["message"], "I couldn't complete that request, Sir. Try another command.")

    # ==========================================
    # 4. Missing argument clarification
    # ==========================================
    def test_04_missing_argument_clarification(self):
        """Verify single concise question when a required argument is missing."""
        # Empty search
        q_search = self.registry.get_missing_arg_prompt({"intent": "web_search", "empty_query": True})
        self.assertEqual(q_search, "What would you like me to search for, Sir?")

        # Missing application
        q_app = self.registry.get_missing_arg_prompt({"intent": "open_app", "missing_arg": "app"})
        self.assertEqual(q_app, "Which application should I open, Sir?")

        # Missing file destination
        q_dest = self.registry.get_missing_arg_prompt({"intent": "filesystem_control", "action": "save_file", "missing_arg": "destination"})
        self.assertEqual(q_dest, "Where should I save the file, Sir?")

        # Runtime handling of missing argument
        runtime = JarvisRuntime()
        res = runtime._execute_intent({"intent": "open_app", "missing_arg": "app"}, speak=False)
        self.assertFalse(res["success"])
        self.assertEqual(res["outcome"], CommandOutcome.MISSING_ARGUMENT.value)
        self.assertEqual(res["message"], "Which application should I open, Sir?")

    # ==========================================
    # 5. Unsupported capability
    # ==========================================
    def test_05_unsupported_capability(self):
        """Verify concise responses for unsupported features and uninstalled apps."""
        # Unsupported capability
        resp_cap = self.registry.get_failure_response({"intent": "unsupported_capability"}, outcome=CommandOutcome.UNSUPPORTED_CAPABILITY)
        self.assertEqual(resp_cap, "That capability isn't available yet, Sir.")

        # Uninstalled application
        resp_app = self.registry.get_failure_response({"intent": "open_app", "target": "fictional_app"}, outcome=CommandOutcome.UNSUPPORTED_CAPABILITY, reason="not installed")
        self.assertEqual(resp_app, "That application isn't installed, Sir.")

        # Executor execution for uninstalled application
        with patch("modules.system.app_control.open_app", return_value=False):
            res = self.executor.execute({"intent": "open_app", "target": "nonexistent_app"})
            self.assertFalse(res["success"])
            self.assertEqual(res["outcome"], CommandOutcome.UNSUPPORTED_CAPABILITY.value)
            self.assertEqual(res["message"], "That application isn't installed, Sir.")

    # ==========================================
    # 6. Provider unavailable
    # ==========================================
    def test_06_provider_unavailable(self):
        """Verify concise response when a search provider or service is unavailable."""
        resp_prov = self.registry.get_failure_response({"intent": "web_search"}, outcome=CommandOutcome.PROVIDER_UNAVAILABLE, reason="temporarily unavailable")
        self.assertEqual(resp_prov, "Search is temporarily unavailable, Sir.")

        # Executor unconfigured provider
        with patch.object(self.executor.browser_mgr, "search", return_value={"success": False, "message": "Search provider 'custom_unknown' is not configured."}):
            res = self.executor.execute({"intent": "web_search", "target": "AI news", "provider": "custom_unknown"})
            self.assertFalse(res["success"])
            self.assertEqual(res["outcome"], CommandOutcome.PROVIDER_UNAVAILABLE.value)
            self.assertIn("not configured", res["message"])

    # ==========================================
    # 7. Permission denied
    # ==========================================
    def test_07_permission_denied(self):
        """Verify polite refusal when an action is blocked by safety gate."""
        resp_perm = self.registry.get_failure_response({"intent": "terminal_execute"}, outcome=CommandOutcome.PERMISSION_DENIED)
        self.assertEqual(resp_perm, "I don't have permission to do that, Sir.")

        # Executor rejects command with forbidden metacharacters
        res = self.executor.execute({"intent": "open_app", "target": "chrome | calc"})
        self.assertFalse(res["success"])
        self.assertEqual(res["outcome"], CommandOutcome.PERMISSION_DENIED.value)
        self.assertIn("blocked", res["message"].lower())

    # ==========================================
    # 8. Tool timeout
    # ==========================================
    def test_08_tool_timeout(self):
        """Verify specific timeout message when a tool operation times out."""
        resp_to = self.registry.get_failure_response({"intent": "web_search"}, outcome=CommandOutcome.TIMEOUT, reason="timed out")
        self.assertEqual(resp_to, "That action timed out, Sir. Please try again.")

        # Executor handling of TimeoutError
        with patch.object(self.executor.browser_mgr, "search", side_effect=TimeoutError("Request timed out")):
            res = self.executor.execute({"intent": "web_search", "target": "weather"})
            self.assertFalse(res["success"])
            self.assertEqual(res["outcome"], CommandOutcome.TIMEOUT.value)
            self.assertEqual(res["message"], "That action timed out, Sir. Please try again.")

    # ==========================================
    # 9. Execution failure
    # ==========================================
    def test_09_execution_failure(self):
        """Verify truthful generic execution failure message without leaking raw stack trace."""
        resp_fail = self.registry.get_failure_response({"intent": "custom_tool"}, outcome=CommandOutcome.EXECUTION_FAILED)
        self.assertEqual(resp_fail, "That action failed, Sir. Please try again.")

        # Website navigation failure
        resp_web = self.registry.get_failure_response({"intent": "open_website", "target": "https://broken.invalid"}, outcome=CommandOutcome.EXECUTION_FAILED)
        self.assertEqual(resp_web, "I couldn't open that website, Sir.")

    # ==========================================
    # 10. Search prefix routing
    # ==========================================
    def test_10_search_prefix_routing(self):
        """Verify 'Jarvis search <query>' acknowledges and routes to web search."""
        runtime = JarvisRuntime()
        with patch.object(runtime.executor.browser_mgr, "search") as mock_search:
            mock_search.return_value = {"success": True, "message": "Here are the search results, Sir."}
            res = runtime._process_single_command("Jarvis search latest AI news", speak=False)

            self.assertTrue(res["success"])
            self.assertEqual(res["action"], "search")
            self.assertEqual(res["message"], "Here are the search results, Sir.")
            mock_search.assert_called_once_with("latest AI news", provider="google")

    # ==========================================
    # 11. Targeted YouTube search
    # ==========================================
    def test_11_targeted_youtube_search(self):
        """Verify targeted YouTube search acknowledgment and provider execution."""
        runtime = JarvisRuntime()
        with patch.object(runtime.executor.browser_mgr, "search") as mock_search:
            mock_search.return_value = {"success": True, "message": "Searching YouTube."}
            res = runtime._process_single_command("Jarvis search YouTube for Python tutorials", speak=False)

            self.assertTrue(res["success"])
            self.assertEqual(res["action"], "search")
            mock_search.assert_called_once_with("python tutorials", provider="youtube")

    # ==========================================
    # 12. Capability summary generation
    # ==========================================
    def test_12_capability_summary_generation(self):
        """Verify dynamic capability summary generated from the real ToolRegistry."""
        summary = self.registry.get_capabilities_summary(tool_registry)
        self.assertIn("Here is what I can do for you, Sir:", summary)
        self.assertIn("Applications", summary)
        self.assertIn("Browser & Tabs", summary)
        self.assertIn("Web & Local Search", summary)
        self.assertIn("Files & Folders", summary)
        self.assertIn("System Controls", summary)

    # ==========================================
    # 13. Consistent UI and voice result states
    # ==========================================
    def test_13_consistent_ui_and_voice_result_states(self):
        """Verify UI status, spoken response, and action completion observers share identical states."""
        runtime = JarvisRuntime()
        status_updates = []
        speech_updates = []
        completion_reports = []

        runtime.register_observers(
            on_status_change=lambda s: status_updates.append(s),
            on_speech_text=lambda t: speech_updates.append(t)
        )
        runtime.on_action_complete_cb = lambda action, success, message: completion_reports.append((action, success, message))

        with patch.object(runtime.executor, "execute", return_value={"success": True, "action": "open_app", "target": "chrome", "message": "Chrome launched."}):
            res = runtime._execute_intent({"intent": "open_app", "target": "chrome"}, speak=False)

            self.assertTrue(res["success"])
            self.assertEqual(res["message"], "Chrome is open, Sir.")
            self.assertIn("Chrome is open, Sir.", speech_updates)
            self.assertEqual(completion_reports[-1], ("open_app", True, "Chrome is open, Sir."))

    # ==========================================
    # 14. TTS failure after successful command execution
    # ==========================================
    def test_14_tts_failure_after_successful_command_execution(self):
        """Verify TTS synthesis failure is recorded separately and does not flip command success."""
        runtime = JarvisRuntime()

        # Mock speaker to raise exception during audio output
        runtime.tts_manager.speak = MagicMock(side_effect=RuntimeError("Sound device output error"))

        with patch.object(runtime.executor, "execute", return_value={"success": True, "action": "volume_up", "message": "Volume increased."}):
            res = runtime._execute_intent({"intent": "system_control", "action": "volume_up"}, speak=True)

            # Command execution itself succeeded
            self.assertTrue(res["success"])
            self.assertEqual(res["outcome"], CommandOutcome.SUCCESS.value)

            # Last response metadata records TTS failure separately
            last_resp = runtime.response_manager.handle_response(
                {"type": "SUCCESS", "text": "Volume increased.", "spoken_text": "Volume increased, Sir.", "metadata": {}},
                speak=True
            )
            self.assertFalse(last_resp["metadata"]["tts_success"])
            self.assertEqual(last_resp["spoken_text"], "Volume increased, Sir.")


if __name__ == "__main__":
    unittest.main()
