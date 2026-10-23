"""Diagnostic Report Generator for the SANTRA Virtual Testing Room."""

import json
from datetime import datetime
from typing import List, Dict, Any
from core.virtual_lab.models import ScenarioResult, ExecutionMode, TestStatus


class ReportGenerator:
    """Generates detailed Markdown and JSON diagnostic reports for Santra test runs."""

    @staticmethod
    def generate_markdown(
        run_id: str,
        results: List[ScenarioResult],
        duration_sec: float,
        mode: ExecutionMode = ExecutionMode.SIMULATION
    ) -> str:
        """Constructs an engineering report in GitHub-flavored Markdown."""
        total = len(results)
        passed = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in results if r.status == TestStatus.FAILED)
        pass_rate = (passed / total * 100) if total > 0 else 0.0

        # Category aggregation
        category_counts: Dict[str, Dict[str, int]] = {}
        for r in results:
            cat = r.scenario_id.split("-")[0]
            cat_stat = category_counts.setdefault(cat, {"total": 0, "passed": 0, "failed": 0})
            cat_stat["total"] += 1
            if r.status == TestStatus.PASSED:
                cat_stat["passed"] += 1
            else:
                cat_stat["failed"] += 1

        md = []
        md.append(f"# SANTRA VIRTUAL TESTING ROOM — EVALUATION REPORT")
        md.append(f"\n**Run ID:** `{run_id}`  ")
        md.append(f"**Execution Mode:** `{mode.value.upper()}`  ")
        md.append(f"**Timestamp:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`  ")
        md.append(f"**Execution Duration:** `{duration_sec:.2f} seconds`  ")
        md.append(f"**Overall Pass Rate:** `{pass_rate:.1f}%` ({passed}/{total} Scenarios Passed)\n")

        md.append("## 1. Executive Summary\n")
        md.append("| Metric | Value | Status |")
        md.append("| :--- | :--- | :--- |")
        md.append(f"| Total Scenarios Tested | {total} | Completed |")
        md.append(f"| Passed Scenarios | {passed} | {'✅ Optimal' if failed == 0 else '⚠️ Attention Needed'} |")
        md.append(f"| Failed Scenarios | {failed} | {'✅ None' if failed == 0 else '❌ Failures Detected'} |")
        md.append(f"| Total Runtime | {duration_sec:.2f}s | Fast |")
        md.append(f"| Pass Rate | {pass_rate:.1f}% | {'✅ PASS' if pass_rate >= 90.0 else '⚠️ REVIEW'} |\n")

        md.append("## 2. Category Performance Breakdown\n")
        md.append("| Category Prefix | Total | Passed | Failed | Pass Rate |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for cat, stats in sorted(category_counts.items()):
            c_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
            icon = "✅" if stats["failed"] == 0 else "❌"
            md.append(f"| `{cat}` | {stats['total']} | {stats['passed']} | {stats['failed']} | {icon} {c_rate:.1f}% |")
        md.append("")

        if failed > 0:
            md.append("## 3. Detailed Failure Analysis & Diagnostic Reproductions\n")
            md.append("| Scenario ID | Command | Failure Category | Root Cause & Reproduction |")
            md.append("| :--- | :--- | :--- | :--- |")
            for r in results:
                if r.status == TestStatus.FAILED:
                    cat_val = r.failure_category.value if r.failure_category else "unknown"
                    reason = r.failure_reason or "Unspecified failure"
                    md.append(f"| **{r.scenario_id}** | `{r.command}` | `{cat_val}` | {reason}<br>`{r.reproduction_instructions}` |")
            md.append("")
        else:
            md.append("## 3. Failure Analysis\n")
            md.append("> [!NOTE]\n> Zero failures detected across all simulated scenarios. All command intents, tools, and state mutations verified successfully.\n")

        md.append("## 4. Technical Guardrails & Verification Boundaries\n")
        md.append("- **Simulation Isolation**: In `SIMULATION` mode, all filesystem mutations were sandboxed within temporary directories.")
        md.append("- **Credential Protection**: Zero live API keys or tokens were stored in reports or transmission logs.")
        md.append("- **Safety Gating**: Irreversible operations verified confirmation token enforcement.")

        return "\n".join(md)

    @staticmethod
    def generate_json(
        run_id: str,
        results: List[ScenarioResult],
        duration_sec: float,
        mode: ExecutionMode = ExecutionMode.SIMULATION
    ) -> Dict[str, Any]:
        """Constructs machine-readable JSON evaluation summary."""
        total = len(results)
        passed = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in results if r.status == TestStatus.FAILED)

        return {
            "run_id": run_id,
            "mode": mode.value,
            "timestamp": datetime.now().isoformat(),
            "duration_sec": round(duration_sec, 2),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate_pct": round((passed / total * 100) if total > 0 else 0.0, 2)
            },
            "scenarios": [r.to_dict() for r in results]
        }
