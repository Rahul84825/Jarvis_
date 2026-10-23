"""Policy Evaluator for JARVIS Multi-Layer AI Cache.
Enforces Section 3 (Do Not Cache Everything) and Section 4 (Context-Aware Validation).
"""

import os
import re
import time
import logging
from typing import Optional, Dict, Any, Tuple

from core.ai.caching.models import CacheEntry, CacheLayer

logger = logging.getLogger("Jarvis.PolicyEvaluator")


class PolicyEvaluator:
    """Evaluates whether requests must bypass caching, determines TTLs,
    and performs 7-point context validation before a candidate cache entry is reused.
    """

    # Live dynamic markers that require fresh data
    DYNAMIC_QUERY_PATTERNS = [
        r"\b(?:what\s+time|current\s+time|time\s+is\s+it|the\s+time)\b",
        r"\b(?:what\s+date|today'?s\s+date|current\s+date|day\s+is\s+it)\b",
        r"\b(?:weather|forecast|temperature|rain|humidity)\b",
        r"\b(?:news|headlines|stock\s+price|market\s+price|bitcoin|crypto)\b",
        r"\b(?:battery(?:\s+level|\s+status)?|power\s+(?:level|status|draw)|cpu(?:\s+usage|\s+load)?|ram(?:\s+usage|\s+load)?|memory\s+usage|free\s+memory|disk\s+space|gpu(?:\s+usage|\s+temp)?|telemetry)\b",
        r"\b(?:active\s+tab|open\s+windows|running\s+processes|list\s+processes)\b"
    ]

    # Explicit user bypass triggers
    EXPLICIT_BYPASS_PATTERNS = [
        r"\b(?:force\s+(?:a\s+)?fresh\s+answer|fresh\s+answer\s+from\s+nemotron|force\s+fresh)\b",
        r"\b(?:bypass\s+cache|without\s+cache|don't\s+use\s+cache|dont\s+use\s+cache|no\s+cache)\b",
        r"\b(?:ask\s+nemotron\s+directly|ask\s+nvidia\s+directly|live\s+query)\b"
    ]

    # Transactional action intents that must execute rather than return cached text
    TRANSACTIONAL_ACTION_PATTERNS = [
        r"\b(?:send\s+(?:the\s+)?message|send\s+(?:the\s+)?email|submit\s+(?:the\s+)?form)\b",
        r"\b(?:delete\s+file|remove\s+file|create\s+directory|overwrite\s+file)\b",
        r"\b(?:shutdown\s+computer|restart\s+computer|lock\s+screen|sleep\s+computer)\b",
        r"\b(?:git\s+commit|git\s+push)\b"
    ]

    def is_bypass_required(self, query: str, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """Determines if a request must strictly bypass cache and hit Nemotron/OS directly.
        Returns: (True, reason_description) or (False, "")
        """
        ctx = context or {}

        # 0. Context flag bypass
        if ctx.get("force_fresh") or ctx.get("force_fresh_capture") or ctx.get("bypass_cache"):
            return True, "bypassed_context_flag"

        clean = query.lower().strip()

        # 1. Explicit user request to force fresh response
        for pat in self.EXPLICIT_BYPASS_PATTERNS:
            if re.search(pat, clean):
                return True, "bypassed_explicit_user_request"

        # 2. Transactional OS actions
        for pat in self.TRANSACTIONAL_ACTION_PATTERNS:
            if re.search(pat, clean):
                return True, "bypassed_transactional_action"

        # 3. Dynamic real-time information
        for pat in self.DYNAMIC_QUERY_PATTERNS:
            if re.search(pat, clean):
                return True, "bypassed_dynamic_query"

        # 4. Screen understanding with changed screen
        if ctx.get("requires_vision"):
            # Check if screen change flag is set or screen hash changed
            if ctx.get("screen_changed", False):
                return True, "bypassed_screen_state_changed"

        # 5. File-based query where file has been modified on disk
        target_file = ctx.get("file_path")
        if target_file and os.path.exists(target_file):
            cached_mtime = ctx.get("file_mtime")
            curr_mtime = os.path.getmtime(target_file)
            if cached_mtime and curr_mtime > cached_mtime:
                return True, "bypassed_file_modified_on_disk"

        return False, ""

    def validate_candidate(
        self,
        candidate: CacheEntry,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        current_time: Optional[float] = None,
        provider: str = "",
        model: str = ""
    ) -> Tuple[bool, str]:
        """Performs 7-point validation on candidate entry before allowing reuse.
        Returns: (is_valid, failure_reason)
        """
        now = current_time or time.time()
        ctx = context or {}

        # Check 1: Disputed entry check (marked by user correction)
        if candidate.is_disputed:
            return False, "rejected_disputed_entry"

        # Check 2: Freshness / TTL check
        if candidate.is_expired(now):
            return False, "rejected_expired_ttl"

        # Check 3: Original generation status (never reuse errors or empty answers)
        if not candidate.response or len(candidate.response.strip()) < 5:
            return False, "rejected_empty_response"
        if candidate.response.startswith("[ERROR]") or "API key or credentials" in candidate.response:
            return False, "rejected_error_response"

        # Check 4: Model and Provider compatibility
        req_provider = provider or ctx.get("provider")
        if req_provider and candidate.provider and req_provider.lower().strip() != candidate.provider.lower().strip():
            return False, "rejected_provider_mismatch"

        req_model = model or ctx.get("model")
        if req_model and candidate.model and req_model.lower().strip() != candidate.model.lower().strip():
            return False, "rejected_model_mismatch"

        # Check 5: Project context isolation (never leak answers between different projects)
        req_project = ctx.get("project_alias")
        if req_project and candidate.project_alias and req_project.lower() != candidate.project_alias.lower():
            return False, "rejected_project_mismatch"

        # Check 6: File freshness (for task results tied to a specific file)
        if candidate.file_path and os.path.exists(candidate.file_path):
            current_mtime = os.path.getmtime(candidate.file_path)
            if candidate.file_mtime and current_mtime > candidate.file_mtime:
                return False, "rejected_file_modified_since_cached"

        # Check 7: Conversation context delta (reject if query contains important conflicting parameters)
        req_style = ctx.get("style")
        if req_style and candidate.style and req_style != candidate.style:
            return False, "rejected_style_mismatch"

        return True, "valid"

    def determine_ttl(self, layer: CacheLayer, query: str, response: str) -> float:
        """Assigns configurable TTL based on stability of the underlying concept.
        Stable factual knowledge gets long TTL (30 days); transient tasks get shorter TTL.
        """
        clean = query.lower()

        # Programming concept or algorithm: Highly stable knowledge -> 30 days
        if any(w in clean for w in ["polymorphism", "inheritance", "binary search", "quicksort", "bubble sort", "dijkstra", "raii", "async", "await", "virtual memory", "recursion"]):
            return 30.0 * 86400.0  # 30 days

        if layer == CacheLayer.KNOWLEDGE:
            return 30.0 * 86400.0  # 30 days
        elif layer == CacheLayer.TASK_RESULT:
            return 3600.0          # 1 hour
        elif layer == CacheLayer.SEMANTIC:
            return 86400.0         # 24 hours
        else:
            return 86400.0         # 24 hours (Exact)
