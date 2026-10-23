"""SQLite Result Store for persisting Virtual Testing Room run history and trends."""

import os
import sqlite3
import logging
import contextlib
from typing import List, Dict, Optional, Any
from pathlib import Path

from core.virtual_lab.models import ScenarioResult, ExecutionMode, TestStatus

logger = logging.getLogger("Santra.VirtualLab.ResultStore")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "virtual_lab_history.db"


class TestResultStore:
    """Persists test executions, outcomes, and failure analytics for regression tracking."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_runs (
                        run_id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        total_tests INTEGER NOT NULL,
                        passed_tests INTEGER NOT NULL,
                        failed_tests INTEGER NOT NULL,
                        duration_sec REAL NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL,
                        scenario_id TEXT NOT NULL,
                        command TEXT NOT NULL,
                        status TEXT NOT NULL,
                        failure_category TEXT,
                        failure_reason TEXT,
                        duration_ms REAL NOT NULL,
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY (run_id) REFERENCES test_runs (run_id)
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"[ResultStore] Database init error: {e}")

    def save_run(self, run_id: str, results: List[ScenarioResult], duration_sec: float, mode: ExecutionMode = ExecutionMode.SIMULATION):
        """Records a completed test run and its detailed scenario outcomes."""
        passed = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in results if r.status == TestStatus.FAILED)
        timestamp = results[0].timestamp if results else ""

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO test_runs (run_id, timestamp, mode, total_tests, passed_tests, failed_tests, duration_sec)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (run_id, timestamp, mode.value, len(results), passed, failed, duration_sec))

                for r in results:
                    cursor.execute("""
                        INSERT INTO test_results (run_id, scenario_id, command, status, failure_category, failure_reason, duration_ms, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        run_id,
                        r.scenario_id,
                        r.command,
                        r.status.value,
                        r.failure_category.value if r.failure_category else None,
                        r.failure_reason,
                        r.duration_ms,
                        r.timestamp
                    ))
                conn.commit()
                logger.info(f"[ResultStore] Saved test run '{run_id}' ({passed}/{len(results)} passed)")
        except Exception as e:
            logger.error(f"[ResultStore] Error saving run '{run_id}': {e}")

    def get_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves summary of recent test runs."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test_runs ORDER BY timestamp DESC LIMIT ?", (limit,))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[ResultStore] Error querying recent runs: {e}")
            return []

    def get_latest_failed_scenario_ids(self) -> List[str]:
        """Returns scenario IDs that failed in the most recent run."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT scenario_id FROM test_results
                    WHERE run_id = (SELECT run_id FROM test_runs ORDER BY timestamp DESC LIMIT 1)
                      AND status = 'FAILED'
                """)
                return [row["scenario_id"] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[ResultStore] Error querying failed scenarios: {e}")
            return []
