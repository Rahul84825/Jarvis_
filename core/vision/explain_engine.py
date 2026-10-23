"""Explain, Teach, and Re-Explain Engine for JARVIS Desktop Intelligence.

Provides 12 distinct explanation styles, bounded multi-turn session tracking,
point re-explanations ("explain point 3 again"), progressive simplification,
and screen-change detection.
"""

import re
import time
import logging
from typing import Optional, Dict, Any, List, Tuple

from core.vision.models import (
    ScreenContext,
    ScreenExplanation,
    ExplanationStyle,
    CaptureTarget
)
from core.vision.session_manager import screen_session_manager, ScreenSession
from core.vision.screen_understanding import screen_understanding_engine

logger = logging.getLogger("Jarvis.ExplainEngine")


class ExplainEngine:
    """Translates screen context into tailored, multi-turn explanations."""

    STYLE_PROMPTS = {
        ExplanationStyle.BEGINNER: "Explain this in very friendly, beginner terms without complex jargon. Use simple everyday language.",
        ExplanationStyle.SIMPLE_ENGLISH: "Explain this in plain, easy-to-read English with short clear sentences.",
        ExplanationStyle.STEP_BY_STEP: "Break down this visible content into a clear, numbered step-by-step walkthrough.",
        ExplanationStyle.IMPORTANT_POINTS: "Extract and present only the most important points as concise bullet points.",
        ExplanationStyle.TECHNICAL: "Provide a detailed technical breakdown, including architecture, mechanics, and underlying concepts.",
        ExplanationStyle.CODE_LINE_BY_LINE: "Explain the visible code line by line, explaining syntax, logic flow, and edge cases.",
        ExplanationStyle.EXAMPLE_BASED: "Explain this concept by providing concrete, practical real-world examples.",
        ExplanationStyle.EXAM_ORIENTED: "Explain this from an academic/exam perspective, highlighting key definitions, formulas, and common exam questions.",
        ExplanationStyle.INTERVIEW_ORIENTED: "Explain this as if preparing for a technical job interview, covering trade-offs, design choices, and common interview questions.",
        ExplanationStyle.SUMMARY_THEN_DETAIL: "Provide a short, direct summary first (1-2 sentences), followed by a structured detailed breakdown.",
        ExplanationStyle.COMPARISON: "Compare and contrast the visible sections, concepts, or approaches, outlining pros and cons.",
    }

    def __init__(self, session_manager=None, understanding_engine=None):
        self.session_mgr = session_manager or screen_session_manager
        self.vision_engine = understanding_engine or screen_understanding_engine

    def resolve_style(self, query: str) -> Tuple[ExplanationStyle, Optional[int]]:
        """Parses natural language user query to determine requested explanation style and optional target point index."""
        q = query.lower()

        # Check for point-specific query: "explain point 3", "explain the second point", "point 4 again"
        m_num = re.search(r"\b(?:point|step|item|bullet)\s+(\d+)\b", q)
        if m_num:
            return ExplanationStyle.EXPLAIN_POINT, int(m_num.group(1))

        ordinals = {
            "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
            "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10
        }
        for word, idx in ordinals.items():
            if f"{word} point" in q or f"{word} step" in q or f"{word} item" in q:
                return ExplanationStyle.EXPLAIN_POINT, idx

        if "beginner" in q or "like i'm 5" in q or "eli5" in q:
            return ExplanationStyle.BEGINNER, None
        if "simple english" in q or "simple words" in q or "in simple terms" in q or "simple language" in q:
            return ExplanationStyle.SIMPLE_ENGLISH, None
        if "step by step" in q or "step-by-step" in q or "walk me through" in q:
            return ExplanationStyle.STEP_BY_STEP, None
        if "important points" in q or "key points" in q or "highlights" in q or "main points" in q:
            return ExplanationStyle.IMPORTANT_POINTS, None
        if "line by line" in q or "code line" in q or "explain the code" in q:
            return ExplanationStyle.CODE_LINE_BY_LINE, None
        if "example" in q or "analogy" in q or "don't understand" in q or "still don't understand" in q:
            return ExplanationStyle.EXAMPLE_BASED, None
        if "exam" in q or "test preparation" in q:
            return ExplanationStyle.EXAM_ORIENTED, None
        if "interview" in q:
            return ExplanationStyle.INTERVIEW_ORIENTED, None
        if "compare" in q or "versus" in q or "vs" in q or "difference between" in q:
            return ExplanationStyle.COMPARISON, None
        if "technical" in q or "deep dive" in q or "advanced" in q:
            return ExplanationStyle.TECHNICAL, None

        return ExplanationStyle.SUMMARY_THEN_DETAIL, None

    def explain(
        self,
        query: str,
        provider_manager: Optional[Any] = None,
        force_fresh_capture: bool = False,
        capture_target: CaptureTarget = CaptureTarget.PRIMARY_SCREEN
    ) -> ScreenExplanation:
        """Main entry point: Generates or continues a screen explanation."""
        if not provider_manager:
            from core.ai.provider_manager import ProviderManager
            provider_manager = ProviderManager()

        style, point_idx = self.resolve_style(query)
        session = self.session_mgr.get_active_session()

        # Check if screen has changed if an active session exists
        screen_changed = False
        if session and not force_fresh_capture:
            try:
                from core.vision.screen_capture import ScreenCaptureManager
                ScreenCaptureManager._attach_thread_to_input_desktop()
                import win32gui
                curr_hwnd = win32gui.GetForegroundWindow()
                curr_title = win32gui.GetWindowText(curr_hwnd)
                screen_changed = session.has_screen_changed(curr_hwnd, curr_title)
            except Exception:
                screen_changed = False

        # If forced, or no session exists, or screen changed significantly and query is not a point reference
        if force_fresh_capture or not session or (screen_changed and style != ExplanationStyle.EXPLAIN_POINT):
            ctx = self.vision_engine.capture_screen_context(target=capture_target)
            session = self.session_mgr.create_session(ctx)
            if screen_changed:
                logger.info("[EXPLAIN] Active screen changed, initiated fresh screen session.")

        # Handle point-specific follow up: "explain point 3 again"
        if style == ExplanationStyle.EXPLAIN_POINT and point_idx:
            point_text = session.get_point(point_idx)
            if point_text:
                prompt = (
                    f"The user wants a detailed, clear explanation of Point #{point_idx} from the previously analyzed screen:\n"
                    f"\"{point_text}\"\n\n"
                    f"Explain this specific point in depth with a practical example. Clarify why it matters."
                )
            else:
                prompt = (
                    f"The user asked to explain point #{point_idx}, but only {len(session.extracted_points)} points were found. "
                    f"Explain the most relevant aspect of the content."
                )
        else:
            style_instruction = self.STYLE_PROMPTS.get(style, self.STYLE_PROMPTS[ExplanationStyle.SUMMARY_THEN_DETAIL])
            prompt = f"User request: '{query}'\nGuidance: {style_instruction}"

        # Analyze with AI
        analysis = self.vision_engine.analyze_screen(prompt, context=session.context, provider_manager=provider_manager)

        # Update session memory
        if analysis.get("important_points"):
            session.extracted_points = analysis["important_points"]

        explanation = ScreenExplanation(
            session_id=session.session_id,
            context_id=session.context.context_id,
            style=style,
            summary=analysis.get("summary", ""),
            important_points=analysis.get("important_points", []),
            detailed_text=analysis.get("full_text", ""),
            code_snippets=analysis.get("code_snippets", []),
            error_diagnosis=analysis.get("error_diagnosis"),
            model_used=analysis.get("model_used", "local")
        )

        session.add_explanation(explanation)
        session.add_turn("user", query)
        session.add_turn("jarvis", explanation.detailed_text)

        return explanation


# Global singleton instance
explain_engine = ExplainEngine()
