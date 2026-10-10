import os
import re
import json
import time
import shutil
import sqlite3
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from config import config

logger = logging.getLogger("Jarvis.ConversationPersistence")

# Secret redaction suite to ensure keys and passwords never hit persistent storage
DEFAULT_REDACTION_PATTERNS = [
    (r"\bsk-[a-zA-Z0-9_-]{12,}\b", "[REDACTED_OPENAI_KEY]"),
    (r"\bAIza[0-9A-Za-z-_]{30,40}\b", "[REDACTED_GEMINI_KEY]"),
    (r"\bgh[pousr]_[A-Za-z0-9_]{36,255}\b", "[REDACTED_GITHUB_TOKEN]"),
    (r"\bsk-ant-[a-zA-Z0-9_-]{20,}\b", "[REDACTED_ANTHROPIC_KEY]"),
    (r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED_AWS_KEY]"),
    (r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{15,}\b", "Bearer [REDACTED_TOKEN]"),
    (r"(?i)(api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?", r"\1: [REDACTED_KEY]"),
    (r"(?i)(password|secret|passwd)\s*[:=]\s*['\"]?([^'\"\s]{6,})['\"]?", r"\1: [REDACTED_PASSWORD]"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
    (r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b", "[REDACTED_JWT]"),
    (r"(?i)(?:postgres|mysql|mongodb|redis):\/\/[^:]+:[^@]+@[a-zA-Z0-9_\.\-]+(?::\d+)?\/[^\s\"']*", "[REDACTED_DATABASE_URI]"),
    (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[REDACTED_CREDIT_CARD]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", "[REDACTED_EMAIL]")
]


class ConversationPersistence:
    """Thread-safe SQLite persistent conversation store for JARVIS.
    Maintains durable conversation history across application restarts, performs secret redaction,
    manages non-destructive schema migrations, recovers safely from corrupt databases,
    and supports targeted relevant context retrieval.
    """

    CURRENT_SCHEMA_VERSION = 1

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or getattr(config, "db_conversations", "memory/conversations.db"))
        self._lock = threading.Lock()
        self._ensure_directory()
        self._init_database()

    def _ensure_directory(self):
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create directory for conversation database: {e}")

    def is_enabled(self) -> bool:
        """Checks whether persistent conversation storage is enabled by configuration or environment."""
        if os.environ.get("JARVIS_PERSISTENT_MEMORY", "").lower() in ["false", "0", "no"]:
            return False
        return bool(getattr(config, "persistent_memory_enabled", True))

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a SQLite connection with timeout and WAL journal mode for concurrency."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        return conn

    def _init_database(self):
        """Initializes tables, indices, and schema migrations with corruption recovery."""
        with self._lock:
            try:
                self._run_schema_setup()
            except sqlite3.DatabaseError as de:
                logger.error(f"Database error during initialization ({de}). Attempting safe recovery.")
                self._handle_corrupt_database()
                self._run_schema_setup()
            except Exception as ex:
                logger.error(f"Unexpected error during conversation db initialization: {ex}", exc_info=True)

    def _handle_corrupt_database(self):
        """Safely renames corrupt database file to preserve evidence and allows recreation."""
        try:
            if self.db_path.exists():
                backup_name = f"{self.db_path}.corrupt.{int(time.time())}"
                shutil.move(str(self.db_path), backup_name)
                logger.warning(f"Corrupt database moved to '{backup_name}'. Created fresh database.")
        except Exception as e:
            logger.error(f"Could not back up corrupt database: {e}")

    def _run_schema_setup(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create migrations tracker
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL,
                    description TEXT
                )
            """)

            # Create main conversations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    source TEXT DEFAULT 'direct',
                    metadata_json TEXT DEFAULT '{}'
                )
            """)

            # Indices for rapid querying
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversation_history(timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_history(session_id);")

            # Check if current migration has been recorded
            cursor.execute("SELECT version FROM schema_migrations WHERE version = ?", (self.CURRENT_SCHEMA_VERSION,))
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                    (self.CURRENT_SCHEMA_VERSION, time.time(), "Initial conversation_history schema with indices")
                )
            conn.commit()

    def redact_secrets(self, text: str) -> str:
        """Sanitizes text by masking sensitive tokens, keys, passwords, and credentials."""
        if not text:
            return ""
        redacted = text
        for pattern, replacement in DEFAULT_REDACTION_PATTERNS:
            redacted = re.sub(pattern, replacement, redacted)
        return redacted

    def save_turn(
        self,
        user_text: str,
        assistant_text: str,
        session_id: str = "default",
        source: str = "assistant",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Saves a conversation interaction turn (user query + assistant response) additively."""
        if not self.is_enabled():
            logger.debug("Persistent conversation memory disabled. Skipping disk save.")
            return False

        clean_user = self.redact_secrets(user_text.strip())
        clean_assistant = self.redact_secrets(assistant_text.strip())
        now = time.time()
        meta_str = json.dumps(metadata or {})

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO conversation_history (session_id, role, content, timestamp, source, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (session_id, "user", clean_user, now, source, meta_str))

                    cursor.execute("""
                        INSERT INTO conversation_history (session_id, role, content, timestamp, source, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (session_id, "assistant", clean_assistant, now + 0.001, source, meta_str))
                    conn.commit()
                logger.info(f"Persisted conversation turn to SQLite ({self.db_path.name}) for session '{session_id}'.")
                return True
            except Exception as e:
                logger.error(f"Failed to persist conversation turn: {e}", exc_info=True)
                return False

    def get_recent_turns(self, limit: int = 10, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves the most recent N conversational turns from SQLite.
        Returns a list of dicts: [{'role': ..., 'content': ..., 'timestamp': ..., 'source': ...}].
        """
        if not self.is_enabled():
            return []

        # Each turn consists of user + assistant, so fetch limit * 2 messages
        message_limit = max(1, limit * 2)

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    if session_id:
                        cursor.execute("""
                            SELECT id, session_id, role, content, timestamp, source
                            FROM conversation_history
                            WHERE session_id = ?
                            ORDER BY timestamp DESC
                            LIMIT ?
                        """, (session_id, message_limit))
                    else:
                        cursor.execute("""
                            SELECT id, session_id, role, content, timestamp, source
                            FROM conversation_history
                            ORDER BY timestamp DESC
                            LIMIT ?
                        """, (message_limit,))

                    rows = cursor.fetchall()
                    # Reverse to chronological order
                    results = []
                    for r in reversed(rows):
                        results.append({
                            "id": r["id"],
                            "session_id": r["session_id"],
                            "role": r["role"],
                            "content": r["content"],
                            "timestamp": r["timestamp"],
                            "source": r["source"]
                        })
                    return results
            except Exception as e:
                logger.error(f"Failed to load recent conversation turns: {e}")
                return []

    def search_relevant_history(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches past conversation history for exchanges relevant to a query keyword without
        dumping the entire database.
        """
        if not self.is_enabled() or not query or not query.strip():
            return []

        keywords = [k.strip().lower() for k in query.split() if len(k.strip()) >= 3]
        if not keywords:
            keywords = [query.strip().lower()]

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    # Match any keyword in user or assistant content
                    clause = " OR ".join(["content LIKE ?" for _ in keywords[:4]])
                    params = [f"%{k}%" for k in keywords[:4]]
                    params.append(limit)

                    sql = f"""
                        SELECT id, session_id, role, content, timestamp, source
                        FROM conversation_history
                        WHERE {clause}
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()

                    matches = []
                    for r in rows:
                        matches.append({
                            "id": r["id"],
                            "session_id": r["session_id"],
                            "role": r["role"],
                            "content": r["content"],
                            "timestamp": r["timestamp"],
                            "source": r["source"]
                        })
                    return matches
            except Exception as e:
                logger.error(f"Error searching conversation history: {e}")
                return []

    def get_context_summary(self, max_turns: int = 4) -> str:
        """Returns a concise formatted string of previous conversation turns for LLM injection."""
        recent = self.get_recent_turns(limit=max_turns)
        if not recent:
            return ""

        lines = ["Relevant previous conversation context:"]
        for msg in recent:
            role_label = "User" if msg["role"] == "user" else "Jarvis"
            lines.append(f"{role_label}: {msg['content']}")
        return "\n".join(lines)

    def clear_all(self) -> bool:
        """Clears all stored conversation history from the SQLite database."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM conversation_history;")
                    conn.commit()
                logger.info(f"Cleared all records from {self.db_path.name}.")
                return True
            except Exception as e:
                logger.error(f"Failed to clear conversation history: {e}")
                return False

    def clear_session(self, session_id: str) -> bool:
        """Clears conversation history for a specific session."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM conversation_history WHERE session_id = ?;", (session_id,))
                    conn.commit()
                logger.info(f"Cleared session '{session_id}' from {self.db_path.name}.")
                return True
            except Exception as e:
                logger.error(f"Failed to clear session '{session_id}': {e}")
                return False
