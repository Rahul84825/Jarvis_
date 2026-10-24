"""Automated Test Suite for the SANTRA Virtual Testing Room Subsystem."""

import os
import unittest
from core.virtual_lab import (
    VirtualLabController,
    ExecutionMode,
    ScenarioCategory,
    CommandScenario,
    EnvironmentSimulator,
    MockToolAdapters,
    CommandTestRunner,
    StateAssertionEngine,
    StressTestManager,
    TestStatus,
    ScenarioLibrary
)


class TestVirtualLab(unittest.TestCase):
    """Verifies the integrity, isolation, assertions, and runner of the Virtual Testing Room."""

    def setUp(self):
        self.controller = VirtualLabController(mode=ExecutionMode.SIMULATION)
        self.env = EnvironmentSimulator()

    def tearDown(self):
        self.env.cleanup()

    def test_environment_simulator_isolation(self):
        """Verify that simulated filesystem operations remain strictly inside the temporary sandbox."""
        self.assertTrue(os.path.isdir(self.env.fs.root_path))
        test_file_path = self.env.fs.resolve_path("Desktop/virtual_sample.py")
        self.assertTrue(test_file_path.startswith(self.env.fs.root_path))

        # Write file inside virtual filesystem
        ok = self.env.fs.save_file(test_file_path, "print('Virtual Lab')", overwrite=False)
        self.assertTrue(ok)
        self.assertTrue(self.env.fs.file_exists("Desktop/virtual_sample.py"))

        # Overwrite protection check
        attempt_ok = self.env.fs.save_file(test_file_path, "new content", overwrite=False)
        self.assertFalse(attempt_ok)
        self.assertIn(test_file_path, self.env.fs.overwrite_attempts)

    def test_virtual_application_lifecycle(self):
        """Verify application launch, focus, and close state mutations."""
        app = self.env.apps["chrome"]
        self.assertTrue(app.is_running)

        app.close()
        self.assertFalse(app.is_running)
        self.assertFalse(app.is_focused)

        app.launch()
        self.assertTrue(app.is_running)
        self.assertTrue(app.is_focused)

    def test_virtual_browser_navigation_and_search(self):
        """Verify virtual browser tab tracking, URL navigation, and search queries."""
        browser = self.env.browser
        browser.open_url("https://example.com", site_name="example", new_tab=False)
        self.assertEqual(browser.active_url, "https://example.com")

        browser.execute_search("valorant highlights", site="youtube", new_tab=True)
        self.assertEqual(browser.last_search_query, "valorant highlights")
        self.assertEqual(browser.last_search_site, "youtube")
        self.assertEqual(len(browser.tabs), 2)

    def test_mock_adapters_redirection(self):
        """Verify mock adapters safely intercept actions without touching real OS."""
        adapters = MockToolAdapters(self.env)

        # App control
        res_app = adapters.handle_app_control(action="open", target="notepad")
        self.assertTrue(res_app["success"])
        self.assertTrue(self.env.apps["notepad"].is_running)

        # Filesystem
        res_fs = adapters.handle_filesystem(action="save_file", target="Desktop/test_mock.py", args={"content": "x = 42"})
        self.assertTrue(res_fs["success"])
        self.assertTrue(self.env.fs.file_exists("Desktop/test_mock.py"))

        # AI generation (deterministic mock)
        ai_resp = adapters.handle_ai_generate([{"role": "user", "content": "What is Python?"}])
        self.assertIn("Python", ai_resp)

        # Screen explanation (synthetic mock)
        screen_resp = adapters.handle_screen_explain()
        self.assertTrue(screen_resp["success"])
        self.assertIn("binary_search", screen_resp["extracted_text"])

    def test_state_assertion_engine_accuracy(self):
        """Verify StateAssertionEngine detects mismatches and classifies failure categories."""
        engine = StateAssertionEngine()
        scenario = CommandScenario(
            scenario_id="TEST-001",
            category=ScenarioCategory.APP_CONTROL,
            command="Open Chrome",
            description="Test app launch assertion",
            expected_intent="open_app",
            expected_action="open",
            expected_state_changes={"app_launched": "chrome"}
        )

        # Pass condition
        parsed = {"intent": "open_app", "action": "open", "target": "chrome"}
        outcome = {"tool": "app_control", "message": "Launched"}
        before = self.env.snapshot()
        self.env.apps["chrome"].launch()
        after = self.env.snapshot()

        res_pass = engine.evaluate(scenario, parsed, outcome, before, after, 5.0, self.env)
        self.assertEqual(res_pass.status, TestStatus.PASSED)

        # Intent failure condition
        parsed_bad = {"intent": "wrong_intent", "action": "wrong"}
        res_fail = engine.evaluate(scenario, parsed_bad, outcome, before, after, 5.0, self.env)
        self.assertEqual(res_fail.status, TestStatus.FAILED)
        self.assertEqual(res_fail.failure_category.value, "intent_resolution")

    def test_single_scenario_execution(self):
        """Verify single scenario execution through CommandTestRunner."""
        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        scenario = ScenarioLibrary.get_by_id("APP-001")
        self.assertIsNotNone(scenario)

        result = runner.run_scenario(scenario)
        self.assertEqual(result.status, TestStatus.PASSED)
        self.assertEqual(result.intent_matched, "open_app")

    def test_ambiguity_clarification_scenario(self):
        """Verify ambiguous command ('Open it') triggers clarification rather than blind action."""
        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        scenario = ScenarioLibrary.get_by_id("AMB-001")
        self.assertIsNotNone(scenario)

        result = runner.run_scenario(scenario)
        # AMB-001 requires clarification
        self.assertEqual(result.status, TestStatus.PASSED)

    def test_run_category_app_control(self):
        """Verify batch execution of Application Control scenarios."""
        results, md_report, json_report = self.controller.run_category(ScenarioCategory.APP_CONTROL)
        self.assertTrue(len(results) >= 4)
        passed = sum(1 for r in results if r.status == TestStatus.PASSED)
        self.assertEqual(passed, len(results))
        self.assertIn("# SANTRA VIRTUAL TESTING ROOM", md_report)

    def test_stress_manager_concurrency(self):
        """Verify stress test manager coordinates concurrent workloads with bounded threads."""
        stress_mgr = StressTestManager(max_workers=3, timeout_sec=10.0)

        def mock_worker(cmd):
            return {"status": True, "cmd": cmd}

        workload = [f"query_{i}" for i in range(6)]
        res = stress_mgr.run_concurrent_workload(mock_worker, workload)
        self.assertEqual(res["total_requests"], 6)
        self.assertEqual(res["success_count"], 6)
        self.assertFalse(res["cancelled"])

    def test_virtual_lab_panel_ui(self):
        """Verify VirtualLabPanel and VirtualLabDialog UI widgets instantiate correctly."""
        from PyQt6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.panels.virtual_lab_panel import VirtualLabDialog, VirtualLabPanel
        dialog = VirtualLabDialog()
        self.assertIsNotNone(dialog)
        self.assertIn("VIRTUAL TESTING ROOM", dialog.windowTitle())
        panel = dialog.panel
        self.assertEqual(panel.card_total.value_label.text(), "0")
        self.assertEqual(panel.combo_cat.count(), 11)
        self.assertTrue(panel.btn_run_all.isEnabled())

    def test_scenario_APP_002(self):
        """Verify APP-002: Open Notepad launches Notepad and sets focus."""
        scenario = ScenarioLibrary.get_by_id("APP-002")
        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        res = runner.run_scenario(scenario)
        self.assertEqual(res.status, TestStatus.PASSED, res.failure_reason)

    def test_scenario_NAV_001(self):
        """Verify NAV-001: Open example.com in Chrome navigates active browser URL."""
        scenario = ScenarioLibrary.get_by_id("NAV-001")
        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        res = runner.run_scenario(scenario)
        self.assertEqual(res.status, TestStatus.PASSED, res.failure_reason)

    def test_scenario_NAV_002(self):
        """Verify NAV-002: Search YouTube for Valorant highlights executes video search."""
        scenario = ScenarioLibrary.get_by_id("NAV-002")
        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        res = runner.run_scenario(scenario)
        self.assertEqual(res.status, TestStatus.PASSED, res.failure_reason)

    def test_scenario_NAV_003(self):
        """Verify NAV-003: Search for Naruto on HiAnime extracts site and query."""
        scenario = ScenarioLibrary.get_by_id("NAV-003")
        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        res = runner.run_scenario(scenario)
        self.assertEqual(res.status, TestStatus.PASSED, res.failure_reason)

    def test_scenario_NAV_004(self):
        """Verify NAV-004: Search Google for python decorators preserves web search."""
        scenario = ScenarioLibrary.get_by_id("NAV-004")
        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        res = runner.run_scenario(scenario)
        self.assertEqual(res.status, TestStatus.PASSED, res.failure_reason)

    def test_scenario_FIL_001(self):
        """Verify FIL-001: Create a Python file on the Desktop called test.py creates file."""
        scenario = ScenarioLibrary.get_by_id("FIL-001")
        runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
        res = runner.run_scenario(scenario)
        self.assertEqual(res.status, TestStatus.PASSED, res.failure_reason)


# Bind test_scenario_<ID> methods dynamically for all 35 library scenarios
# to enable python -m unittest tests.test_virtual_lab -k <SCENARIO_ID>
for _sc in ScenarioLibrary.get_all_scenarios():
    _sid_clean = _sc.scenario_id.replace("-", "_")
    _m_name = f"test_scenario_{_sid_clean}"
    if not hasattr(TestVirtualLab, _m_name):
        def _make_scenario_test(target_id):
            def _test_method(self):
                sc = ScenarioLibrary.get_by_id(target_id)
                self.assertIsNotNone(sc, f"Scenario '{target_id}' not found in library.")
                runner = CommandTestRunner(mode=ExecutionMode.SIMULATION)
                res = runner.run_scenario(sc)
                self.assertEqual(res.status, TestStatus.PASSED, res.failure_reason)
            return _test_method
        setattr(TestVirtualLab, _m_name, _make_scenario_test(_sc.scenario_id))


if __name__ == "__main__":
    unittest.main()
