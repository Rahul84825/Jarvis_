import re
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List

from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.os.project_registry import ProjectRegistry
from memory.persistent_memory import persistent_memory

logger = logging.getLogger("Jarvis.IntelligenceRouter")

# Mode Constants
MODE_FAST_LOCAL = "FAST_LOCAL"
MODE_CONTEXT = "CONTEXT"
MODE_REASONING = "REASONING"
MODE_QUESTION = "QUESTION"

LAYER_1 = 1  # Reflex / Fast Local
LAYER_2 = 2  # Understanding / Context
LAYER_3 = 3  # Reasoning / Agent

@dataclass
class StructuredRequest:
    """Standardized Structured Request Object passed through the intelligence pipeline."""
    raw_text: str
    normalized_text: str
    mode: str
    layer: int
    intent: str
    action: str = ""
    target: str = ""
    confidence: float = 1.0
    context_required: bool = False
    planning_required: bool = False
    clarification_prompt: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class IntelligenceRouter:
    """Central Intelligence Router for Jarvis.
    Routes user speech across:
      Layer 1 (Reflex / Fast Local) -> Zero-latency deterministic OS tools
      Layer 2 (Understanding / Context) -> Context resolution & preferences
      Layer 3 (Reasoning / Agentic) -> Multi-step ReAct agent planning
    """

    def __init__(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.project_registry = ProjectRegistry()

    def route(self, raw_text: str, session_context: Optional[Dict[str, Any]] = None) -> StructuredRequest:
        """Analyzes and classifies raw user speech into a StructuredRequest."""
        t0 = time.perf_counter()
        norm_res = self.normalizer.normalize(raw_text)
        normalized = norm_res["normalized"]
        clean = normalized.lower().strip()

        # Step 1: Detect Complex Multi-Step / Reasoning Requests (Layer 3)
        if self._is_complex_reasoning(clean, raw_text):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as LAYER 3 REASONING (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_REASONING,
                layer=LAYER_3,
                intent="COMPLEX_TASK",
                action="agent_plan_and_execute",
                target=clean,
                confidence=0.92,
                context_required=True,
                planning_required=True
            )

        # Step 2: Detect Informational Questions (Strict Filter)
        if self._is_informational_question(raw_text, clean):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as QUESTION (Layer 2/3 conversation, Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_QUESTION,
                layer=LAYER_2,
                intent="informational_question",
                action="explain",
                target=clean,
                confidence=0.95,
                context_required=True,
                planning_required=False
            )

        # Step 3: Check Contextual References & Pronominals (Layer 2)
        contextual_req = self._check_contextual_request(raw_text, normalized, clean, session_context)
        if contextual_req:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as LAYER 2 CONTEXT (Latency={elapsed_ms:.2f}ms)")
            return contextual_req

        # Step 4: Deterministic Local Parsing (Layer 1 Fast Reflex)
        intent_node = self.intent_engine.parse(normalized)
        intent = intent_node.get("intent", "unknown")
        confidence = intent_node.get("confidence", 0.0)

        # Known Layer 1 Fast Local intents
        deterministic_intents = {
            "open_app", "close_app", "minimize_app", "maximize_app", "window_control", "system_control",
            "open_new_chrome_tab", "open_new_chrome_window", "open_folder", "open_file",
            "screenshot", "time_query", "date_query", "math_calculation",
            "media_control", "open_website", "terminal_execute", "file_access",
            "system_telemetry", "greeting", "thank_you", "goodbye", "help",
            "identity", "repeat_response", "status_request", "acknowledgement",
            "affirmation", "negation", "how_are_you", "status_check",
            "turn_on_camera", "turn_off_camera", "start_hand_tracking", "stop_hand_tracking", "camera_snapshot"
        }


        if intent in deterministic_intents and confidence >= 0.75:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as LAYER 1 FAST LOCAL ({intent}, Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent=intent.upper(),
                action=intent_node.get("action", ""),
                target=intent_node.get("target", ""),
                confidence=confidence,
                context_required=False,
                planning_required=False,
                entities=intent_node
            )

        # Step 5: Fallback / Conversational Understanding (Layer 2)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"[ROUTER] Routed to LAYER 2 CONVERSATION (Fallback, Latency={elapsed_ms:.2f}ms)")
        return StructuredRequest(
            raw_text=raw_text,
            normalized_text=normalized,
            mode=MODE_CONTEXT,
            layer=LAYER_2,
            intent=intent.upper() if intent != "unknown" else "CONVERSATION",
            action=intent_node.get("action", "conversation"),
            target=intent_node.get("target", clean),
            confidence=max(confidence, 0.60),
            context_required=True,
            planning_required=False,
            entities=intent_node
        )

    def _is_informational_question(self, raw: str, clean: str) -> bool:
        """Determines if the request is an informational question rather than an imperative command."""
        # Math calculation bypass
        if any(op in clean for op in ["times", "plus", "minus", "divided by", "multiplied by", "+", "*", "/"]) and any(c.isdigit() for c in clean):
            return False

        # Time & Date bypass
        if any(t in clean for t in ["what time is it", "what's the time", "what is the time", "what is the date", "what's the date", "what day is it"]):
            return False

        # Capabilities, Help & Identity bypass
        if any(h in clean for h in [
            "what can you do", "what can jarvis do", "what are your capabilities",
            "what commands do you know", "what do you do", "show capabilities",
            "how can you help", "who are you", "who made you"
        ]):
            return False

        question_starters = (
            "how do i", "how can i", "how to", "why does", "why is", "why isn't",
            "what is", "what does", "what are", "tell me about", "can you explain",
            "explain what", "explain why", "should i", "is it possible to", "who is",
            "where is the documentation for", "describe"
        )
        if any(clean.startswith(q) for q in question_starters):
            # Check if it contains an imperative override
            if not any(clean.startswith(f"{q} open ") or clean.startswith(f"{q} close ") for q in ["can you", "could you"]):
                return True

        if raw.strip().endswith("?") and not any(clean.startswith(p) for p in [
            "open", "close", "lock", "sleep", "restart", "shutdown",
            "take a screenshot", "take a photo", "turn on", "turn off", "start", "stop"
        ]):
            return True

        return False

    def _is_complex_reasoning(self, clean: str, raw_text: str = "") -> bool:
        """Identifies multi-step, investigative, coding, or planning requests (Layer 3)."""
        raw_clean = raw_text.lower().strip()
        reasoning_patterns = [
            r"prepare (?:my|the)?\s*(?:development|dev)?\s*environment",
            r"get (?:my|the)?\s*(?:development|dev)?\s*environment ready",
            r"check why (?:my|the)?\s*(?:backend|server|app|project|build|tests?)",
            r"find (?:the )?bug",
            r"fix (?:the |all )?(?:failing )?tests?",
            r"run (?:the )?tests and (?:fix|tell|report|explain)",
            r"compare (?:these|the)? .* architectures?",
            r"search (?:the )?internet for .* and summarize",
            r"search (?:the )?web and compare",
            r"find (?:the )?file where i implemented",
            r"find (?:the )?project i was working on",
            r"investigate why",
            r"diagnose (?:the )?issue",
            r"check git status, run (?:the )?tests",
            r"set up my project"
        ]
        return any(re.search(pat, clean) or re.search(pat, raw_clean) for pat in reasoning_patterns)

    def _check_contextual_request(
        self,
        raw_text: str,
        normalized: str,
        clean: str,
        session_context: Optional[Dict[str, Any]]
    ) -> Optional[StructuredRequest]:
        """Resolves Layer 2 contextual requests (pronominals, user preferences, project context)."""
        ctx = session_context or {}
        last_target = ctx.get("last_target", "")
        last_action = ctx.get("last_action", "")
        active_project = ctx.get("active_project") or self.project_registry.current_project_alias or "jarvis"
        raw_clean = raw_text.lower().strip()

        # 1. Pronominals: "close it", "minimize it", "maximize it"
        pronominal_match = re.search(r"^(?:now\s+)?(close|exit|quit|minimize|maximize|kill|shut)\s+(?:it|this|that|the app)$", clean)
        if pronominal_match:
            verb = pronominal_match.group(1)
            target = last_target or "active_app"
            action = "close_application" if verb in ["close", "exit", "quit", "kill", "shut"] else (
                "minimize_application" if verb == "minimize" else "maximize_application"
            )
            intent = "CLOSE_APP" if "close" in action else "WINDOW_CONTROL"
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent=intent,
                action=action,
                target=target,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"resolved_from_context": True, "pronominal": True, "target": target}
            )

        # 2. Preference lookup: "open the browser I usually use" / "open my favorite editor"
        if "browser i usually use" in clean or "browser i normally use" in clean or "my default browser" in clean:
            pref_browser = persistent_memory.get_preference("default_browser", default="chrome")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="OPEN_APP",
                action="open_application",
                target=pref_browser,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"preference_resolved": True, "key": "default_browser", "value": pref_browser}
            )

        # 3. Preference lookup: "open my coding environment" / "open my editor"
        if clean in ["open my coding environment", "open my editor", "launch my editor"]:
            pref_editor = persistent_memory.get_preference("default_editor", default="vscode")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="OPEN_APP",
                action="open_application",
                target=pref_editor,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"preference_resolved": True, "key": "default_editor", "value": pref_editor}
            )

        # 4. Project context commands: "work on <project>", "switch to <project>"
        switch_match = re.search(r"^(?:work on|switch to)\s+([a-zA-Z0-9_\-]+)$", raw_clean) or re.search(r"^(?:work on|switch to)\s+([a-zA-Z0-9_\-]+)$", clean)
        if switch_match:
            proj_name = switch_match.group(1).lower()
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="PROJECT_CONTROL",
                action="switch_project",
                target=proj_name,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"project": proj_name}
            )

        # 5. Ambiguous project command: "open my project" / "run the tests"
        if clean in ["open my project", "open the project"]:
            known_projects = persistent_memory.list_projects()
            if not known_projects:
                known_projects = list(self.project_registry.projects.keys())

            if len(known_projects) > 1 and not ctx.get("explicit_project"):
                # Needs clarification
                proj_names = ", ".join([p.get("name", p) if isinstance(p, dict) else str(p).title() for p in known_projects[:3]])
                return StructuredRequest(
                    raw_text=raw_text,
                    normalized_text=normalized,
                    mode=MODE_CONTEXT,
                    layer=LAYER_2,
                    intent="CLARIFICATION_REQUIRED",
                    action="ask_clarification",
                    target="project",
                    confidence=0.90,
                    context_required=True,
                    planning_required=False,
                    clarification_prompt=f"Which project do you want — {proj_names}?",
                    entities={"ambiguous_type": "project", "options": known_projects}
                )
            else:
                return StructuredRequest(
                    raw_text=raw_text,
                    normalized_text=normalized,
                    mode=MODE_CONTEXT,
                    layer=LAYER_2,
                    intent="PROJECT_CONTROL",
                    action="open_project",
                    target=active_project,
                    confidence=0.90,
                    context_required=True,
                    planning_required=False,
                    entities={"project": active_project}
                )

        # 6. "run the tests" / "run tests" -> resolves to active project tests
        if clean in ["run the tests", "run tests", "execute tests"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="PROJECT_CONTROL",
                action="run_tests",
                target=active_project,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"project": active_project}
            )

        # 7. Memory question: "what did I tell you about my project yesterday?" / "what is my name?"
        if "what did i tell you" in clean or "what is my name" in clean or "do you remember" in clean:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="MEMORY_QUERY",
                action="recall_memory",
                target=clean,
                confidence=0.90,
                context_required=True,
                planning_required=False
            )

        return None

# Global singleton
intelligence_router = IntelligenceRouter()
