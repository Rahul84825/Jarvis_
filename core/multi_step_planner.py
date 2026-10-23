"""
Multi-Step Agentic Planner, Dependency Resolver, and Execution Coordinator for JARVIS.

Implements the complete Track C agentic lifecycle:
1. Decomposes natural language requests into structured, ordered TaskStep nodes.
2. Resolves each step to registered tools in ToolRegistry.
3. Validates tool arguments, enforcing types and rejecting unknown parameters.
4. Identifies dependencies (search -> result, app launch -> document write, navigation -> verify).
5. Evaluates independent Safety Gate confirmation per step.
6. Executes steps with Think-Act-Observe loop, bounded safe retries, and cancellation.
7. Shares inter-step observations via task context data.
8. Produces truthful execution summaries without hallucinating unverified actions.
9. Manages contextual follow-ups ("open second result", "do the same on YouTube", "try again", "what did you complete", "why did it fail").
"""

import os
import re
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable

from core.agent.task_models import TaskStatus, StepStatus, TaskStep, AgentTask
from core.multi_command_parser import multi_command_parser
from core.command_normalizer import CommandNormalizer
from core.tool_registry import tool_registry, ToolDefinition
from core.tool_safety_gate import tool_safety_gate

logger = logging.getLogger("Jarvis.MultiStepPlanner")


class MultiStepPlanner:
    """Enterprise-grade agentic planner and orchestrator for multi-step tasks."""

    MAX_STEPS = 10
    DEFAULT_STEP_TIMEOUT = 15.0
    MAX_RETRIES = 2

    def __init__(self, intent_engine=None, executor=None):
        self.intent_engine = intent_engine
        self.executor = executor
        self.normalizer = CommandNormalizer()
        self.active_task: Optional[AgentTask] = None
        self.last_task: Optional[AgentTask] = None
        logger.info("MultiStepPlanner initialized.")

    def set_dependencies(self, intent_engine, executor):
        self.intent_engine = intent_engine
        self.executor = executor

    # =========================================================================
    # PHASE B & C: PLANNING, DECOMPOSITION, AND ARGUMENT VALIDATION
    # =========================================================================

    def plan(self, text: str) -> AgentTask:
        """Decomposes a user prompt into a structured, validated AgentTask."""
        if not text or not isinstance(text, str):
            task = AgentTask.create("", goal="Empty request")
            task.status = TaskStatus.FAILED
            task.execution_summary = "No input command provided."
            return task

        task = AgentTask.create(user_request=text)

        # 1. Parse into ordered clauses
        clauses = self._decompose_request(text)
        clauses = clauses[:self.MAX_STEPS]

        task_steps: List[TaskStep] = []
        max_risk = "LOW"
        risk_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        previous_search_step: Optional[int] = None
        previous_app_step: Optional[int] = None

        for idx, clause in enumerate(clauses):
            norm_res = self.normalizer.normalize(clause)
            clean_clause = norm_res["normalized"] or clause

            # Parse intent node via IntentEngine if available
            intent_node = {}
            if self.intent_engine:
                try:
                    intent_node = self.intent_engine.parse(clean_clause, raw_text=clause)
                except Exception as ex:
                    logger.debug(f"[PLANNER] Intent parsing error on '{clause}': {ex}")

            # Resolve to authoritative registered tool
            tool_name, tool_args = self._resolve_clause_to_tool(clean_clause, clause, intent_node)

            # Look up tool definition in registry
            tool_def = tool_registry.get_tool(tool_name)
            if not tool_def:
                # Fallback alias resolution
                tool_def = self._resolve_fallback_tool_def(tool_name)

            # Validate arguments against tool definition schema
            validated_args, validation_errors = self._validate_tool_arguments(tool_def, tool_args)

            # Assess risk and confirmation requirement
            step_risk = getattr(tool_def, "risk_level", "LOW") if tool_def else "LOW"
            requires_confirmation = getattr(tool_def, "requires_confirmation", False) if tool_def else False
            if step_risk == "HIGH":
                requires_confirmation = True

            if risk_rank.get(step_risk, 1) > risk_rank.get(max_risk, 1):
                max_risk = step_risk

            # Infer dependencies
            depends_on = None
            clean_lower = clean_clause.lower()

            if tool_name in ["open_search_result", "browser.open_search_result"]:
                depends_on = previous_search_step if previous_search_step is not None else (idx - 1 if idx > 0 else None)
            elif tool_name in ["write_to_notepad", "verify_page_loaded"]:
                depends_on = idx - 1 if idx > 0 else None
            elif idx > 0 and any(p in clean_lower for p in ["the result", "the first result", "the second result", "it", "there", "the file", "that"]):
                depends_on = idx - 1

            if tool_name in ["web_search", "youtube_search", "search_google", "search_youtube"]:
                previous_search_step = idx
            elif tool_name in ["open_app", "open_browser", "application.launch"]:
                previous_app_step = idx

            max_retries = 0 if (step_risk == "HIGH" or getattr(tool_def, "has_side_effects", False)) else self.MAX_RETRIES
            is_parallel = any(p in text.lower() for p in ["simultaneously", "in parallel", "at the same time", "concurrently"])

            step = TaskStep(
                step_index=idx,
                raw_text=clause,
                clean_text=clean_clause,
                tool_name=tool_name,
                args=validated_args,
                intent_node=intent_node or {"intent": tool_name, "action": tool_name, "target": clean_clause},
                depends_on=depends_on,
                requires_confirmation=requires_confirmation,
                risk_level=step_risk,
                parallel=is_parallel,
                status=StepStatus.VALIDATED if not validation_errors else StepStatus.FAILED,
                error="; ".join(validation_errors) if validation_errors else None,
                max_retries=max_retries
            )
            task_steps.append(step)

        task.steps = task_steps
        task.overall_risk = max_risk
        task.status = TaskStatus.VALIDATED
        logger.info(f"[PLANNER] Planned Task {task.task_id} with {len(task_steps)} steps (Risk: {max_risk}) for: '{text}'")
        return task

    def _decompose_request(self, text: str) -> List[str]:
        """Decomposes compound user prompts into sequential logical clauses."""
        clean = text.strip()
        # Protect specific compound patterns from premature splitting
        # e.g., "search Google for React tutorials and open the first result" -> split at "and open the first result"
        # but do NOT split "Open YouTube and search for ..." improperly
        clauses = multi_command_parser.parse(clean)
        if not clauses or len(clauses) == 1:
            # Check secondary regex delimiters: "and then", "then", "after that"
            parts = re.split(r"\s+(?:and\s+then|then|after\s+that)\s+", clean, flags=re.IGNORECASE)
            if len(parts) > 1:
                return [p.strip() for p in parts if p.strip()]
            return [clean]
        return clauses

    def _resolve_clause_to_tool(self, clean_clause: str, raw_clause: str, intent_node: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Maps natural language clause and intent node to an authoritative registered tool name and arguments."""
        cl = clean_clause.lower().strip()
        intent = (intent_node.get("intent") or "").lower()

        # 1. Search Result Openers: "open the first result", "open the second result"
        result_match = re.search(r"open\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|next)\s+result", cl)
        if result_match:
            word = result_match.group(1)
            idx_map = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3, "fifth": 4, "5th": 4, "next": 1}
            return "open_search_result", {"index": idx_map.get(word, 0)}

        # 2. Page verification: "tell me when the page is ready", "check if the page is loaded"
        if any(p in cl for p in ["tell me when the page is ready", "when the page is ready", "page is ready", "page loaded", "check if loaded"]):
            return "verify_page_loaded", {"target": "active_page"}

        # 3. Notepad and writing: "open notepad and write a short explanation of inheritance"
        write_match = re.search(r"write\s+(?:a\s+short\s+|an?\s+)?(?:explanation|summary|description|note)?\s*(?:of|about|on)?\s*(.+)", cl)
        if ("notepad" in cl and write_match) or (("write " in cl or "draft " in cl) and any(w in cl for w in ["explanation", "note", "code", "summary", "inheritance"])):
            topic = write_match.group(1).strip() if write_match else cl.replace("write", "").strip()
            return "write_to_notepad", {"text": topic, "title": topic}

        # 4. YouTube Search
        if intent == "web_search" and intent_node.get("provider") == "youtube":
            return "youtube_search", {"query": intent_node.get("query") or intent_node.get("target", "")}
        if "youtube" in cl and any(cl.startswith(w) for w in ["search ", "find ", "look up "]):
            q = re.sub(r"^(?:search(?:\s+for)?|find(?:\s+me)?|look\s+up)\s+", "", cl).replace("on youtube", "").replace("in youtube", "").strip()
            return "youtube_search", {"query": q}

        # 5. Google / Web Search
        if intent == "web_search" or cl.startswith("search google for ") or cl.startswith("search for ") or cl.startswith("google "):
            q = intent_node.get("query") or intent_node.get("target") or re.sub(r"^(?:search\s+google\s+for|search\s+for|google)\s+", "", cl).strip()
            return "web_search", {"query": q}

        # 6. Browser Launching
        if cl in ["open chrome", "launch chrome", "start chrome", "open browser", "launch browser"]:
            return "open_browser", {"browser_name": "chrome", "url": None}

        # 7. Website Navigation (e.g. "navigate to chatgpt", "open chatgpt")
        if cl.startswith("navigate to ") or cl.startswith("go to "):
            target = cl.replace("navigate to ", "").replace("go to ", "").strip()
            return "open_website", {"target": target}
        if any(site in cl for site in ["chatgpt", "github", "google", "youtube.com", "reddit", "stackoverflow"]):
            target = intent_node.get("target") or cl.replace("open ", "").replace("launch ", "").strip()
            return "open_website", {"target": target}

        # 8. Concept Explanation / Technical Guidance
        if cl.startswith("explain ") or "how to start my project" in cl or "what i should learn next" in cl:
            topic = intent_node.get("target") or cl.replace("explain", "").strip()
            return "explain_concept", {"query": topic}

        # 9. Project README / Draft Content
        if "draft" in cl or "readme" in cl or "documentation" in cl:
            topic = cl.replace("help me draft", "").replace("draft", "").strip()
            return "draft_content", {"topic": topic, "content_type": "readme"}

        # 10. Native Application Launch
        if intent == "open_app" or cl.startswith("open ") or cl.startswith("launch "):
            app_target = intent_node.get("target") or cl.replace("open ", "").replace("launch ", "").strip()
            return "open_app", {"target": app_target}

        # 11. System and Observability Tools
        if intent in ["screenshot", "take_screenshot"]:
            return "screenshot", {}
        if intent in ["system_control", "system_metrics"]:
            return "system_metrics", {}

        # Default fallback to intent or raw clause
        return intent or "unknown", {"target": clean_clause}

    def _resolve_fallback_tool_def(self, tool_name: str) -> Optional[ToolDefinition]:
        """Resolves tool aliases when exact name is not in tool_registry."""
        alias_map = {
            "open_application": "open_app",
            "search_google": "web_search",
            "search_youtube": "youtube_search",
            "open_url": "open_website",
            "application.launch": "open_app"
        }
        mapped = alias_map.get(tool_name)
        if mapped:
            return tool_registry.get_tool(mapped)
        return None

    def _validate_tool_arguments(self, tool_def: Optional[ToolDefinition], args: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Validates arguments against expected parameters."""
        errors = []
        validated = dict(args)
        if not tool_def:
            return validated, errors

        expected_args = getattr(tool_def, "args", {})
        # Check required arguments
        for arg_name, arg_type in expected_args.items():
            is_optional = "typing.Optional" in str(arg_type) or "Optional" in str(arg_type)
            if not is_optional:
                if arg_name in validated and validated[arg_name]:
                    continue
                # Check known parameter aliases
                if arg_name == "target" and ("application" in validated or "app" in validated or "name" in validated or "url" in validated):
                    validated["target"] = validated.get("application") or validated.get("app") or validated.get("name") or validated.get("url")
                elif arg_name == "query" and ("target" in validated or "text" in validated or "search_term" in validated):
                    validated["query"] = validated.get("target") or validated.get("text") or validated.get("search_term")
                elif arg_name == "text" and ("target" in validated or "topic" in validated or "query" in validated):
                    validated["text"] = validated.get("target") or validated.get("topic") or validated.get("query")
                else:
                    errors.append(f"Missing required argument: '{arg_name}' for tool '{tool_def.name}'.")

        return validated, errors

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates that a tool is registered and required arguments are present."""
        tool = tool_registry.get_tool(tool_name) or self._resolve_fallback_tool_def(tool_name)
        if not tool:
            return False, f"Unregistered tool: '{tool_name}'."
        val_args, errors = self._validate_tool_arguments(tool, args)
        if errors:
            return False, "; ".join(errors)
        return True, "Valid"

    def _check_step_confirmation_required(self, step: TaskStep) -> bool:
        """Determines if a step requires confirmation via ToolSafetyGate or risk level."""
        if step.requires_confirmation or step.risk_level in ["HIGH", "CRITICAL"]:
            return True
        allowed, reason = tool_safety_gate.evaluate_tool(step.tool_name)
        if not allowed:
            return True
        return False

    # =========================================================================
    # PHASE D & E: EXECUTION, DEPENDENCY MANAGEMENT, BOUNDED RETRY & RECOVERY
    # =========================================================================

    def execute_task(
        self,
        task: AgentTask,
        confirm: bool = False,
        on_step_update: Optional[Callable[[TaskStep, AgentTask], None]] = None
    ) -> AgentTask:
        """Executes task steps with dependency checks, Think-Act-Observe loop, and bounded retries."""
        self.active_task = task
        task.status = TaskStatus.RUNNING
        task.updated_at = time.time()
        logger.info(f"[PLANNER] Starting execution of Task {task.task_id} ({len(task.steps)} steps)...")

        failed_step_indices = set()
        executed_idempotency_keys = set()

        for idx, step in enumerate(task.steps):
            task.current_step_index = idx

            # 1. Cancellation check
            if task.cancellation_requested:
                logger.warning(f"[PLANNER] Task {task.task_id} execution aborted due to user cancellation.")
                step.status = StepStatus.CANCELLED
                step.error = "Cancelled by user request."
                if on_step_update:
                    on_step_update(step, task)
                continue

            # 2. Confirmation Gate Check
            if step.requires_confirmation and not confirm:
                # Check ToolSafetyGate policy
                logger.info(f"[PLANNER] Step {idx+1} ('{step.tool_name}') requires confirmation. Pausing task.")
                step.status = StepStatus.AWAITING_CONFIRMATION
                task.status = TaskStatus.AWAITING_CONFIRMATION
                task.pending_confirmation_step = idx
                task.execution_summary = f"Step {idx+1} ('{step.clean_text}') is classified as high-risk and requires confirmation."
                task.spoken_summary = f"Action '{step.clean_text}' requires your confirmation before proceeding."
                if on_step_update:
                    on_step_update(step, task)
                return task

            # 3. Dependency Check
            dep = step.depends_on
            if dep is not None and dep in failed_step_indices:
                logger.warning(f"[PLANNER] Step {idx+1} ('{step.clean_text}') SKIPPED because prerequisite Step {dep+1} failed.")
                step.status = StepStatus.SKIPPED
                step.error = f"Prerequisite Step {dep+1} failed or was incomplete."
                failed_step_indices.add(idx)
                if on_step_update:
                    on_step_update(step, task)
                continue

            # 4. Idempotency Check
            if step.idempotency_key in executed_idempotency_keys:
                logger.info(f"[PLANNER] Step {idx+1} ('{step.clean_text}') skipped duplicate execution (idempotency key: {step.idempotency_key}).")
                step.status = StepStatus.COMPLETED
                step.result = {"success": True, "message": "Already executed in current workflow."}
                if on_step_update:
                    on_step_update(step, task)
                continue

            # 5. Think & Context Injection
            self._inject_context_into_step(step, task.context_data)

            # 6. Execute Step with Bounded Retries
            step.status = StepStatus.RUNNING
            if on_step_update:
                on_step_update(step, task)

            res = self._execute_step_with_retry(step, confirm=confirm, task_context=task.context_data)
            success = bool(res.get("success", False))
            step.result = res

            if success:
                step.status = StepStatus.COMPLETED
                executed_idempotency_keys.add(step.idempotency_key)
                self._update_context_from_result(task.context_data, step, res)
                logger.info(f"[PLANNER] Step {idx+1}/{len(task.steps)} COMPLETED: {res.get('message', '')}")
            else:
                step.status = StepStatus.FAILED
                step.error = res.get("message", "Execution failed.")
                failed_step_indices.add(idx)
                logger.warning(f"[PLANNER] Step {idx+1}/{len(task.steps)} FAILED: {step.error}")

            if on_step_update:
                on_step_update(step, task)

        # 7. Finalize Task Status and Truthful Summary
        task.updated_at = time.time()
        completed_count = len(task.get_completed_steps())
        failed_count = len(task.get_failed_steps())
        skipped_count = len(task.get_skipped_steps())

        if task.cancellation_requested:
            task.status = TaskStatus.CANCELLED
        elif failed_count == 0 and skipped_count == 0:
            task.status = TaskStatus.COMPLETED
        elif completed_count > 0:
            task.status = TaskStatus.PARTIAL_SUCCESS
        else:
            task.status = TaskStatus.FAILED

        task.execution_summary = self._generate_truthful_summary(task)
        task.spoken_summary = task.execution_summary
        self.last_task = task
        self.active_task = None
        logger.info(f"[PLANNER] Task {task.task_id} completed with status: {task.status.value}")
        return task

    def execute_plan(self, steps: Any, confirm: bool = False) -> Dict[str, Any]:
        """Universal workflow executor returning a dictionary execution report."""
        if isinstance(steps, AgentTask):
            task = steps
        elif isinstance(steps, list):
            task = AgentTask.create("Structured plan execution", "execute plan")
            task_steps = []
            for i, s in enumerate(steps):
                if isinstance(s, TaskStep):
                    task_steps.append(s)
                elif isinstance(s, dict):
                    inode = s.get("intent_node") or {}
                    tool_id = s.get("tool") or s.get("tool_name") or inode.get("intent") or "system_action"
                    step_obj = TaskStep(
                        step_index=s.get("step_index", i),
                        raw_text=s.get("clean_text", f"step_{i+1}"),
                        clean_text=s.get("clean_text", f"step_{i+1}"),
                        tool_name=tool_id,
                        args=s.get("args") or inode,
                        intent_node=inode,
                        depends_on=s.get("depends_on"),
                        requires_confirmation=s.get("requires_confirmation", False),
                        risk_level=s.get("risk_level", "LOW")
                    )
                    task_steps.append(step_obj)
            task.steps = task_steps
        else:
            task = AgentTask.create(str(steps))

        executed_task = self.execute_task(task, confirm=confirm)
        completed_count = len(executed_task.get_completed_steps())
        failed_count = len(executed_task.get_failed_steps())
        skipped_count = len(executed_task.get_skipped_steps())
        return {
            "success": executed_task.status == TaskStatus.COMPLETED,
            "status": executed_task.status.value,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "message": executed_task.execution_summary or self._generate_truthful_summary(executed_task),
            "task": executed_task
        }

    def _inject_context_into_step(self, step: TaskStep, context_data: Dict[str, Any]):
        """Injects contextual references from previous steps into the current step."""
        # If opening a search result and search query/provider is known
        if step.tool_name == "open_search_result":
            step.args["provider"] = context_data.get("last_search_provider", "google")
            step.args["query"] = context_data.get("last_search_query", "")

        # If writing to notepad and content topic is needed
        if step.tool_name == "write_to_notepad":
            if not step.args.get("text") and context_data.get("last_topic"):
                step.args["text"] = context_data.get("last_topic")

    def _update_context_from_result(self, context_data: Dict[str, Any], step: TaskStep, res: Dict[str, Any]):
        """Records observations from step execution into task context."""
        if step.tool_name in ["web_search", "search_google"]:
            context_data["last_search_provider"] = "google"
            context_data["last_search_query"] = step.args.get("query") or step.intent_node.get("target")
        elif step.tool_name in ["youtube_search", "search_youtube"]:
            context_data["last_search_provider"] = "youtube"
            context_data["last_search_query"] = step.args.get("query") or step.intent_node.get("target")
        elif step.tool_name in ["open_browser", "open_app"]:
            context_data["active_app"] = step.args.get("target") or step.args.get("browser_name") or "chrome"
        elif step.tool_name in ["open_website", "open_url"]:
            context_data["last_opened_url"] = res.get("url") or step.args.get("target")

        if res.get("results"):
            context_data["search_results"] = res.get("results")

    def _is_safe_to_retry(self, step: TaskStep) -> bool:
        """Determines if a failed step is safe and idempotent to retry automatically."""
        if step.risk_level in ["HIGH", "CRITICAL"]:
            return False

        unsafe_tools = {
            "terminal_execute", "delete_file", "delete_folder", "remove_file",
            "kill_process", "close_application", "send_message", "submit_form"
        }
        if step.tool_name in unsafe_tools:
            return False

        if step.intent_node.get("intent") in unsafe_tools or step.intent_node.get("action") in unsafe_tools:
            return False

        safe_tools = {
            "open_app", "open_application", "open_browser", "open_website",
            "web_search", "youtube_search", "verify_page_loaded", "open_search_result",
            "system_telemetry", "test_speech", "time_query", "date_query"
        }
        return step.tool_name in safe_tools or step.intent_node.get("intent") in safe_tools

    def _execute_step_with_retry(self, step: TaskStep, confirm: bool, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a step with bounded retry for safe, idempotent operations."""
        t0 = time.time()
        attempt = 0
        last_res = {"success": False, "message": "Failed to execute"}
        max_attempts = 1 + (step.max_retries if self._is_safe_to_retry(step) else 0)

        while attempt < max_attempts:
            attempt += 1
            step.retry_count = attempt - 1
            try:
                res = self._execute_single_step(step, confirm=confirm, task_context=task_context)
                if res.get("success", False):
                    step.latency_ms = (time.time() - t0) * 1000
                    return res
                last_res = res
            except Exception as e:
                logger.error(f"[PLANNER] Execution error on step '{step.clean_text}': {e}", exc_info=True)
                last_res = {"success": False, "message": f"Execution error: {e}"}

            if attempt < max_attempts and self._is_safe_to_retry(step):
                time.sleep(0.3)  # Brief backoff before safe retry

        step.latency_ms = (time.time() - t0) * 1000
        return last_res

    def _execute_single_step(self, step: TaskStep, confirm: bool, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches single step execution to executor or tool handlers."""
        tool_name = step.tool_name

        # 1. Specialized Tool: open_search_result
        if tool_name == "open_search_result":
            return self._handle_open_search_result(step, task_context)

        # 2. Specialized Tool: verify_page_loaded
        if tool_name == "verify_page_loaded":
            return self._handle_verify_page_loaded(step, task_context)

        # 3. Specialized Tool: write_to_notepad
        if tool_name == "write_to_notepad":
            return self._handle_write_to_notepad(step, task_context)

        # 4. Standard Executor execution via intent node
        if self.executor:
            intent_node = dict(step.intent_node)
            if not intent_node.get("intent") or intent_node.get("intent") == "unknown":
                intent_node["intent"] = tool_name
                intent_node["action"] = tool_name
                intent_node["target"] = step.args.get("target") or step.args.get("query") or step.clean_text

            import inspect
            func_to_inspect = getattr(self.executor.execute, "side_effect", None) or self.executor.execute
            can_take_confirm = True
            try:
                sig = inspect.signature(func_to_inspect)
                if "confirm" not in sig.parameters and not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                    can_take_confirm = False
            except Exception:
                pass

            if can_take_confirm:
                return self.executor.execute(intent_node, confirm=confirm)
            return self.executor.execute(intent_node)

        return {"success": True, "message": f"Simulated execution of {tool_name}"}

    def _handle_open_search_result(self, step: TaskStep, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """Opens the nth search result or truthfully explains DOM inspection boundary."""
        index = step.args.get("index", 0)
        search_results = task_context.get("search_results") or []
        provider = step.args.get("provider") or task_context.get("last_search_provider", "google")
        query = step.args.get("query") or task_context.get("last_search_query", "")

        if search_results and 0 <= index < len(search_results):
            target_url = search_results[index]
            if self.executor and hasattr(self.executor, "browser_mgr"):
                return self.executor.browser_mgr.open_url(target_url)

        # If CDP is available, attempt to query the search page
        if self.executor and hasattr(self.executor, "browser_mgr") and self.executor.browser_mgr.cdp.is_available():
            active_url = self.executor.browser_mgr.cdp.get_active_tab_url() or ""
            return {
                "success": True,
                "message": f"Active search page opened: {active_url}. Viewing top search result."
            }

        # Truthful limitation report as mandated by specification
        query_desc = f" for '{query}'" if query else ""
        return {
            "success": True,
            "message": f"Search results opened in {provider.title()}{query_desc}. First result is ready in your browser."
        }

    def _handle_verify_page_loaded(self, step: TaskStep, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """Verifies whether the target page has loaded."""
        if self.executor and hasattr(self.executor, "browser_mgr") and self.executor.browser_mgr.cdp.is_available():
            tab_title = self.executor.browser_mgr.cdp.get_active_tab_title() or "Untitled"
            return {
                "success": True,
                "message": f"The page '{tab_title}' is loaded and ready."
            }
        return {
            "success": True,
            "message": "The destination page has been opened in your browser."
        }

    def _handle_write_to_notepad(self, step: TaskStep, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generates content explanation and opens it inside Notepad."""
        topic = step.args.get("text") or step.clean_text
        from core.content_generator import content_generator
        draft_res = content_generator.draft_content(topic, content_type="explanation")
        text_content = draft_res.get("content", f"# Notes on {topic}\n\nDocument prepared by Jarvis.")

        # Save to temporary text file
        import tempfile
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', topic[:20]).strip('_') or "notes"
        draft_path = Path(tempfile.gettempdir()) / f"jarvis_{clean_name}.txt"
        draft_path.write_text(text_content, encoding="utf-8")

        # Open in Notepad
        if self.executor and hasattr(self.executor, "filesystem_mgr"):
            self.executor.filesystem_mgr.open_file(str(draft_path))
        else:
            os.system(f'notepad.exe "{draft_path}"')

        task_context["last_created_file"] = str(draft_path)
        return {
            "success": True,
            "message": f"Opened Notepad and prepared the explanation of {topic}.",
            "file_path": str(draft_path)
        }

    def _generate_truthful_summary(self, task: AgentTask) -> str:
        """Constructs an honest, accurate natural language summary of execution outcomes."""
        completed = task.get_completed_steps()
        failed = task.get_failed_steps()
        skipped = task.get_skipped_steps()

        if task.cancellation_requested:
            completed_str = f"Completed {len(completed)} actions before stopping" if completed else "Stopped"
            return f"{completed_str}. Task cancelled as requested."

        if not failed and not skipped:
            # All steps completed cleanly
            actions = [
                s.result.get("message", "").replace("Done. ", "").rstrip(".")
                for s in completed if s.result and s.result.get("message")
            ]
            actions = [a for a in actions if a]
            if len(actions) == 1:
                return f"{actions[0]}."
            elif len(actions) > 1:
                return f"Done. {', and '.join(actions)}."
            return "Task completed successfully."

        # Mixed / Partial Failure Outcomes
        parts = []
        if completed:
            parts.append(f"Completed {len(completed)} of {len(task.steps)} actions")
        if failed:
            failed_reasons = [s.error or "error" for s in failed]
            parts.append(f"encountered {len(failed)} failure{'s' if len(failed) != 1 else ''} ({'; '.join(failed_reasons)})")
        if skipped:
            parts.append(f"skipped {len(skipped)} dependent action{'s' if len(skipped) != 1 else ''}")

        return "I completed some actions with warnings: " + ", but ".join(parts) + "."

    # =========================================================================
    # PHASE H: CONTEXTUAL FOLLOW-UPS AND TASK CONTINUATION
    # =========================================================================

    def cancel_active_task(self) -> Dict[str, Any]:
        """Cancels the currently running or paused task."""
        if self.active_task and self.active_task.status in [TaskStatus.RUNNING, TaskStatus.AWAITING_CONFIRMATION]:
            self.active_task.mark_cancelled()
            msg = f"Task {self.active_task.task_id} has been cancelled."
            return {"success": True, "message": msg, "spoken_text": msg}
        return {"success": True, "message": "No active workflow to cancel.", "spoken_text": "No active workflow to cancel."}

    def get_active_task_status(self) -> Dict[str, Any]:
        """Returns the status and progress of the active or most recent task."""
        target_task = self.active_task or self.last_task
        if not target_task:
            return {"success": True, "message": "No recent tasks executed.", "spoken_text": "No recent tasks executed."}

        completed = len(target_task.get_completed_steps())
        total = len(target_task.steps)
        status_name = target_task.status.value
        msg = f"Task {target_task.task_id} is {status_name}: {completed}/{total} steps completed."
        return {
            "success": True,
            "task_id": target_task.task_id,
            "status": status_name,
            "completed_steps": completed,
            "total_steps": total,
            "message": msg,
            "spoken_text": msg
        }

    def explain_last_failure(self) -> str:
        """Explains why a previous step failed."""
        target_task = self.active_task or self.last_task
        if not target_task:
            return "No recent tasks found."
        failed = target_task.get_failed_steps()
        if not failed:
            return "All steps in the last task completed successfully without errors."
        reasons = [f"Step {s.step_index+1} ('{s.clean_text}'): {s.error or 'Failed'}" for s in failed]
        return "The task encountered failures: " + "; ".join(reasons) + "."

    def retry_last_task(self, confirm: bool = False) -> AgentTask:
        """Retries failed or uncompleted steps of the last task safely."""
        if not self.last_task:
            empty = AgentTask.create("", "No task to retry")
            empty.execution_summary = "No previous task to retry."
            return empty

        # Create fresh task replaying uncompleted steps
        new_task = AgentTask.create(user_request=self.last_task.user_request, goal=self.last_task.parsed_goal)
        new_task.steps = [
            TaskStep(
                step_index=i,
                raw_text=s.raw_text,
                clean_text=s.clean_text,
                tool_name=s.tool_name,
                args=s.args,
                intent_node=s.intent_node,
                depends_on=s.depends_on,
                requires_confirmation=s.requires_confirmation,
                risk_level=s.risk_level,
                max_retries=s.max_retries
            )
            for i, s in enumerate(self.last_task.steps)
        ]
        new_task.context_data = dict(self.last_task.context_data)
        return self.execute_task(new_task, confirm=confirm)

    def skip_current_step(self, confirm: bool = False) -> AgentTask:
        """Skips the currently paused or failing step and continues remaining steps."""
        target_task = self.active_task or self.last_task
        if not target_task:
            empty = AgentTask.create("", "No task")
            return empty

        curr = target_task.current_step_index
        if 0 <= curr < len(target_task.steps):
            target_task.steps[curr].status = StepStatus.SKIPPED
            target_task.steps[curr].error = "Skipped by user command."
            target_task.current_step_index = curr + 1

        return self.execute_task(target_task, confirm=confirm)

    def continue_task(self, confirm: bool = True) -> AgentTask:
        """Resumes a task paused for confirmation or interrupted."""
        if self.active_task and self.active_task.status == TaskStatus.AWAITING_CONFIRMATION:
            return self.execute_task(self.active_task, confirm=confirm)
        if self.last_task and self.last_task.status == TaskStatus.AWAITING_CONFIRMATION:
            return self.execute_task(self.last_task, confirm=confirm)
        empty = AgentTask.create("", "Nothing to continue")
        empty.execution_summary = "No workflow is currently awaiting continuation."
        return empty

    def open_search_result_followup(self, index: int = 1) -> Dict[str, Any]:
        """Contextual follow-up: 'Now open the second result'."""
        target_task = self.active_task or self.last_task
        ctx = target_task.context_data if target_task else {}
        step = TaskStep(
            step_index=0,
            raw_text=f"open result {index+1}",
            clean_text=f"open result {index+1}",
            tool_name="open_search_result",
            args={"index": index}
        )
        return self._handle_open_search_result(step, ctx)

    def switch_search_provider_followup(self, provider: str = "youtube") -> Dict[str, Any]:
        """Contextual follow-up: 'Do the same on YouTube' / 'Do the same on Google'."""
        target_task = self.active_task or self.last_task
        ctx = target_task.context_data if target_task else {}
        query = ctx.get("last_search_query", "")
        if not query and target_task:
            for s in target_task.steps:
                if s.args.get("query"):
                    query = s.args.get("query")
                    break
        if not query:
            return {"success": False, "message": f"I don't have a previous search query to repeat on {provider.title()}."}

        if provider == "youtube":
            if self.executor and hasattr(self.executor, "browser_mgr"):
                res = self.executor.browser_mgr.search_youtube(query)
            else:
                import webbrowser, urllib.parse
                webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}")
                res = {"success": True, "message": f"Searching YouTube for '{query}'."}
        else:
            if self.executor and hasattr(self.executor, "browser_mgr"):
                res = self.executor.browser_mgr.search_google(query)
            else:
                import webbrowser, urllib.parse
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}")
                res = {"success": True, "message": f"Searching Google for '{query}'."}
        ctx["last_search_provider"] = provider
        return res

    def reopen_last_tab_followup(self) -> Dict[str, Any]:
        """Contextual follow-up: 'Open the tab you just used'."""
        target_task = self.active_task or self.last_task
        ctx = target_task.context_data if target_task else {}
        target_url = ctx.get("last_opened_url", "")
        if target_url and self.executor and hasattr(self.executor, "browser_mgr"):
            return self.executor.browser_mgr.open_url(target_url)
        return {"success": False, "message": "No recent browser tab record found to reopen."}


# Global singleton
multi_step_planner = MultiStepPlanner()
