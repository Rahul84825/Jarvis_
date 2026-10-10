"""Structured Workflow Engine for JARVIS Custom Commands.

Executes sequential multi-step workflows represented as structured data without runtime
code generation, eval, or exec. Enforces Tool Registry validation, Safety Gate checks,
dependency tracking, bounded timeouts, safe retries, cancellation, and truthful reporting.
"""

import time
import logging
from typing import List, Dict, Optional, Tuple, Any, Callable
from core.tool_registry import tool_registry, ToolDefinition
from modules.system import permissions
from core.response_registry import CommandOutcome

logger = logging.getLogger("Jarvis.WorkflowEngine")


class WorkflowEngine:
    """Validates and executes data-driven multi-step command workflows."""

    MAX_STEPS = 10
    MAX_STEP_TIMEOUT = 60.0
    DEFAULT_STEP_TIMEOUT = 10.0
    MAX_RETRIES = 2

    def __init__(self, tool_reg=None, executor=None):
        self.tool_registry = tool_reg or tool_registry
        self.executor = executor
        self._cancelled = False
        logger.info("WorkflowEngine initialized.")

    def set_executor(self, executor):
        self.executor = executor

    def cancel_execution(self):
        """Signals active workflow execution to halt safely."""
        self._cancelled = True
        logger.warning("[WORKFLOW] Cancellation signal received.")

    # =========================================================================
    # WORKFLOW DEFINITION VALIDATION
    # =========================================================================

    def validate_workflow(
        self,
        workflow: List[Dict[str, Any]],
        strict_args: bool = True
    ) -> Tuple[bool, List[str], str]:
        """Validates a workflow definition against registered capabilities.

        Returns:
            Tuple of (is_valid, error_list, overall_risk_classification)
        """
        errors = []
        if not workflow or not isinstance(workflow, list):
            return False, ["Workflow definition must be a non-empty list of steps."], "LOW"

        if len(workflow) > self.MAX_STEPS:
            errors.append(f"Workflow exceeds maximum step count of {self.MAX_STEPS} (provided: {len(workflow)}).")

        max_risk = "LOW"
        risk_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

        for idx, step in enumerate(workflow):
            if not isinstance(step, dict):
                errors.append(f"Step {idx+1} must be a JSON object.")
                continue

            # Tool identification
            tool_name = step.get("tool") or step.get("action")
            if not tool_name:
                errors.append(f"Step {idx+1} is missing required 'tool' field.")
                continue

            # Tool resolution in authoritative ToolRegistry
            tool_def = self.tool_registry.get_tool(tool_name)
            if not tool_def:
                # Also accept generic application.launch or open_app
                if tool_name in ["application.launch", "open_app"]:
                    tool_def = self.tool_registry.get_tool("open_app")
                else:
                    errors.append(
                        f"Step {idx+1} specifies unknown or unimplemented tool '{tool_name}'. "
                        f"Custom commands can only compose registered tools."
                    )
                    continue

            # Risk level tracking
            step_risk = getattr(tool_def, "risk_level", "LOW")
            if risk_rank.get(step_risk, 1) > risk_rank.get(max_risk, 1):
                max_risk = step_risk

            # Validate arguments
            args = step.get("args") or {}
            if not isinstance(args, dict):
                errors.append(f"Step {idx+1} 'args' must be a dictionary.")

            # Validate dependencies
            depends_on = step.get("depends_on")
            if depends_on is not None:
                if not isinstance(depends_on, int) or depends_on < 0 or depends_on >= idx:
                    errors.append(f"Step {idx+1} depends_on must reference a prior step index (0 to {idx-1}).")

            # Validate timeout
            timeout = step.get("timeout_sec", self.DEFAULT_STEP_TIMEOUT)
            if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > self.MAX_STEP_TIMEOUT:
                errors.append(f"Step {idx+1} timeout must be between 1 and {self.MAX_STEP_TIMEOUT} seconds.")

        return len(errors) == 0, errors, max_risk

    # =========================================================================
    # WORKFLOW EXECUTION
    # =========================================================================

    def execute_workflow(
        self,
        workflow: List[Dict[str, Any]],
        confirm: bool = False,
        executor: Any = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Executes a structured workflow sequentially with Safety Gate and dependency tracking."""
        exec_engine = executor or self.executor
        if not exec_engine:
            from modules.system.executor import CommandExecutor
            exec_engine = CommandExecutor()

        # Check if already cancelled before starting
        if self._cancelled:
            logger.warning("[WORKFLOW] Execution halted due to prior cancellation signal.")
            self._cancelled = False
            return {
                "success": False,
                "outcome": CommandOutcome.CANCELLED.value,
                "message": "Workflow execution cancelled.",
                "completed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "total_steps": len(workflow),
                "steps": [
                    {
                        "step_index": i,
                        "tool": s.get("tool"),
                        "status": "CANCELLED",
                        "success": False,
                        "message": "Workflow execution cancelled.",
                        "latency_ms": 0.0
                    }
                    for i, s in enumerate(workflow)
                ]
            }

        # 1. Validate structure first
        is_valid, errors, overall_risk = self.validate_workflow(workflow)
        if not is_valid:
            logger.error(f"[WORKFLOW] Validation failed: {errors}")
            return {
                "success": False,
                "outcome": CommandOutcome.INVALID_COMMAND.value,
                "message": f"Workflow validation failed: {'; '.join(errors)}",
                "steps": [],
                "completed_count": 0,
                "failed_count": len(workflow)
            }

        # 2. Check Safety Gate for high-risk workflows
        if overall_risk == "HIGH" and not confirm:
            logger.info("[WORKFLOW] Workflow contains high-risk actions. Requesting confirmation.")
            return {
                "success": False,
                "outcome": CommandOutcome.PERMISSION_DENIED.value,
                "message": "This workflow contains high-risk actions and requires user confirmation.",
                "pending_confirmation": True,
                "risk_level": overall_risk,
                "steps": []
            }

        executed_steps = []
        failed_indices = set()
        last_step_output = None
        overall_success = True

        logger.info(f"[WORKFLOW] Starting sequential execution of {len(workflow)} steps (Risk: {overall_risk})...")

        for idx, step in enumerate(workflow):
            if self._cancelled:
                logger.warning(f"[WORKFLOW] Execution halted at step {idx+1} due to cancellation.")
                executed_steps.append({
                    "step_index": idx,
                    "tool": step.get("tool"),
                    "status": "CANCELLED",
                    "success": False,
                    "message": "Workflow execution cancelled.",
                    "latency_ms": 0.0
                })
                overall_success = False
                break

            dep = step.get("depends_on")
            # Dependency failure check
            if dep is not None and dep in failed_indices:
                logger.warning(f"[WORKFLOW] Step {idx+1} SKIPPED due to prior failure in dependent step {dep+1}.")
                executed_steps.append({
                    "step_index": idx,
                    "tool": step.get("tool"),
                    "status": "SKIPPED",
                    "success": False,
                    "message": f"Skipped because required step {dep+1} failed.",
                    "latency_ms": 0.0
                })
                failed_indices.add(idx)
                overall_success = False
                continue

            tool_name = step.get("tool") or step.get("action")
            args = dict(step.get("args") or {})
            required = step.get("required", True)
            step_timeout = min(step.get("timeout_sec", self.DEFAULT_STEP_TIMEOUT), self.MAX_STEP_TIMEOUT)
            max_retries = min(step.get("retry_count", 0), self.MAX_RETRIES)

            # Map dependent output into target if specified
            if dep is not None and last_step_output and "target" in args:
                if args["target"] in ["it", "there", "the file", "output", ""]:
                    args["target"] = last_step_output

            # Construct intent node for executor
            intent_node = {
                "intent": tool_name,
                "action": step.get("action") or tool_name,
                "target": args.get("target") or args.get("query") or args.get("path") or "",
                **args
            }

            # Execute with safe retry support
            step_success = False
            step_msg = ""
            attempt = 0
            t0 = time.time()

            while attempt <= max_retries and not step_success:
                attempt += 1
                try:
                    res = exec_engine.execute(intent_node, confirm=confirm)
                    step_success = bool(res.get("success", False))
                    step_msg = res.get("message", "")
                    last_step_output = res.get("target") or getattr(exec_engine, "last_created_file", None)
                    if step_success:
                        break
                    elif attempt <= max_retries:
                        logger.warning(f"[WORKFLOW] Step {idx+1} attempt {attempt} failed, retrying...")
                        time.sleep(0.2)
                except Exception as e:
                    step_success = False
                    step_msg = f"Step encountered error: {e}"
                    logger.error(f"[WORKFLOW] Step {idx+1} exception: {e}")

            latency_ms = (time.time() - t0) * 1000

            step_record = {
                "step_index": idx,
                "tool": tool_name,
                "status": "COMPLETED" if step_success else "FAILED",
                "success": step_success,
                "message": step_msg,
                "latency_ms": latency_ms
            }
            executed_steps.append(step_record)

            if not step_success:
                failed_indices.add(idx)
                overall_success = False
                logger.warning(f"[WORKFLOW] Step {idx+1} ('{tool_name}') FAILED: {step_msg}")
                if required:
                    logger.info(f"[WORKFLOW] Halting workflow because required step {idx+1} failed.")
                    for rem_idx in range(idx + 1, len(workflow)):
                        rem_step = workflow[rem_idx]
                        executed_steps.append({
                            "step_index": rem_idx,
                            "tool": rem_step.get("tool"),
                            "status": "SKIPPED",
                            "success": False,
                            "message": f"Skipped because required step {idx+1} failed.",
                            "latency_ms": 0.0
                        })
                    break

        completed_count = sum(1 for s in executed_steps if s["status"] == "COMPLETED")
        failed_count = sum(1 for s in executed_steps if s["status"] == "FAILED")
        skipped_count = sum(1 for s in executed_steps if s["status"] == "SKIPPED")

        # Composite truthful summary
        if overall_success and failed_count == 0:
            summary = f"Workflow completed successfully ({completed_count} actions executed)."
            outcome = CommandOutcome.SUCCESS.value
        else:
            first_fail = next((s for s in executed_steps if s["status"] == "FAILED"), None)
            fail_detail = f": {first_fail['message']}" if first_fail else ""
            summary = f"Workflow failed at step {first_fail['step_index']+1 if first_fail else 'unknown'}{fail_detail}"
            outcome = CommandOutcome.EXECUTION_FAILED.value

        logger.info(f"[WORKFLOW] Finished: {completed_count} completed, {failed_count} failed, {skipped_count} skipped.")
        return {
            "success": overall_success and (failed_count == 0),
            "outcome": outcome,
            "message": summary,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "total_steps": len(workflow),
            "steps": executed_steps
        }


# Global singleton instance
workflow_engine = WorkflowEngine()
