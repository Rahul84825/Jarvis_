"""Observability & Execution Transparency Subsystem for JARVIS.
Provides full visibility into why tools were selected, which tools executed, sanitized arguments,
latencies, verification outcomes, and answers: "Explain what tools you just called and why."
Reference: https://jarvis.institute/guide/#tips (Pattern 08: Ask Why It Did What It Did)
"""

import time
import logging
from typing import Dict, List, Optional, Any
from core.security.privacy_guard import privacy_guard

logger = logging.getLogger("Jarvis.Observability")

class ToolDecision:
    def __init__(
        self,
        query: str,
        intent: str,
        tool_name: str,
        rationale: str,
        args: Dict[str, Any],
        duration_ms: float = 0.0,
        success: bool = True,
        verification_evidence: Optional[str] = None
    ):
        self.timestamp = time.time()
        self.query = query
        self.intent = intent
        self.tool_name = tool_name
        self.rationale = rationale
        # Sanitize arguments via PrivacyGuard
        sanitized_args = {}
        for k, v in args.items():
            if isinstance(v, str):
                if any(sec in k.lower() for sec in ["key", "secret", "token", "password"]):
                    clean_v, _, _ = privacy_guard.redact_text(v)
                    if clean_v == v:
                        clean_v = "[REDACTED_SENSITIVE_VALUE]"
                else:
                    clean_v, _, _ = privacy_guard.redact_text(v)
                sanitized_args[k] = clean_v
            else:
                sanitized_args[k] = v
        self.args = sanitized_args
        self.duration_ms = duration_ms
        self.success = success
        self.verification_evidence = verification_evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "query": self.query,
            "intent": self.intent,
            "tool_name": self.tool_name,
            "rationale": self.rationale,
            "args": self.args,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "verification_evidence": self.verification_evidence
        }


class ToolDecisionExplainer:
    """Maintains a rolling ledger of tool selection rationales and formats explanations."""

    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self._decisions: List[ToolDecision] = []

    def record_decision(
        self,
        query: str,
        intent: str,
        tool_name: str,
        rationale: str,
        args: Dict[str, Any],
        duration_ms: float = 0.0,
        success: bool = True,
        verification_evidence: Optional[str] = None
    ):
        decision = ToolDecision(
            query=query,
            intent=intent,
            tool_name=tool_name,
            rationale=rationale,
            args=args,
            duration_ms=duration_ms,
            success=success,
            verification_evidence=verification_evidence
        )
        self._decisions.append(decision)
        if len(self._decisions) > self.max_history:
            self._decisions.pop(0)
        logger.info(f"[OBSERVABILITY] Recorded tool decision for '{tool_name}' ({duration_ms:.1f}ms). Rationale: {rationale}")

    def get_last_decision(self) -> Optional[ToolDecision]:
        return self._decisions[-1] if self._decisions else None

    def explain_recent_executions(self, count: int = 3) -> Dict[str, Any]:
        """Produces a clear, human-readable explanation of why recent tools were invoked."""
        if not self._decisions:
            return {
                "text": "No recent tools have been executed in this session yet.",
                "spoken_text": "No tools have been executed recently.",
                "count": 0,
                "decisions": []
            }

        recent = self._decisions[-count:]
        lines = ["### Execution Rationale Breakdown\n"]
        for i, d in enumerate(recent, 1):
            status_icon = "✅" if d.success else "❌"
            lines.append(f"**{i}. Tool: `{d.tool_name}`** ({status_icon} in {d.duration_ms:.1f}ms)")
            lines.append(f"- **Trigger Command:** \"{d.query}\"")
            lines.append(f"- **Why Selected:** {d.rationale}")
            if d.args:
                clean_args_str = ", ".join(f"{k}='{v}'" for k, v in d.args.items() if v is not None)
                lines.append(f"- **Arguments:** `{clean_args_str}`")
            if d.verification_evidence:
                lines.append(f"- **Verification Evidence:** {d.verification_evidence}")
            lines.append("")

        spoken = f"I executed {len(recent)} recent tool actions. The most recent was {recent[-1].tool_name} because {recent[-1].rationale.lower()}."

        return {
            "text": "\n".join(lines).strip(),
            "spoken_text": spoken,
            "count": len(recent),
            "decisions": [d.to_dict() for d in recent]
        }


# Global Singleton Instance
tool_explainer = ToolDecisionExplainer()
