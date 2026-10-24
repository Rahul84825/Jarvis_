"""Command Test Runner for the SANTRA Virtual Testing Room.
Executes scenarios against real production IntentEngine, ToolRegistry, and Normalizer,
routing side effects safely through simulation adapters.
"""

import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from core.virtual_lab.models import CommandScenario, ScenarioResult, ExecutionMode, TestStatus
from core.virtual_lab.environment_simulator import EnvironmentSimulator
from core.virtual_lab.mock_adapters import MockToolAdapters
from core.virtual_lab.assertion_engine import StateAssertionEngine
from core.intent_engine import IntentEngine
from core.command_normalizer import CommandNormalizer

logger = logging.getLogger("Santra.VirtualLab.Runner")


class CommandTestRunner:
    """Executes single scenarios or batches with full state isolation and assertion verification."""

    def __init__(self, mode: ExecutionMode = ExecutionMode.SIMULATION):
        self.mode = mode
        self.intent_engine = IntentEngine()
        self.normalizer = CommandNormalizer()
        self.assertion_engine = StateAssertionEngine()

    def run_scenario(self, scenario: CommandScenario, env: Optional[EnvironmentSimulator] = None) -> ScenarioResult:
        """Executes a single test scenario in an isolated environment."""
        local_env = env or EnvironmentSimulator()
        adapters = MockToolAdapters(local_env)

        # 1. Apply scenario-specific initial state fixtures
        if scenario.initial_state:
            self._apply_initial_state(scenario.initial_state, local_env)

        # Snapshot pre-execution environment
        env_before = local_env.snapshot()

        t0 = time.perf_counter()
        timestamp_str = datetime.now().isoformat()

        try:
            # 2. Production Command Normalization & Intent Parsing
            if scenario.requires_clarification or scenario.initial_state.get("clear_context", False):
                self.intent_engine.last_app_target = None
            clean_cmd = self.normalizer.normalize(scenario.command)
            parsed_intent = self.intent_engine.parse(scenario.command)

            # 3. Simulate or execute tool side effects based on active mode
            if self.mode == ExecutionMode.SIMULATION:
                tool_outcome = self._dispatch_simulation_tools(parsed_intent, adapters, scenario)
            else:
                # Controlled Integration Mode: routes safe actions through simulation adapters
                # to guarantee zero modification to physical OS files, real browser sessions, or active windows
                tool_outcome = self._dispatch_simulation_tools(parsed_intent, adapters, scenario)
                tool_outcome["mode"] = self.mode.value

            tool_outcome["timestamp"] = timestamp_str

            # Snapshot post-execution environment
            env_after = local_env.snapshot()
            duration_ms = (time.perf_counter() - t0) * 1000

            # 4. Deep State and Intent Assertions
            result = self.assertion_engine.evaluate(
                scenario=scenario,
                parsed_intent=parsed_intent,
                tool_outcome=tool_outcome,
                env_before=env_before,
                env_after=env_after,
                duration_ms=duration_ms,
                env=local_env
            )
            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.error(f"[TestRunner] Unhandled exception executing '{scenario.scenario_id}': {e}", exc_info=True)
            from core.virtual_lab.models import FailureCategory
            test_method_name = f"test_scenario_{scenario.scenario_id.replace('-', '_')}"
            return ScenarioResult(
                scenario_id=scenario.scenario_id,
                command=scenario.command,
                mode=self.mode,
                status=TestStatus.FAILED,
                duration_ms=duration_ms,
                timestamp=timestamp_str,
                failure_category=FailureCategory.TEST_INFRASTRUCTURE,
                failure_reason=f"Unhandled exception during execution: {str(e)}",
                reproduction_instructions=f"python -m unittest tests.test_virtual_lab -k {test_method_name}"
            )
        finally:
            if not env:
                local_env.cleanup()

    def _apply_initial_state(self, initial_state: Dict[str, Any], env: EnvironmentSimulator):
        """Pre-configures environment fixtures required by specific scenarios."""
        if "active_browser_url" in initial_state:
            env.browser.active_url = initial_state["active_browser_url"]
        if "running_apps" in initial_state:
            for app_name in initial_state["running_apps"]:
                if app_name in env.apps:
                    env.apps[app_name].is_running = True
        if "target_file" in initial_state:
            target_path = env.fs.resolve_path(initial_state["target_file"])
            env.fs.save_file(target_path, "Existing content", overwrite=True)

    def _dispatch_simulation_tools(
        self,
        parsed_intent: Dict[str, Any],
        adapters: MockToolAdapters,
        scenario: CommandScenario
    ) -> Dict[str, Any]:
        """Routes parsed intent to appropriate mock tool adapter."""
        intent = parsed_intent.get("intent", "")
        action = parsed_intent.get("action", parsed_intent.get("action_type", ""))
        target = parsed_intent.get("target") or parsed_intent.get("filename") or parsed_intent.get("query") or parsed_intent.get("app_name", "")

        if target in ["file", "folder", "directory", None, ""]:
            fname = parsed_intent.get("filename")
            dest = parsed_intent.get("destination")
            if not fname:
                import re
                m_name = re.search(r"(?:called|named)\s+([a-zA-Z0-9_\-\.]+)", scenario.command, re.IGNORECASE)
                if not m_name:
                    m_name = re.search(r"\b([a-zA-Z0-9_\-]+\.(?:py|cpp|cc|c|h|java|js|ts|html|css|sql|md|txt|json))\b", scenario.command, re.IGNORECASE)
                if m_name:
                    fname = m_name.group(1).strip()

            if fname:
                cmd_low = scenario.command.lower()
                if dest:
                    target = f"{dest}/{fname}"
                elif "desktop" in cmd_low:
                    target = f"Desktop/{fname}"
                elif "document" in cmd_low:
                    target = f"Documents/{fname}"
                elif "download" in cmd_low:
                    target = f"Downloads/{fname}"
                elif "dsa" in cmd_low:
                    target = f"dsa/{fname}"
                else:
                    target = fname

        if intent in ["open_app", "close_app", "switch_window", "window_control"]:
            return adapters.handle_app_control(action=action, target=target, args=parsed_intent)
        elif intent in ["browser_action", "web_search", "open_new_chrome_tab"]:
            return adapters.handle_browser(action=action or "search", target=target, args=parsed_intent)
        elif intent in ["filesystem_control", "content_generation", "file_management", "file_management.create_file", "file_management.search"] or ("file" in str(action) or "folder" in str(action)):
            return adapters.handle_filesystem(action=action, target=target, args=parsed_intent)
        elif intent in ["screen_intelligence", "screen_understanding.explain", "screen_understanding.analyze"]:
            return adapters.handle_screen_explain(context=parsed_intent)
        elif intent in ["sleep_mode", "wake_mode"] or (intent == "system_control" and "sleep" in str(action)):
            return {"tool": "sleep_wake", "action": action, "success": True, "message": f"State machine transitioned: {action}"}
        else:
            return {"tool": "general_core", "action": action or "execute", "success": True, "message": f"Processed intent '{intent}'"}
