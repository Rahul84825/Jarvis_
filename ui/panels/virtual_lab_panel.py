"""
SANTRA Virtual Testing Room — Interactive PyQt6 HUD Dashboard & Capability Evaluation Panel.

Provides:
- Real-time simulation runner with non-blocking QThread execution.
- Metrics cards: Total, Passed, Failed, Pass Rate %, Duration.
- Scenario filter by category and execution mode selector (Simulation vs Controlled Integration).
- Full command execution history, state assertions, and failure inspection.
- Report export (Markdown and JSON).
- Bounded concurrent stress test runner.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QTextEdit, QFrame, QSplitter, QDialog,
    QMessageBox, QFileDialog
)

from ui.theme import HUDColors
from core.virtual_lab.models import (
    ScenarioCategory, ExecutionMode, TestStatus,
    FailureCategory, ScenarioResult
)
from core.virtual_lab.scenario_library import ScenarioLibrary
from core.virtual_lab.lab_controller import VirtualLabController
from core.virtual_lab.report_generator import ReportGenerator

logger = logging.getLogger("Santra.UI.VirtualLab")


class VirtualLabWorker(QThread):
    """Background worker thread executing scenarios asynchronously without freezing the PyQt6 UI."""
    sig_progress = pyqtSignal(int, int, object)  # current, total, ScenarioResult
    sig_finished = pyqtSignal(list, str, dict)   # results, md_report, json_report
    sig_error = pyqtSignal(str)

    def __init__(
        self,
        controller: VirtualLabController,
        action: str = "run_all",
        category: Optional[ScenarioCategory] = None,
        failed_ids: Optional[List[str]] = None,
        mode: Optional[ExecutionMode] = None
    ):
        super().__init__()
        self.controller = controller
        self.action = action
        self.category = category
        self.failed_ids = failed_ids or []
        self.mode = mode or ExecutionMode.SIMULATION

    def run(self):
        try:
            def on_progress(curr: int, tot: int, res: ScenarioResult):
                self.sig_progress.emit(curr, tot, res)

            if self.action == "run_all":
                results, md, j = self.controller.run_all(mode=self.mode, on_progress=on_progress)
            elif self.action == "run_category" and self.category:
                results, md, j = self.controller.run_category(self.category, mode=self.mode, on_progress=on_progress)
            elif self.action == "re_run_failed":
                results, md, j = self.controller.re_run_failed(mode=self.mode, on_progress=on_progress)
            elif self.action == "stress":
                stress_res = self.controller.run_stress_test(concurrency=4, total_requests=8)
                md = f"# STRESS TEST RUN COMPLETE\n\n```json\n{json.dumps(stress_res, indent=2)}\n```"
                j = {"stress_results": stress_res}
                results = []
            else:
                results, md, j = self.controller.run_all(mode=self.mode, on_progress=on_progress)

            self.sig_finished.emit(results, md, j)
        except Exception as e:
            logger.error(f"[VirtualLabWorker] Execution error: {e}", exc_info=True)
            self.sig_error.emit(str(e))

    def cancel(self):
        self.controller.cancel()


class VirtualLabPanel(QWidget):
    """Interactive HUD Panel for testing and evaluating Santra's capabilities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controller = VirtualLabController(mode=ExecutionMode.SIMULATION)
        self.worker: Optional[VirtualLabWorker] = None
        self.last_results: List[ScenarioResult] = []
        self.last_md_report: str = ""
        self.last_json_report: Dict[str, Any] = {}

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header Title & Subtitle Banner
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet("background: rgba(10, 16, 26, 220); border: 1px solid rgba(0, 240, 255, 45); border-radius: 6px; padding: 10px;")
        hdr_layout = QHBoxLayout(hdr_frame)
        hdr_layout.setContentsMargins(12, 6, 12, 6)

        title_box = QVBoxLayout()
        title_lbl = QLabel("🧪 SANTRA VIRTUAL TESTING ROOM // CAPABILITY EVALUATION LAB")
        title_lbl.setStyleSheet("color: #00f0ff; font-weight: 800; font-size: 14px; letter-spacing: 1.5px;")
        sub_lbl = QLabel("Isolated Desktop Simulation, Ambiguity Detection, State Assertions & Stress Verification")
        sub_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        hdr_layout.addLayout(title_box)
        hdr_layout.addStretch()

        # Mode Badge / Selector
        mode_box = QVBoxLayout()
        mode_box.setAlignment(Qt.AlignmentFlag.AlignRight)
        mode_title = QLabel("EXECUTION ENVIRONMENT")
        mode_title.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: bold; letter-spacing: 1px;")
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("🛡️ Simulation Mode (Default & Safe)", ExecutionMode.SIMULATION)
        self.combo_mode.addItem("⚙️ Controlled Integration Mode", ExecutionMode.CONTROLLED_INTEGRATION)
        self.combo_mode.setStyleSheet("""
            QComboBox {
                background: #0f172a;
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 60);
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        mode_box.addWidget(mode_title)
        mode_box.addWidget(self.combo_mode)
        hdr_layout.addLayout(mode_box)
        main_layout.addWidget(hdr_frame)

        # 2. Metric Scorecards Row
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(10)

        self.card_total = self._create_metric_card("TOTAL SCENARIOS", "0", "#94a3b8")
        self.card_passed = self._create_metric_card("PASSED", "0", "#00e5a3")
        self.card_failed = self._create_metric_card("FAILED", "0", "#ff3366")
        self.card_rate = self._create_metric_card("PASS RATE", "0.0%", "#00f0ff")
        self.card_duration = self._create_metric_card("BATCH TIME", "0.0s", "#ffb300")

        metrics_layout.addWidget(self.card_total)
        metrics_layout.addWidget(self.card_passed)
        metrics_layout.addWidget(self.card_failed)
        metrics_layout.addWidget(self.card_rate)
        metrics_layout.addWidget(self.card_duration)
        main_layout.addLayout(metrics_layout)

        # 3. Action Toolbar & Category Selector
        toolbar = QFrame()
        toolbar.setStyleSheet("background: rgba(15, 23, 42, 160); border: 1px solid rgba(255, 255, 255, 12); border-radius: 6px; padding: 6px;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(8)

        # Category Filter
        self.combo_cat = QComboBox()
        self.combo_cat.addItem("📂 All Categories (Full Suite)", None)
        for cat in ScenarioCategory:
            self.combo_cat.addItem(f"📁 {cat.value.replace('_', ' ').title()}", cat)
        self.combo_cat.setStyleSheet("background: #0b1120; color: #cbd5e1; border: 1px solid #334155; padding: 4px 8px; border-radius: 4px; font-size: 11px;")
        tb_layout.addWidget(self.combo_cat)

        # Run Buttons
        self.btn_run_all = QPushButton("▶ RUN ALL")
        self.btn_run_all.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px; border: none; font-size: 11px;")
        self.btn_run_all.clicked.connect(self._on_run_all)
        tb_layout.addWidget(self.btn_run_all)

        self.btn_run_cat = QPushButton("🎯 RUN CATEGORY")
        self.btn_run_cat.setStyleSheet("background: #0f766e; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: none; font-size: 11px;")
        self.btn_run_cat.clicked.connect(self._on_run_category)
        tb_layout.addWidget(self.btn_run_cat)

        self.btn_rerun_failed = QPushButton("🔄 RE-RUN FAILED")
        self.btn_rerun_failed.setStyleSheet("background: #b45309; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: none; font-size: 11px;")
        self.btn_rerun_failed.clicked.connect(self._on_rerun_failed)
        tb_layout.addWidget(self.btn_rerun_failed)

        self.btn_stress = QPushButton("⚡ STRESS TEST")
        self.btn_stress.setStyleSheet("background: #6d28d9; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: none; font-size: 11px;")
        self.btn_stress.clicked.connect(self._on_run_stress)
        tb_layout.addWidget(self.btn_stress)

        self.btn_stop = QPushButton("⏹ STOP")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("background: #be123c; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: none; font-size: 11px;")
        self.btn_stop.clicked.connect(self._on_stop)
        tb_layout.addWidget(self.btn_stop)

        tb_layout.addStretch()

        self.btn_export = QPushButton("💾 EXPORT REPORT")
        self.btn_export.setStyleSheet("background: #334155; color: #38bdf8; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: 1px solid #475569; font-size: 11px;")
        self.btn_export.clicked.connect(self._on_export)
        tb_layout.addWidget(self.btn_export)

        main_layout.addWidget(toolbar)

        # 4. Live Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #0f172a;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f0ff, stop:1 #00e5a3);
                border-radius: 2px;
            }
        """)
        main_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Virtual Lab Ready. Select an action above to execute deterministic simulation tests.")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 10px; font-family: monospace;")
        main_layout.addWidget(self.lbl_status)

        # 5. Splitter: Results Table (Top/Left) and Inspector Card (Bottom/Right)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Table Widget
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Category", "Command", "Status", "Intent Matched", "Duration"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet("""
            QTableWidget {
                background: rgba(11, 15, 25, 230);
                color: #e2e8f0;
                border: 1px solid rgba(0, 240, 255, 30);
                gridline-color: rgba(255, 255, 255, 10);
                font-size: 11px;
                selection-background-color: rgba(0, 240, 255, 40);
            }
            QHeaderView::section {
                background: #0f172a;
                color: #00f0ff;
                font-weight: bold;
                font-size: 10px;
                border: none;
                padding: 6px;
                letter-spacing: 1px;
            }
        """)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        splitter.addWidget(self.table)

        # Inspector Card (Bottom)
        self.inspector_card = QFrame()
        self.inspector_card.setStyleSheet("background: rgba(13, 19, 33, 230); border: 1px solid rgba(255, 255, 255, 15); border-radius: 6px;")
        insp_layout = QVBoxLayout(self.inspector_card)
        insp_layout.setContentsMargins(12, 10, 12, 10)
        insp_layout.setSpacing(6)

        insp_title = QLabel("🔍 SCENARIO DIAGNOSTIC & STATE INSPECTOR")
        insp_title.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 10px; letter-spacing: 1px;")
        insp_layout.addWidget(insp_title)

        self.txt_inspector = QTextEdit()
        self.txt_inspector.setReadOnly(True)
        self.txt_inspector.setStyleSheet("background: #090d16; color: #94a3b8; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #1e293b; border-radius: 4px;")
        self.txt_inspector.setPlaceholderText("Click any executed test scenario above to inspect parsed intents, state mutations, and diagnostics.")
        insp_layout.addWidget(self.txt_inspector)

        splitter.addWidget(self.inspector_card)
        splitter.setSizes([380, 180])
        main_layout.addWidget(splitter)

    def _create_metric_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background: rgba(15, 23, 42, 210); border: 1px solid rgba(255, 255, 255, 12); border-left: 3px solid {color}; border-radius: 4px; padding: 6px;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #64748b; font-size: 9px; font-weight: bold; letter-spacing: 1px;")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 800; font-family: monospace;")
        card.value_label = lbl_v

        layout.addWidget(lbl_t)
        layout.addWidget(lbl_v)
        return card

    def _on_run_all(self):
        self._start_execution(action="run_all")

    def _on_run_category(self):
        cat = self.combo_cat.currentData()
        if not cat:
            self._start_execution(action="run_all")
        else:
            self._start_execution(action="run_category", category=cat)

    def _on_rerun_failed(self):
        self._start_execution(action="re_run_failed")

    def _on_run_stress(self):
        self._start_execution(action="stress")

    def _start_execution(self, action: str, category: Optional[ScenarioCategory] = None):
        if self.worker and self.worker.isRunning():
            return

        mode = self.combo_mode.currentData()
        self.table.setRowCount(0)
        self.txt_inspector.clear()
        self.progress_bar.setValue(0)
        self.btn_stop.setEnabled(True)
        self.btn_run_all.setEnabled(False)
        self.btn_run_cat.setEnabled(False)
        self.btn_rerun_failed.setEnabled(False)
        self.btn_stress.setEnabled(False)

        self.lbl_status.setText(f"Executing batch '{action}' (Mode: {mode.value})...")

        self.worker = VirtualLabWorker(
            controller=self.controller,
            action=action,
            category=category,
            mode=mode
        )
        self.worker.sig_progress.connect(self._on_worker_progress)
        self.worker.sig_finished.connect(self._on_worker_finished)
        self.worker.sig_error.connect(self._on_worker_error)
        self.worker.start()

    def _on_stop(self):
        if self.worker and self.worker.isRunning():
            self.lbl_status.setText("Halting test execution...")
            self.worker.cancel()

    def _on_worker_progress(self, current: int, total: int, res: ScenarioResult):
        pct = int((current / max(total, 1)) * 100)
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(f"Running [{current}/{total}]: {res.command}")

        # Append row to table
        row = self.table.rowCount()
        self.table.insertRow(row)

        item_id = QTableWidgetItem(res.scenario_id)
        item_cat = QTableWidgetItem(res.scenario_id.split("-")[0])
        item_cmd = QTableWidgetItem(res.command)

        status_text = "✔ PASS" if res.status == TestStatus.PASSED else "✖ FAIL"
        item_status = QTableWidgetItem(status_text)
        if res.status == TestStatus.PASSED:
            item_status.setForeground(QColor("#00e5a3"))
        else:
            item_status.setForeground(QColor("#ff3366"))

        item_intent = QTableWidgetItem(res.intent_matched or "unknown")
        item_dur = QTableWidgetItem(f"{res.duration_ms:.1f} ms")

        # Associate result data with row
        item_id.setData(Qt.ItemDataRole.UserRole, res)

        for col, it in enumerate([item_id, item_cat, item_cmd, item_status, item_intent, item_dur]):
            it.setFlags(it.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, it)

        self.table.scrollToBottom()

    def _on_worker_finished(self, results: List[ScenarioResult], md_report: str, json_report: Dict[str, Any]):
        self.last_results = results
        self.last_md_report = md_report
        self.last_json_report = json_report

        self.btn_stop.setEnabled(False)
        self.btn_run_all.setEnabled(True)
        self.btn_run_cat.setEnabled(True)
        self.btn_rerun_failed.setEnabled(True)
        self.btn_stress.setEnabled(True)
        self.progress_bar.setValue(100)

        total = len(results)
        passed = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed = total - passed
        rate = (passed / total * 100) if total > 0 else 0.0
        tot_time = sum(r.duration_ms for r in results) / 1000.0

        self.card_total.value_label.setText(str(total))
        self.card_passed.value_label.setText(str(passed))
        self.card_failed.value_label.setText(str(failed))
        self.card_rate.value_label.setText(f"{rate:.1f}%")
        self.card_duration.value_label.setText(f"{tot_time:.2f}s")

        self.lbl_status.setText(f"Batch execution complete: {passed}/{total} passed ({rate:.1f}%) in {tot_time:.2f}s.")

    def _on_worker_error(self, err_msg: str):
        self.btn_stop.setEnabled(False)
        self.btn_run_all.setEnabled(True)
        self.btn_run_cat.setEnabled(True)
        self.btn_rerun_failed.setEnabled(True)
        self.btn_stress.setEnabled(True)
        self.lbl_status.setText(f"Error during execution: {err_msg}")
        QMessageBox.critical(self, "Virtual Lab Execution Error", f"An unexpected error occurred during test execution:\n{err_msg}")

    def _on_table_selection(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        item_id = self.table.item(row, 0)
        if not item_id:
            return

        res: ScenarioResult = item_id.data(Qt.ItemDataRole.UserRole)
        if not res:
            return

        # Format diagnostic inspection
        diag_lines = [
            f"=== SCENARIO {res.scenario_id} [{res.status.value.upper()}] ===",
            f"Command:                '{res.command}'",
            f"Execution Mode:         {res.mode.value}",
            f"Execution Duration:     {res.duration_ms:.2f} ms",
            f"Matched Intent:         {res.intent_matched}",
            f"Matched Action:         {res.action_matched}",
            f"Tool Invoked:           {res.tool_invoked}",
            f"Tool Arguments:         {json.dumps(res.tool_args or {})}",
            f"Output Message:         {res.output_message}",
        ]

        if res.status != TestStatus.PASSED:
            diag_lines.extend([
                "",
                f"✖ FAILURE CATEGORY:     {res.failure_category.value if res.failure_category else 'UNKNOWN'}",
                f"✖ FAILURE REASON:       {res.failure_reason}",
            ])

        if res.simulated_state_diff:
            diag_lines.extend([
                "",
                "--- SIMULATED STATE MUTATIONS ---",
                json.dumps(res.simulated_state_diff, indent=2)
            ])

        if res.reproduction_instructions:
            diag_lines.extend([
                "",
                "--- REPRODUCTION COMMAND ---",
                res.reproduction_instructions
            ])

        self.txt_inspector.setText("\n".join(diag_lines))

    def _on_export(self):
        if not self.last_md_report:
            QMessageBox.information(self, "Export Report", "No test run report available yet. Run a test batch first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Virtual Lab Diagnostic Report",
            os.path.join(os.getcwd(), "docs", "SANTRA_VIRTUAL_LAB_REPORT.md"),
            "Markdown (*.md);;JSON (*.json)"
        )
        if not file_path:
            return

        try:
            if file_path.endswith(".json"):
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(self.last_json_report, f, indent=2)
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.last_md_report)
            QMessageBox.information(self, "Export Succeeded", f"Virtual Lab report exported successfully to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to save report: {e}")


class VirtualLabDialog(QDialog):
    """Modal or modeless dialog housing the Santra Virtual Testing Room HUD."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SANTRA VIRTUAL TESTING ROOM // CAPABILITY EVALUATION LAB")
        self.resize(1160, 740)
        self.setMinimumSize(960, 600)
        self.setStyleSheet("background-color: #0b0f19; color: #e2e8f0;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.panel = VirtualLabPanel(self)
        layout.addWidget(self.panel)
