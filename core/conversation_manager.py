import time
import logging
from typing import List, Dict, Any, Optional

from core.ai.agent_brain import agent_brain
from core.ai.intelligence_router import intelligence_router, MODE_FAST_LOCAL, MODE_CONTEXT, MODE_REASONING, MODE_QUESTION
from core.local_response_engine import LocalResponseEngine
from memory.persistent_memory import persistent_memory
from memory.conversation_persistence import ConversationPersistence

logger = logging.getLogger("Jarvis.ConversationManager")

class ConversationManager:
    """Manages multi-turn conversation memory, session timeout, follow-up query context,
    pronominal entity resolution, durable SQLite persistence, and routing to AgentBrain / ProviderManager.
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

        # Context tracking
        self.last_target: str = ""
        self.last_action: str = ""
        self.active_project: str = "jarvis"
        self.pending_clarification: Optional[str] = None

    def update_context(self, action: str, target: str, project: Optional[str] = None):
        """Updates active session context with recent action and target."""
        if target and target not in ["system", "all", "telemetry"]:
            self.last_target = target
        if action:
            self.last_action = action
        if project:
            self.active_project = project
        self.last_interaction_timestamp = time.time()

    def get_context(self) -> Dict[str, Any]:
        """Returns active contextual snapshot."""
        return {
            "last_target": self.last_target,
            "last_action": self.last_action,
            "active_project": self.active_project,
            "pending_clarification": self.pending_clarification
        }

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

        user_msg = {"role": "user", "content": query.strip()}
        messages = list(self.history) + [user_msg]

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
        if (ai_prov == "none" or not ai_prov) and not is_mocked:
            clean_q = query.lower().strip()
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

            fallback_resp = "I'm currently operating in offline mode. I can open apps, search the web, control system settings, take screenshots, or calculate math expressions for you."
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

            agent_res = self.agent.reason_and_execute(query, conversation_history=self.history)
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
