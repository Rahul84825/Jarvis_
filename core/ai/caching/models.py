"""Data models and enums for JARVIS Multi-Layer AI Caching Engine."""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


class CacheLayer(str, Enum):
    """Enumeration of cache hierarchy layers."""
    EXACT = "exact"              # Layer A: Exact normalized response cache
    SEMANTIC = "semantic"        # Layer B: Semantic equivalence cache
    KNOWLEDGE = "knowledge"      # Layer C: Persistent verified factual knowledge
    TASK_RESULT = "task_result"  # Layer D: Deterministic tool and file analysis cache


class CacheStatus(str, Enum):
    """Validation status for cache entries."""
    VALID = "valid"
    EXPIRED = "expired"
    DISPUTED = "disputed"
    INVALIDATED = "invalidated"


@dataclass
class CacheEntry:
    """Represents a cached response or verified task result."""
    key: str
    layer: CacheLayer
    query: str
    normalized_query: str
    response: str
    provider: str
    model: str
    prompt_version: str = "1.0"
    context_fingerprint: str = ""
    style: str = "default"
    language: str = "en"
    created_at: float = 0.0
    last_accessed_at: float = 0.0
    expires_at: Optional[float] = None
    hit_count: int = 0
    is_disputed: bool = False
    provenance: str = "NVIDIA Nemotron"
    source_reference: str = ""
    file_path: str = ""
    file_mtime: float = 0.0
    project_alias: str = ""

    def is_expired(self, current_time: float) -> bool:
        """Checks if entry TTL has expired."""
        if self.expires_at is None:
            return False
        return current_time > self.expires_at


@dataclass
class CacheLookupResult:
    """Outcome of checking the multi-layer cache."""
    hit: bool
    response: Optional[str] = None
    layer: Optional[CacheLayer] = None
    entry: Optional[CacheEntry] = None
    reason: str = "miss"
    similarity_score: float = 1.0
    latency_ms: float = 0.0

    @property
    def source_label(self) -> str:
        """Returns clean source label for response attribution."""
        if not self.hit:
            return "AI Provider"
        if self.layer == CacheLayer.EXACT:
            return "Exact Response Cache"
        elif self.layer == CacheLayer.SEMANTIC:
            return f"Semantic Cache ({self.similarity_score:.0%})"
        elif self.layer == CacheLayer.KNOWLEDGE:
            return "Verified Knowledge Cache"
        elif self.layer == CacheLayer.TASK_RESULT:
            return "Task Result Cache"
        return "Cache"


@dataclass
class CacheStats:
    """Cumulative telemetry and metrics for AI cache usage."""
    total_lookups: int = 0
    exact_hits: int = 0
    semantic_hits: int = 0
    knowledge_hits: int = 0
    task_hits: int = 0
    misses: int = 0
    bypasses: int = 0
    duplicates_avoided: int = 0
    invalidations: int = 0

    @property
    def total_hits(self) -> int:
        return self.exact_hits + self.semantic_hits + self.knowledge_hits + self.task_hits

    @property
    def hit_rate_pct(self) -> float:
        eligible = self.total_lookups - self.bypasses
        if eligible <= 0:
            return 0.0
        return (self.total_hits / eligible) * 100.0

    @property
    def api_calls_saved(self) -> int:
        return self.total_hits + self.duplicates_avoided

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_lookups": self.total_lookups,
            "total_hits": self.total_hits,
            "exact_hits": self.exact_hits,
            "semantic_hits": self.semantic_hits,
            "knowledge_hits": self.knowledge_hits,
            "task_hits": self.task_hits,
            "misses": self.misses,
            "bypasses": self.bypasses,
            "duplicates_avoided": self.duplicates_avoided,
            "invalidations": self.invalidations,
            "hit_rate_pct": round(self.hit_rate_pct, 1),
            "api_calls_saved": self.api_calls_saved
        }
