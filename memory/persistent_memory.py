import os
import sqlite3
import json
import time
import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("Jarvis.Memory")

class PersistentMemory:
    """Long-Term SQLite-backed memory and autonomous learning engine for Jarvis.
    Stores user preferences, habits, custom notes, and episodic conversational memory.
    Automatically extracts facts from user speech to build a personalized user profile.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(__file__).parent
            self.db_path = str(base_dir / "jarvis_memory.db")
        else:
            self.db_path = db_path

        self._init_db()
        logger.info(f"PersistentMemory initialized with database: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # Secret redaction suite to ensure keys and passwords never hit persistent storage
    REDACTION_PATTERNS = [
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
        (r"(?i)(?:postgres|mysql|mongodb|redis):\/\/[^:]+:[^@]+@[a-zA-Z0-9_\.\-]+(?::\d+)?\/[^\s\"']*", "[REDACTED_DATABASE_URI]")
    ]

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Sanitizes sensitive tokens, API keys, and credentials from string values."""
        if not isinstance(text, str):
            return text
        clean = text
        for pattern, replacement in cls.REDACTION_PATTERNS:
            clean = re.sub(pattern, replacement, clean)
        return clean

    @classmethod
    def sanitize_data(cls, data: Any) -> Any:
        """Recursively sanitizes sensitive information from dictionaries, lists, or strings."""
        if isinstance(data, str):
            return cls.sanitize_text(data)
        elif isinstance(data, dict):
            res = {}
            for k, v in data.items():
                clean_k = cls.sanitize_text(k) if isinstance(k, str) else k
                k_lower = str(k).lower().strip()
                if any(sec in k_lower for sec in ["password", "passwd", "secret"]):
                    res[clean_k] = "[REDACTED_PASSWORD]"
                elif any(sec in k_lower for sec in ["api_key", "apikey", "access_token"]):
                    res[clean_k] = "[REDACTED_KEY]"
                elif isinstance(v, str):
                    res[clean_k] = cls.sanitize_text(v)
                else:
                    res[clean_k] = cls.sanitize_data(v)
            return res
        elif isinstance(data, list):
            return [cls.sanitize_data(item) for item in data]
        return data

    def _init_db(self):
        """Initializes database schema with safe backward-compatible migrations."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # User preferences & profile facts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    confidence REAL DEFAULT 1.0,
                    updated_at REAL NOT NULL
                )
            """)

            # Episodic conversation log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    user_prompt TEXT NOT NULL,
                    assistant_response TEXT NOT NULL,
                    intent TEXT,
                    summary TEXT,
                    tags TEXT
                )
            """)

            # Custom knowledge & user notes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT DEFAULT 'user',
                    created_at REAL NOT NULL
                )
            """)

            # Scheduled reminders & autonomous alerts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    trigger_time REAL NOT NULL,
                    recurrence TEXT DEFAULT 'once',
                    action_type TEXT DEFAULT 'voice_reminder',
                    action_payload TEXT,
                    status TEXT DEFAULT 'pending'
                )
            """)

            # Projects registry table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    alias TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    framework TEXT DEFAULT '',
                    backend_port INTEGER DEFAULT NULL,
                    test_cmd TEXT DEFAULT '',
                    updated_at REAL NOT NULL
                )
            """)

            # Structured categorized memories table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    timestamp REAL NOT NULL
                )
            """)

            # Schema migrations tracker
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL,
                    description TEXT NOT NULL
                )
            """)

            # Phase 2 & 3: Structured Execution Experiences
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    user_request TEXT NOT NULL,
                    normalized_intent TEXT NOT NULL,
                    tool_or_procedure TEXT NOT NULL,
                    execution_parameters TEXT NOT NULL,
                    preconditions TEXT,
                    environment TEXT,
                    execution_outcome TEXT NOT NULL,
                    verification_evidence TEXT,
                    observed_failure TEXT,
                    user_corrections TEXT,
                    software_version TEXT DEFAULT '2.0.0',
                    confidence REAL DEFAULT 1.0,
                    applicable_conditions TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_intent ON execution_experiences(normalized_intent)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_timestamp ON execution_experiences(timestamp)")

            # Phase 3: Verified Learned Procedures
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_procedures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    procedure_name TEXT UNIQUE NOT NULL,
                    intent TEXT NOT NULL,
                    trigger_patterns TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    prerequisites TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_verified_at REAL,
                    confidence REAL DEFAULT 1.0,
                    is_active INTEGER DEFAULT 1,
                    source TEXT DEFAULT 'learned',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_proc_intent ON learned_procedures(intent)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_proc_active ON learned_procedures(is_active)")

            # Phase 4: User Learned Preferences (Corrections, Aliases, Folders)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_learned_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    preference_type TEXT NOT NULL,
                    trigger_key TEXT NOT NULL,
                    preferred_value TEXT NOT NULL,
                    evidence_source TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    scope TEXT DEFAULT 'persistent',
                    last_applied_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(preference_type, trigger_key)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_type ON user_learned_preferences(preference_type)")

            # Phase 5: Verified Reasoning & Local Computation Cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verified_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT UNIQUE NOT NULL,
                    query_normalized TEXT NOT NULL,
                    cached_response TEXT NOT NULL,
                    source_provider TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    is_dynamic INTEGER DEFAULT 0,
                    access_count INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    expires_at REAL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_hash ON verified_cache(query_hash)")

            # Record migration 1
            cursor.execute("""
                INSERT OR IGNORE INTO schema_migrations (version, applied_at, description)
                VALUES (1, ?, 'Phase 6/7: Added execution_experiences, learned_procedures, user_learned_preferences, verified_cache')
            """, (time.time(),))

            conn.commit()

    # ==========================================
    # PROFILE & PREFERENCES
    # ==========================================
    def set_preference(self, key: str, value: str, category: str = "general") -> bool:
        """Saves or updates a user preference/fact."""
        try:
            clean_key = key.lower().strip().replace(" ", "_")
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_profile (key, value, category, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        category = excluded.category,
                        updated_at = excluded.updated_at
                """, (clean_key, str(value).strip(), category, time.time()))
                conn.commit()
            logger.info(f"Saved memory preference: {clean_key} = {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to set preference '{key}': {e}")
            return False

    def get_preference(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieves a specific user preference."""
        clean_key = key.lower().strip().replace(" ", "_")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM user_profile WHERE key = ?", (clean_key,))
                row = cursor.fetchone()
                return row["value"] if row else default
        except Exception as e:
            logger.error(f"Failed to get preference '{key}': {e}")
            return default

    def get_all_preferences(self) -> Dict[str, str]:
        """Returns all stored user preferences as a dictionary."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM user_profile ORDER BY category, key")
                rows = cursor.fetchall()
                return {row["key"]: row["value"] for row in rows}
        except Exception as e:
            logger.error(f"Failed to fetch preferences: {e}")
            return {}

    def delete_preference(self, key: str) -> bool:
        """Deletes a specific user preference from user_profile."""
        clean_key = key.lower().strip().replace(" ", "_")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM user_profile WHERE key = ?", (clean_key,))
                conn.commit()
            logger.info(f"Deleted memory preference: {clean_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete preference '{key}': {e}")
            return False

    # ==========================================
    # EPISODIC MEMORY
    # ==========================================
    def record_interaction(self, user_prompt: str, assistant_response: str, intent: str = "general", summary: str = "", tags: List[str] = None):
        """Records a conversational turn into long-term episodic memory."""
        if not user_prompt or not assistant_response:
            return

        tags_str = ",".join(tags) if tags else ""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO episodic_memory (timestamp, user_prompt, assistant_response, intent, summary, tags)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (time.time(), user_prompt.strip(), assistant_response.strip(), intent, summary, tags_str))
                conn.commit()

            # Trigger auto-learning in background
            self.auto_learn_from_speech(user_prompt)
        except Exception as e:
            logger.error(f"Failed to record episodic memory: {e}")

    def get_recent_interactions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetches the most recent interactions."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, user_prompt, assistant_response, intent, summary
                    FROM episodic_memory
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                results = []
                for r in reversed(rows):
                    results.append({
                        "timestamp": r["timestamp"],
                        "user": r["user_prompt"],
                        "assistant": r["assistant_response"],
                        "intent": r["intent"]
                    })
                return results
        except Exception as e:
            logger.error(f"Failed to get recent episodic interactions: {e}")
            return []

    # ==========================================
    # KNOWLEDGE NOTES
    # ==========================================
    def add_note(self, topic: str, content: str, source: str = "user") -> bool:
        """Stores custom knowledge or user notes."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO knowledge_notes (topic, content, source, created_at)
                    VALUES (?, ?, ?, ?)
                """, (topic.strip(), content.strip(), source, time.time()))
                conn.commit()
            logger.info(f"Saved knowledge note under topic '{topic}'")
            return True
        except Exception as e:
            logger.error(f"Failed to add knowledge note: {e}")
            return False

    def search_notes(self, query: str) -> List[Dict[str, Any]]:
        """Searches notes matching keywords."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT topic, content, created_at FROM knowledge_notes
                    WHERE topic LIKE ? OR content LIKE ?
                    ORDER BY id DESC LIMIT 5
                """, (f"%{query}%", f"%{query}%"))
                rows = cursor.fetchall()
                return [{"topic": r["topic"], "content": r["content"], "created_at": r["created_at"]} for r in rows]
        except Exception as e:
            logger.error(f"Failed to search notes: {e}")
            return []

    # ==========================================
    # AUTONOMOUS LEARNING ENGINE
    # ==========================================
    def auto_learn_from_speech(self, text: str) -> Optional[str]:
        """Analyzes text for statements of preference, identity, or habits, saving them automatically."""
        if not text:
            return None

        clean = text.strip()
        learned = []

        # Name extraction
        name_match = re.search(r"(?:my name is|call me)\s+([A-Za-z]+)", clean, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).capitalize()
            self.set_preference("user_name", name, category="identity")
            learned.append(f"user_name = {name}")

        # Favorite items
        fav_match = re.search(r"my favorite\s+([A-Za-z0-9_ ]+?)\s+is\s+([^.,!]+)", clean, re.IGNORECASE)
        if fav_match:
            item = fav_match.group(1).strip()
            val = fav_match.group(2).strip()
            self.set_preference(f"favorite_{item}", val, category="favorites")
            learned.append(f"favorite_{item} = {val}")

        # Explicit 'remember that'
        rem_match = re.search(r"(?:remember that|note that)\s+(.*)", clean, re.IGNORECASE)
        if rem_match:
            fact = rem_match.group(1).strip()
            self.add_note("User Fact", fact)
            learned.append(f"fact = {fact}")

        if learned:
            logger.info(f"[AUTO-LEARN] Learned new facts from user speech: {', '.join(learned)}")
            return ", ".join(learned)
        return None

    # ==========================================
    # STRUCTURED CATEGORIZED MEMORY
    # ==========================================
    def remember(self, category: str, key: str, value: str, confidence: float = 1.0) -> bool:
        """Stores a structured memory entry under a specific category."""
        try:
            clean_key = key.lower().strip()
            clean_cat = category.lower().strip()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO memories (category, key, value, confidence, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (clean_cat, clean_key, str(value).strip(), confidence, time.time()))
                conn.commit()
            logger.info(f"Remembered: [{clean_cat}] {clean_key} = {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to remember '{key}': {e}")
            return False

    def recall(self, key: str, category: Optional[str] = None) -> Optional[str]:
        """Recalls the most recent memory value for a key."""
        clean_key = key.lower().strip()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if category:
                    cursor.execute("""
                        SELECT value FROM memories
                        WHERE key = ? AND category = ?
                        ORDER BY id DESC LIMIT 1
                    """, (clean_key, category.lower().strip()))
                else:
                    cursor.execute("""
                        SELECT value FROM memories
                        WHERE key = ?
                        ORDER BY id DESC LIMIT 1
                    """, (clean_key,))
                row = cursor.fetchone()
                if row:
                    return row["value"]
                # Fallback check in user_profile
                return self.get_preference(key)
        except Exception as e:
            logger.error(f"Failed to recall '{key}': {e}")
            return None

    def search_memories(self, query: str) -> List[Dict[str, Any]]:
        """Searches across structured memories."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT category, key, value, timestamp FROM memories
                    WHERE key LIKE ? OR value LIKE ?
                    ORDER BY id DESC LIMIT 10
                """, (f"%{query}%", f"%{query}%"))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []

    # ==========================================
    # PROJECT REGISTRY
    # ==========================================
    def register_project(self, alias: str, name: str, path: str, framework: str = "", backend_port: Optional[int] = None, test_cmd: str = "") -> bool:
        """Registers or updates a persistent project configuration."""
        try:
            clean_alias = alias.lower().strip()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO projects (alias, name, path, framework, backend_port, test_cmd, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(alias) DO UPDATE SET
                        name = excluded.name,
                        path = excluded.path,
                        framework = excluded.framework,
                        backend_port = excluded.backend_port,
                        test_cmd = excluded.test_cmd,
                        updated_at = excluded.updated_at
                """, (clean_alias, name.strip(), str(path).strip(), framework.strip(), backend_port, test_cmd.strip(), time.time()))
                conn.commit()
            logger.info(f"Registered project in memory: {clean_alias} ({name}) -> {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to register project '{alias}': {e}")
            return False

    def get_project(self, alias_or_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves project details by alias or name."""
        clean = alias_or_name.lower().strip()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT alias, name, path, framework, backend_port, test_cmd, updated_at
                    FROM projects
                    WHERE alias = ? OR LOWER(name) = ?
                """, (clean, clean))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get project '{alias_or_name}': {e}")
            return None

    def list_projects(self) -> List[Dict[str, Any]]:
        """Lists all registered projects."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT alias, name, path, framework, backend_port, test_cmd, updated_at FROM projects ORDER BY name")
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list projects: {e}")
            return []

    def build_memory_context_prompt(self, query: str = "") -> str:
        """Constructs a context string containing relevant user profile facts and memories for LLM injection."""
        prefs = self.get_all_preferences()

        lines = ["[LONG-TERM MEMORY CONTEXT]"]
        if prefs:
            lines.append("User Profile & Preferences:")
            for k, v in prefs.items():
                lines.append(f" - {k.replace('_', ' ').capitalize()}: {v}")

        # Check for matching notes
        if query:
            matching_notes = self.search_notes(query)
            if matching_notes:
                lines.append("Relevant Knowledge Notes:")
                for n in matching_notes:
                    lines.append(f" - [{n['topic']}]: {n['content']}")

        if len(lines) == 1:
            return ""

        return "\n".join(lines)

    # ==========================================
    # STRUCTURED EXECUTION EXPERIENCES (PHASE 2)
    # ==========================================
    def record_execution_experience(
        self,
        user_request: str,
        normalized_intent: str,
        tool_or_procedure: str,
        execution_parameters: Dict[str, Any],
        execution_outcome: str,
        preconditions: Optional[Dict[str, Any]] = None,
        environment: Optional[Dict[str, Any]] = None,
        verification_evidence: Optional[Dict[str, Any]] = None,
        observed_failure: Optional[str] = None,
        user_corrections: Optional[str] = None,
        software_version: str = "2.0.0",
        confidence: float = 1.0,
        applicable_conditions: Optional[Dict[str, Any]] = None
    ) -> int:
        """Records a structured tool/procedure execution experience with verification evidence."""
        sanitized_params = json.dumps(self.sanitize_data(execution_parameters or {}))
        sanitized_preconditions = json.dumps(self.sanitize_data(preconditions or {}))
        sanitized_env = json.dumps(self.sanitize_data(environment or {}))
        sanitized_evidence = json.dumps(self.sanitize_data(verification_evidence or {}))
        sanitized_app_cond = json.dumps(self.sanitize_data(applicable_conditions or {}))
        sanitized_request = self.sanitize_text(user_request.strip())
        sanitized_failure = self.sanitize_text(observed_failure) if observed_failure else None
        sanitized_corrections = self.sanitize_text(user_corrections) if user_corrections else None

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO execution_experiences (
                        timestamp, user_request, normalized_intent, tool_or_procedure,
                        execution_parameters, preconditions, environment, execution_outcome,
                        verification_evidence, observed_failure, user_corrections,
                        software_version, confidence, applicable_conditions
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.time(), sanitized_request, normalized_intent.strip(), tool_or_procedure.strip(),
                    sanitized_params, sanitized_preconditions, sanitized_env, execution_outcome.strip(),
                    sanitized_evidence, sanitized_failure, sanitized_corrections,
                    software_version, confidence, sanitized_app_cond
                ))
                conn.commit()
                row_id = cursor.lastrowid
                logger.info(f"Recorded execution experience #{row_id}: [{normalized_intent}] {tool_or_procedure} -> {execution_outcome}")
                return row_id
        except Exception as e:
            logger.error(f"Failed to record execution experience: {e}")
            return -1

    def get_execution_experiences(
        self,
        limit: int = 20,
        intent: Optional[str] = None,
        outcome: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves past execution experiences with deserialized parameters and verification evidence."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM execution_experiences"
                params = []
                clauses = []
                if intent:
                    clauses.append("normalized_intent = ?")
                    params.append(intent.strip())
                if outcome:
                    clauses.append("execution_outcome = ?")
                    params.append(outcome.strip())
                if clauses:
                    query += " WHERE " + " AND ".join(clauses)
                query += " ORDER BY id DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    item = dict(r)
                    for field in ["execution_parameters", "preconditions", "environment", "verification_evidence", "applicable_conditions"]:
                        if item.get(field):
                            try:
                                item[field] = json.loads(item[field])
                            except Exception:
                                pass
                    results.append(item)
                return results
        except Exception as e:
            logger.error(f"Failed to query execution experiences: {e}")
            return []

    # ==========================================
    # VERIFIED LEARNED PROCEDURES (PHASE 3 & 6)
    # ==========================================
    def save_learned_procedure(
        self,
        procedure_name: str,
        intent: str,
        trigger_patterns: List[str],
        steps: List[Dict[str, Any]],
        prerequisites: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        source: str = "learned"
    ) -> bool:
        """Saves or updates a validated reusable procedure."""
        clean_name = procedure_name.strip()
        sanitized_triggers = json.dumps(self.sanitize_data(trigger_patterns or []))
        sanitized_steps = json.dumps(self.sanitize_data(steps or []))
        sanitized_prereqs = json.dumps(self.sanitize_data(prerequisites or {}))
        now = time.time()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO learned_procedures (
                        procedure_name, intent, trigger_patterns, steps, prerequisites,
                        confidence, source, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(procedure_name) DO UPDATE SET
                        intent = excluded.intent,
                        trigger_patterns = excluded.trigger_patterns,
                        steps = excluded.steps,
                        prerequisites = excluded.prerequisites,
                        confidence = excluded.confidence,
                        source = excluded.source,
                        is_active = 1,
                        updated_at = excluded.updated_at
                """, (clean_name, intent.strip(), sanitized_triggers, sanitized_steps, sanitized_prereqs, confidence, source, now, now))
                conn.commit()
                logger.info(f"Saved verified learned procedure: '{clean_name}' (intent={intent}, steps={len(steps)})")
                return True
        except Exception as e:
            logger.error(f"Failed to save learned procedure '{procedure_name}': {e}")
            return False

    def get_learned_procedure(self, procedure_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single learned procedure by name."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM learned_procedures WHERE procedure_name = ?", (procedure_name.strip(),))
                row = cursor.fetchone()
                if not row:
                    return None
                data = dict(row)
                data["trigger_patterns"] = json.loads(data["trigger_patterns"]) if data.get("trigger_patterns") else []
                data["steps"] = json.loads(data["steps"]) if data.get("steps") else []
                data["prerequisites"] = json.loads(data["prerequisites"]) if data.get("prerequisites") else {}
                return data
        except Exception as e:
            logger.error(f"Failed to get learned procedure '{procedure_name}': {e}")
            return None

    def list_learned_procedures(self, intent: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """Lists learned procedures matching intent and active state."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM learned_procedures"
                clauses = []
                params = []
                if active_only:
                    clauses.append("is_active = 1")
                if intent:
                    clauses.append("intent = ?")
                    params.append(intent.strip())
                if clauses:
                    query += " WHERE " + " AND ".join(clauses)
                query += " ORDER BY confidence DESC, success_count DESC"

                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    data = dict(r)
                    data["trigger_patterns"] = json.loads(data["trigger_patterns"]) if data.get("trigger_patterns") else []
                    data["steps"] = json.loads(data["steps"]) if data.get("steps") else []
                    data["prerequisites"] = json.loads(data["prerequisites"]) if data.get("prerequisites") else {}
                    results.append(data)
                return results
        except Exception as e:
            logger.error(f"Failed to list learned procedures: {e}")
            return []

    def update_procedure_reliability(self, procedure_name: str, success: bool, evidence: Optional[Dict[str, Any]] = None) -> bool:
        """Dynamically adjusts procedure confidence and reliability history based on real outcome."""
        proc = self.get_learned_procedure(procedure_name)
        if not proc:
            return False

        current_conf = float(proc.get("confidence", 1.0))
        success_count = int(proc.get("success_count", 0))
        failure_count = int(proc.get("failure_count", 0))
        now = time.time()

        if success:
            success_count += 1
            new_conf = min(1.0, current_conf + 0.05)
            is_active = 1
            last_verified = now
        else:
            failure_count += 1
            new_conf = max(0.0, current_conf - 0.25)
            is_active = 1 if new_conf >= 0.40 else 0
            last_verified = proc.get("last_verified_at")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE learned_procedures
                    SET success_count = ?, failure_count = ?, confidence = ?, is_active = ?, last_verified_at = ?, updated_at = ?
                    WHERE procedure_name = ?
                """, (success_count, failure_count, new_conf, is_active, last_verified, now, procedure_name))
                conn.commit()
                logger.info(f"Updated reliability for '{procedure_name}': success={success}, conf={current_conf:.2f}->{new_conf:.2f}, active={is_active}")
                return True
        except Exception as e:
            logger.error(f"Failed to update procedure reliability for '{procedure_name}': {e}")
            return False

    # ==========================================
    # USER LEARNED PREFERENCES & CORRECTIONS (PHASE 4)
    # ==========================================
    def set_user_learned_preference(
        self,
        preference_type: str,
        trigger_key: str,
        preferred_value: str,
        evidence_source: str = "user_correction",
        confidence: float = 1.0,
        scope: str = "persistent"
    ) -> bool:
        """Persists a learned user preference (app alias, folder mapping, tool preference)."""
        clean_type = preference_type.lower().strip()
        clean_key = trigger_key.lower().strip()
        clean_val = str(preferred_value).strip()
        now = time.time()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_learned_preferences (
                        preference_type, trigger_key, preferred_value, evidence_source,
                        confidence, scope, last_applied_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(preference_type, trigger_key) DO UPDATE SET
                        preferred_value = excluded.preferred_value,
                        evidence_source = excluded.evidence_source,
                        confidence = excluded.confidence,
                        scope = excluded.scope,
                        updated_at = excluded.updated_at
                """, (clean_type, clean_key, clean_val, evidence_source, confidence, scope, now, now, now))
                conn.commit()
                logger.info(f"Recorded learned preference: [{clean_type}] {clean_key} -> '{clean_val}' (source={evidence_source})")
                return True
        except Exception as e:
            logger.error(f"Failed to set user learned preference: {e}")
            return False

    def get_user_learned_preference(
        self,
        preference_type: str,
        trigger_key: str,
        default: Optional[str] = None
    ) -> Optional[str]:
        """Retrieves a learned preference by type and trigger key."""
        clean_type = preference_type.lower().strip()
        clean_key = trigger_key.lower().strip()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT preferred_value, confidence FROM user_learned_preferences
                    WHERE preference_type = ? AND trigger_key = ?
                """, (clean_type, clean_key))
                row = cursor.fetchone()
                if row and row["confidence"] >= 0.50:
                    return row["preferred_value"]
                return default
        except Exception as e:
            logger.error(f"Failed to get user learned preference: {e}")
            return default

    def get_all_learned_preferences(self, preference_type: Optional[str] = None) -> Dict[str, str]:
        """Retrieves all learned preferences, optionally filtered by type."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if preference_type:
                    cursor.execute("""
                        SELECT trigger_key, preferred_value FROM user_learned_preferences
                        WHERE preference_type = ? AND confidence >= 0.50
                    """, (preference_type.lower().strip(),))
                else:
                    cursor.execute("""
                        SELECT trigger_key, preferred_value FROM user_learned_preferences
                        WHERE confidence >= 0.50
                    """)
                rows = cursor.fetchall()
                return {r["trigger_key"]: r["preferred_value"] for r in rows}
        except Exception as e:
            logger.error(f"Failed to get all learned preferences: {e}")
            return {}

    def delete_user_learned_preference(self, preference_type: str, trigger_key: str) -> bool:
        """Deletes a learned preference."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM user_learned_preferences
                    WHERE preference_type = ? AND trigger_key = ?
                """, (preference_type.lower().strip(), trigger_key.lower().strip()))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to delete learned preference: {e}")
            return False

    # ==========================================
    # VERIFIED REASONING CACHE (PHASE 5)
    # ==========================================
    @staticmethod
    def _is_dynamic_query(clean_query: str) -> bool:
        """Determines if a query requires fresh information and must NEVER be served from static cache."""
        clean = clean_query.lower().strip()
        dynamic_markers = [
            "time", "clock", "date", "today", "tomorrow", "yesterday",
            "weather", "forecast", "temperature", "news", "headline",
            "battery", "power", "cpu", "memory", "ram", "disk", "gpu",
            "status", "process", "running", "active tab", "open tabs", "current"
        ]
        return any(re.search(rf"\b{re.escape(m)}\b", clean) for m in dynamic_markers)

    def get_cached_query(self, query: str) -> Optional[Dict[str, Any]]:
        """Retrieves a cached factual reasoning response if valid and not dynamic."""
        clean = query.lower().strip()
        if self._is_dynamic_query(clean):
            return None

        import hashlib
        q_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        now = time.time()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT cached_response, source_provider, confidence, expires_at, access_count
                    FROM verified_cache
                    WHERE query_hash = ?
                """, (q_hash,))
                row = cursor.fetchone()
                if not row:
                    return None

                expires_at = row["expires_at"]
                if expires_at and now > expires_at:
                    cursor.execute("DELETE FROM verified_cache WHERE query_hash = ?", (q_hash,))
                    conn.commit()
                    return None

                cursor.execute("""
                    UPDATE verified_cache
                    SET access_count = access_count + 1, last_accessed_at = ?
                    WHERE query_hash = ?
                """, (now, q_hash))
                conn.commit()

                return {
                    "text": row["cached_response"],
                    "source": f"{row['source_provider']} (Verified Cache)",
                    "confidence": row["confidence"],
                    "cached": True
                }
        except Exception as e:
            logger.error(f"Failed to get cached query: {e}")
            return None

    def set_cached_query(
        self,
        query: str,
        response: str,
        source_provider: str = "AI Provider",
        confidence: float = 1.0,
        ttl_seconds: Optional[float] = None
    ) -> bool:
        """Caches a verified reasoning response for a static factual query."""
        clean = query.lower().strip()
        if self._is_dynamic_query(clean):
            return False
        if not response or len(response.strip()) < 5:
            return False

        import hashlib
        q_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        now = time.time()
        expires_at = (now + ttl_seconds) if ttl_seconds else None
        sanitized_resp = self.sanitize_text(response.strip())

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO verified_cache (
                        query_hash, query_normalized, cached_response, source_provider,
                        confidence, is_dynamic, access_count, created_at, last_accessed_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?, ?)
                    ON CONFLICT(query_hash) DO UPDATE SET
                        cached_response = excluded.cached_response,
                        source_provider = excluded.source_provider,
                        confidence = excluded.confidence,
                        last_accessed_at = excluded.last_accessed_at,
                        expires_at = excluded.expires_at
                """, (q_hash, clean, sanitized_resp, source_provider, confidence, now, now, expires_at))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to cache query: {e}")
            return False

# Module-level aliases
sanitize_text = PersistentMemory.sanitize_text
sanitize_data = PersistentMemory.sanitize_data

# Global singleton
persistent_memory = PersistentMemory()

