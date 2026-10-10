"""Multi-Step Execution Planner and Dependency Resolver for JARVIS.
Decomposes complex requests, constructs ordered execution plans, resolves dependencies,
verifies step outcomes, supports failure recovery, and generates truthful execution reports.
"""

import time
import logging
from typing import List, Dict, Any, Optional
from core.multi_command_parser import multi_command_parser
from core.command_normalizer import CommandNormalizer

logger = logging.getLogger("Jarvis.MultiStepPlanner")

class MultiStepPlanner:
    """Plans and executes multi-step sequential actions with dependency tracking and verification."""

    def __init__(self, intent_engine=None, executor=None):
        if intent_engine is None:
            try:
                from core.intent_engine import IntentEngine
                self.intent_engine = IntentEngine()
            except Exception:
                self.intent_engine = None
        else:
            self.intent_engine = intent_engine
        self.executor = executor
        self.normalizer = CommandNormalizer()
        logger.info("MultiStepPlanner initialized.")

    def set_dependencies(self, intent_engine, executor):
        self.intent_engine = intent_engine
        self.executor = executor

    def plan(self, text: str) -> List[Dict[str, Any]]:
        """Decomposes complex chained speech into an ordered plan of structured intent nodes."""
        if not text or not isinstance(text, str):
            return []

        raw_clauses = multi_command_parser.parse(text)
        if not raw_clauses:
            raw_clauses = [text]

        # Bound maximum steps to prevent runaway loops
        raw_clauses = raw_clauses[:10]

        is_explicit_parallel = any(p in text.lower() for p in ["simultaneously", "in parallel", "concurrently"])

        plan_steps = []
        seen_targets = set()
        step_idx = 0

        for clause in raw_clauses:
            norm_res = self.normalizer.normalize(clause)
            clean_clause = norm_res["normalized"] or clause

            # Deduplicate adjacent identical actions (e.g. duplicate "open chrome")
            dedup_key = clean_clause.lower().strip()
            if dedup_key in seen_targets and any(clean_clause.startswith(w) for w in ["open ", "start "]):
                logger.info(f"[PLANNER] Deduplicated redundant repeated action: '{clean_clause}'")
                continue
            seen_targets.add(dedup_key)

            # Parse intent node
            if self.intent_engine:
                node = self.intent_engine.parse(clean_clause, raw_text=clause)
            else:
                node = {"intent": "unknown", "action": None, "target": clean_clause, "query": clean_clause}

            # Infer dependency: if this step operates on output of prior step
            depends_on = None
            if step_idx > 0:
                clause_lower = clean_clause.lower()
                if any(w in clause_lower for w in ["there", "it", "that", "the file", "inside it", "then"]):
                    depends_on = step_idx - 1

            step = {
                "step_index": step_idx,
                "raw_text": clause,
                "clean_text": clean_clause,
                "intent_node": node,
                "depends_on": depends_on,
                "parallel": is_explicit_parallel and (depends_on is None),
                "required": True,
                "status": "PENDING"
            }
            plan_steps.append(step)
            step_idx += 1

        logger.info(f"[PLANNER] Created plan with {len(plan_steps)} steps (Parallel={is_explicit_parallel}) for: '{text}'")
        return plan_steps

    def execute_plan(self, plan_steps: List[Dict[str, Any]], stop_on_failure: bool = False) -> Dict[str, Any]:
        """Executes plan steps with Think-Act-Observe execution loop and parallel dispatch support."""
        if not plan_steps:
            return {"success": False, "message": "No steps in plan to execute.", "steps": []}

        executed_steps = []
        failed_indices = set()
        last_step_output = None
        overall_success = True

        # Check if all steps can execute in parallel
        all_parallel = len(plan_steps) > 1 and all(s.get("parallel", False) for s in plan_steps)
        if all_parallel:
            logger.info(f"[PLANNER] Executing {len(plan_steps)} independent steps in parallel...")
            from concurrent.futures import ThreadPoolExecutor
            def _exec_single(s):
                t0 = time.time()
                res = self.executor.execute(s["intent_node"]) if self.executor else {"success": True, "message": "Simulated."}
                lat = (time.time() - t0) * 1000
                return {
                    "step_index": s["step_index"],
                    "command": s["clean_text"],
                    "status": "COMPLETED" if res.get("success", False) else "FAILED",
                    "success": bool(res.get("success", False)),
                    "message": res.get("message", ""),
                    "latency_ms": lat
                }

            with ThreadPoolExecutor(max_workers=min(len(plan_steps), 5)) as pool:
                executed_steps = list(pool.map(_exec_single, plan_steps))

            completed_count = sum(1 for s in executed_steps if s["status"] == "COMPLETED")
            failed_count = sum(1 for s in executed_steps if s["status"] == "FAILED")
            summary_msg = f"Simultaneously executed {len(executed_steps)} actions ({completed_count} succeeded, {failed_count} failed)."
            return {
                "success": failed_count == 0,
                "completed_count": completed_count,
                "failed_count": failed_count,
                "skipped_count": 0,
                "total_steps": len(plan_steps),
                "summary": summary_msg,
                "steps": executed_steps
            }

        # Sequential Think-Act-Observe Execution Loop
        for step in plan_steps:
            idx = step["step_index"]
            dep = step.get("depends_on")

            # Check dependency failure
            if dep is not None and dep in failed_indices:
                logger.warning(f"[PLANNER] Step {idx} ('{step['clean_text']}') SKIPPED due to prior failure in step {dep}.")
                step_record = {
                    "step_index": idx,
                    "command": step["clean_text"],
                    "status": "SKIPPED",
                    "success": False,
                    "message": f"Skipped because required step {dep+1} failed.",
                    "latency_ms": 0.0
                }
                executed_steps.append(step_record)
                failed_indices.add(idx)
                overall_success = False
                continue

            # Feed observation from previous step into dependent intent node if applicable
            intent_node = step["intent_node"]
            if dep is not None and last_step_output:
                if intent_node.get("target") in ["it", "there", "the file"] or not intent_node.get("target"):
                    intent_node["target"] = last_step_output

            # Execute step
            t0 = time.time()
            logger.info(f"[PLANNER] Executing Step {idx+1}/{len(plan_steps)}: '{step['clean_text']}'")

            if self.executor:
                try:
                    res = self.executor.execute(intent_node)
                    success = bool(res.get("success", False))
                    msg = res.get("message", "Executed.")
                    last_step_output = getattr(self.executor, "last_created_file", None) or res.get("target")
                except Exception as e:
                    logger.error(f"[PLANNER] Step {idx+1} execution raised exception: {e}")
                    success = False
                    msg = f"Step failed with error: {e}"
            else:
                success = True
                msg = f"Simulated execution of: {step['clean_text']}"

            latency_ms = (time.time() - t0) * 1000

            step_record = {
                "step_index": idx,
                "command": step["clean_text"],
                "status": "COMPLETED" if success else "FAILED",
                "success": success,
                "message": msg,
                "latency_ms": latency_ms
            }
            executed_steps.append(step_record)

            if not success:
                failed_indices.add(idx)
                overall_success = False
                logger.warning(f"[PLANNER] Step {idx+1} FAILED: {msg}")
                if stop_on_failure and step.get("required", True):
                    logger.info("[PLANNER] Halting plan execution due to stop_on_failure policy.")
                    break

        # Generate truthful composite summary
        completed_count = sum(1 for s in executed_steps if s["status"] == "COMPLETED")
        failed_count = sum(1 for s in executed_steps if s["status"] == "FAILED")
        skipped_count = sum(1 for s in executed_steps if s["status"] == "SKIPPED")

        summary_msg = self._generate_truthful_summary(executed_steps, completed_count, failed_count, skipped_count)

        logger.info(f"[PLANNER] Execution finished: {completed_count} completed, {failed_count} failed, {skipped_count} skipped.")
        return {
            "success": overall_success and (failed_count == 0),
            "completed_count": completed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "total_steps": len(plan_steps),
            "steps": executed_steps,
            "message": summary_msg,
            "spoken_text": summary_msg
        }

    def _generate_truthful_summary(self, steps: List[Dict[str, Any]], completed: int, failed: int, skipped: int) -> str:
        """Produces accurate natural language description of what succeeded and what failed."""
        if failed == 0 and skipped == 0:
            actions = [s["message"].replace("Sure, ", "").replace("Done. ", "").rstrip(".") for s in steps if s["message"]]
            if len(actions) == 1:
                return actions[0] + "."
            return "Done. " + ", and ".join(actions) + "."

        parts = []
        if completed > 0:
            parts.append(f"Completed {completed} action{'s' if completed != 1 else ''}")
        if failed > 0:
            failed_msgs = [s["message"].rstrip(".") for s in steps if s["status"] == "FAILED"]
            parts.append(f"encountered {failed} failure{'s' if failed != 1 else ''} ({'; '.join(failed_msgs)})")
        if skipped > 0:
            parts.append(f"skipped {skipped} dependent action{'s' if skipped != 1 else ''}")

        return "I completed some actions with warnings: " + ", but ".join(parts) + "."

# Global singleton
multi_step_planner = MultiStepPlanner()
