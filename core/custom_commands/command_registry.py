"""SQLite-Backed Persistent Custom Command Registry for JARVIS.

Stores, validates, versions, and manages natural-language custom commands and workflows.
Provides additive schema migrations, conflict detection, alias management, and rollback.
"""

import time
import json
import uuid
import sqlite3
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger("Jarvis.CustomCommandRegistry")


@dataclass
class CustomCommand:
    """Persistent custom command definition."""
    command_id: str
    name: str
    trigger_phrases: List[str]
    workflow_definition: List[Dict[str, Any]]
    aliases: List[str] = field(default_factory=list)
    intent_description: str = ""
    required_arguments: List[str] = field(default_factory=list)
    risk_classification: str = "LOW"  # LOW, MEDIUM, HIGH
    enabled: bool = True
    validation_status: str = "VALID"  # VALID, INVALID, DRAFT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "name": self.name,
            "trigger_phrases": json.dumps(self.trigger_phrases),
            "aliases": json.dumps(self.aliases),
            "intent_description": self.intent_description,
            "workflow_definition": json.dumps(self.workflow_definition),
            "required_arguments": json.dumps(self.required_arguments),
            "risk_classification": self.risk_classification,
            "enabled": 1 if self.enabled else 0,
            "validation_status": self.validation_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "history": json.dumps(self.history)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CustomCommand":
        def _parse_json(val, default):
            if isinstance(val, (list, dict)):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    pass
            return default

        return cls(
            command_id=data["command_id"],
            name=data["name"],
            trigger_phrases=_parse_json(data.get("trigger_phrases"), []),
            aliases=_parse_json(data.get("aliases"), []),
            intent_description=data.get("intent_description", ""),
            workflow_definition=_parse_json(data.get("workflow_definition"), []),
            required_arguments=_parse_json(data.get("required_arguments"), []),
            risk_classification=data.get("risk_classification", "LOW"),
            enabled=bool(data.get("enabled", 1)),
            validation_status=data.get("validation_status", "VALID"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            version=int(data.get("version", 1)),
            history=_parse_json(data.get("history"), [])
        )


class CustomCommandRegistry:
    """SQLite-backed registry for persistent custom commands."""

    # Core built-in phrases that cannot be hijacked by custom commands
    PROTECTED_BUILTINS = [
        "search", "google", "youtube", "shutdown", "restart", "sleep", "lock",
        "volume up", "volume down", "mute", "unmute", "stop", "cancel", "help",
        "what can you do", "who are you", "what time", "today's date", "about",
        "calculate", "add command", "create command", "delete command",
        "list commands", "scan applications", "refresh applications"
    ]

    def __init__(self, db_path: Optional[str] = None):
        base_dir = Path(__file__).parent.parent.parent
        self.db_path = db_path or str(base_dir / "logs" / "custom_commands.db")
        self._commands: Dict[str, CustomCommand] = {}
        self._init_db()
        self._load_all()

    def _init_db(self):
        """Initializes database with additive schema migrations. Never drops or resets tables."""
        conn = None
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Base table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_commands (
                    command_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    trigger_phrases TEXT NOT NULL,
                    aliases TEXT NOT NULL,
                    intent_description TEXT,
                    workflow_definition TEXT NOT NULL,
                    required_arguments TEXT,
                    risk_classification TEXT DEFAULT 'LOW',
                    enabled INTEGER DEFAULT 1,
                    validation_status TEXT DEFAULT 'VALID',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    version INTEGER DEFAULT 1,
                    history TEXT
                )
            """)

            # Additive migration: check existing columns and add any missing
            cursor.execute("PRAGMA table_info(custom_commands)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            expected_cols = {
                "command_id": "TEXT PRIMARY KEY",
                "name": "TEXT NOT NULL",
                "trigger_phrases": "TEXT NOT NULL",
                "aliases": "TEXT NOT NULL",
                "intent_description": "TEXT",
                "workflow_definition": "TEXT NOT NULL",
                "required_arguments": "TEXT",
                "risk_classification": "TEXT DEFAULT 'LOW'",
                "enabled": "INTEGER DEFAULT 1",
                "validation_status": "TEXT DEFAULT 'VALID'",
                "created_at": "REAL NOT NULL",
                "updated_at": "REAL NOT NULL",
                "version": "INTEGER DEFAULT 1",
                "history": "TEXT"
            }

            for col_name, col_def in expected_cols.items():
                if col_name not in existing_cols and "PRIMARY KEY" not in col_def:
                    logger.info(f"Applying additive schema migration: adding column {col_name} to custom_commands.")
                    cursor.execute(f"ALTER TABLE custom_commands ADD COLUMN {col_name} {col_def}")

            conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize custom_commands.db: {e}")
        finally:
            if conn:
                conn.close()

    def _load_all(self):
        """Loads all custom commands from SQLite into in-memory cache."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM custom_commands")
            rows = cursor.fetchall()
            self._commands.clear()
            for r in rows:
                cmd = CustomCommand.from_dict(dict(r))
                self._commands[cmd.command_id] = cmd
            logger.info(f"CustomCommandRegistry loaded {len(self._commands)} custom commands.")
        except Exception as e:
            logger.error(f"Failed to load custom commands: {e}")
        finally:
            if conn:
                conn.close()

    def _persist_command(self, cmd: CustomCommand) -> bool:
        """Saves a command to SQLite."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            d = cmd.to_dict()
            cursor.execute("""
                INSERT INTO custom_commands 
                (command_id, name, trigger_phrases, aliases, intent_description,
                 workflow_definition, required_arguments, risk_classification,
                 enabled, validation_status, created_at, updated_at, version, history)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(command_id) DO UPDATE SET
                    name = excluded.name,
                    trigger_phrases = excluded.trigger_phrases,
                    aliases = excluded.aliases,
                    intent_description = excluded.intent_description,
                    workflow_definition = excluded.workflow_definition,
                    required_arguments = excluded.required_arguments,
                    risk_classification = excluded.risk_classification,
                    enabled = excluded.enabled,
                    validation_status = excluded.validation_status,
                    updated_at = excluded.updated_at,
                    version = excluded.version,
                    history = excluded.history
            """, (
                d["command_id"], d["name"], d["trigger_phrases"], d["aliases"],
                d["intent_description"], d["workflow_definition"], d["required_arguments"],
                d["risk_classification"], d["enabled"], d["validation_status"],
                d["created_at"], d["updated_at"], d["version"], d["history"]
            ))
            conn.commit()
            self._commands[cmd.command_id] = cmd
            return True
        except Exception as e:
            logger.error(f"Failed to persist command '{cmd.name}': {e}")
            return False
        finally:
            if conn:
                conn.close()

    # =========================================================================
    # CONFLICT AND SAFETY CHECKS
    # =========================================================================

    def detect_conflicts(self, triggers: List[str], exclude_command_id: Optional[str] = None) -> List[str]:
        """Detects whether proposed triggers conflict with built-in commands or existing custom commands."""
        conflicts = []
        for phrase in triggers:
            clean = phrase.lower().strip()
            # 1. Check protected built-ins
            for builtin in self.PROTECTED_BUILTINS:
                if clean == builtin:
                    conflicts.append(f"Conflicts with protected built-in command '{builtin}'")
                    break

            # 2. Check existing active custom commands
            for cmd_id, cmd in self._commands.items():
                if exclude_command_id and cmd_id == exclude_command_id:
                    continue
                all_phrases = [p.lower().strip() for p in (cmd.trigger_phrases + cmd.aliases)]
                if clean in all_phrases:
                    conflicts.append(f"Trigger '{clean}' is already used by custom command '{cmd.name}'")
                    break
        return conflicts

    # =========================================================================
    # CRUD OPERATIONS
    # =========================================================================

    def register_command(
        self,
        name: str,
        trigger_phrases: List[str],
        workflow_definition: List[Dict[str, Any]],
        aliases: Optional[List[str]] = None,
        intent_description: str = "",
        required_arguments: Optional[List[str]] = None,
        risk_classification: str = "LOW",
        enabled: bool = True,
        command_id: Optional[str] = None
    ) -> Tuple[bool, str, Optional[CustomCommand]]:
        """Validates and registers a new custom command."""
        # Clean triggers
        clean_triggers = [t.strip().lower() for t in trigger_phrases if t and t.strip()]
        if not clean_triggers:
            return False, "At least one valid trigger phrase is required.", None

        clean_aliases = [a.strip().lower() for a in (aliases or []) if a and a.strip()]

        # Check conflicts
        conflicts = self.detect_conflicts(clean_triggers + clean_aliases, exclude_command_id=command_id)
        if conflicts:
            return False, f"Trigger conflict: {'; '.join(conflicts)}", None

        # Generate stable ID if not provided
        cid = command_id or f"cmd_{uuid.uuid4().hex[:8]}"

        cmd = CustomCommand(
            command_id=cid,
            name=name.strip(),
            trigger_phrases=clean_triggers,
            aliases=clean_aliases,
            intent_description=intent_description.strip(),
            workflow_definition=workflow_definition,
            required_arguments=required_arguments or [],
            risk_classification=risk_classification,
            enabled=enabled,
            validation_status="VALID",
            created_at=time.time(),
            updated_at=time.time(),
            version=1,
            history=[]
        )

        ok = self._persist_command(cmd)
        if ok:
            return True, f"Command '{cmd.name}' created successfully.", cmd
        return False, "Failed to save command to database.", None

    def get_command(self, command_id: str) -> Optional[CustomCommand]:
        """Retrieves command by stable command_id."""
        return self._commands.get(command_id)

    def get_command_by_name(self, name: str) -> Optional[CustomCommand]:
        """Retrieves command by human-readable name."""
        clean = name.lower().strip()
        for cmd in self._commands.values():
            if cmd.name.lower() == clean:
                return cmd
        return None

    def list_commands(self, enabled_only: bool = False) -> List[CustomCommand]:
        """Returns all registered custom commands."""
        if enabled_only:
            return [c for c in self._commands.values() if c.enabled]
        return list(self._commands.values())

    def search_commands(self, query: str) -> List[CustomCommand]:
        """Searches commands by name, intent description, or trigger phrases."""
        clean = query.lower().strip()
        results = []
        for cmd in self._commands.values():
            if (clean in cmd.name.lower()) or (clean in cmd.intent_description.lower()):
                results.append(cmd)
            elif any(clean in t.lower() for t in cmd.trigger_phrases + cmd.aliases):
                results.append(cmd)
        return results

    def update_command(self, command_id: str, updates: Dict[str, Any]) -> Tuple[bool, str, Optional[CustomCommand]]:
        """Updates an existing command and saves the prior version snapshot in history for rollback."""
        cmd = self.get_command(command_id)
        if not cmd:
            return False, f"Command '{command_id}' not found.", None

        # Check trigger conflicts if triggers or aliases are being updated
        if "trigger_phrases" in updates or "aliases" in updates:
            new_triggers = updates.get("trigger_phrases", cmd.trigger_phrases)
            new_aliases = updates.get("aliases", cmd.aliases)
            conflicts = self.detect_conflicts(new_triggers + new_aliases, exclude_command_id=command_id)
            if conflicts:
                return False, f"Conflict in updated triggers: {'; '.join(conflicts)}", None

        # Save snapshot into history
        snapshot = {
            "version": cmd.version,
            "name": cmd.name,
            "trigger_phrases": list(cmd.trigger_phrases),
            "aliases": list(cmd.aliases),
            "intent_description": cmd.intent_description,
            "workflow_definition": list(cmd.workflow_definition),
            "risk_classification": cmd.risk_classification,
            "enabled": cmd.enabled,
            "updated_at": cmd.updated_at
        }
        cmd.history.append(snapshot)

        # Apply updates
        for k, v in updates.items():
            if hasattr(cmd, k) and k not in ["command_id", "created_at", "history", "version"]:
                setattr(cmd, k, v)

        cmd.version += 1
        cmd.updated_at = time.time()

        ok = self._persist_command(cmd)
        if ok:
            return True, f"Command '{cmd.name}' updated to version {cmd.version}.", cmd
        return False, "Failed to persist updated command.", None

    def rollback_command(self, command_id: str) -> Tuple[bool, str, Optional[CustomCommand]]:
        """Rolls back the command to its previous version using saved history snapshots."""
        cmd = self.get_command(command_id)
        if not cmd:
            return False, f"Command '{command_id}' not found.", None

        if not cmd.history:
            return False, f"No previous version available for command '{cmd.name}'.", None

        # Pop previous snapshot
        prev = cmd.history.pop()
        cmd.name = prev.get("name", cmd.name)
        cmd.trigger_phrases = prev.get("trigger_phrases", cmd.trigger_phrases)
        cmd.aliases = prev.get("aliases", cmd.aliases)
        cmd.intent_description = prev.get("intent_description", cmd.intent_description)
        cmd.workflow_definition = prev.get("workflow_definition", cmd.workflow_definition)
        cmd.risk_classification = prev.get("risk_classification", cmd.risk_classification)
        cmd.enabled = prev.get("enabled", cmd.enabled)
        cmd.version += 1  # Additive versioning reflecting rollback action
        cmd.updated_at = time.time()

        ok = self._persist_command(cmd)
        if ok:
            return True, f"Command '{cmd.name}' rolled back successfully.", cmd
        return False, "Failed to persist rolled back command.", None

    def delete_command(self, command_id: str) -> Tuple[bool, str]:
        """Deletes custom command definition from SQLite. Never deletes application or user files."""
        cmd = self.get_command(command_id)
        if not cmd:
            return False, f"Command '{command_id}' not found."

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM custom_commands WHERE command_id = ?", (command_id,))
            conn.commit()
            name = cmd.name
            del self._commands[command_id]
            logger.info(f"Custom command '{name}' ({command_id}) deleted.")
            return True, f"Command '{name}' has been deleted."
        except Exception as e:
            logger.error(f"Failed to delete command {command_id}: {e}")
            return False, f"Database error deleting command: {e}"
        finally:
            if conn:
                conn.close()

    def enable_command(self, command_id: str) -> Tuple[bool, str]:
        """Enables a disabled command."""
        cmd = self.get_command(command_id)
        if not cmd:
            return False, f"Command '{command_id}' not found."
        cmd.enabled = True
        cmd.updated_at = time.time()
        ok = self._persist_command(cmd)
        return (True, f"Command '{cmd.name}' is now enabled.") if ok else (False, "Failed to update command.")

    def disable_command(self, command_id: str) -> Tuple[bool, str]:
        """Disables a command without deleting it."""
        cmd = self.get_command(command_id)
        if not cmd:
            return False, f"Command '{command_id}' not found."
        cmd.enabled = False
        cmd.updated_at = time.time()
        ok = self._persist_command(cmd)
        return (True, f"Command '{cmd.name}' is now disabled.") if ok else (False, "Failed to update command.")

    def add_alias(self, command_id: str, alias: str) -> Tuple[bool, str]:
        """Adds an alias to a command."""
        cmd = self.get_command(command_id)
        if not cmd:
            return False, f"Command '{command_id}' not found."
        clean_alias = alias.strip().lower()
        if not clean_alias:
            return False, "Alias cannot be empty."

        conflicts = self.detect_conflicts([clean_alias], exclude_command_id=command_id)
        if conflicts:
            return False, f"Conflict: {'; '.join(conflicts)}"

        if clean_alias not in cmd.aliases:
            aliases = list(cmd.aliases) + [clean_alias]
            return self.update_command(command_id, {"aliases": aliases})[:2]
        return True, f"Alias '{clean_alias}' already exists on command '{cmd.name}'."

    def remove_alias(self, command_id: str, alias: str) -> Tuple[bool, str]:
        """Removes an alias from a command."""
        cmd = self.get_command(command_id)
        if not cmd:
            return False, f"Command '{command_id}' not found."
        clean_alias = alias.strip().lower()
        if clean_alias in cmd.aliases:
            aliases = [a for a in cmd.aliases if a != clean_alias]
            return self.update_command(command_id, {"aliases": aliases})[:2]
        return False, f"Alias '{clean_alias}' was not found on command '{cmd.name}'."

    # =========================================================================
    # INTENT MATCHING
    # =========================================================================

    def find_matching_command(self, phrase: str) -> Tuple[Optional[CustomCommand], float]:
        """Matches input text against enabled custom commands.

        Exact trigger/alias matches return 1.0 confidence.
        Normalized matches return 0.95 confidence.
        Returns (command, confidence) if confidence >= 0.85, else (None, 0.0).
        """
        if not phrase or not phrase.strip():
            return None, 0.0

        clean = phrase.lower().strip()

        # 1. Exact match against trigger phrases and aliases
        for cmd in self._commands.values():
            if not cmd.enabled or cmd.validation_status != "VALID":
                continue
            for trigger in cmd.trigger_phrases:
                if clean == trigger.lower().strip():
                    return cmd, 1.0
            for alias in cmd.aliases:
                if clean == alias.lower().strip():
                    return cmd, 1.0

        # 2. Check stripping of speech filler ("jarvis", "please", etc.)
        for cmd in self._commands.values():
            if not cmd.enabled or cmd.validation_status != "VALID":
                continue
            for trigger in cmd.trigger_phrases + cmd.aliases:
                t_clean = trigger.lower().strip()
                if clean.endswith(t_clean) or t_clean.endswith(clean):
                    if len(clean) >= 4 and len(t_clean) >= 4:
                        return cmd, 0.90

        return None, 0.0


# Global singleton instance
custom_command_registry = CustomCommandRegistry()
