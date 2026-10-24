"""Virtual Lab Controller — Central facade and orchestrator for the SANTRA Virtual Testing Room."""

import time
import uuid
import logging
from typing import List, Dict, Optional, Any, Callable, Tuple

from core.virtual_lab.models import (
    CommandScenario, ScenarioResult, ExecutionMode, ScenarioCategory, TestStatus
)
from core.virtual_lab.environment_simulator import EnvironmentSimulator
from core.virtual_lab.scenario_library import ScenarioLibrary
from core.virtual_lab.test_runner import CommandTestRunner
from core.virtual_lab.stress_manager import StressTestManager
from core.virtual_lab.result_store import TestResultStore
from core.virtual_lab.report_generator import ReportGenerator

logger = logging.getLogger("Santra.VirtualLab.Controller")


class VirtualLabController:
    """Master controller managing simulation runs, stress testing, and capability reports."""

    def __init__(self, mode: ExecutionMode = ExecutionMode.SIMULATION):
        self.mode = mode
        self.store = TestResultStore()
        self.stress_mgr = StressTestManager()
        self._is_cancelled = False
        self.last_results: List[ScenarioResult] = []
        self.last_run_id: str = ""

    def set_execution_mode(self, mode: ExecutionMode):
        """Sets the active execution mode (SIMULATION or CONTROLLED_INTEGRATION)."""
        self.mode = mode
        logger.info(f"[VirtualLab] Active execution mode set to: {self.mode.value}")

    def cancel(self):
        """Halts active testing workflows."""
        self._is_cancelled = True
        self.stress_mgr.cancel()
        logger.warning("[VirtualLab] Cancellation requested.")

    def run_all(
        self,
        mode: Optional[ExecutionMode] = None,
        on_progress: Optional[Callable[[int, int, ScenarioResult], None]] = None
    ) -> Tuple[List[ScenarioResult], str, Dict[str, Any]]:
        """Executes all scenarios across all 10 categories."""
        scenarios = ScenarioLibrary.get_all_scenarios()
        return self._execute_scenario_batch(scenarios, mode=mode, on_progress=on_progress)

    def run_category(
        self,
        category: ScenarioCategory,
        mode: Optional[ExecutionMode] = None,
        on_progress: Optional[Callable[[int, int, ScenarioResult], None]] = None
    ) -> Tuple[List[ScenarioResult], str, Dict[str, Any]]:
        """Executes scenarios filtered by a specific category."""
        scenarios = ScenarioLibrary.get_by_category(category)
        return self._execute_scenario_batch(scenarios, mode=mode, on_progress=on_progress)

    def run_failed_scenarios(
        self,
        mode: Optional[ExecutionMode] = None,
        on_progress: Optional[Callable[[int, int, ScenarioResult], None]] = None
    ) -> Tuple[List[ScenarioResult], str, Dict[str, Any]]:
        """Re-runs scenarios that failed in the most recent test run."""
        failed_ids = self.store.get_latest_failed_scenario_ids()
        if not failed_ids and self.last_results:
            failed_ids = [r.scenario_id for r in self.last_results if r.status == TestStatus.FAILED]

        scenarios = [s for s in ScenarioLibrary.get_all_scenarios() if s.scenario_id in failed_ids]
        if not scenarios:
            logger.info("[VirtualLab] No failed scenarios found to re-run.")
            return [], "", {}

        return self._execute_scenario_batch(scenarios, mode=mode, on_progress=on_progress)

    re_run_failed = run_failed_scenarios

    def run_single(self, scenario_id: str, mode: Optional[ExecutionMode] = None) -> Optional[ScenarioResult]:
        """Executes a single test scenario by ID."""
        scenario = ScenarioLibrary.get_by_id(scenario_id)
        if not scenario:
            logger.error(f"[VirtualLab] Scenario '{scenario_id}' not found.")
            return None

        runner = CommandTestRunner(mode=mode or self.mode)
        res = runner.run_scenario(scenario)
        return res

    def _execute_scenario_batch(
        self,
        scenarios: List[CommandScenario],
        mode: Optional[ExecutionMode] = None,
        on_progress: Optional[Callable[[int, int, ScenarioResult], None]] = None
    ) -> Tuple[List[ScenarioResult], str, Dict[str, Any]]:
        """Internal worker executing a list of scenarios with isolated environments and progress reporting."""
        self._is_cancelled = False
        exec_mode = mode or self.mode
        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
        self.last_run_id = run_id

        runner = CommandTestRunner(mode=exec_mode)
        results: List[ScenarioResult] = []
        total = len(scenarios)

        t_start = time.perf_counter()
        logger.info(f"[VirtualLab] Starting test batch '{run_id}' with {total} scenarios (Mode: {exec_mode.value})")

        # Share persistent virtual environment across scenarios for multi-turn/contextual scenarios,
        # but reset transient states as needed.
        shared_env = EnvironmentSimulator()

        try:
            for idx, sc in enumerate(scenarios, 1):
                if self._is_cancelled:
                    logger.info("[VirtualLab] Batch run cancelled by user.")
                    break

                res = runner.run_scenario(sc, env=shared_env)
                results.append(res)

                if on_progress:
                    try:
                        on_progress(idx, total, res)
                    except Exception as pe:
                        logger.debug(f"[VirtualLab] Progress callback error: {pe}")

        finally:
            shared_env.cleanup()

        duration_sec = time.perf_counter() - t_start
        self.last_results = results

        # Persist outcomes in SQLite result store
        self.store.save_run(run_id=run_id, results=results, duration_sec=duration_sec, mode=exec_mode)

        # Generate diagnostic outputs
        md_report = ReportGenerator.generate_markdown(run_id=run_id, results=results, duration_sec=duration_sec, mode=exec_mode)
        json_report = ReportGenerator.generate_json(run_id=run_id, results=results, duration_sec=duration_sec, mode=exec_mode)

        return results, md_report, json_report

    def run_stress_test(
        self,
        concurrency: int = 4,
        count: int = 15,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """Runs bounded concurrency stress tests."""
        test_commands = [
            "Explain polymorphism in C++",
            "What is Python?",
            "Explain recursion",
            "What is quicksort?",
            "Open Chrome"
        ] * (count // 5 + 1)
        workload = test_commands[:count]

        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        sample_sc = ScenarioLibrary.get_by_id("AI-002") or ScenarioLibrary.get_all_scenarios()[0]

        def _execute_cmd(cmd: str):
            sc = CommandScenario(
                scenario_id=f"STRESS-{uuid.uuid4().hex[:6]}",
                category=ScenarioCategory.STRESS_CONCURRENCY,
                command=cmd,
                description="Concurrent load test task",
                expected_intent="content_generation"
            )
            return runner.run_scenario(sc)

        self.stress_mgr.max_workers = concurrency
        return self.stress_mgr.run_concurrent_workload(_execute_cmd, workload, on_progress=on_progress)

    def get_capability_matrix(self) -> List[Dict[str, Any]]:
        """Returns structured capability matrix assessing coverage across all command categories."""
        from core.tool_registry import tool_registry
        all_tools = tool_registry.list_all_tools()
        scenarios = ScenarioLibrary.get_all_scenarios()

        matrix: List[Dict[str, Any]] = []
        for cat in ScenarioCategory:
            cat_scenarios = [s for s in scenarios if s.category == cat]
            matrix.append({
                "category": cat.value,
                "scenarios_count": len(cat_scenarios),
                "status": "IMPLEMENTED_AND_TESTED" if cat_scenarios else "REQUIRES_SCENARIOS",
                "sample_command": cat_scenarios[0].command if cat_scenarios else "None"
            })
        return matrix
