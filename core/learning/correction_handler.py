"""User Correction Handler and Adaptive Preference Engine for JARVIS.
Extracts user intent from corrections (e.g. "Open Brave, not Chrome", "Use the docs folder, not downloads",
"This method failed, use the other supported method"), updates active task context, and persists verified
preferences so JARVIS learns continuously rather than repeating past mistakes.
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple

from memory.persistent_memory import persistent_memory

logger = logging.getLogger("Jarvis.CorrectionHandler")


class CorrectionHandler:
    """Parses corrections, extracts preference pairs, updates routing rules, and records persistent memory."""

    def __init__(self, memory_backend=None):
        self.memory = memory_backend or persistent_memory
        logger.info("CorrectionHandler initialized.")

    def handle_correction(
        self,
        correction_text: str,
        session_context: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyzes a correction utterance and extracts the revised instruction and learned preference."""
        ctx = context or session_context
        clean = correction_text.strip()
        cleaned = re.sub(r"^(?:no,?\s*(?:i meant|i said)?|actually,?\s*|correction:?\s*)", "", clean, flags=re.IGNORECASE).strip()

        # Pattern 1: "That is not the folder/file I meant. Use X"
        folder_match = re.search(
            r"(?:that is not|not)\s+(?:the\s+)?(folder|directory|file|path)\s+(?:i meant|wanted)\.?\s*(?:use|open)\s+(.+)$",
            cleaned,
            re.IGNORECASE
        )
        if folder_match:
            kind = folder_match.group(1).lower()
            target_path = folder_match.group(2).strip().strip("'\"")
            return self._apply_path_correction(kind, target_path, ctx)

        # Pattern 2: "This method failed. Use the other supported method / Use X instead"
        method_match = re.search(
            r"(?:this\s+method\s+failed|failed)\.?\s*(?:use\s+(?:the\s+other\s+supported\s+method|([a-zA-Z0-9_\-\s]+))(?:\s+instead)?)",
            cleaned,
            re.IGNORECASE
        )
        if method_match:
            alt_method = method_match.group(1) or "alternative"
            return self._apply_method_failure_correction(alt_method, ctx)

        # Pattern 3: "Instead of X, use Y"
        instead_match = re.search(
            r"instead\s+of\s+([a-zA-Z0-9_\-\.\s]+?)\s*,\s*(?:use|open|launch)?\s*([a-zA-Z0-9_\-\.\s]+)$",
            cleaned,
            re.IGNORECASE
        )
        if instead_match:
            rejected = instead_match.group(1).strip()
            preferred = instead_match.group(2).strip()
            return self._apply_contrast_correction(preferred, rejected, cleaned, ctx)

        # Pattern 4: Explicit Contrast ("Open Brave, not Chrome" / "Use Python, not C++" / "Docs folder, not downloads")
        contrast_match = re.search(
            r"^(?:(?:open|launch|run|use|start)\s+)?([a-zA-Z0-9_\-\.\s]+?)\s*,?\s*not\s+([a-zA-Z0-9_\-\.\s]+)$",
            cleaned,
            re.IGNORECASE
        )
        if contrast_match:
            preferred = contrast_match.group(1).strip()
            rejected = contrast_match.group(2).strip()
            return self._apply_contrast_correction(preferred, rejected, cleaned, ctx)

        # Fallback: simple directive ("use Brave instead", "Python version")
        mod_cleaned = re.sub(r"^(?:use\s+)?(.*?)(?:\s+instead)?$", r"\1", cleaned, flags=re.IGNORECASE).strip()
        mod_cleaned = re.sub(r"^(?:the\s+)?(.*?)(?:\s+version)?$", r"\1", mod_cleaned, flags=re.IGNORECASE).strip()

        return {
            "success": True,
            "revised_command": mod_cleaned or cleaned,
            "actionable_command": mod_cleaned or cleaned,
            "preferred_target": mod_cleaned,
            "intended": mod_cleaned,
            "rejected_target": None,
            "preference_type": "general",
            "scope": "task",
            "learned": False,
            "message": f"Applied correction: '{mod_cleaned}'."
        }

    # =========================================================================
    # CORRECTION SPECIALIZATIONS
    # =========================================================================

    def _apply_contrast_correction(
        self,
        preferred: str,
        rejected: str,
        raw_cleaned: str,
        session_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handles contrast corrections like 'Open Brave, not Chrome'."""
        clean_pref = preferred.lower().strip()
        clean_rej = rejected.lower().strip()

        # Identify entity domain (e.g. browsers, editors, applications)
        browsers = ["brave", "chrome", "firefox", "edge", "safari", "opera"]
        editors = ["vscode", "vs code", "pycharm", "notepad", "sublime", "vim"]

        pref_type = "app_alias"
        if clean_pref in browsers or clean_rej in browsers or "browser" in raw_cleaned.lower():
            pref_type = "browser_preference"
            # Persist default browser preference
            self.memory.set_user_learned_preference(
                preference_type="browser_preference",
                trigger_key="default_browser",
                preferred_value=clean_pref,
                evidence_source="user_correction",
                confidence=1.0,
                scope="persistent"
            )
            self.memory.set_preference("preferred_browser", clean_pref, category="applications")

        elif clean_pref in editors or clean_rej in editors or "editor" in raw_cleaned.lower():
            pref_type = "editor_preference"
            self.memory.set_user_learned_preference(
                preference_type="editor_preference",
                trigger_key="default_editor",
                preferred_value=clean_pref,
                evidence_source="user_correction",
                confidence=1.0,
                scope="persistent"
            )
            self.memory.set_preference("preferred_editor", clean_pref, category="applications")

        # Map rejected -> preferred as an application alias
        self.memory.set_user_learned_preference(
            preference_type="app_alias",
            trigger_key=clean_rej,
            preferred_value=clean_pref,
            evidence_source="user_correction",
            confidence=1.0,
            scope="persistent"
        )

        revised = f"open {clean_pref}"
        logger.info(f"[CORRECTION_LEARNED] Learned preference: '{clean_rej}' -> '{clean_pref}' (type={pref_type}). Revised: '{revised}'")

        return {
            "success": True,
            "revised_command": revised,
            "actionable_command": revised,
            "correction_type": "contrast_preference",
            "preferred_target": clean_pref,
            "intended": clean_pref,
            "rejected_target": clean_rej,
            "preference_type": pref_type,
            "scope": "persistent",
            "learned": True,
            "message": f"Understood. Opening {preferred} instead and noted your preference, Sir."
        }

    def _apply_path_correction(
        self,
        kind: str,
        target_path: str,
        session_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handles directory or file corrections like 'That is not the folder I meant. Use Projects'."""
        clean_path = target_path.strip()
        last_target = (session_context or {}).get("last_target", "folder")

        self.memory.set_user_learned_preference(
            preference_type="path_mapping",
            trigger_key=last_target.lower(),
            preferred_value=clean_path,
            evidence_source="user_correction",
            confidence=1.0,
            scope="persistent"
        )

        revised = f"open {kind} {clean_path}" if kind in ["folder", "directory", "file"] else f"open {clean_path}"
        logger.info(f"[CORRECTION_PATH] Updated path mapping for '{last_target}' -> '{clean_path}'. Revised: '{revised}'")

        return {
            "success": True,
            "revised_command": revised,
            "actionable_command": revised,
            "correction_type": "folder_correction",
            "preferred_target": clean_path,
            "intended": clean_path.lower(),
            "rejected_target": last_target,
            "preference_type": "path_mapping",
            "scope": "persistent",
            "learned": True,
            "message": f"Understood. Using {clean_path} as the target {kind}, Sir."
        }

    def _apply_method_failure_correction(
        self,
        alt_method: str,
        session_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handles procedure failure corrections like 'This method failed. Use the other supported method'."""
        last_action = (session_context or {}).get("last_procedure") or (session_context or {}).get("last_action", "previous_procedure")

        # Penalize confidence of last action
        procs = self.memory.list_learned_procedures()
        for p in procs:
            if p.get("procedure_name") == last_action or p.get("intent") == last_action:
                self.memory.update_procedure_reliability(
                    procedure_name=p["procedure_name"],
                    success=False,
                    evidence={"failure_reason": "user_reported_failure"}
                )

        revised = f"use {alt_method}" if alt_method != "alternative" else "use alternative method"
        return {
            "success": True,
            "revised_command": revised,
            "actionable_command": revised,
            "correction_type": "method_failure",
            "preferred_target": alt_method,
            "intended": alt_method,
            "rejected_target": last_action,
            "preference_type": "method_override",
            "scope": "persistent",
            "learned": True,
            "message": f"Recorded failure of previous method. Switching to {alt_method}, Sir."
        }


# Global singleton
correction_handler = CorrectionHandler()
