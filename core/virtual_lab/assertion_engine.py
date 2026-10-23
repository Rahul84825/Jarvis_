"""State Assertion Engine and Root-Cause Failure Analyzer for the SANTRA Virtual Testing Room."""

import logging
from typing import Dict, Any, Tuple, Optional
from core.virtual_lab.models import CommandScenario, ScenarioResult, FailureCategory, TestStatus, ExecutionMode
from core.virtual_lab.environment_simulator import EnvironmentSimulator

logger = logging.getLogger("Santra.VirtualLab.Assert")


class StateAssertionEngine:
    """Evaluates scenario outcomes against strict intent, tool, and environmental state criteria."""

    def evaluate(
        self,
        scenario: CommandScenario,
        parsed_intent: Dict[str, Any],
        tool_outcome: Dict[str, Any],
        env_before: Dict[str, Any],
        env_after: Dict[str, Any],
        duration_ms: float,
        env: EnvironmentSimulator
    ) -> ScenarioResult:
        """Runs multi-dimensional assertions to verify intent, tool, and state diffs."""
        matched_intent = parsed_intent.get("intent", "unknown")
        matched_action = parsed_intent.get("action", parsed_intent.get("action_type"))
        tool_name = tool_outcome.get("tool") or tool_outcome.get("action")
        output_msg = tool_outcome.get("message", "")
        diff = env.compute_diff(env_before, env_after)

        failure_cat: Optional[FailureCategory] = None
        failure_msg: Optional[str] = None
        status = TestStatus.PASSED

        # 1. Ambiguity / Clarification Check
        if scenario.requires_clarification:
            is_clarification = (
                matched_action == "clarification_needed" or
                matched_intent in ["clarification_needed", "clarification"] or
                "clarification_prompt" in parsed_intent or
                "where would you like" in output_msg.lower() or
                "which" in output_msg.lower()
            )
            if not is_clarification:
                status = TestStatus.FAILED
                failure_cat = FailureCategory.INTENT_RESOLUTION
                failure_msg = f"Expected clarification prompt for ambiguous input, but resolved to intent '{matched_intent}'."

        # 2. Safety / Sensitivity Check
        elif scenario.is_sensitive:
            requires_confirm = parsed_intent.get("requires_confirmation", False) or tool_outcome.get("requires_confirmation", False)
            if not requires_confirm and parsed_intent.get("confidence", 0) > 0.9:
                # Sensitive actions must require confirmation
                status = TestStatus.FAILED
                failure_cat = FailureCategory.SAFETY
                failure_msg = f"Sensitive scenario '{scenario.scenario_id}' executed without requiring user confirmation."

        # 3. Intent & Action Matching Check
        elif scenario.expected_intent:
            expected_intents = [scenario.expected_intent] if isinstance(scenario.expected_intent, str) else list(scenario.expected_intent)
            if matched_intent not in expected_intents:
                status = TestStatus.FAILED
                failure_cat = FailureCategory.INTENT_RESOLUTION
                failure_msg = f"Intent mismatch: expected '{scenario.expected_intent}', got '{matched_intent}'."

        if status == TestStatus.PASSED and scenario.expected_action:
            expected_actions = [scenario.expected_action] if isinstance(scenario.expected_action, str) else list(scenario.expected_action)
            if matched_action not in expected_actions:
                status = TestStatus.FAILED
                failure_cat = FailureCategory.INTENT_RESOLUTION
                failure_msg = f"Action mismatch: expected '{scenario.expected_action}', got '{matched_action}'."

        # 4. State Verification Check
        if status == TestStatus.PASSED and scenario.expected_state_changes:
            state_ok, state_err = self._verify_state_changes(scenario.expected_state_changes, diff, env, tool_outcome)
            if not state_ok:
                status = TestStatus.FAILED
                failure_cat = FailureCategory.STATE_VERIFICATION
                failure_msg = state_err

        # Generate reproduction command
        repro = (
            f"python -m unittest tests.test_virtual_lab -k {scenario.scenario_id}\n"
            f"# Command: '{scenario.command}'"
        )

        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            command=scenario.command,
            mode=ExecutionMode(scenario.initial_state.get("mode", "simulation")) if isinstance(scenario.initial_state.get("mode"), str) else scenario.initial_state.get("mode", ExecutionMode.SIMULATION),
            status=status,
            duration_ms=duration_ms,
            timestamp=tool_outcome.get("timestamp", ""),
            failure_category=failure_cat,
            failure_reason=failure_msg,
            intent_matched=matched_intent,
            action_matched=matched_action,
            tool_invoked=tool_name,
            tool_args=parsed_intent,
            output_message=output_msg,
            simulated_state_diff=diff,
            telemetry={"cpu_load": env.telemetry.cpu_percent, "ram_load": env.telemetry.ram_percent},
            reproduction_instructions=repro
        )

    def _verify_state_changes(
        self,
        expected: Dict[str, Any],
        diff: Dict[str, Any],
        env: EnvironmentSimulator,
        outcome: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Verifies that the simulated environment mutated precisely as expected."""

        # App launched
        if "app_launched" in expected:
            target_app = expected["app_launched"].lower().strip()
            app_obj = env.apps.get(target_app)
            if not app_obj or not app_obj.is_running:
                return False, f"Expected app '{target_app}' to be launched and running."

        # File created
        if "file_created" in expected:
            rel_file = expected["file_created"]
            if not env.fs.file_exists(rel_file):
                return False, f"Expected file '{rel_file}' to exist in the virtual filesystem."

        # Overwrite prevented
        if expected.get("overwrite_prevented"):
            if not env.fs.overwrite_attempts and outcome.get("success"):
                return False, "Expected file overwrite to be rejected, but operation succeeded."

        # Browser search executed
        if "browser_search" in expected:
            expected_q = expected["browser_search"].lower().strip()
            actual_q = (env.browser.last_search_query or "").lower().strip()
            if expected_q not in actual_q:
                return False, f"Expected browser search '{expected_q}', but recorded '{actual_q}'."

        # Browser URL opened
        if "url_opened" in expected:
            expected_url = expected["url_opened"].lower().strip()
            actual_url = (env.browser.active_url or "").lower().strip()
            if expected_url not in actual_url:
                return False, f"Expected URL '{expected_url}', but active browser URL is '{actual_url}'."

        return True, None
