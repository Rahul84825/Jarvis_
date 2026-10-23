"""Procedure Learner and Reusable Execution Engine for JARVIS.
Stores, retrieves, validates prerequisites for, and executes verified multi-step procedures.
Reduces unnecessary external LLM calls by reusing proven deterministic tool sequences.
"""

import os
import re
import time
import logging
import platform
from typing import Dict, List, Any, Optional, Tuple

from memory.persistent_memory import persistent_memory
from core.learning.verification_engine import verification_engine, OutcomeLevel
from core.tool_registry import tool_registry

logger = logging.getLogger("Jarvis.ProcedureLearner")


class ProcedureLearner:
    """Manages the lifecycle of learned procedures: extraction, prerequisite checks,
    deterministic tool execution, confidence updates, and staleness invalidation.
    """

    CONFIDENCE_THRESHOLD = 0.70
    STALENESS_SECONDS = 30 * 86400  # 30 days

    def __init__(self, executor=None, memory_backend=None):
        self.executor = executor
        self.memory = memory_backend or persistent_memory
        logger.info("ProcedureLearner initialized.")

    def set_executor(self, executor):
        self.executor = executor

    # =========================================================================
    # LEARNING PROCEDURES
    # =========================================================================

    def learn_procedure(
        self,
        name: str,
        intent: str,
        user_request: str,
        steps: List[Dict[str, Any]],
        prerequisites: Optional[Dict[str, Any]] = None,
        source: str = "learned"
    ) -> bool:
        """Saves a verified sequence of tool steps as a reusable procedure."""
        if not steps:
            logger.warning("Refusing to learn empty procedure.")
            return False

        # Build trigger patterns from user request and name
        clean_req = user_request.lower().strip()
        clean_name = name.lower().strip().replace(" ", "_")

        trigger_patterns = [
            clean_req,
            clean_name.replace("_", " ")
        ]

        # Extract core command phrase if prefixed with polite phrasing
        phrase = re.sub(r"^(?:please\s+|jarvis\s+|could you\s+|can you\s+)", "", clean_req).strip()
        if phrase and phrase not in trigger_patterns:
            trigger_patterns.append(phrase)

        # Infer prerequisites if not supplied
        prereqs = dict(prerequisites or {})
        if "os" not in prereqs:
            prereqs["os"] = platform.system().lower()

        required_apps = set(prereqs.get("required_apps", []))
        for s in steps:
            tool = s.get("tool") or s.get("tool_name")
            args = s.get("args") or s.get("execution_parameters") or {}
            target = args.get("target") or args.get("application") or ""
            if tool in ["open_app", "application.launch", "open_application"] and target:
                required_apps.add(target.lower())
        if required_apps:
            prereqs["required_apps"] = sorted(list(required_apps))

        success = self.memory.save_learned_procedure(
            procedure_name=clean_name,
            intent=intent,
            trigger_patterns=trigger_patterns,
            steps=steps,
            prerequisites=prereqs,
            confidence=1.0,
            source=source
        )
        return success

    # =========================================================================
    # MATCHING & PREREQUISITE VALIDATION
    # =========================================================================

    def match_procedure(
        self,
        query: str,
        intent: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Finds the best-matching active procedure whose prerequisites currently hold on the operating system."""
        clean = query.lower().strip()
        norm_query = re.sub(r"[^\w\s]", "", clean)

        candidates = self.memory.list_learned_procedures(intent=None, active_only=True)
        if not candidates:
            return None

        matched_candidates = []

        for proc in candidates:
            # Check confidence threshold
            conf = float(proc.get("confidence", 1.0))
            if conf < self.CONFIDENCE_THRESHOLD:
                continue

            patterns = proc.get("trigger_patterns", [])
            matches = False
            for p in patterns:
                p_clean = p.lower().strip()
                p_norm = re.sub(r"[^\w\s]", "", p_clean)
                if p_clean == clean or p_norm == norm_query or p_clean in clean or clean in p_clean:
                    matches = True
                    break
                # Try regex matching safely
                try:
                    if re.search(rf"\b{re.escape(p_clean)}\b", clean):
                        matches = True
                        break
                except Exception:
                    pass

            if not matches and intent and proc.get("intent") == intent:
                matches = True

            if matches:
                # Validate Prerequisites against Real-World OS State
                prereqs = proc.get("prerequisites", {})
                valid, reason = self.validate_prerequisites(prereqs)
                if valid:
                    matched_candidates.append((conf, proc.get("last_verified_at", 0), proc))
                else:
                    logger.info(f"[PROCEDURE_PREREQ_FAIL] Candidate '{proc['procedure_name']}' rejected: {reason}")

        if not matched_candidates:
            return None

        # Sort by confidence descending, then recency descending
        matched_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        chosen = matched_candidates[0][2]
        chosen["name"] = chosen.get("procedure_name")
        logger.info(f"[PROCEDURE_MATCH] Selected procedure '{chosen['procedure_name']}' (conf={chosen['confidence']:.2f}) for query '{query}'")
        return chosen

    def validate_prerequisites(self, prereqs: Dict[str, Any]) -> Tuple[bool, str]:
        """Checks whether operating system conditions (installed apps, OS type, paths) still hold."""
        if not prereqs:
            return True, "No prerequisites"

        current_os = platform.system().lower()
        required_os = prereqs.get("os")
        if required_os and required_os.lower() != current_os:
            return False, f"OS mismatch: required {required_os}, current {current_os}"

        # Check required files or directories
        required_paths = prereqs.get("required_paths", [])
        for p in required_paths:
            resolved = os.path.expanduser(str(p))
            if not os.path.exists(resolved):
                return False, f"Required path '{p}' does not exist on disk."

        # Check required applications
        required_apps = prereqs.get("required_apps", [])
        if required_apps:
            from core.apps.application_discovery import application_discovery
            installed_apps = application_discovery.get_installed_applications()
            for app in required_apps:
                app_clean = app.lower().strip()
                # Check installed applications registry
                found = any(app_clean in k.lower() or app_clean in (v.get("name") or "").lower() for k, v in installed_apps.items())
                # Fallback to PATH probe
                if not found:
                    import shutil
                    found = bool(shutil.which(app_clean) or shutil.which(f"{app_clean}.exe"))
                if not found:
                    return False, f"Required application '{app}' is not installed on this system."

        return True, "All prerequisites valid"

    # =========================================================================
    # PROCEDURE EXECUTION
    # =========================================================================

    def execute_procedure(
        self,
        procedure: Dict[str, Any],
        executor=None
    ) -> Dict[str, Any]:
        """Executes a learned procedure deterministically through ToolRegistry and CommandExecutor."""
        exec_engine = executor or self.executor
        if not exec_engine:
            from modules.system.executor import CommandExecutor
            exec_engine = CommandExecutor()

        proc_name = procedure.get("procedure_name", "unknown")
        steps = procedure.get("steps", [])
        logger.info(f"[PROCEDURE_EXECUTE] Executing learned procedure '{proc_name}' ({len(steps)} steps)...")

        executed_steps = []
        overall_success = True
        failed_reason = None

        for idx, step in enumerate(steps):
            tool_name = step.get("tool") or step.get("tool_name")
            args = step.get("args") or step.get("execution_parameters") or {}
            target = args.get("target") or args.get("application") or args.get("path") or ""

            # Check ToolRegistry authorization & risk
            tool_def = tool_registry.get_tool(tool_name)
            if tool_def and tool_def.risk_level == "HIGH":
                logger.warning(f"[PROCEDURE_SAFETY] Step {idx+1} '{tool_name}' requires explicit security authorization.")
                # High risk steps in procedures must not silently bypass permission
                return {
                    "success": False,
                    "action": tool_name,
                    "message": f"Procedure '{proc_name}' contains high-risk step '{tool_name}' requiring authorization.",
                    "pending_confirmation": True
                }

            logger.info(f"[PROCEDURE_STEP] Step {idx+1}/{len(steps)}: Running '{tool_name}' with {args}")
            intent_node = {
                "intent": tool_name,
                "action": tool_name,
                "target": target,
                **args
            }

            try:
                res = exec_engine.execute(intent_node, confirm=False)
                # Verify step outcome independently
                verif = verification_engine.verify_action_outcome(tool_name, args, res)
                executed_steps.append({
                    "step": idx + 1,
                    "tool": tool_name,
                    "result": res,
                    "outcome": verif.get("outcome"),
                    "verified": verif.get("verified")
                })

                if not res.get("success") or verif.get("outcome") == OutcomeLevel.FAILED.value:
                    overall_success = False
                    failed_reason = res.get("message") or verif.get("failure_reason") or f"Step {idx+1} failed verification."
                    logger.warning(f"[PROCEDURE_STEP_FAILED] Step {idx+1} failed: {failed_reason}")
                    break

            except Exception as e:
                overall_success = False
                failed_reason = str(e)
                logger.error(f"[PROCEDURE_STEP_EXCEPTION] Step {idx+1} threw exception: {e}")
                break

        # Update reliability history
        self.memory.update_procedure_reliability(
            procedure_name=proc_name,
            success=overall_success,
            evidence={"executed_steps": len(executed_steps), "total_steps": len(steps)}
        )

        if overall_success:
            msg = f"Procedure '{proc_name.replace('_', ' ')}' executed successfully ({len(executed_steps)} actions verified)."
            return {
                "success": True,
                "action": "learned_procedure",
                "message": msg,
                "procedure_name": proc_name,
                "steps_completed": len(executed_steps),
                "source": "Verified Learned Procedure"
            }
        else:
            msg = f"Procedure '{proc_name.replace('_', ' ')}' encountered a failure: {failed_reason}"
            return {
                "success": False,
                "action": "learned_procedure",
                "message": msg,
                "procedure_name": proc_name,
                "steps_completed": len(executed_steps),
                "failure_reason": failed_reason
            }


# Global singleton
procedure_learner = ProcedureLearner()
