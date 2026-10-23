"""Controlled Benchmark for JARVIS Multi-Layer AI Caching & Cost Optimization Engine.
Compares baseline un-cached workload vs multi-layer intelligent cache workload.
Measures request counts, outbound API calls, exact/semantic hits, bypasses, coalescing,
and response latency percentiles (Mean, P50, P90, P99).
"""

import os
import sys
import time
import json
import tempfile
import threading
from typing import Dict, Any, List
import numpy as np

# Ensure workspace root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai.caching.models import CacheLayer
from core.ai.caching.cache_manager import NemotronCacheManager


class MockNemotronClient:
    """Deterministic Mock Nemotron client simulating API response and latency."""
    def __init__(self, simulated_latency_ms: float = 1200.0):
        self.simulated_latency_s = simulated_latency_ms / 1000.0
        self.call_count = 0
        self._lock = threading.Lock()

    def generate(self, prompt: str, **kwargs) -> str:
        with self._lock:
            self.call_count += 1
        time.sleep(self.simulated_latency_s)
        return f"[Nemotron-3.5 Verified Answer]: Comprehensive explanation of {prompt[:30]}..."


def run_workload(use_cache: bool) -> Dict[str, Any]:
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = os.path.join(temp_dir.name, "bench_cache.db")
    cache_mgr = NemotronCacheManager(db_path=db_path)
    cache_mgr.is_enabled = use_cache
    mock_client = MockNemotronClient(simulated_latency_ms=400.0)

    latencies = []
    outbound_calls = 0
    exact_hits = 0
    semantic_hits = 0
    bypasses = 0
    misses = 0
    coalesced_avoided = 0

    workload = [
        # Batch 1: Cold requests (5 distinct technical questions)
        ("What is polymorphism in C++?", "default", "any", None, False),
        ("Explain binary search algorithm", "default", "any", None, False),
        ("What is RAII in modern C++?", "default", "any", None, False),
        ("Explain Dijkstra shortest path algorithm", "default", "any", None, False),
        ("How does virtual memory work in OS?", "default", "any", None, False),

        # Batch 2: Exact repeats of Batch 1 (Identical requests)
        ("What is polymorphism in C++?", "default", "any", None, False),
        ("Explain binary search algorithm", "default", "any", None, False),
        ("What is RAII in modern C++?", "default", "any", None, False),
        ("Explain Dijkstra shortest path algorithm", "default", "any", None, False),
        ("How does virtual memory work in OS?", "default", "any", None, False),

        # Batch 3: Semantic variations of earlier questions
        ("Can you explain polymorphism in C++?", "default", "any", None, False),
        ("Can you explain polymorphism in C++ again?", "default", "any", None, False),
        ("Explain binary search algorithm", "default", "any", None, False),

        # Batch 4: Divergent requests (different style or language -> must NOT reuse default cache)
        ("Explain polymorphism like I'm a beginner", "beginner", "any", None, False),
        ("Explain polymorphism in Java", "default", "java", None, False),

        # Batch 5: Real-time dynamic & bypass queries (must strictly bypass)
        ("What time is it right now?", "default", "any", None, False),
        ("What is the current weather forecast?", "default", "any", None, False),
        ("Check current battery level", "default", "any", None, False),
        ("Force a fresh answer from Nemotron for RAII", "default", "any", {"force_fresh": True}, False),

        # Batch 6: Repeated exact queries (demonstrating persistent exact hit)
        ("What is polymorphism in C++?", "default", "any", None, False),
        ("Explain binary search algorithm", "default", "any", None, False),
    ]

    def execute_single(item):
        nonlocal outbound_calls, exact_hits, semantic_hits, bypasses, misses
        q, style, lang, ctx, is_concurrent = item
        context = ctx or {}
        if style != "default":
            context["style"] = style
        if lang != "any":
            context["language"] = lang

        t0 = time.perf_counter()

        if use_cache:
            res = cache_mgr.lookup(q, provider="nvidia", model="nemotron-3.5", context=context)
            if res.hit:
                if res.layer == CacheLayer.EXACT:
                    exact_hits += 1
                elif res.layer == CacheLayer.SEMANTIC:
                    semantic_hits += 1
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return elapsed_ms
            elif "bypassed" in res.reason:
                bypasses += 1

            misses += 1
            # Outbound API call
            outbound_calls += 1
            answer = mock_client.generate(q)
            # Store in cache
            cache_mgr.store_response(q, answer, provider="nvidia", model="nemotron-3.5", context=context)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return elapsed_ms
        else:
            # Baseline: No caching
            outbound_calls += 1
            mock_client.generate(q)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return elapsed_ms

    # Execute sequential workload
    for item in workload:
        lat = execute_single(item)
        latencies.append(lat)

    # Batch 7: Concurrent duplicate test (5 threads requesting identical query at the same instant)
    concurrent_query = "What is deadlock prevention in OS?"
    threads = []
    concurrent_latencies = []

    def concurrent_worker():
        nonlocal outbound_calls, exact_hits, coalesced_avoided
        t0 = time.perf_counter()
        if use_cache:
            key = cache_mgr.generate_cache_key(concurrent_query, "nvidia", "nemotron-3.5")
            res = cache_mgr.lookup(concurrent_query, "nvidia", "nemotron-3.5")
            if res.hit:
                exact_hits += 1
                elapsed = (time.perf_counter() - t0) * 1000.0
                concurrent_latencies.append(elapsed)
                return

            def execute_api():
                nonlocal outbound_calls
                outbound_calls += 1
                ans = mock_client.generate(concurrent_query)
                cache_mgr.store_response(concurrent_query, ans, "nvidia", "nemotron-3.5")
                return ans

            ans, was_coalesced = cache_mgr.single_flight.do(key, execute_api)
            if was_coalesced:
                coalesced_avoided += 1
            elapsed = (time.perf_counter() - t0) * 1000.0
            concurrent_latencies.append(elapsed)
        else:
            outbound_calls += 1
            mock_client.generate(concurrent_query)
            elapsed = (time.perf_counter() - t0) * 1000.0
            concurrent_latencies.append(elapsed)

    for _ in range(5):
        t = threading.Thread(target=concurrent_worker)
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    latencies.extend(concurrent_latencies)

    total_requests = len(workload) + 5
    lat_arr = np.array(latencies)

    try:
        temp_dir.cleanup()
    except Exception:
        pass

    return {
        "use_cache": use_cache,
        "total_requests": total_requests,
        "outbound_api_calls": outbound_calls,
        "exact_hits": exact_hits,
        "semantic_hits": semantic_hits,
        "bypasses": bypasses,
        "misses": misses,
        "coalesced_avoided": coalesced_avoided,
        "mean_latency_ms": float(np.mean(lat_arr)),
        "p50_latency_ms": float(np.percentile(lat_arr, 50)),
        "p90_latency_ms": float(np.percentile(lat_arr, 90)),
        "p99_latency_ms": float(np.percentile(lat_arr, 99))
    }


def main():
    print("================================================================================")
    print("   JARVIS NEMOTRON API CACHE & COST OPTIMIZATION CONTROLLED BENCHMARK")
    print("================================================================================")
    print("Executing Benchmark Scenario 1: Baseline (Cache Disabled)...")
    baseline = run_workload(use_cache=False)

    print("\nExecuting Benchmark Scenario 2: Multi-Layer Intelligent Cache Enabled...")
    cached = run_workload(use_cache=True)

    # Eligible requests = total requests - bypasses
    eligible_requests = cached["total_requests"] - cached["bypasses"]
    total_cache_hits = cached["exact_hits"] + cached["semantic_hits"] + cached["coalesced_avoided"]
    cache_hit_rate = (total_cache_hits / eligible_requests) if eligible_requests > 0 else 0.0

    api_calls_avoided = baseline["outbound_api_calls"] - cached["outbound_api_calls"]
    api_reduction_pct = (api_calls_avoided / baseline["outbound_api_calls"]) * 100.0

    results = {
        "baseline": baseline,
        "cached": cached,
        "comparison": {
            "total_requests_submitted": baseline["total_requests"],
            "eligible_requests": eligible_requests,
            "baseline_outbound_api_calls": baseline["outbound_api_calls"],
            "cached_outbound_api_calls": cached["outbound_api_calls"],
            "actual_api_calls_avoided": api_calls_avoided,
            "api_call_reduction_pct": api_reduction_pct,
            "exact_hits": cached["exact_hits"],
            "semantic_hits": cached["semantic_hits"],
            "single_flight_coalesced_avoided": cached["coalesced_avoided"],
            "cache_bypasses": cached["bypasses"],
            "cache_misses": cached["misses"],
            "cache_hit_rate_pct": cache_hit_rate * 100.0,
            "baseline_mean_latency_ms": baseline["mean_latency_ms"],
            "cached_mean_latency_ms": cached["mean_latency_ms"],
            "latency_reduction_pct": ((baseline["mean_latency_ms"] - cached["mean_latency_ms"]) / baseline["mean_latency_ms"]) * 100.0,
            "cached_p50_latency_ms": cached["p50_latency_ms"],
            "cached_p90_latency_ms": cached["p90_latency_ms"],
            "cached_p99_latency_ms": cached["p99_latency_ms"]
        }
    }

    print("\n" + "=" * 80)
    print("                      CONTROLLED BENCHMARK RESULTS")
    print("=" * 80)
    print(f"Total Requests Submitted:         {results['comparison']['total_requests_submitted']}")
    print(f"Eligible Requests:                {results['comparison']['eligible_requests']}")
    print(f"Baseline Outbound API Calls:      {results['comparison']['baseline_outbound_api_calls']}")
    print(f"Cached Outbound API Calls:        {results['comparison']['cached_outbound_api_calls']}")
    print(f"Actual API Calls Avoided:         {results['comparison']['actual_api_calls_avoided']} ({results['comparison']['api_call_reduction_pct']:.1f}% reduction)")
    print(f"Exact Cache Hits:                 {results['comparison']['exact_hits']}")
    print(f"Semantic Cache Hits:              {results['comparison']['semantic_hits']}")
    print(f"Single-Flight Coalesced Avoided:  {results['comparison']['single_flight_coalesced_avoided']}")
    print(f"Cache Bypasses (Live/Action):     {results['comparison']['cache_bypasses']}")
    print(f"Cache Misses (Cold/Divergent):    {results['comparison']['cache_misses']}")
    print(f"Cache Hit Rate (Eligible):        {results['comparison']['cache_hit_rate_pct']:.1f}%")
    print("-" * 80)
    print("LATENCY MEASUREMENTS:")
    print(f"Baseline Mean Latency:            {results['comparison']['baseline_mean_latency_ms']:.2f} ms")
    print(f"Cached Mean Latency:              {results['comparison']['cached_mean_latency_ms']:.2f} ms ({results['comparison']['latency_reduction_pct']:.1f}% faster)")
    print(f"Cached P50 Latency:               {results['comparison']['cached_p50_latency_ms']:.2f} ms")
    print(f"Cached P90 Latency:               {results['comparison']['cached_p90_latency_ms']:.2f} ms")
    print(f"Cached P99 Latency:               {results['comparison']['cached_p99_latency_ms']:.2f} ms")
    print("=" * 80)

    # Save benchmark json artifact
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nemotron_cache_benchmark_results.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved raw benchmark report to: {report_path}")


if __name__ == "__main__":
    main()
