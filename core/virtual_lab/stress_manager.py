"""Stress, Concurrency, and Resource Limit Manager for the SANTRA Virtual Testing Room."""

import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Callable, Optional

logger = logging.getLogger("Santra.VirtualLab.Stress")


class StressTestManager:
    """Coordinates bounded, safe concurrency and load testing without exhausting system resources."""

    def __init__(self, max_workers: int = 6, timeout_sec: float = 20.0):
        self.max_workers = max_workers
        self.timeout_sec = timeout_sec
        self._is_cancelled = threading.Event()

    def cancel(self):
        """Immediately signals ongoing stress tests to halt."""
        self._is_cancelled.set()
        logger.warning("[StressManager] Cancellation signal dispatched to active workers.")

    def run_concurrent_workload(
        self,
        command_fn: Callable[[str], Any],
        commands: List[str],
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """Runs batch of commands concurrently across bounded thread pool."""
        self._is_cancelled.clear()
        total_tasks = len(commands)
        completed_tasks = 0
        success_count = 0
        failure_count = 0
        latencies: List[float] = []

        start_time = time.perf_counter()
        results: List[Dict[str, Any]] = []

        logger.info(f"[StressManager] Launching concurrent workload ({total_tasks} requests, max_workers={self.max_workers})")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_cmd = {}
            for cmd in commands:
                if self._is_cancelled.is_set():
                    break
                future = executor.submit(self._worker_execute, command_fn, cmd)
                future_to_cmd[future] = cmd

            for future in as_completed(future_to_cmd, timeout=self.timeout_sec):
                cmd = future_to_cmd[future]
                completed_tasks += 1

                try:
                    res, duration_ms = future.result()
                    latencies.append(duration_ms)
                    if res.get("status") in ["PASSED", True]:
                        success_count += 1
                    else:
                        failure_count += 1
                    results.append({"command": cmd, "duration_ms": duration_ms, "outcome": res})
                except Exception as e:
                    failure_count += 1
                    results.append({"command": cmd, "duration_ms": 0.0, "error": str(e)})

                if on_progress:
                    on_progress(completed_tasks, total_tasks)

                if self._is_cancelled.is_set():
                    logger.info("[StressManager] Execution aborted due to active cancellation.")
                    break

        total_elapsed = time.perf_counter() - start_time
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
        max_latency = max(latencies) if latencies else 0.0
        min_latency = min(latencies) if latencies else 0.0
        qps = (completed_tasks / total_elapsed) if total_elapsed > 0 else 0.0

        return {
            "total_requests": total_tasks,
            "completed_requests": completed_tasks,
            "success_count": success_count,
            "failure_count": failure_count,
            "total_elapsed_sec": round(total_elapsed, 2),
            "throughput_qps": round(qps, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": round(min_latency, 2),
            "max_latency_ms": round(max_latency, 2),
            "cancelled": self._is_cancelled.is_set(),
            "results": results
        }

    def _worker_execute(self, command_fn: Callable[[str], Any], cmd: str):
        t0 = time.perf_counter()
        res = command_fn(cmd)
        dur = (time.perf_counter() - t0) * 1000
        return res, dur
