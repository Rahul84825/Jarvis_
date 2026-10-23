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

    def classify(self, raw_text: str, session_context: Optional[Dict[str, Any]] = None) -> StructuredRequest:
        """Alias for route() method for classification."""
        return self.route(raw_text, session_context)

    def route(self, raw_text: str, session_context: Optional[Dict[str, Any]] = None) -> StructuredRequest:
        """Analyzes and classifies raw user speech into a StructuredRequest."""
        t0 = time.perf_counter()
        norm_res = self.normalizer.normalize(raw_text)
        normalized = norm_res["normalized"]
        clean = normalized.lower().strip()
        raw_clean = raw_text.lower().strip()

        # Step 0: Explicit Model Prefix Routing (e.g. 'nvidia:', 'nemotron:')
        if any(raw_clean.startswith(pref) for pref in ["nvidia:", "nemotron:"]):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as LAYER 3 NEMOTRON (Explicit Prefix, Latency={elapsed_ms:.2f}ms)")
            clean_sub = re.sub(r"^(?:nvidia|nemotron):\s*", "", clean).strip()
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_REASONING,
                layer=LAYER_3,
                intent="NEMOTRON_REASONING",
                action="agent_plan_and_execute",
                target=clean_sub or clean,
                confidence=1.0,
                context_required=True,
                planning_required=True
            )

        # Step 0A: Instant Reflex for Stop Talking (Layer 1 Fast Local)
        if clean in ["stop", "stop talking", "stop speaking", "be quiet", "shut up", "hush", "silence"]:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as STOP_TALKING (Reflex, Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="STOP_TALKING",
                action="stop_speech",
                target="tts",
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        # Step 0B: User Corrections ("no, I meant...", "actually, use...", "Open Brave, not Chrome", "This method failed")
        is_correction = (
            re.search(r"^(?:no|actually|correction)[,:\s]+(?:i meant|use|not|it's|it is|i said)", clean) or
            clean.startswith("no, ") or clean.startswith("no i meant") or
            re.search(r",\s*not\s+[a-zA-Z0-9_\-]+", clean) or
            re.search(r"\bnot\s+(?:the\s+)?(?:folder|directory|file|path)\s+(?:i\s+meant|wanted)\b", clean) or
            re.search(r"\bthat\s+is\s+not\s+(?:the\s+)?(?:folder|directory|file|path)\b", clean) or
            re.search(r"\bthis\s+method\s+failed\b", clean) or
            clean.startswith("instead of ")
        )
        if is_correction:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as CORRECTION (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="CORRECTION",
                action="apply_correction",
                target=clean,
                confidence=0.98,
                context_required=True,
                planning_required=False
            )

        # Step 0C: Explicit Model / Provider Routing ("Ask Nemotron...", "Ask NVIDIA...")
        nemotron_match = re.search(r"^(?:ask\s+)?(?:nvidia|nemotron)(?:\s+to|\s*[,:]\s*|\s+model\s+to|\s+ai\s+to|\s+explain\s+)(.+)$", clean)
        if nemotron_match:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            prompt = nemotron_match.group(1).strip()
            logger.info(f"[ROUTER] Classified as NEMOTRON_REASONING (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_REASONING,
                layer=LAYER_3,
                intent="NEMOTRON_REASONING",
                action="agent_plan_and_execute",
                target=prompt if prompt.startswith("explain") else f"explain {prompt}",
                confidence=0.98,
                context_required=True,
                planning_required=True,
                entities={"prompt": prompt, "provider": "nvidia"}
            )

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
            "media_control", "open_website", "browser_action", "browser.action", "terminal_execute", "file_access",
            "web_search", "workspace.launch", "workspace_control", "launch_workspace",
            "application.launch", "application.properties", "application.install_dir",
            "application.settings", "application.metadata", "application.status",
            "application.list_installed", "application.refresh",
            "desktop.get_context", "desktop.enter_text", "desktop.search_in_app",
            "desktop.replace_selection", "desktop.send_message",
            "desktop_interaction.type_text", "desktop_interaction.write_reply",
            "desktop_interaction.search_app", "desktop_interaction.replace_selection",
            "desktop_interaction.continue_writing", "desktop_interaction.edit_draft",
            "desktop_interaction.paste_text", "desktop_interaction.send_message",
            "screen.analyze", "screen.explain", "screen_understanding.analyze", "screen_understanding.explain",
            "files.create", "files.search", "files.open", "file_management.create_file", "file_management.search",
            "file_management.open_project", "project.inspect", "ai.get_providers", "ai.update_provider",
            "ai.cache_stats", "ai.clear_cache", "ai.forget_cache",
            "ai_management.list_providers", "ai_management.update_provider",
            "ai_management.cache_stats", "ai_management.clear_cache", "ai_management.forget_cache",
            "system_telemetry", "greeting", "thank_you", "goodbye", "help",
            "identity", "repeat_response", "status_request", "acknowledgement",
            "affirmation", "negation", "how_are_you", "status_check",
            "turn_on_camera", "turn_off_camera", "start_hand_tracking", "stop_hand_tracking", "camera_snapshot",
            "social_humor", "social_personality", "social_chat", "social_greeting", "about"
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
        # Desktop Intelligence, Screen Understanding & File Creation/Search Bypass
        if (
            re.search(r"^(?:explain|analyze|inspect|summarize)\s+(?:my\s+|this\s+|the\s+)?(?:screen|page|code|error|graph|pdf|point|section)\b", clean, re.IGNORECASE) or
            re.search(r"^(?:where\s+did\s+i\s+save|where\s+is\s+my\s+.*(?:program|file|code|repository|project|folder|readme)|find\s+(?:the\s+)?.*(?:created|saved|written))\b", clean, re.IGNORECASE) or
            re.search(r"^(?:what\s+are\s+the\s+important\s+points|what\s+does\s+this\s+error\s+mean|what\s+is\s+this\s+button\s+used\s+for|what\s+is\s+on\s+my\s+screen|compare\s+these\s+two)\b", clean, re.IGNORECASE) or
            clean.startswith("explain point ") or clean.startswith("explain the ") or clean.startswith("i still don't understand") or
            "short answer first" in clean or "like i'm a beginner" in clean or
            clean.startswith("create a ") or clean.startswith("write a ") or clean.startswith("generate a ") or clean.startswith("save this explanation") or
            "ai provider" in clean or "ai providers" in clean or "list ai" in clean or
            "cache stat" in clean or "caching save" in clean or "clear cache" in clean or ("forget" in clean and "cache" in clean)
        ):
            return False

        # Explicit search bypass (must be evaluated in Layer 1, not question fallback)
        if clean.startswith("search ") or "search youtube" in clean or "youtube search" in clean or "search the web" in clean or "search brave" in clean or "search chrome" in clean:
            return False

        # Math calculation bypass
        if any(op in clean for op in ["times", "plus", "minus", "divided by", "multiplied by", "+", "*", "/"]) and any(c.isdigit() for c in clean):
            return False

        # Time & Date bypass
        if any(t in clean for t in [
            "what time is it", "what's the time", "whats the time", "what is the time",
            "what is the date", "what's the date", "whats the date", "what day is it",
            "tell me what time", "tell me the time", "current time", "what time do you have",
            "time now", "today's date", "todays date", "today s date", "today date",
            "what date is", "tell me the date", "what is today"
        ]):
            return False

        # Capabilities, Help, Identity & Social Intelligence bypass
        social_identity_bypass = [
            "what can you do", "what can jarvis do", "what are your capabilities",
            "what commands do you know", "what do you do", "show capabilities",
            "how can you help", "who are you", "who made you", "who built you",
            "who created you", "who is your developer", "who is your creator",
            "what is your name", "what's your name", "what does jarvis stand for",
            "what's jarvis stand for", "what does the name jarvis stand for",
            "what is your purpose", "what's your purpose", "are you a real person",
            "are you an ai", "are you real", "are you human", "are you like chatgpt",
            "what makes you different", "what makes you intelligent",
            "are you always listening", "can you hear me", "can you control my computer",
            "can you control this pc", "can you work without internet", "can you work offline",
            "what can you do offline", "can you search youtube", "can you open applications",
            "can you search the web", "what voice commands do you understand",
            "show all commands", "tell me a joke", "tell me a programming joke",
            "tell me a coding joke", "roast me", "give me a savage reply", "be sarcastic",
            "say something funny", "tell me a dark joke", "give me a nerdy joke",
            "make a joke about programmers", "tell me a random fun fact", "give me a tech fact",
            "introduce yourself dramatically", "roast my code", "say something that sounds like a futuristic ai",
            "fun fact", "another one", "tell me another", "be more funny", "be professional",
            "stop being sarcastic", "talk casually", "keep it short", "explain things in detail",
            "be more dramatic", "use your normal personality", "don't tell jokes for now",
            "enable humor", "disable humor", "i'm bored", "im bored", "guess what",
            "tell me something interesting", "surprise me", "let's talk", "lets talk"
        ]
        if any(h in clean for h in social_identity_bypass):
            return False

        # Application discovery, properties, installation, and browser inquiry bypass (Phase 6)
        if re.search(r"\b(is|check\s+if)\s+.+?\s+installed\b", clean) or \
           re.search(r"\bwhere\s+is\s+.+?\s+installed\b", clean) or \
           re.search(r"\bwhat\s+version\s+of\s+.+?\s+is\s+installed\b", clean) or \
           re.search(r"\b(?:what\s+apps|what\s+applications|what\s+browsers|which\s+browsers)\b", clean) or \
           "installed applications" in clean or "available browsers" in clean or "my browsers" in clean or \
           "properties" in clean or "install folder" in clean or "installation folder" in clean or \
           "installation directory" in clean or "installed yesterday" in clean:
            return False

        # Desktop Interaction & Text Entry Bypass (Phase 7)
        if any(clean.startswith(p) for p in [
            "write a reply", "write a response", "draft a reply", "draft a response",
            "reply to this", "type this into", "type into", "type this in",
            "paste this into", "enter this code", "fill in the", "put this into",
            "search for", "enter the search term", "replace the selected text",
            "replace selection", "continue writing", "make the current draft", "send the message", "submit the form"
        ]) or "in this application" in clean or "in the current application" in clean or "in the search bar" in clean:
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

        # Follow-up questions and single-command task continuations should be routed to context, not complex reasoning
        if any(clean.startswith(p) for p in ["why did it fail", "why did that fail", "what went wrong", "what have you completed", "cancel the task", "stop what you're doing"]):
            return False
        if re.search(r"^(?:now\s+)?open\s+(?:the\s+)?(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|\d+)(?:st|nd|rd|th)?\s+result$", clean):
            return False
        if clean.startswith("do the same on ") or clean in ["try that again", "skip this step", "continue", "continue task"]:
            return False

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
            r"set up my project",
            # Multi-step agentic execution patterns
            r"(?:open|launch)\s+[a-zA-Z0-9_\-\s]+(?:,|,\s*and|\s+and|\s+then)\s+(?:search|navigate|write|explain|tell|help)",
            r"search\s+[a-zA-Z0-9_\-\s]+(?:,|,\s*and|\s+and|\s+then)\s+(?:open|tell|explain|navigate)",
            r"open\s+notepad\s+and\s+write",
            r"tell me when the page is ready",
            r"(?:and|then)\s+open\s+(?:the\s+)?(?:first|1st|second|2nd|third|3rd|\d+)\s+result",
            r"find\s+a\s+.*and\s+explain",
            r"help\s+me\s+draft",
            r"(?:find|search)\s+(?:the\s+|a\s+)?.*(?:online|on the web|on the internet|news)?\s+and\s+(?:explain|summarize)(?:\s+it)?",
            r"^(?:ask\s+)?(?:nvidia|nemotron)\b",
            # Programming, DSA, Algorithmic and Cloud Reasoning
            r"(?:explain|solve|write|implement|debug)\s+.*(?:in\s+c\+\+|in\s+cpp|in\s+python|algorithm|data\s+structure|leetcode|binary\s+search|merge\s+sort|quicksort|bfs|dfs|dynamic\s+programming)",
            r"explain\s+(?:leetcode|binary\s+search|merge\s+sort|quicksort|depth\s+first|breadth\s+first)",
            r"time\s+(?:and\s+)?(?:space\s+)?complexity|space\s+complexity",
            r"why\s+does\s+my\s+.*(?:algorithm|code|function|solution)\s+fail",
            r"compare\s+.*sort\s+and\s+.*sort",
            r"explain\s+this\s+error\s+and\s+suggest\s+(?:a\s+)?fix",
            r"plan\s+a\s+safe\s+sequence\s+of\s+steps",
            r"based\s+on\s+our\s+previous\s+question,\s+explain",
        ]
        return any(re.search(pat, clean) or re.search(pat, raw_clean) for pat in reasoning_patterns)

    def _check_contextual_request(
        self,
        raw_text: str,
        normalized: str,
        clean: str,
        session_context: Optional[Dict[str, Any]]
    ) -> Optional[StructuredRequest]:
        """Resolves Layer 2 contextual requests (pronominals, user preferences, project context, task follow-ups)."""
        ctx = session_context or {}
        last_target = ctx.get("last_target", "")
        last_action = ctx.get("last_action", "")
        active_project = ctx.get("active_project") or self.project_registry.current_project_alias or "jarvis"
        raw_clean = raw_text.lower().strip()

        # Contextual follow-up 00: Task Follow-ups & Lifecycle Controls
        # Cancellation / Abort
        if clean in [
            "cancel", "cancel that", "cancel the task", "cancel task", "stop what you're doing",
            "abort this workflow", "abort the workflow", "abort workflow", "abort task", "cancel the workflow",
            "forget about that", "never mind", "cancel that operation"
        ] or clean.startswith("cancel the task") or clean.startswith("stop what you're doing") or clean == "stop task" or clean.startswith("cancel that"):
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="cancel",
                target="active_task",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Retry
        if clean in ["try that again", "try again", "retry the task", "retry task", "retry last task", "retry"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="retry",
                target="last_task",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Skip Step
        if clean in ["skip this step", "skip the current step", "skip step", "skip current step"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="skip_step",
                target="current_step",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Continue / Resume
        if clean in [
            "continue", "continue task", "continue the task", "continue from where you stopped",
            "resume", "resume task", "resume workflow", "go on", "keep going", "okay continue", "ok continue",
            "now continue", "proceed", "carry on"
        ]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="continue",
                target="active_task",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Task Progress & Status
        if clean in [
            "what have you completed", "what have you completed?", "what did you do", "what did you do?",
            "what have you done", "what have you done?", "what's completed", "what's completed?",
            "what is completed?", "task status", "show task status", "show task progress", "what is the task status"
        ]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="status",
                target="task_status",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Failure Explanation
        if clean in [
            "why did it fail", "why did it fail?", "why did that fail", "why did that fail?",
            "what went wrong", "what went wrong?", "explain the failure", "explain why it failed", "why did the task fail"
        ]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="explain_failure",
                target="failure_reason",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Search Result Follow-up ("now open the second result", "open the 1st result")
        res_match = re.search(r"^(?:now\s+)?open\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|\d+)(?:st|nd|rd|th)?\s+result$", clean)
        if res_match:
            idx_str = res_match.group(1).lower()
            ord_map = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5}
            idx_num = ord_map.get(idx_str, int(idx_str) if idx_str.isdigit() else 1)
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="open_result",
                target=str(idx_num),
                confidence=0.99,
                context_required=True,
                planning_required=False,
                entities={"index": idx_num - 1}
            )

        # Search Provider Switch ("do the same on youtube", "do the same on google")
        if clean in ["do the same on youtube", "try the same on youtube", "search the same on youtube", "do that on youtube", "now do the same on youtube"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="switch_provider",
                target="youtube",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )
        if clean in ["do the same on google", "try the same on google", "search the same on google", "do that on google", "now do the same on google"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="switch_provider",
                target="google",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Reopen Recent Tab ("open the tab you just used")
        if clean in ["open the tab you just used", "open the tab we just used", "reopen the tab you just used", "switch to the tab you just used"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="reopen_tab",
                target="recent_tab",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Contextual follow-up 0A: Social humor "another one" / "tell me another"
        if clean in ["another one", "tell me another", "give me another", "give me another one", "one more", "tell another", "another"] or clean.startswith("another "):
            from core.social_engine import social_engine
            last_soc = getattr(social_engine, "_last_social_type", "joke") or "joke"
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="SOCIAL_HUMOR",
                action="followup",
                target="another",
                confidence=0.98,
                context_required=True,
                planning_required=False,
                entities={"last_social_type": last_soc}
            )

        # Contextual follow-up 0B: Creator other work follow-up
        if any(clean.startswith(p) for p in ["what else did they build", "what else did he build", "what else did she build", "what else did they make", "what else did he make"]):
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="IDENTITY",
                action="explain_identity",
                target="creator_other_work",
                confidence=0.98,
                context_required=True,
                planning_required=False,
                entities={"sub_type": "creator_other_work"}
            )

        # Contextual follow-up 0C: Follow-up to YouTube search capability inquiry
        if ctx.get("last_target") == "youtube" or ctx.get("last_topic") == "youtube":
            find_match = re.match(r"^(?:find(?:\s+me)?|search(?:\s+for)?|look\s+up)\s+(.+)$", clean)
            if find_match:
                extracted = find_match.group(1).strip()
                return StructuredRequest(
                    raw_text=raw_text,
                    normalized_text=normalized,
                    mode=MODE_CONTEXT,
                    layer=LAYER_2,
                    intent="WEB_SEARCH",
                    action="search",
                    target=extracted.lower(),
                    confidence=0.98,
                    context_required=True,
                    planning_required=False,
                    entities={"provider": "youtube", "browser": "default", "query": extracted, "raw_text": raw_text}
                )

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
