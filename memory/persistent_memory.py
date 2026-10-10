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

    def _init_db(self):
        """Initializes database schema if not present."""
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

# Global singleton
persistent_memory = PersistentMemory()
