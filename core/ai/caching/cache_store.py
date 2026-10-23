"""Persistent SQLite storage implementation for JARVIS Multi-Layer AI Cache."""

import os
import time
import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.ai.caching.models import CacheEntry, CacheLayer

logger = logging.getLogger("Jarvis.CacheStore")


class CacheStore:
    """Thread-safe SQLite persistent store for cached AI responses and knowledge."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.db_path = str(base_dir / "logs" / "nemotron_cache.db")
        else:
            self.db_path = db_path

        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"[CACHE_STORE] Initialized SQLite cache database at: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes tables and indexes with safe idempotency."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,
                    query TEXT NOT NULL,
                    normalized_query TEXT NOT NULL,
                    response TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT DEFAULT '1.0',
                    context_fingerprint TEXT DEFAULT '',
                    style TEXT DEFAULT 'default',
                    language TEXT DEFAULT 'en',
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    expires_at REAL,
                    hit_count INTEGER DEFAULT 0,
                    is_disputed INTEGER DEFAULT 0,
                    provenance TEXT DEFAULT 'NVIDIA Nemotron',
                    source_reference TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    file_mtime REAL DEFAULT 0.0,
                    project_alias TEXT DEFAULT ''
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_norm_query ON api_cache(normalized_query)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_layer ON api_cache(layer)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON api_cache(expires_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_disputed ON api_cache(is_disputed)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_file ON api_cache(file_path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_project ON api_cache(project_alias)")
            conn.commit()

    def get(self, cache_key: str) -> Optional[CacheEntry]:
        """Retrieves entry by primary cache key."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM api_cache
                    WHERE cache_key = ?
                """, (cache_key,))
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_entry(row)
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error fetching cache key '{cache_key[:12]}...': {e}")
            return None

    def put(self, entry: CacheEntry) -> bool:
        """Inserts or replaces a cache entry."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO api_cache (
                        cache_key, layer, query, normalized_query, response, provider, model,
                        prompt_version, context_fingerprint, style, language, created_at,
                        last_accessed_at, expires_at, hit_count, is_disputed, provenance,
                        source_reference, file_path, file_mtime, project_alias
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.key,
                    entry.layer.value if hasattr(entry.layer, "value") else str(entry.layer),
                    entry.query,
                    entry.normalized_query,
                    entry.response,
                    entry.provider,
                    entry.model,
                    entry.prompt_version,
                    entry.context_fingerprint,
                    entry.style,
                    entry.language,
                    entry.created_at,
                    entry.last_accessed_at,
                    entry.expires_at,
                    entry.hit_count,
                    1 if entry.is_disputed else 0,
                    entry.provenance,
                    entry.source_reference,
                    entry.file_path,
                    entry.file_mtime,
                    entry.project_alias
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error saving cache entry '{entry.key[:12]}...': {e}")
            return False

    def touch(self, cache_key: str) -> bool:
        """Updates last_accessed_at timestamp and increments hit counter."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE api_cache
                    SET last_accessed_at = ?, hit_count = hit_count + 1
                    WHERE cache_key = ?
                """, (time.time(), cache_key))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error touching cache key '{cache_key[:12]}...': {e}")
            return False

    def mark_disputed(self, target: str) -> int:
        """Marks matching entries as disputed so they are never returned as valid cache."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Check if target is a cache key or query snippet
                cursor.execute("""
                    UPDATE api_cache
                    SET is_disputed = 1
                    WHERE cache_key = ? OR normalized_query LIKE ? OR query LIKE ?
                """, (target, f"%{target.lower().strip()}%", f"%{target.strip()}%"))
                conn.commit()
                count = cursor.rowcount
                if count > 0:
                    logger.info(f"[CACHE_STORE] Marked {count} cache entry(ies) as DISPUTED for target: '{target}'")
                return count
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error marking disputed '{target}': {e}")
            return 0

    def invalidate_by_file(self, file_path: str) -> int:
        """Invalidates task and knowledge entries associated with a modified file."""
        if not file_path:
            return 0
        try:
            norm_path = os.path.normpath(file_path).lower()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM api_cache
                    WHERE LOWER(file_path) = ? OR LOWER(file_path) LIKE ?
                """, (norm_path, f"%{norm_path}%"))
                conn.commit()
                count = cursor.rowcount
                if count > 0:
                    logger.info(f"[CACHE_STORE] Invalidated {count} cache entry(ies) for file: {file_path}")
                return count
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error invalidating by file '{file_path}': {e}")
            return 0

    def invalidate_by_project(self, project_alias: str) -> int:
        """Invalidates entries tied to a specific project."""
        if not project_alias:
            return 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM api_cache
                    WHERE LOWER(project_alias) = ?
                """, (project_alias.lower().strip(),))
                conn.commit()
                count = cursor.rowcount
                if count > 0:
                    logger.info(f"[CACHE_STORE] Invalidated {count} cache entry(ies) for project: {project_alias}")
                return count
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error invalidating by project '{project_alias}': {e}")
            return 0

    def delete_expired(self, current_time: Optional[float] = None) -> int:
        """Prunes expired entries based on TTL."""
        now = current_time or time.time()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM api_cache
                    WHERE expires_at IS NOT NULL AND expires_at < ?
                """, (now,))
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error deleting expired entries: {e}")
            return 0

    def evict_lru(self, max_entries: int = 5000) -> int:
        """Evicts oldest accessed entries when table exceeds max_entries."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM api_cache")
                total = cursor.fetchone()[0]
                if total <= max_entries:
                    return 0

                excess = total - max_entries
                cursor.execute("""
                    DELETE FROM api_cache
                    WHERE cache_key IN (
                        SELECT cache_key FROM api_cache
                        WHERE layer != 'knowledge' -- Preserve persistent knowledge from LRU eviction
                        ORDER BY last_accessed_at ASC
                        LIMIT ?
                    )
                """, (excess,))
                conn.commit()
                evicted = cursor.rowcount
                logger.info(f"[CACHE_STORE] Evicted {evicted} LRU cache entries (Capacity: {max_entries})")
                return evicted
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error during LRU eviction: {e}")
            return 0

    def clear(self, layer: Optional[str] = None) -> int:
        """Clears all or layer-specific cache entries."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if layer:
                    cursor.execute("DELETE FROM api_cache WHERE layer = ?", (layer,))
                else:
                    cursor.execute("DELETE FROM api_cache")
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error clearing cache: {e}")
            return 0

    def count(self, layer: Optional[str] = None) -> int:
        """Returns total active entries count."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if layer:
                    cursor.execute("SELECT COUNT(*) FROM api_cache WHERE layer = ?", (layer,))
                else:
                    cursor.execute("SELECT COUNT(*) FROM api_cache")
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error counting cache: {e}")
            return 0

    def get_candidates_for_semantic(
        self,
        limit: int = 300,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> List[CacheEntry]:
        """Returns valid non-disputed candidates for semantic similarity matching."""
        try:
            now = time.time()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query_sql = """
                    SELECT * FROM api_cache
                    WHERE is_disputed = 0
                      AND (expires_at IS NULL OR expires_at > ?)
                """
                params: List[Any] = [now]
                if provider:
                    query_sql += " AND LOWER(provider) = ?"
                    params.append(provider.lower().strip())
                if model:
                    query_sql += " AND LOWER(model) = ?"
                    params.append(model.lower().strip())

                query_sql += " ORDER BY last_accessed_at DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query_sql, tuple(params))
                rows = cursor.fetchall()
                return [self._row_to_entry(r) for r in rows]
        except Exception as e:
            logger.error(f"[CACHE_STORE] Error fetching semantic candidates: {e}")
            return []

    def _row_to_entry(self, row: sqlite3.Row) -> CacheEntry:
        """Converts SQLite Row to typed CacheEntry."""
        return CacheEntry(
            key=row["cache_key"],
            layer=CacheLayer(row["layer"]) if row["layer"] in CacheLayer._value2member_map_ else CacheLayer.EXACT,
            query=row["query"],
            normalized_query=row["normalized_query"],
            response=row["response"],
            provider=row["provider"],
            model=row["model"],
            prompt_version=row["prompt_version"],
            context_fingerprint=row["context_fingerprint"],
            style=row["style"],
            language=row["language"],
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
            expires_at=row["expires_at"],
            hit_count=row["hit_count"],
            is_disputed=bool(row["is_disputed"]),
            provenance=row["provenance"],
            source_reference=row["source_reference"],
            file_path=row["file_path"],
            file_mtime=row["file_mtime"],
            project_alias=row["project_alias"]
        )
