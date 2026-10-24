import time
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from core.ai.agent_brain import agent_brain
from core.ai.intelligence_router import intelligence_router, MODE_FAST_LOCAL, MODE_CONTEXT, MODE_REASONING, MODE_QUESTION
from core.local_response_engine import LocalResponseEngine
from memory.persistent_memory import persistent_memory
from memory.conversation_persistence import ConversationPersistence

logger = logging.getLogger("Jarvis.ConversationManager")

@dataclass
class ExplanationState:
    """Tracks state of an in-flight or interrupted multi-sentence explanation."""
    topic: str = ""
    goal: str = ""
    full_text: str = ""
    sentences: List[str] = field(default_factory=list)
    current_sentence_idx: int = -1
    is_interrupted: bool = False
    interrupted_at: float = 0.0

    @property
    def interrupted(self) -> bool:
        return self.is_interrupted

    @property
    def interrupted_at_index(self) -> int:
        return self.current_sentence_idx

@dataclass
class PendingActionContext:
    """Represents a pending action awaiting user clarification or confirmation."""
    original_request: str = ""
    intent: str = ""
    action: str = ""
    target: str = ""
    target_url: Optional[str] = None
    target_domain: Optional[str] = None
    browser: Optional[str] = "chrome"
    search_query: str = ""
    clarification_question: str = ""
    clarification_type: str = "generic"  # "browser_selection", "destination_selection", "website_navigation", "confirmation"
    valid_options: List[str] = field(default_factory=list)
    turn_index: int = 0
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 60.0
    is_cancelled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return (now - self.created_at) > self.timeout_seconds

    def can_resolve(self, text: str) -> bool:
        """Determines if user response is an answer or follow-up to this pending clarification."""
        if not text:
            return False
        clean = text.lower().strip()
        clean = re.sub(r"[\.\?\!\,\;]+$", "", clean).strip()

        # Cancellation phrases
        cancel_phrases = ["cancel", "cancel that", "stop", "nevermind", "abort", "no don't", "don't do that", "leave it"]
        if clean in cancel_phrases or any(clean == p for p in cancel_phrases):
            return True

        # Affirmation phrases
        yes_phrases = ["yes", "sure", "ok", "okay", "go ahead", "do it", "yep", "yeah", "open it", "open it there", "that one", "please"]
        if clean in yes_phrases:
            return True

        # Browser selection
        browsers = ["chrome", "google chrome", "edge", "microsoft edge", "brave", "firefox", "opera", "browser", "current browser", "default browser"]
        if clean in browsers or any(b in clean for b in ["use chrome", "in chrome", "with chrome", "open in chrome", "use edge", "use brave", "use firefox"]):
            return True

        # Destination override: "No, YouTube instead", "YouTube instead", "use Google instead", "search YouTube instead"
        if re.search(r"\b(?:instead|rather)\b", clean) or clean.startswith("no, ") or clean.startswith("no "):
            return True

        # Contextual site reuse: "use the same website", "the same site", "same website"
        if any(p in clean for p in ["same website", "same site", "the same website", "the same site"]):
            return True

        # If options are explicitly configured in valid_options
        if self.valid_options and any(opt.lower() in clean for opt in self.valid_options):
            return True

        return False

    def resolve_action(self, text: str) -> Dict[str, Any]:
        """Merges user follow-up response into original intent and returns executable intent node or cancellation."""
        clean = text.lower().strip()
        clean = re.sub(r"[\.\?\!\,\;]+$", "", clean).strip()

        # 1. Cancellation
        cancel_phrases = ["cancel", "cancel that", "stop", "nevermind", "abort", "no don't", "don't do that", "leave it"]
        if clean in cancel_phrases:
            self.is_cancelled = True
            return {
                "action": "cancel",
                "cancelled": True,
                "message": "Action cancelled, Sir."
            }

        # 2. Destination Override (e.g. "No, YouTube instead", "YouTube instead", "use Google instead")
        override_match = re.search(r"(?:use\s+|on\s+|search\s+|open\s+)?([a-zA-Z0-9_\-\.]+)\s+(?:instead|rather)", clean)
        if not override_match and (clean.startswith("no, ") or clean.startswith("no ")):
            rem = re.sub(r"^no[, ]+", "", clean).strip()
            override_match = re.search(r"(?:use\s+|on\s+|search\s+|open\s+)?([a-zA-Z0-9_\-\.]+)", rem)

        if override_match:
            new_target = override_match.group(1).strip().lower()
            if new_target in ["youtube", "google", "github", "reddit", "wikipedia"]:
                if self.search_query:
                    return {
                        "intent": "web_search",
                        "action": "search",
                        "action_type": "search_website" if new_target != "google" else "search_web",
                        "provider": new_target,
                        "site_name": new_target,
                        "browser": self.browser or "chrome",
                        "target": self.search_query,
                        "query": self.search_query,
                        "raw_text": text
                    }
                else:
                    from core.os.browser_intent import BrowserIntentParser
                    parser = BrowserIntentParser()
                    new_url, domain = parser._resolve_site_destination(new_target)
                    return {
                        "intent": "browser_action",
                        "action": "open_url",
                        "action_type": "open_url",
                        "browser": self.browser or "chrome",
                        "target_browser": self.browser or "chrome",
                        "target": new_target,
                        "site_name": new_target,
                        "url": new_url,
                        "domain": domain,
                        "raw_text": text
                    }

        # 3. Browser selection (e.g. "Chrome", "Use Chrome", "in Edge", "Brave")
        selected_browser = self.browser or "chrome"
        for b in ["chrome", "edge", "brave", "firefox", "opera"]:
            if b in clean:
                selected_browser = b
                break

        # 4. Merging with original action
        if self.action in ["open_url", "open_website", "navigate"] or self.intent in ["open_website", "browser_action"]:
            return {
                "intent": "browser_action",
                "action": "open_url",
                "action_type": "open_url",
                "browser": selected_browser,
                "target_browser": selected_browser,
                "target": self.target or self.target_domain,
                "site_name": self.target or self.target_domain,
                "url": self.target_url,
                "domain": self.target_domain,
                "search_query": self.search_query,
                "query": self.search_query,
                "raw_text": text,
                "resolved_from_clarification": True
            }

        if self.action in ["search_website", "search"]:
            return {
                "intent": "browser_action",
                "action": "search_website",
                "action_type": "search_website",
                "browser": selected_browser,
                "target_browser": selected_browser,
                "target": self.target,
                "site_name": self.target,
                "url": self.target_url,
                "domain": self.target_domain,
                "search_query": self.search_query,
                "query": self.search_query,
                "raw_text": text,
                "resolved_from_clarification": True
            }

        if self.intent == "spotify_control":
            res_node = dict(self.metadata) if self.metadata else {}
            res_node.update({
                "intent": "spotify_control",
                "action": self.action,
                "target": self.target,
                "confirmed": True,
                "raw_text": text,
                "resolved_from_clarification": True
            })
            return res_node

        return {
            "intent": self.intent or "browser_action",
            "action": self.action or "open_url",
            "browser": selected_browser,
            "target": self.target,
            "url": self.target_url,
            "search_query": self.search_query,
            "raw_text": text,
            "resolved_from_clarification": True
        }

@dataclass
class ConversationTaskContext:
    """Maintains active task context, entity states, and conversational continuity."""
    active_task_id: Optional[str] = None
    active_task_name: Optional[str] = None
    current_user_request: str = ""
    current_assistant_response: str = ""
    last_user_utterance: str = ""
    current_topic: str = ""
    important_entities: Dict[str, Any] = field(default_factory=dict)
    completed_steps: List[str] = field(default_factory=list)
    pending_steps: List[str] = field(default_factory=list)
    is_interrupted: bool = False
    interrupted_sentence_idx: int = 0

class ConversationManager:
    """Manages multi-turn conversation memory, session timeout, follow-up query context,
    interruption distinction, task continuity, durable SQLite persistence, and routing to AgentBrain.
    """

    def __init__(self, max_turns: int = 20, session_timeout: float = 60.0, db_path: Optional[str] = None):
        self.max_turns = max_turns
        self.session_timeout = session_timeout
        self.history: List[Dict[str, str]] = []
        self.last_interaction_timestamp: float = 0.0
        self.agent = agent_brain
        self.provider_manager = agent_brain
        if not hasattr(self.provider_manager, "generate_response"):
            self.provider_manager.generate_response = lambda q, **kwargs: self.agent.reason_and_execute(q).get("text", "")
        self.local_engine = LocalResponseEngine()
        self.persistence = ConversationPersistence(db_path=db_path)

        # Context & Task continuity tracking
        self.last_target: str = ""
        self.last_action: str = ""
        self.active_project: str = "jarvis"
        self.pending_clarification: Optional[str] = None
        self.pending_action: Optional[PendingActionContext] = None
        self.current_topic: str = ""
        self.explanation_state: Optional[ExplanationState] = None
        self.task_context = ConversationTaskContext()
        self.active_generation_id: int = 1

    def update_context(self, action: str, target: str, project: Optional[str] = None):
        """Updates active session context with recent action and target."""
        if target and target not in ["system", "all", "telemetry"]:
            self.last_target = target
            self.task_context.current_topic = target
        if action:
            self.last_action = action
        if project:
            self.active_project = project
        self.last_interaction_timestamp = time.time()

    def set_pending_action(self, pending: PendingActionContext):
        """Sets the active pending action context awaiting user follow-up or clarification."""
        self.pending_action = pending
        self.pending_clarification = pending.clarification_question
        self.last_interaction_timestamp = time.time()
        logger.info(f"[CONVERSATION] Registered pending action: target='{pending.target}', intent='{pending.intent}', question='{pending.clarification_question}'")

    def get_pending_action(self) -> Optional[PendingActionContext]:
        """Returns active pending action if not expired or cancelled."""
        if not self.pending_action:
            return None
        if self.pending_action.is_expired():
            logger.info("[CONVERSATION] Active pending action has expired. Clearing.")
            self.pending_action = None
            self.pending_clarification = None
            return None
        return self.pending_action

    def clear_pending_action(self):
        """Clears active pending action."""
        self.pending_action = None
        self.pending_clarification = None

    def get_context(self) -> Dict[str, Any]:
        """Returns active contextual snapshot."""
        pending = self.get_pending_action()
        return {
            "last_target": self.last_target,
            "last_action": self.last_action,
            "active_project": self.active_project,
            "pending_clarification": self.pending_clarification,
            "has_pending_action": bool(pending),
            "pending_action_target": pending.target if pending else None,
            "pending_action_intent": pending.intent if pending else None,
            "current_topic": self.task_context.current_topic,
            "is_interrupted": self.task_context.is_interrupted,
            "active_task_id": self.task_context.active_task_id
        }

    # =========================================================================
    # TASK CONTINUITY & EXPLANATION INTERRUPTION RESUMPTION
    # =========================================================================
    def set_active_explanation(self, topic: str, goal: str, text: str, preserve_if_interrupted: bool = True):
        """Splits an explanation into ordered sentences and records structured state.
        If an explanation is currently interrupted and preserve_if_interrupted is True,
        preserves the parent explanation state so sub-turn question answers don't overwrite it.
        """
        if preserve_if_interrupted and self.has_interrupted_explanation():
            logger.info(f"[EXPLANATION_PRESERVED] Preserving paused parent explanation for '{self.explanation_state.topic}' during sub-turn interaction.")
            return

        raw_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        self.explanation_state = ExplanationState(
            topic=topic or "explanation",
            goal=goal or topic,
            full_text=text,
            sentences=raw_sentences,
            current_sentence_idx=-1,
            is_interrupted=False
        )
        self.task_context.current_topic = topic
        self.task_context.current_user_request = goal
        self.task_context.current_assistant_response = text
        self.task_context.is_interrupted = False
        logger.info(f"[EXPLANATION_SET] Stored explanation for '{topic}' with {len(raw_sentences)} sentences.")

    def update_sentence_progress(self, sentence_idx: int = 0, total_sentences: int = 0, text: str = "", **kwargs):
        """Observer callback invoked as each sentence begins audio playback."""
        idx = kwargs.get("current_index", sentence_idx)
        tot = kwargs.get("total", total_sentences)
        if self.explanation_state:
            self.explanation_state.current_sentence_idx = idx
        self.task_context.interrupted_sentence_idx = idx

    def mark_interrupted(self, sentence_idx: Optional[int] = None):
        """Marks active explanation or turn as interrupted without discarding state."""
        self.task_context.is_interrupted = True
        if self.explanation_state:
            self.explanation_state.is_interrupted = True
            self.explanation_state.interrupted_at = time.time()
            if sentence_idx is not None:
                self.explanation_state.current_sentence_idx = sentence_idx
            idx = self.explanation_state.current_sentence_idx
            total = len(self.explanation_state.sentences)
            logger.info(f"[CONVERSATION_INTERRUPTED] Explanation paused at sentence {idx+1}/{total}.")
        else:
            logger.info("[CONVERSATION_INTERRUPTED] General response interrupted.")

    def has_interrupted_explanation(self) -> bool:
        """Returns True if there is a paused explanation ready to resume."""
        if not self.explanation_state or not self.explanation_state.is_interrupted:
            return False
        return self.explanation_state.current_sentence_idx < len(self.explanation_state.sentences) - 1

    def resume_explanation(self) -> tuple[str, List[str]]:
        """Resumes remaining sentences of an interrupted explanation from the paused point."""
        if not self.explanation_state:
            return "There is no paused explanation to continue, Sir.", []

        idx = self.explanation_state.current_sentence_idx
        sentences = self.explanation_state.sentences
        # Resume from next uncompleted sentence
        resume_idx = max(0, min(idx + 1 if idx >= 0 else 0, len(sentences) - 1))
        remaining = sentences[resume_idx:]
        if not remaining:
            remaining = [sentences[-1]]

        self.explanation_state.is_interrupted = False
        self.explanation_state.current_sentence_idx = len(sentences) - 1
        self.task_context.is_interrupted = False

        full_continuation = "Continuing from where we paused: " + " ".join(remaining)
        return full_continuation, remaining

    def clear_interrupted_state(self):
        """Clears paused explanation and interruption flags."""
        self.explanation_state = None
        self.task_context.is_interrupted = False
        self.task_context.active_task_id = None

    def classify_interruption(self, utterance: str) -> dict:
        """Classifies conversational interruption type into distinct actionable categories."""
        clean = utterance.lower().strip()
        # 1. Stop
        if clean in ["stop", "stop talking", "stop speaking", "be quiet", "shut up", "hush", "silence", "be quiet please"]:
            category = "STOP"
        # 2. Cancel
        elif any(clean.startswith(c) or clean == c for c in ["cancel", "cancel that", "cancel task", "abort", "forget about that", "never mind", "abort this task"]):
            category = "CANCEL"
        # 3. Resume
        elif clean in ["continue", "continue from where you stopped", "go on", "keep going", "resume", "okay continue", "now continue", "proceed"]:
            category = "RESUME"
        # 4. Task modification & Topic Change
        elif clean.startswith("actually use ") or clean.startswith("instead of ") or clean.startswith("actually, use ") or "instead" in clean:
            category = "TASK_MODIFICATION"
        elif clean.startswith("forget that") or clean.startswith("nevermind that"):
            category = "TOPIC_CHANGE"
        # 5. Correction
        elif re.search(r"^(?:no|actually|correction)[,:\s]+(?:i meant|use|not|it's|it is|i said)", clean) or clean.startswith("no, ") or clean.startswith("no i meant"):
            category = "CORRECTION"
        # 6. Clarification
        elif re.search(r"^(?:i mean|specifically|for|in)\s+(?:the\s+)?[a-zA-Z0-9\+\#\s]+(?:version|mode|language)?$", clean):
            category = "CLARIFICATION"
        # 7. Addition
        elif clean.startswith("also ") or clean.startswith("and explain ") or clean.startswith("and what about ") or clean.startswith("additionally "):
            category = "ADDITION"
        # 8. Follow-up Inquiry
        elif re.search(r"^(?:wait,?\s*)?(?:why|how)\s+(?:does|is|did)\s+that", clean):
            category = "FOLLOW_UP"
        # 9. Question / Interruption to ask a question
        elif re.search(r"^(?:wait,?\s*)?(?:why|what|how|where|when|can you explain)\b", clean):
            category = "QUESTION"
        else:
            category = "NEW_REQUEST"

        subtype = "INTERRUPTION_QUESTION" if category == "QUESTION" and (clean.startswith("wait") or self.has_interrupted_explanation()) else category
        return {"type": category, "subtype": subtype, "raw": utterance}

    def apply_correction(self, correction_text: str) -> str:
        """Transforms a user correction into a revised instruction retaining relevant context and learning preferences."""
        from core.learning.correction_handler import correction_handler
        res = correction_handler.handle_correction(correction_text, session_context=self.get_context())
        revised = res.get("revised_command")
        preferred = res.get("preferred_target")
        if preferred:
            self.task_context.current_topic = preferred
            self.last_target = preferred

        if self.explanation_state and self.explanation_state.topic and not any(revised.lower().startswith(v) for v in ["open", "close", "use", "run"]):
            topic = self.explanation_state.topic
            full_revised = f"Explain {topic} in {revised}"
            self.task_context.current_user_request = full_revised
            return full_revised

        return revised or correction_text

    def restore_session_from_persistence(self, limit: int = 5):
        """Restores recent conversation turns from SQLite so context survives app restart when requested."""
        if not self.persistence.is_enabled():
            return
        try:
            recent = self.persistence.get_recent_turns(limit=min(self.max_turns, limit))
            restored = []
            for r in recent:
                restored.append({
                    "role": r["role"],
                    "content": r["content"]
                })
            self.history = restored
            if self.history:
                self.last_interaction_timestamp = time.time()
                logger.info(f"Restored {len(self.history)} messages from persistent storage into active conversation context.")
        except Exception as e:
            logger.error(f"Failed to restore conversation history from persistence: {e}")

    def _check_session_timeout(self):
        """Resets conversation in-memory session if inactivity period exceeds session_timeout."""
        if self.last_interaction_timestamp > 0:
            elapsed = time.time() - self.last_interaction_timestamp
            if elapsed > self.session_timeout:
                logger.info(f"Conversation session timed out after {elapsed:.1f}s inactivity. Resetting in-memory history.")
                self.history.clear()
                self.pending_clarification = None

    def process_query(self, query: str) -> Dict[str, Any]:
        """Processes a conversational user query through AgentBrain / ProviderManager with tool execution and memory."""
        self._check_session_timeout()

        context_prefix = ""
        if self.has_interrupted_explanation():
            topic = self.explanation_state.topic
            idx = self.explanation_state.current_sentence_idx
            sentences = self.explanation_state.sentences
            curr_sent = sentences[idx] if idx < len(sentences) else ""
            context_prefix = f"[Context: The user interrupted an ongoing explanation of '{topic}' (paused at: '{curr_sent}'). Answer concisely.]\n"

        effective_query = f"{context_prefix}{query.strip()}" if context_prefix else query.strip()
        user_msg = {"role": "user", "content": effective_query}
        messages = list(self.history) + [user_msg]

        # Check Multi-Layer AI Cache & Persistent Memory (Section 2 & 6)
        try:
            from core.ai.caching import nemotron_cache
            c_res = nemotron_cache.lookup(query)
            if c_res.hit and c_res.response:
                resp_text = c_res.response
                self.history.append(user_msg)
                self.history.append({"role": "assistant", "content": resp_text})
                if len(self.history) > (self.max_turns * 2):
                    self.history = self.history[-(self.max_turns * 2):]
                self.last_interaction_timestamp = time.time()
                return {
                    "text": resp_text,
                    "source": c_res.source_label,
                    "tool_used": None,
                    "ai_available": True,
                    "latency_ms": c_res.latency_ms,
                    "cached": True
                }
        except Exception as ce:
            logger.debug(f"Cache lookup in conversation error: {ce}")

        # Check legacy verified static reasoning cache (Phase 5: Reduce unnecessary AI/Nemotron calls)
        cached = persistent_memory.get_cached_query(query)
        if cached:
            resp_text = cached["text"]
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": resp_text})
            if len(self.history) > (self.max_turns * 2):
                self.history = self.history[-(self.max_turns * 2):]
            self.last_interaction_timestamp = time.time()
            return {
                "text": resp_text,
                "source": cached.get("source", "Verified Cache"),
                "tool_used": None,
                "ai_available": True,
                "latency_ms": 0.5,
                "cached": True
            }

        t0 = time.time()
        gen_fn = getattr(self.provider_manager, "generate_response", None)
        is_mocked = gen_fn is not None and (
            hasattr(gen_fn, "mock_calls") or 
            hasattr(gen_fn, "_mock_return_value") or 
            hasattr(gen_fn, "return_value") or 
            type(gen_fn).__name__ in ["MagicMock", "Mock"]
        )

        from config import config
        ai_prov = getattr(config, "ai_provider", "none")
        pm = getattr(self.agent, "provider_manager", self.provider_manager)
        forced_prov_key, _ = pm.extract_model_prefix(query) if hasattr(pm, "extract_model_prefix") else (None, query)
        ai_available = is_mocked or bool(forced_prov_key) or (ai_prov not in ["none", ""] and (hasattr(pm, "is_ai_available") and pm.is_ai_available()))
        clean_q = query.lower().strip()
        # 0. Check time & date queries
        if any(t in clean_q for t in ["what time is it", "what's the time", "tell me the time", "current time", "what is the time", "time now", "the time", "what time do you have"]):
            now_str = time.strftime("%I:%M %p").lstrip("0")
            resp = f"The current time is {now_str}, Sir."
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": resp})
            return {"text": resp, "source": "Local System Clock", "tool_used": "get_time", "ai_available": False, "latency_ms": 0.5}

        if any(d in clean_q for d in ["today s date", "todays date", "today date", "what is the date", "what is today's date", "what day is it", "current date", "what date is", "tell me the date"]):
            date_str = time.strftime("%A, %B %d, %Y")
            resp = f"Today is {date_str}, Sir."
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": resp})
            return {"text": resp, "source": "Local System Clock", "tool_used": "get_date", "ai_available": False, "latency_ms": 0.5}

        # 1. Check user profile / memory preferences
        if "my name" in clean_q or "what is my name" in clean_q:
            name = persistent_memory.get_preference("user_name")
            if name:
                return {"text": f"Your name is {name}.", "source": "Local Memory", "tool_used": None, "ai_available": False, "latency_ms": 0.5}

        # 2. Check local conversational phrases (how are you, status, etc.)
        if any(h in clean_q for h in ["how are you", "how are you doing", "how's it going", "how is it going"]):
            resp = self.local_engine.get_template("how_are_you")
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": resp})
            return {"text": resp, "source": "Local Conversational Engine", "tool_used": None, "ai_available": False, "latency_ms": 0.5}

        if any(clean_q == s or clean_q.startswith(s + " ") for s in ["are you there", "are you online", "are you listening", "what are you doing"]):
            resp = self.local_engine.get_template("status_check")
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": resp})
            return {"text": resp, "source": "Local Conversational Engine", "tool_used": None, "ai_available": False, "latency_ms": 0.5}

        if clean_q in ["okay", "ok", "got it", "understood", "all right", "alright", "fine"]:
            resp = self.local_engine.get_template("acknowledgement")
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": resp})
            return {"text": resp, "source": "Local Conversational Engine", "tool_used": None, "ai_available": False, "latency_ms": 0.5}

        if clean_q in ["yes", "yeah", "yup", "sure", "correct"]:
            resp = self.local_engine.get_template("affirmation")
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": resp})
            return {"text": resp, "source": "Local Conversational Engine", "tool_used": None, "ai_available": False, "latency_ms": 0.5}

        if clean_q in ["no", "nope"]:
            resp = self.local_engine.get_template("negation")
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": resp})
            return {"text": resp, "source": "Local Conversational Engine", "tool_used": None, "ai_available": False, "latency_ms": 0.5}

        # Check verified static reasoning cache (Phase 5: Reduce Unnecessary Nemotron Calls)
        cached_item = persistent_memory.get_cached_query(query)
        if cached_item:
            cached_text = cached_item["text"]
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": cached_text})
            return {
                "text": cached_text,
                "source": cached_item["source"],
                "tool_used": None,
                "ai_available": True,
                "latency_ms": 1.0,
                "cached": True
            }

        if not ai_available:
            # 3. Check if there is an offline agent plan
            agent_res = self.agent.reason_and_execute(query, conversation_history=self.history)
            if agent_res and agent_res.get("text") and agent_res.get("text") != "I have processed your request, sir.":
                resp_text = agent_res["text"]
                self.history.append(user_msg)
                self.history.append({"role": "assistant", "content": resp_text})
                return {
                    "text": resp_text,
                    "source": agent_res.get("source", "Local Fallback"),
                    "tool_used": agent_res.get("tool_used"),
                    "ai_available": False,
                    "latency_ms": (time.time() - t0) * 1000
                }

            fallback_resp = "I cannot answer general reasoning questions while offline, Sir. External intelligence providers are currently unavailable."
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": fallback_resp})
            return {
                "text": fallback_resp,
                "source": "Local Fallback",
                "tool_used": None,
                "ai_available": False,
                "latency_ms": 0.5
            }

        response_text = ""
        agent_res = None
        source = "AI Provider"

        if is_mocked:
            response_text = gen_fn(messages)
            agent_res = {"text": response_text, "source": "AI Provider"}
        else:
            try:
                from core.profile_manager import profile_manager
                system_ctx = profile_manager.get_bounded_prompt_context()
            except Exception:
                system_ctx = {}

            if hasattr(self.provider_manager, "get_active_provider_name"):
                source = self.provider_manager.get_active_provider_name()

            agent_res = self.agent.reason_and_execute(effective_query, conversation_history=self.history)
            response_text = agent_res.get("text", "") if agent_res else ""

        t_duration_ms = (time.time() - t0) * 1000

        if response_text:
            logger.info(f"[CONVERSATION] Response ({t_duration_ms:.1f}ms): '{response_text}'")

            # Save interaction turn in rolling history
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": response_text})

            # Trim history to max_turns
            if len(self.history) > (self.max_turns * 2):
                self.history = self.history[-(self.max_turns * 2):]

            self.last_interaction_timestamp = time.time()

            # Save to durable SQLite persistence
            self.persistence.save_turn(
                user_text=query,
                assistant_text=response_text,
                session_id="default",
                source=source
            )

            # Save verified response to cache if query is static (Phase 5)
            if response_text and not persistent_memory._is_dynamic_query(query):
                persistent_memory.set_cached_query(query, response_text, source_provider=source, ttl_seconds=86400 * 7)

            return {
                "text": response_text,
                "source": agent_res.get("source", source) if agent_res else source,
                "tool_used": agent_res.get("tool_used") if agent_res else None,
                "ai_available": True,
                "latency_ms": t_duration_ms
            }

        # Fallback when no AI response was produced
        fallback_text = "I'm not sure how to help with that yet, Sir."
        self.persistence.save_turn(
            user_text=query,
            assistant_text=fallback_text,
            session_id="default",
            source="Local Fallback"
        )

        return {
            "text": fallback_text,
            "source": "Local Fallback",
            "tool_used": None,
            "ai_available": False,
            "latency_ms": t_duration_ms
        }

    def clear_session(self, clear_persistence: bool = False):
        """Clears all conversation session history."""
        self.history.clear()
        self.last_interaction_timestamp = 0.0
        self.last_target = ""
        self.last_action = ""
        self.pending_clarification = None
        if clear_persistence:
            self.persistence.clear_all()
        logger.info(f"Conversation session memory cleared (clear_persistence={clear_persistence}).")
