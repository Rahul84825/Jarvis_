"""Central Cache Manager and Facade for JARVIS Multi-Layer AI Caching Engine."""

import os
import time
import hashlib
import logging
import threading
from typing import Optional, Dict, Any, List, Tuple, Callable

from core.ai.caching.models import CacheEntry, CacheLayer, CacheLookupResult, CacheStats
from core.ai.caching.cache_store import CacheStore
from core.ai.caching.semantic_matcher import SemanticMatcher
from core.ai.caching.policy_evaluator import PolicyEvaluator
from core.ai.caching.single_flight import SingleFlightGroup

logger = logging.getLogger("Jarvis.CacheManager")


class NemotronCacheManager:
    """Master controller orchestrating Layer A Exact, Layer B Semantic,
    Layer C Knowledge, and Layer D Task Result caching for NVIDIA Nemotron.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.RLock()
        self.store = CacheStore(db_path=db_path)
        self.semantic_matcher = SemanticMatcher(similarity_threshold=0.88)
        self.policy_evaluator = PolicyEvaluator()
        self.single_flight = SingleFlightGroup()
        self.stats = CacheStats()

        # Configurable runtime controls
        self.is_enabled = True
        self.is_semantic_enabled = True
        self.prompt_version = "1.0"
        self._last_cleanup_time = time.time()

    def normalize_query(self, query: str) -> str:
        """Produces canonical normalized string for consistent exact hashing."""
        clean = (query or "").lower().strip()
        # Remove trailing question marks, periods, and conversational commas
        clean = clean.rstrip("?.!,:;")
        # Collapse multi-whitespace
        return " ".join(clean.split())

    def generate_cache_key(
        self,
        query: str,
        provider: str = "nvidia",
        model: str = "nvidia/nemotron-3.5-super-vl-120b-a12b",
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Computes deterministic SHA256 cache key without exposing secrets,
        incorporating screen capture fingerprinting when vision context is present.
        """
        ctx = context or {}
        norm_q = self.normalize_query(query)
        style = ctx.get("style", "default")
        lang = ctx.get("language", "en")
        proj = ctx.get("project_alias", "")

        # Screen / vision content fingerprinting
        screen_tag = ""
        if ctx.get("requires_vision") or ctx.get("image_base64") or ctx.get("capture_id") or ctx.get("screen_capture_hash"):
            img_b64 = str(ctx.get("image_base64", "") or "")
            cap_id = str(ctx.get("capture_id", "") or "")
            win_title = str(ctx.get("window_title", "") or "")
            screen_hash = str(ctx.get("screen_capture_hash", "") or "")
            sample = f"{win_title}|{cap_id}|{screen_hash}|{len(img_b64)}|{img_b64[:128]}|{img_b64[-128:]}"
            screen_tag = f"|screen:{hashlib.sha256(sample.encode('utf-8')).hexdigest()[:16]}"

        fingerprint = f"{norm_q}|{provider.lower()}|{model.lower()}|{self.prompt_version}|{style}|{lang}|{proj}{screen_tag}"
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

    def lookup(
        self,
        query: str,
        provider: str = "nvidia",
        model: str = "nvidia/nemotron-3.5-super-vl-120b-a12b",
        context: Optional[Dict[str, Any]] = None
    ) -> CacheLookupResult:
        """Evaluates cache hierarchy: Policy -> Exact (Layer A) -> Knowledge (Layer C) -> Semantic (Layer B)."""
        t0 = time.perf_counter()

        with self._lock:
            self.stats.total_lookups += 1

            if not self.is_enabled:
                self.stats.bypasses += 1
                return CacheLookupResult(hit=False, reason="cache_disabled", latency_ms=(time.perf_counter() - t0) * 1000)

            # 1. Evaluate Bypass Policies (Section 3)
            is_bypass, bypass_reason = self.policy_evaluator.is_bypass_required(query, context)
            if is_bypass:
                self.stats.bypasses += 1
                logger.info(f"[CACHE_BYPASS] Request '{query[:40]}...' bypassed: {bypass_reason}")
                return CacheLookupResult(hit=False, reason=bypass_reason, latency_ms=(time.perf_counter() - t0) * 1000)

            exact_key = self.generate_cache_key(query, provider, model, context)

            # 2. Check Layer A: Exact Response Cache
            exact_entry = self.store.get(exact_key)
            if exact_entry:
                is_valid, validation_reason = self.policy_evaluator.validate_candidate(exact_entry, query, context, provider=provider, model=model)
                if is_valid:
                    self.store.touch(exact_key)
                    self.stats.exact_hits += 1
                    lat = (time.perf_counter() - t0) * 1000
                    logger.info(f"[EXACT_CACHE_HIT] Served '{query[:40]}...' in {lat:.2f}ms (Key: {exact_key[:10]}...)")
                    return CacheLookupResult(
                        hit=True,
                        response=exact_entry.response,
                        layer=CacheLayer.EXACT,
                        entry=exact_entry,
                        reason="exact_hit",
                        latency_ms=lat
                    )
                else:
                    logger.debug(f"[EXACT_CACHE_REJECT] Exact candidate rejected: {validation_reason}")

            # 3. Check Layer C & D: Task Result & Knowledge Cache
            ctx = context or {}
            target_file = ctx.get("file_path")
            if target_file and os.path.exists(target_file):
                # Check if task result for this file exists
                file_key = hashlib.sha256(f"file_task|{os.path.normpath(target_file).lower()}|{query.strip().lower()}".encode("utf-8")).hexdigest()
                task_entry = self.store.get(file_key)
                if task_entry:
                    is_valid, v_reason = self.policy_evaluator.validate_candidate(task_entry, query, context, provider=provider, model=model)
                    if is_valid:
                        self.store.touch(file_key)
                        self.stats.task_hits += 1
                        lat = (time.perf_counter() - t0) * 1000
                        return CacheLookupResult(
                            hit=True,
                            response=task_entry.response,
                            layer=CacheLayer.TASK_RESULT,
                            entry=task_entry,
                            reason="task_result_hit",
                            latency_ms=lat
                        )

            # 4. Check Layer B: Semantic Cache (Section 2)
            if self.is_semantic_enabled:
                candidates = self.store.get_candidates_for_semantic(limit=250, provider=provider, model=model)
                best_match, sim_score = self.semantic_matcher.find_best_semantic_match(query, candidates)
                if best_match:
                    is_valid, val_reason = self.policy_evaluator.validate_candidate(best_match, query, context, provider=provider, model=model)
                    if is_valid:
                        self.store.touch(best_match.key)
                        if best_match.layer == CacheLayer.KNOWLEDGE:
                            self.stats.knowledge_hits += 1
                        else:
                            self.stats.semantic_hits += 1
                        lat = (time.perf_counter() - t0) * 1000
                        logger.info(
                            f"[SEMANTIC_CACHE_HIT] Served '{query[:40]}...' "
                            f"(Matched: '{best_match.query[:40]}...', Sim: {sim_score:.1%}, Lat: {lat:.2f}ms)"
                        )
                        return CacheLookupResult(
                            hit=True,
                            response=best_match.response,
                            layer=CacheLayer.SEMANTIC,
                            entry=best_match,
                            similarity_score=sim_score,
                            reason="semantic_hit",
                            latency_ms=lat
                        )
                    else:
                        logger.debug(f"[SEMANTIC_CACHE_REJECT] Candidate rejected: {val_reason}")

            # Cache Miss
            self.stats.misses += 1
            lat = (time.perf_counter() - t0) * 1000
            return CacheLookupResult(hit=False, reason="miss", latency_ms=lat)

    def store_response(
        self,
        query: str,
        response: str,
        provider: str = "nvidia",
        model: str = "nvidia/nemotron-3.5-super-vl-120b-a12b",
        layer: CacheLayer = CacheLayer.EXACT,
        context: Optional[Dict[str, Any]] = None,
        source_reference: str = ""
    ) -> bool:
        """Stores a successful generation response into the appropriate cache layer."""
        if not self.is_enabled:
            return False

        if not response or len(response.strip()) < 5:
            return False

        # Never cache error strings or authentication failures
        if response.startswith("[ERROR]") or "API key or credentials" in response:
            return False

        ctx = context or {}
        # Bypass check: never store dynamic or action responses
        is_bypass, _ = self.policy_evaluator.is_bypass_required(query, context)
        if is_bypass:
            return False

        with self._lock:
            now = time.time()
            ttl_sec = self.policy_evaluator.determine_ttl(layer, query, response)
            expires_at = now + ttl_sec if ttl_sec else None

            style = ctx.get("style") or self.semantic_matcher.extract_style(query)
            lang = ctx.get("language") or self.semantic_matcher.extract_target_language(query)
            file_p = ctx.get("file_path", "")
            file_mt = os.path.getmtime(file_p) if file_p and os.path.exists(file_p) else 0.0
            proj = ctx.get("project_alias", "")

            # If tied to a file, generate file-scoped key
            if layer == CacheLayer.TASK_RESULT and file_p:
                cache_key = hashlib.sha256(f"file_task|{os.path.normpath(file_p).lower()}|{query.strip().lower()}".encode("utf-8")).hexdigest()
            else:
                cache_key = self.generate_cache_key(query, provider, model, context)

            entry = CacheEntry(
                key=cache_key,
                layer=layer,
                query=query.strip(),
                normalized_query=self.normalize_query(query),
                response=response.strip(),
                provider=provider,
                model=model,
                prompt_version=self.prompt_version,
                context_fingerprint=f"style={style};lang={lang};proj={proj}",
                style=style,
                language=lang,
                created_at=now,
                last_accessed_at=now,
                expires_at=expires_at,
                hit_count=0,
                is_disputed=False,
                provenance=f"NVIDIA Nemotron ({model.split('/')[-1]})",
                source_reference=source_reference,
                file_path=file_p,
                file_mtime=file_mt,
                project_alias=proj
            )

            success = self.store.put(entry)
            if success:
                logger.info(f"[CACHE_STORE] Saved {layer.value.upper()} cache entry (TTL: {ttl_sec/3600:.1f}h, Key: {cache_key[:10]}...)")

            # Periodic maintenance (LRU eviction & expired pruning)
            if now - self._last_cleanup_time > 300:  # Every 5 minutes
                self._last_cleanup_time = now
                self.store.delete_expired(now)
                self.store.evict_lru(max_entries=5000)

            return success

    def coalesce_and_execute(
        self,
        cache_key: str,
        execute_fn: Callable[[], Optional[str]],
        timeout: float = 30.0
    ) -> Tuple[Optional[str], bool]:
        """Runs single-flight execution: coalesces identical concurrent calls."""
        res, was_coalesced = self.single_flight.execute(cache_key, execute_fn, timeout=timeout)
        if was_coalesced:
            with self._lock:
                self.stats.duplicates_avoided += 1
            logger.info(f"[COALESCED] Avoided duplicate API call for key '{cache_key[:12]}...'")
        return res, was_coalesced

    def mark_disputed(self, target: str) -> int:
        """Marks entry as disputed due to user correction or reported inaccuracy."""
        with self._lock:
            count = self.store.mark_disputed(target)
            self.stats.invalidations += count
            return count

    def invalidate_by_file(self, file_path: str) -> int:
        """Invalidates entries dependent on a modified file."""
        with self._lock:
            count = self.store.invalidate_by_file(file_path)
            self.stats.invalidations += count
            return count

    def invalidate_by_project(self, project_alias: str) -> int:
        """Invalidates entries dependent on a project."""
        with self._lock:
            count = self.store.invalidate_by_project(project_alias)
            self.stats.invalidations += count
            return count

    def clear(self, layer: Optional[str] = None) -> int:
        """Clears all or specified layer cache entries."""
        with self._lock:
            count = self.store.clear(layer=layer)
            logger.info(f"[CACHE_CLEARED] Removed {count} entries (Layer: {layer or 'ALL'})")
            return count

    def get_stats(self) -> CacheStats:
        """Returns current cache statistics."""
        with self._lock:
            return self.stats

    def reset_stats(self):
        """Resets telemetry counters."""
        with self._lock:
            self.stats = CacheStats()


# Global Singleton Instance
nemotron_cache = NemotronCacheManager()
generate_cache_key = nemotron_cache.generate_cache_key
