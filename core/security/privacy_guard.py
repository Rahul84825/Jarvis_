"""PrivacyGuard Security and Audit Subsystem for JARVIS.
Implements the 3-tier privacy mode architecture (STRICT, GUARDED, RELAXED),
17-pattern secret redaction, audit ledger recording, and output prompt-injection isolation.
Reference: https://jarvis.institute/guide/ and https://jarvis.institute/security/
"""

import os
import re
import json
import time
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger("Jarvis.PrivacyGuard")

class PrivacyMode:
    STRICT = "STRICT"    # 100% Local-first. Zero Cloud. Local models only.
    GUARDED = "GUARDED"  # Cloud allowed with auto-redaction & local audit trail. (Default / Recommended)
    RELAXED = "RELAXED"  # Direct cloud throughput without interception (Development only).

# 17-Pattern Redaction Suite for API Keys, Passwords, Tokens, and PII
REDACTION_PATTERNS = [
    # 1. OpenAI API Keys (sk-...)
    (r"\bsk-[a-zA-Z0-9_-]{12,}\b", "[REDACTED_OPENAI_KEY]"),
    # 2. Google AI / Gemini API Keys (AIza...)
    (r"\bAIza[0-9A-Za-z-_]{30,40}\b", "[REDACTED_GEMINI_KEY]"),
    # 3. GitHub Personal Access & Fine-Grained Tokens
    (r"\bgh[pousr]_[A-Za-z0-9_]{36,255}\b", "[REDACTED_GITHUB_TOKEN]"),
    # 4. Anthropic API Keys (sk-ant-...)
    (r"\bsk-ant-[a-zA-Z0-9_-]{20,}\b", "[REDACTED_ANTHROPIC_KEY]"),
    # 5. AWS Access Key IDs
    (r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED_AWS_KEY]"),
    # 6. Bearer Authorization Headers
    (r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{15,}\b", "Bearer [REDACTED_TOKEN]"),
    # 7. Generic API Keys in key-value form
    (r"(?i)(api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?", r"\1: [REDACTED_KEY]"),
    # 8. Passwords and Secrets in key-value form
    (r"(?i)(password|secret|passwd)\s*[:=]\s*['\"]?([^'\"\s]{6,})['\"]?", r"\1: [REDACTED_PASSWORD]"),
    # 9. Private RSA / OpenSSH / EC Keys
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
    # 10. JSON Web Tokens (JWT)
    (r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b", "[REDACTED_JWT]"),
    # 11. Database Connection Strings with Credentials
    (r"(?i)(?:postgres|mysql|mongodb|redis):\/\/[^:]+:[^@]+@[a-zA-Z0-9_\.\-]+(?::\d+)?\/[^\s\"']*", "[REDACTED_DATABASE_URI]"),
    # 12. Slack Bot & User Tokens
    (r"\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,32}\b", "[REDACTED_SLACK_TOKEN]"),
    # 13. Stripe Live Secret Keys
    (r"\bsk_live_[0-9a-zA-Z]{24,}\b", "[REDACTED_STRIPE_KEY]"),
    # 14. IPv4 with Credentials (e.g., user:pass@192.168.1.1)
    (r"(?i)[a-zA-Z0-9_]+:[^@\s]+@(?:\d{1,3}\.){3}\d{1,3}", "[REDACTED_HOST_CREDENTIALS]"),
    # 15. Credit Card Numbers (Major card patterns)
    (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[REDACTED_CREDIT_CARD]"),
    # 16. US Social Security Numbers
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
    # 17. Standard Email Addresses (PII protection)
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", "[REDACTED_EMAIL]"),
    # 18. NVIDIA API Keys (nvapi-...)
    (r"\bnvapi-[a-zA-Z0-9_-]{20,}\b", "[REDACTED_NVIDIA_KEY]")
]

# Injection Patterns for External Output Sanitization
PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
    r"(?i)system:\s*you\s+are\s+now",
    r"(?i)disregard\s+(?:all\s+)?prior\s+safety",
    r"(?i)you\s+must\s+now\s+act\s+as\s+an\s+unrestricted"
]


class PrivacyGuard:
    """Central Privacy Guard and Security Audit Manager."""

    def __init__(self, mode: Optional[str] = None, audit_db_path: Optional[str] = None):
        self.mode = mode or os.environ.get("JARVIS_PRIVACY_MODE", PrivacyMode.GUARDED).upper()
        if self.mode not in [PrivacyMode.STRICT, PrivacyMode.GUARDED, PrivacyMode.RELAXED]:
            self.mode = PrivacyMode.GUARDED

        base_dir = Path(__file__).parent.parent.parent
        self.audit_db_path = audit_db_path or str(base_dir / "logs" / "security_audit.db")
        self._init_audit_db()
        logger.info(f"PrivacyGuard initialized in [{self.mode}] mode.")

    def _init_audit_db(self):
        """Initializes SQLite security audit ledger."""
        conn = None
        try:
            Path(self.audit_db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.audit_db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    privacy_mode TEXT,
                    provider TEXT,
                    operation TEXT,
                    redacted_count INTEGER,
                    redacted_types TEXT,
                    prompt_length INTEGER,
                    status TEXT
                )
            """)
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize security audit DB: {e}")
        finally:
            if conn:
                conn.close()

    def set_mode(self, mode: str) -> bool:
        """Dynamically updates the active privacy mode."""
        m_up = mode.upper().strip()
        if m_up in [PrivacyMode.STRICT, PrivacyMode.GUARDED, PrivacyMode.RELAXED]:
            self.mode = m_up
            logger.info(f"[PRIVACY] Mode changed to [{self.mode}]")
            return True
        return False

    def get_mode(self) -> str:
        return self.mode

    def is_cloud_allowed(self) -> bool:
        """Returns True if outbound cloud requests are allowed under current policy."""
        return self.mode != PrivacyMode.STRICT

    def redact_text(self, text: str) -> Tuple[str, int, List[str]]:
        """Scans outgoing text and masks sensitive credentials using the 17-pattern suite.
        Returns: (sanitized_text, count_of_redactions, list_of_redacted_types)
        """
        if not text or not isinstance(text, str):
            return text, 0, []

        if self.mode == PrivacyMode.RELAXED:
            # RELAXED mode skips outbound interception
            return text, 0, []

        sanitized = text
        redacted_count = 0
        redacted_types = []

        for pattern, replacement in REDACTION_PATTERNS:
            matches = re.findall(pattern, sanitized)
            if matches:
                redacted_count += len(matches)
                redacted_types.append(replacement.strip("[]"))
                sanitized = re.sub(pattern, replacement, sanitized)

        return sanitized, redacted_count, redacted_types

    def record_audit(
        self,
        provider: str,
        operation: str,
        redacted_count: int,
        redacted_types: List[str],
        prompt_length: int,
        status: str = "PERMITTED"
    ):
        """Records an external call to the audit ledger."""
        conn = None
        try:
            conn = sqlite3.connect(self.audit_db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO security_audit 
                (timestamp, privacy_mode, provider, operation, redacted_count, redacted_types, prompt_length, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                time.time(),
                self.mode,
                provider,
                operation,
                redacted_count,
                json.dumps(redacted_types),
                prompt_length,
                status
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to record audit event: {e}")
        finally:
            if conn:
                conn.close()

    def sanitize_external_output(self, content: str) -> str:
        """Inspects and neutralizes prompt-injection attempts from external tool outputs or webpages."""
        if not content or not isinstance(content, str):
            return content

        sanitized = content
        for pat in PROMPT_INJECTION_PATTERNS:
            if re.search(pat, sanitized):
                logger.warning(f"[SECURITY] Potential prompt injection detected and neutralized in tool output.")
                sanitized = re.sub(pat, "[SUSPICIOUS_INSTRUCTION_BLOCKED]", sanitized)

        return sanitized

    def get_audit_summary(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns the most recent security audit records for inspection."""
        records = []
        conn = None
        try:
            conn = sqlite3.connect(self.audit_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, privacy_mode, provider, operation, redacted_count, redacted_types, prompt_length, status
                FROM security_audit
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            for row in cursor.fetchall():
                records.append(dict(row))
        except Exception as e:
            logger.error(f"Failed to query security audit records: {e}")
        finally:
            if conn:
                conn.close()
        return records


# Global Singleton Instance
privacy_guard = PrivacyGuard()
