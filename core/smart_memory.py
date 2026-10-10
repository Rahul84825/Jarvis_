"""Smart Memory and Tool Performance Tracker for JARVIS.
Tracks tool success/failure rates, error-to-fix patterns, and execution metrics in smart_memory.db.
Reference: https://jarvis.institute/guide/#profile
"""

import sqlite3
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger("Jarvis.SmartMemory")

class SmartMemory:
    """Tracks tool reliability metrics, execution times, and failure patterns."""

    def __init__(self, db_path: Optional[str] = None):
        base_dir = Path(__file__).parent.parent
        self.db_path = db_path or str(base_dir / "logs" / "smart_memory.db")
        self._init_db()

    def _init_db(self):
        conn = None
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tool_metrics (
                    tool_name TEXT PRIMARY KEY,
                    total_runs INTEGER DEFAULT 0,
                    success_runs INTEGER DEFAULT 0,
                    failed_runs INTEGER DEFAULT 0,
                    last_duration_ms REAL DEFAULT 0.0,
                    last_error TEXT,
                    last_run_timestamp REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS error_fixes (
                    error_pattern TEXT PRIMARY KEY,
                    recommended_action TEXT,
                    occurrence_count INTEGER DEFAULT 1
                )
            """)
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize smart_memory.db: {e}")
        finally:
            if conn:
                conn.close()

    def record_tool_execution(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float,
        error: Optional[str] = None
    ):
        """Updates run counts, success rate, and error records for a tool."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tool_metrics (tool_name, total_runs, success_runs, failed_runs, last_duration_ms, last_error, last_run_timestamp)
                VALUES (?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(tool_name) DO UPDATE SET
                    total_runs = total_runs + 1,
                    success_runs = success_runs + ?,
                    failed_runs = failed_runs + ?,
                    last_duration_ms = ?,
                    last_error = ?,
                    last_run_timestamp = ?
            """, (
                tool_name,
                1 if success else 0,
                0 if success else 1,
                duration_ms,
                error or "",
                time.time(),
                1 if success else 0,
                0 if success else 1,
                duration_ms,
                error or "",
                time.time()
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to record tool execution in smart_memory: {e}")
        finally:
            if conn:
                conn.close()

    def get_tool_reliability(self, tool_name: str) -> Dict[str, Any]:
        """Returns success rate and performance stats for a specified tool."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT total_runs, success_runs, failed_runs, last_duration_ms, last_error
                FROM tool_metrics WHERE tool_name = ?
            """, (tool_name,))
            row = cursor.fetchone()
            if row:
                total, succ, fail, dur, err = row
                rate = (succ / total) * 100.0 if total > 0 else 100.0
                return {
                    "tool_name": tool_name,
                    "total_runs": total,
                    "success_rate": round(rate, 1),
                    "avg_duration_ms": dur,
                    "last_error": err
                }
        except Exception as e:
            logger.error(f"Failed to query tool reliability: {e}")
        finally:
            if conn:
                conn.close()

        return {"tool_name": tool_name, "total_runs": 0, "success_rate": 100.0, "avg_duration_ms": 0.0, "last_error": None}

    def get_summary(self) -> List[Dict[str, Any]]:
        """Returns summary of all recorded tool reliability metrics."""
        results = []
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT tool_name, total_runs, success_runs, failed_runs FROM tool_metrics ORDER BY total_runs DESC")
            for row in cursor.fetchall():
                name, total, succ, fail = row
                rate = (succ / total) * 100.0 if total > 0 else 100.0
                results.append({"tool": name, "runs": total, "success_pct": round(rate, 1)})
        except Exception as e:
            logger.error(f"Failed to get smart memory summary: {e}")
        finally:
            if conn:
                conn.close()
        return results


# Global Singleton Instance
smart_memory = SmartMemory()
