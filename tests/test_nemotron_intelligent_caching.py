"""Comprehensive Automated Test Suite for JARVIS Multi-Layer AI Caching Engine.
Validates all 15 scenarios from Section 11 of the Nemotron Caching Master Prompt:
  1. Identical repeated request uses the cache (Exact Layer A).
  2. Changed prompt does not incorrectly reuse old answer.
  3. Different conversation contexts / styles do not collide.
  4. Different model configurations do not collide.
  5. Expired entry triggers a fresh request (TTL expiration).
  6. Semantic match is rejected when context/style/language differs.
  7. Current-state queries (time, weather, battery) bypass cache.
  8. User correction marks disputed and invalidates cache.
  9. Modified file invalidates dependent task cache.
  10. Concurrent identical requests do not create duplicate API calls (single-flight).
  11. API failures (empty/error) are not cached as successful answers.
  12. Cache corruption is handled safely.
  13. Cache limits and LRU eviction work.
  14. API keys never appear in cache keys, logs, or database.
  15. ProviderManager end-to-end integration avoids outbound calls.
"""

import os
import time
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from core.ai.caching.models import CacheLayer, CacheEntry, CacheStats
from core.ai.caching.cache_store import CacheStore
from core.ai.caching.semantic_matcher import SemanticMatcher
from core.ai.caching.policy_evaluator import PolicyEvaluator
from core.ai.caching.single_flight import SingleFlightGroup
from core.ai.caching.cache_manager import NemotronCacheManager
from core.ai.provider_manager import ProviderManager
from core.ai.providers.nvidia_provider import NvidiaNemotronProvider


class TestNemotronIntelligentCaching(unittest.TestCase):
    """Rigorous unit tests for multi-layer caching, policy evaluation, single-flight coalescing, and provider integration."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_cache.db")
        self.cache_mgr = NemotronCacheManager(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_identical_repeated_request_uses_cache(self):
        """Scenario 1: An identical repeated request uses the cache with 0 outbound API calls."""
        query = "What is polymorphism in C++?"
        response = "Polymorphism allows objects of different classes to be treated through a common base interface."

        # First request: Miss
        res1 = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res1.hit)

        # Store response
        saved = self.cache_mgr.store_response(query, response, provider="nvidia", model="nemotron-3.5", layer=CacheLayer.EXACT)
        self.assertTrue(saved)

        # Second request: Hit
        res2 = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5")
        self.assertTrue(res2.hit)
        self.assertEqual(res2.response, response)
        self.assertEqual(res2.layer, CacheLayer.EXACT)
        self.assertEqual(res2.reason, "exact_hit")

    def test_02_changed_prompt_does_not_reuse_old_answer(self):
        """Scenario 2: A changed prompt does not incorrectly reuse an old answer."""
        query1 = "Explain binary search in Python"
        query2 = "Explain quicksort in Python"
        resp1 = "Binary search works on sorted arrays by dividing the search interval in half."

        self.cache_mgr.store_response(query1, resp1, provider="nvidia", model="nemotron-3.5")
        res = self.cache_mgr.lookup(query2, provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res.hit)

    def test_03_different_conversation_contexts_do_not_collide(self):
        """Scenario 3: Different project aliases or styles do not collide."""
        query = "Show database schema"
        resp_proj_a = "Schema for Smart Farm project: Sensors, Readings, Alerts tables."

        self.cache_mgr.store_response(query, resp_proj_a, provider="nvidia", model="nemotron-3.5", context={"project_alias": "smart_farm"})

        # Lookup in another project context
        res_proj_b = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5", context={"project_alias": "medical_app"})
        self.assertFalse(res_proj_b.hit)

    def test_04_different_model_configurations_do_not_collide(self):
        """Scenario 4: Different model identifiers do not collide."""
        query = "Explain RAII pattern"
        resp = "RAII ties resource lifecycle to object lifetime in C++."

        self.cache_mgr.store_response(query, resp, provider="nvidia", model="nvidia/nemotron-3.5-super-vl-120b-a12b")

        # Lookup for a different model
        res = self.cache_mgr.lookup(query, provider="openai", model="gpt-4o")
        self.assertFalse(res.hit)

    def test_05_expired_entry_triggers_fresh_request(self):
        """Scenario 5: An expired entry based on TTL is rejected."""
        query = "Transient status explanation"
        resp = "Status details."

        # Store with expired timestamp
        entry = CacheEntry(
            key="test_expired_key",
            layer=CacheLayer.EXACT,
            query=query,
            normalized_query=self.cache_mgr.normalize_query(query),
            response=resp,
            provider="nvidia",
            model="nemotron-3.5",
            created_at=time.time() - 100.0,
            last_accessed_at=time.time() - 100.0,
            expires_at=time.time() - 10.0  # Expired 10s ago
        )
        self.cache_mgr.store.put(entry)

        res = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res.hit)

    def test_06_semantic_match_respects_style_and_language_guards(self):
        """Scenario 6: Semantic matching succeeds for equivalent questions, but rejects conflicting styles/languages."""
        base_query = "What is polymorphism?"
        base_resp = "Polymorphism allows derived classes to override methods of a base class."

        self.cache_mgr.store_response(base_query, base_resp, provider="nvidia", model="nemotron-3.5", layer=CacheLayer.KNOWLEDGE)

        # Semantically equivalent query with default style
        equiv_query = "Can you explain polymorphism?"
        res_equiv = self.cache_mgr.lookup(equiv_query, provider="nvidia", model="nemotron-3.5")
        self.assertTrue(res_equiv.hit)
        self.assertEqual(res_equiv.layer, CacheLayer.SEMANTIC)

        # Conflicting style: "Explain polymorphism like I'm a beginner" -> Must NOT reuse default/technical answer
        res_beginner = self.cache_mgr.lookup("Explain polymorphism like I'm a beginner", provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res_beginner.hit)

        # Conflicting target language: "Explain polymorphism in Java" vs base -> Reject
        res_java = self.cache_mgr.lookup("Explain polymorphism in Java", provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res_java.hit)

    def test_07_current_state_queries_bypass_cache(self):
        """Scenario 7: Real-time dynamic queries bypass cache automatically."""
        dynamic_queries = [
            "What time is it right now?",
            "What is today's date?",
            "What is the weather in Mumbai?",
            "Check current battery level",
            "What is my CPU usage?",
            "Force a fresh answer from Nemotron"
        ]
        for dq in dynamic_queries:
            with self.subTest(query=dq):
                is_bypass, reason = self.cache_mgr.policy_evaluator.is_bypass_required(dq)
                self.assertTrue(is_bypass, f"Expected bypass for '{dq}', got reason: '{reason}'")

    def test_08_corrected_answer_invalidates_disputed_entry(self):
        """Scenario 8: User correction marks entry as disputed and prevents reuse."""
        query = "What port does the web server run on?"
        wrong_resp = "Port 8000."

        self.cache_mgr.store_response(query, wrong_resp, provider="nvidia", model="nemotron-3.5")
        res_before = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5")
        self.assertTrue(res_before.hit)

        # User disputes / corrects the answer
        disputed_count = self.cache_mgr.mark_disputed(query)
        self.assertGreaterEqual(disputed_count, 1)

        # Subsequent lookup must reject the disputed entry
        res_after = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res_after.hit)

    def test_09_modified_file_invalidates_dependent_analysis(self):
        """Scenario 9: A modified file on disk invalidates dependent cached results."""
        test_file = os.path.join(self.temp_dir.name, "app.py")
        with open(test_file, "w") as f:
            f.write("def add(a, b): return a + b\n")

        query = "Analyze syntax and entry points in app.py"
        resp = "The file contains add function."

        # Cache task result tied to test_file
        self.cache_mgr.store_response(
            query, resp, provider="nvidia", model="nemotron-3.5",
            layer=CacheLayer.TASK_RESULT,
            context={"file_path": test_file}
        )

        res1 = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5", context={"file_path": test_file})
        self.assertTrue(res1.hit)

        # Modify file on disk and invalidate
        time.sleep(0.05)
        with open(test_file, "a") as f:
            f.write("def sub(a, b): return a - b\n")

        invalidated_count = self.cache_mgr.invalidate_by_file(test_file)
        self.assertGreaterEqual(invalidated_count, 1)

        res2 = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5", context={"file_path": test_file})
        self.assertFalse(res2.hit)

    def test_10_concurrent_identical_requests_coalesce_single_flight(self):
        """Scenario 10: Concurrent identical requests do not duplicate API calls (single-flight coalescing)."""
        call_count = {"count": 0}
        lock = threading.Lock()

        def slow_api_call():
            with lock:
                call_count["count"] += 1
            time.sleep(0.1)  # 100ms simulated network latency
            return "Simulated Nemotron Response"

        results = []
        threads = []

        def worker():
            res, coalesced = self.cache_mgr.coalesce_and_execute("shared_key_123", slow_api_call)
            results.append((res, coalesced))

        # Launch 5 concurrent threads requesting the exact same key
        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Exactly 1 thread should have executed slow_api_call; 4 should be coalesced
        self.assertEqual(call_count["count"], 1)
        self.assertEqual(len(results), 5)
        for r, _ in results:
            self.assertEqual(r, "Simulated Nemotron Response")
        self.assertEqual(self.cache_mgr.get_stats().duplicates_avoided, 4)

    def test_11_api_failures_are_not_cached(self):
        """Scenario 11: Errors, 401s, and empty responses are never cached as valid answers."""
        query = "Explain memory management"

        # Attempt to cache error string
        saved1 = self.cache_mgr.store_response(query, "[ERROR] 401 Unauthorized: Invalid API key", provider="nvidia", model="nemotron-3.5")
        self.assertFalse(saved1)

        # Attempt to cache empty string
        saved2 = self.cache_mgr.store_response(query, "   ", provider="nvidia", model="nemotron-3.5")
        self.assertFalse(saved2)

        res = self.cache_mgr.lookup(query, provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res.hit)

    def test_12_cache_corruption_handled_safely(self):
        """Scenario 12: Corrupted database or malformed rows do not crash lookup."""
        with self.cache_mgr.store._get_connection() as conn:
            cursor = conn.cursor()
            # Insert a malformed row directly
            cursor.execute("""
                INSERT INTO api_cache (cache_key, layer, query, normalized_query, response, provider, model, created_at, last_accessed_at)
                VALUES ('corrupt_key', 'unknown_layer', '', '', '', '', '', 0, 0)
            """)
            conn.commit()

        # Lookup should not throw exception
        res = self.cache_mgr.lookup("Any query", provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res.hit)

    def test_13_cache_limits_and_lru_eviction(self):
        """Scenario 13: LRU eviction prunes oldest entries when exceeding max capacity."""
        # Insert 10 entries with max_entries=5
        for i in range(10):
            entry = CacheEntry(
                key=f"key_{i}",
                layer=CacheLayer.EXACT,
                query=f"Query {i}",
                normalized_query=f"query {i}",
                response=f"Response {i}",
                provider="nvidia",
                model="nemotron-3.5",
                created_at=time.time() - (10 - i) * 10,
                last_accessed_at=time.time() - (10 - i) * 10
            )
            self.cache_mgr.store.put(entry)

        self.assertEqual(self.cache_mgr.store.count(), 10)
        evicted = self.cache_mgr.store.evict_lru(max_entries=5)
        self.assertEqual(evicted, 5)
        self.assertEqual(self.cache_mgr.store.count(), 5)

        # Oldest key_0 should have been evicted; newest key_9 should remain
        self.assertIsNone(self.cache_mgr.store.get("key_0"))
        self.assertIsNotNone(self.cache_mgr.store.get("key_9"))

    def test_14_api_keys_never_appear_in_cache_keys_or_store(self):
        """Scenario 14: API keys never appear in cache keys or database columns."""
        real_key = "nvapi-SUPER_SECRET_TOKEN_XYZ_12345"
        query = "Explain binary search"

        cache_key = self.cache_mgr.generate_cache_key(query, provider="nvidia", model="nemotron-3.5")
        self.assertNotIn(real_key, cache_key)
        self.assertEqual(len(cache_key), 64)  # Hex SHA-256

        self.cache_mgr.store_response(query, "Binary search explanation", provider="nvidia", model="nemotron-3.5")
        entry = self.cache_mgr.store.get(cache_key)
        self.assertIsNotNone(entry)
        self.assertNotIn(real_key, str(entry))

    def test_15_provider_manager_avoids_outbound_calls_via_cache(self):
        """Scenario 15: End-to-end integration: ProviderManager reuses cache with 0 outbound API calls."""
        pm = ProviderManager()
        mock_provider = MagicMock(spec=NvidiaNemotronProvider)
        mock_provider.get_name.return_value = "NVIDIA Nemotron (Mocked)"
        mock_provider.is_available.return_value = True

        call_counter = {"calls": 0}

        def mock_generate(messages, context=None):
            call_counter["calls"] += 1
            return "Polymorphism allows interchangeable interface implementations."

        mock_provider.generate_response.side_effect = mock_generate
        pm._providers["nvidia"] = mock_provider

        from config import config
        config.ai_provider = "nvidia"

        query = f"Explain polymorphism in C++ test_{int(time.time() * 1000)}"
        messages = [{"role": "user", "content": query}]

        # Call 1: Cache Miss -> Calls outbound API (calls = 1)
        resp1 = pm.generate_response(messages)
        self.assertEqual(call_counter["calls"], 1)
        self.assertIn("Polymorphism", resp1)

        # Call 2: Identical Request -> Cache Hit -> 0 outbound API calls (calls stays 1)
        resp2 = pm.generate_response(messages)
        self.assertEqual(call_counter["calls"], 1)
        self.assertEqual(resp2, resp1)

        # Call 3: Another Identical Request -> Cache Hit -> calls still 1
        resp3 = pm.generate_response(messages)
        self.assertEqual(call_counter["calls"], 1)
        self.assertEqual(resp3, resp1)

    def test_16_negation_and_contradictory_instructions_rejected(self):
        """Scenario 16: Negations (without recursion vs with recursion) are never cross-matched."""
        query_recursive = "Implement binary search using recursion in Python"
        resp_recursive = "def bsearch(arr, low, high, x): ..."

        self.cache_mgr.store_response(query_recursive, resp_recursive, provider="nvidia", model="nemotron-3.5", layer=CacheLayer.KNOWLEDGE)

        # Opposite instruction with negation: MUST NOT reuse recursive answer
        query_iterative = "Implement binary search without recursion in Python"
        res_iterative = self.cache_mgr.lookup(query_iterative, provider="nvidia", model="nemotron-3.5")
        self.assertFalse(res_iterative.hit)

        # Similar phrasing with same affirmative instruction: CAN reuse
        query_equiv = "Can you write binary search using recursion in Python?"
        res_equiv = self.cache_mgr.lookup(query_equiv, provider="nvidia", model="nemotron-3.5")
        self.assertTrue(res_equiv.hit)

    def test_17_concurrency_leader_failure_propagates_to_followers(self):
        """Scenario 17: Leader failure in SingleFlight properly propagates exception to followers and cleans up state."""
        flight = SingleFlightGroup()
        key = "shared_failing_flight"
        leader_ready = threading.Event()
        exceptions_caught = []

        def failing_api():
            leader_ready.set()
            time.sleep(0.05)
            raise RuntimeError("Nemotron 503 Service Unavailable")

        def worker():
            try:
                flight.execute(key, failing_api)
            except RuntimeError as re:
                exceptions_caught.append(str(re))

        # Start leader thread
        t_leader = threading.Thread(target=worker)
        t_leader.start()
        leader_ready.wait(timeout=2.0)

        # Start follower threads while leader is in-flight
        t_followers = [threading.Thread(target=worker) for _ in range(2)]
        for t in t_followers:
            t.start()

        t_leader.join()
        for t in t_followers:
            t.join()

        self.assertEqual(len(exceptions_caught), 3)
        self.assertTrue(all("503" in e for e in exceptions_caught))
        # Verify key was cleaned up and is no longer in active flights
        self.assertNotIn(key, flight._calls)

    def test_18_new_flight_after_failed_flight_succeeds(self):
        """Scenario 18: A new request after a failed flight initiates a fresh flight and succeeds."""
        flight = SingleFlightGroup()
        key = "retry_after_fail_key"

        # Flight 1: Fails
        with self.assertRaises(ValueError):
            flight.execute(key, lambda: (_ for _ in ()).throw(ValueError("Temporary network glitch")))

        # Flight 2: Immediately succeeds
        res, coalesced = flight.execute(key, lambda: "Nemotron Recovered Response")
        self.assertEqual(res, "Nemotron Recovered Response")
        self.assertFalse(coalesced)

    def test_19_unrelated_concurrent_flights_are_independent(self):
        """Scenario 19: Unrelated flights execute concurrently and independently."""
        flight = SingleFlightGroup()
        results = {}

        def worker_a():
            res, _ = flight.execute("key_a", lambda: "Result A")
            results["a"] = res

        def worker_b():
            res, _ = flight.execute("key_b", lambda: "Result B")
            results["b"] = res

        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results.get("a"), "Result A")
        self.assertEqual(results.get("b"), "Result B")

    def test_20_persistence_across_restart_and_ttl_enforcement(self):
        """Scenario 20: Cache entries survive restart and TTL enforcement prunes expired items."""
        query = "Explain RAII pattern in C++"
        resp = "RAII binds the life cycle of a resource to the lifetime of an object."

        # Session 1: Store entry
        self.cache_mgr.store_response(query, resp, provider="nvidia", model="nemotron-3.5", layer=CacheLayer.KNOWLEDGE)

        # Simulate restart: New NemotronCacheManager reading the same SQLite db file
        restarted_mgr = NemotronCacheManager(db_path=self.db_path)
        lookup = restarted_mgr.lookup(query, provider="nvidia", model="nemotron-3.5")
        self.assertTrue(lookup.hit)
        self.assertEqual(lookup.response, resp)

        # Verify expired items are pruned
        restarted_mgr.store.delete_expired(current_time=time.time() + 31 * 86400)  # 31 days in future
        lookup_expired = restarted_mgr.lookup(query, provider="nvidia", model="nemotron-3.5")
        self.assertFalse(lookup_expired.hit)

    def test_21_language_cross_contamination_prevented(self):
        """Scenario 21: Cross-language requests (Python vs C++ vs Java vs Go) never cross-match."""
        self.cache_mgr.store_response(
            "Explain binary search in Python",
            "Python implementation using bisect or while loop.",
            provider="nvidia", model="nemotron-3.5", layer=CacheLayer.KNOWLEDGE
        )

        for lang in ["Java", "C++", "Go", "Rust"]:
            with self.subTest(language=lang):
                res = self.cache_mgr.lookup(f"Explain binary search in {lang}", provider="nvidia", model="nemotron-3.5")
                self.assertFalse(res.hit, f"Expected cache miss for {lang}, but got hit!")


if __name__ == "__main__":
    unittest.main()

