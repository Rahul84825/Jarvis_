"""
Comprehensive Track C Automated Test Suite for JARVIS
Agentic Intelligence, Multi-Step Task Planning, Tool Orchestration & Reliable Execution
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.agent.task_models import TaskStatus, StepStatus, TaskStep, AgentTask
from core.multi_step_planner import MultiStepPlanner
from core.tool_registry import tool_registry
from core.tool_safety_gate import tool_safety_gate
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.ai.intelligence_router import intelligence_router, MODE_REASONING, MODE_CONTEXT
from modules.system.executor import CommandExecutor


class TestTrackCAgenticExecution(unittest.TestCase):
    """Rigorous tests covering the complete Track C Agentic Planning & Execution Lifecycle."""

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.mock_executor = MagicMock(spec=CommandExecutor)
        self.mock_executor.execute = MagicMock(return_value={"success": True, "message": "Command executed successfully."})

        self.planner = MultiStepPlanner()
        self.planner.set_dependencies(self.intent_engine, self.mock_executor)

    # =========================================================================
    # 1. PLANNING TESTS
    # =========================================================================

    def test_plan_single_step_request(self):
        """Single-step request decomposition."""
        task = self.planner.plan("Open Chrome")
        self.assertIsInstance(task, AgentTask)
        self.assertEqual(len(task.steps), 1)
        self.assertIn(task.steps[0].tool_name, ["open_application", "open_browser", "open_app"])
        self.assertEqual(task.status, TaskStatus.VALIDATED)

    def test_plan_multi_step_search_and_result(self):
        """Multi-step request: 'Open Chrome, search Google for React tutorials, and open the first result'."""
        task = self.planner.plan("Open Chrome, search Google for React tutorials, and open the first result")
        self.assertGreaterEqual(len(task.steps), 3)
        tools = [s.tool_name for s in task.steps]
        self.assertTrue(any(t in tools for t in ["open_application", "open_browser", "open_app"]))
        self.assertIn("web_search", tools)
        self.assertIn("open_search_result", tools)
        # Verify dependency: step 3 (open_search_result) depends on step 2 (web_search)
        search_idx = tools.index("web_search")
        result_idx = tools.index("open_search_result")
        self.assertEqual(task.steps[result_idx].depends_on, search_idx)

    def test_plan_notepad_and_write_explanation(self):
        """Multi-step request: 'Open Notepad and write a short explanation of inheritance'."""
        task = self.planner.plan("Open Notepad and write a short explanation of inheritance")
        self.assertGreaterEqual(len(task.steps), 1)
        tools = [s.tool_name for s in task.steps]
        self.assertIn("write_to_notepad", tools)

    def test_plan_youtube_search_and_chrome(self):
        """Multi-step request: 'Search YouTube for MERN stack tutorials, then open Chrome'."""
        task = self.planner.plan("Search YouTube for MERN stack tutorials, then open Chrome")
        self.assertGreaterEqual(len(task.steps), 2)
        tools = [s.tool_name for s in task.steps]
        self.assertIn("youtube_search", tools)
        self.assertTrue(any(t in tools for t in ["open_application", "open_browser", "open_app"]))

    def test_plan_chrome_navigate_verify_loaded(self):
        """Multi-step request: 'Open Chrome, navigate to ChatGPT, and tell me when the page is ready'."""
        task = self.planner.plan("Open Chrome, navigate to ChatGPT, and tell me when the page is ready")
        self.assertGreaterEqual(len(task.steps), 2)
        tools = [s.tool_name for s in task.steps]
        self.assertIn("open_website", tools)
        self.assertIn("verify_page_loaded", tools)

    def test_plan_unknown_tool_rejection(self):
        """Ensures that invalid plans or unregistered tools are rejected gracefully."""
        is_valid, reason = self.planner.validate_tool_call("hack_nasa_mainframe", {})
        self.assertFalse(is_valid)
        self.assertIn("Unregistered tool", reason)

    def test_plan_argument_schema_validation(self):
        """Rejects tools called with missing required parameters."""
        is_valid, reason = self.planner.validate_tool_call("open_application", {})
        self.assertFalse(is_valid)
        self.assertIn("Missing required argument", reason)

        is_valid, reason = self.planner.validate_tool_call("open_application", {"application": "notepad"})
        self.assertTrue(is_valid)

    def test_plan_confirmation_required_detection(self):
        """Flags high-risk tools (like delete_file, system_shutdown) with requires_confirmation=True."""
        step = TaskStep(
            step_index=0,
            raw_text="delete database",
            clean_text="delete database",
            tool_name="delete_file",
            args={"path": "C:\\data.db"},
            risk_level="HIGH"
        )
        self.assertTrue(self.planner._check_step_confirmation_required(step))

    # =========================================================================
    # 2. EXECUTION & DEPENDENCY MANAGEMENT TESTS
    # =========================================================================

    def test_execution_successful_sequence(self):
        """Sequential execution of dependent steps where all succeed."""
        task = AgentTask.create("Open Chrome and search React", "search react")
        step1 = TaskStep(0, "open chrome", "open chrome", "open_application", {"application": "chrome"})
        step2 = TaskStep(1, "search react", "search react", "web_search", {"query": "React tutorials"}, depends_on=0)
        task.steps = [step1, step2]

        exec_task = self.planner.execute_task(task)
        self.assertEqual(exec_task.status, TaskStatus.COMPLETED)
        self.assertEqual(step1.status, StepStatus.COMPLETED)
        self.assertEqual(step2.status, StepStatus.COMPLETED)
        self.assertIn("Done", exec_task.execution_summary)

    def test_execution_dependent_step_skipping_on_failure(self):
        """When prerequisite fails, dependent steps are SKIPPED rather than run erroneously."""
        task = AgentTask.create("Search and open result", "search and open")
        step1 = TaskStep(0, "search react", "search react", "web_search", {"query": "React"})
        step2 = TaskStep(1, "open result", "open result", "open_search_result", {"index": 0}, depends_on=0)
        task.steps = [step1, step2]

        self.mock_executor.execute = MagicMock(return_value={"success": False, "message": "DNS resolution failed"})

        exec_task = self.planner.execute_task(task)
        self.assertEqual(exec_task.status, TaskStatus.FAILED)
        self.assertEqual(step1.status, StepStatus.FAILED)
        self.assertEqual(step2.status, StepStatus.SKIPPED)
        self.assertIn("skipped", exec_task.execution_summary)

    def test_execution_idempotency_prevents_duplicate_run(self):
        """Ensures identical steps in same workflow are not executed twice."""
        task = AgentTask.create("Double open", "idempotency test")
        step1 = TaskStep(0, "open chrome", "open chrome", "open_application", {"application": "chrome"})
        step2 = TaskStep(1, "open chrome again", "open chrome again", "open_application", {"application": "chrome"})
        task.steps = [step1, step2]

        exec_task = self.planner.execute_task(task)
        self.assertEqual(exec_task.status, TaskStatus.COMPLETED)
        # Executor should only have been called ONCE for the duplicate step
        self.assertEqual(self.mock_executor.execute.call_count, 1)

    # =========================================================================
    # 3. BOUNDED RETRIES & SAFETY RECOVERY TESTS
    # =========================================================================

    def test_bounded_retry_on_safe_transient_failure(self):
        """Safe idempotent tool (web_search) retries up to max_retries on transient failure."""
        step = TaskStep(0, "web search", "web search", "web_search", {"query": "python"}, max_retries=2)
        # Fail once, then succeed
        self.mock_executor.execute = MagicMock(side_effect=[
            {"success": False, "message": "Connection timeout"},
            {"success": True, "message": "Search results loaded."}
        ])

        res = self.planner._execute_step_with_retry(step, confirm=False, task_context={})
        self.assertTrue(res["success"])
        self.assertEqual(step.retry_count, 1)

    def test_never_retry_destructive_or_terminal_actions(self):
        """Destructive/terminal actions must NEVER be automatically retried."""
        step = TaskStep(0, "run bash", "run bash", "terminal_execute", {"command": "rm -rf /"}, max_retries=2)
        self.mock_executor.execute = MagicMock(return_value={"success": False, "message": "Permission denied"})

        res = self.planner._execute_step_with_retry(step, confirm=False, task_context={})
        self.assertFalse(res["success"])
        # Must only have been attempted once (0 retries)
        self.assertEqual(self.mock_executor.execute.call_count, 1)
        self.assertEqual(step.retry_count, 0)

    def test_cancellation_aborts_pending_steps(self):
        """Cancellation stops remaining steps immediately and truthfully reports state."""
        task = AgentTask.create("Three step task", "cancellation test")
        step1 = TaskStep(0, "step 1", "step 1", "open_application", {"application": "notepad"})
        step2 = TaskStep(1, "step 2", "step 2", "open_application", {"application": "calc"})
        task.steps = [step1, step2]

        def cancel_on_first_step(step, t):
            t.mark_cancelled()

        exec_task = self.planner.execute_task(task, on_step_update=cancel_on_first_step)
        self.assertEqual(exec_task.status, TaskStatus.CANCELLED)
        self.assertIn(step2.status, [StepStatus.SKIPPED, StepStatus.CANCELLED])
        self.assertIn("Task cancelled", exec_task.execution_summary)

    # =========================================================================
    # 4. CONTEXTUAL FOLLOW-UPS & TASK CONTINUATION TESTS
    # =========================================================================

    def test_contextual_followup_open_second_result(self):
        """Follow-up: 'Now open the second result'."""
        task = AgentTask.create("Search", "search")
        task.context_data = {"last_search_provider": "google", "last_search_query": "React tutorials"}
        self.planner.last_task = task

        res = self.planner.open_search_result_followup(index=1)
        self.assertTrue(res["success"])
        self.assertIn("Google", res["message"])

    def test_contextual_followup_switch_provider_to_youtube(self):
        """Follow-up: 'Do the same on YouTube'."""
        task = AgentTask.create("Search", "search")
        task.context_data = {"last_search_provider": "google", "last_search_query": "Python tutorials"}
        task.steps = [TaskStep(0, "search", "search", "web_search", {"query": "Python tutorials"})]
        self.planner.active_task = None
        self.planner.last_task = task

        mock_bm = MagicMock()
        mock_bm.search_youtube.return_value = {"success": True, "message": "Searching YouTube."}
        self.mock_executor.browser_mgr = mock_bm
        res = self.planner.switch_search_provider_followup(provider="youtube")
        self.assertTrue(res["success"])
        self.assertIn("YouTube", res["message"])

    def test_contextual_task_status_query(self):
        """Follow-up: 'What have you completed?'."""
        task = AgentTask.create("Sample task", "test status")
        step1 = TaskStep(0, "step 1", "step 1", "open_application", {"application": "chrome"})
        step1.status = StepStatus.COMPLETED
        task.steps = [step1]
        task.status = TaskStatus.COMPLETED
        self.planner.last_task = task

        status_info = self.planner.get_active_task_status()
        self.assertTrue(status_info["success"])
        self.assertEqual(status_info["completed_steps"], 1)
        self.assertIn("COMPLETED", status_info["message"])

    def test_contextual_explain_failure_query(self):
        """Follow-up: 'Why did it fail?'."""
        task = AgentTask.create("Failing task", "test failure")
        step1 = TaskStep(0, "step 1", "step 1", "terminal_execute", {"command": "bad_command"})
        step1.status = StepStatus.FAILED
        step1.error = "File or command not found"
        task.steps = [step1]
        task.status = TaskStatus.FAILED
        self.planner.last_task = task

        explanation = self.planner.explain_last_failure()
        self.assertIn("File or command not found", explanation)

    # =========================================================================
    # 5. TRUTHFULNESS & BROWSER/DOM BOUNDARY TESTS
    # =========================================================================

    def test_truthful_browser_search_result_reporting(self):
        """Never fabricates DOM inspection if CDP is offline; truthfully reports browser search status."""
        step = TaskStep(0, "open result", "open result", "open_search_result", {"index": 0})
        ctx = {"last_search_provider": "google", "last_search_query": "React tutorials"}

        res = self.planner._handle_open_search_result(step, ctx)
        self.assertTrue(res["success"])
        self.assertIn("Search results opened in Google", res["message"])
        self.assertIn("First result is ready in your browser", res["message"])
        # Must not claim it analyzed video content or clicked DOM elements
        self.assertNotIn("analyzed video content", res["message"].lower())
        self.assertNotIn("clicked element", res["message"].lower())

    # =========================================================================
    # 6. ROUTER INTEGRATION TESTS
    # =========================================================================

    def test_router_classifies_task_followup_cancel(self):
        """Intelligence router classifies 'cancel the task' into TASK_FOLLOWUP/cancel."""
        req = intelligence_router.route("cancel the task")
        self.assertEqual(req.intent, "TASK_FOLLOWUP")
        self.assertEqual(req.action, "cancel")

    def test_router_classifies_task_followup_retry(self):
        """Intelligence router classifies 'try that again' into TASK_FOLLOWUP/retry."""
        req = intelligence_router.route("try that again")
        self.assertEqual(req.intent, "TASK_FOLLOWUP")
        self.assertEqual(req.action, "retry")

    def test_router_classifies_task_followup_skip(self):
        """Intelligence router classifies 'skip this step' into TASK_FOLLOWUP/skip_step."""
        req = intelligence_router.route("skip this step")
        self.assertEqual(req.intent, "TASK_FOLLOWUP")
        self.assertEqual(req.action, "skip_step")

    def test_router_classifies_task_followup_open_second_result(self):
        """Intelligence router classifies 'now open the second result' into TASK_FOLLOWUP/open_result."""
        req = intelligence_router.route("now open the second result")
        self.assertEqual(req.intent, "TASK_FOLLOWUP")
        self.assertEqual(req.action, "open_result")
        self.assertEqual(req.target, "2")


if __name__ == "__main__":
    unittest.main()
