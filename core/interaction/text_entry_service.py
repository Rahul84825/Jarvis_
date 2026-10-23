"""Intelligent Text Entry and Universal Desktop Target Selection Service."""

import logging
import time
from typing import Optional, List, Dict, Any, Tuple

from core.interaction.models import (
    TargetControl,
    DesktopContext,
    ControlType,
    TargetResolution
)
from core.interaction.desktop_context_service import (
    DesktopContextService,
    desktop_context_service
)

logger = logging.getLogger("Jarvis.TextEntryService")


class TextEntryService:
    """Orchestrates universal desktop target selection, field clarification, and text injection."""

    def __init__(self, context_service: Optional[DesktopContextService] = None):
        self.context_service = context_service or desktop_context_service

    def resolve_target(
        self,
        ctx: DesktopContext,
        action: str = "enter_text",
        explicit_destination: Optional[str] = None
    ) -> Tuple[TargetResolution, Optional[TargetControl], List[TargetControl], str]:
        """Resolves the intended input target following Cases A, B, C, D.

        Returns:
            Tuple of (ResolutionStatus, SelectedTarget, CandidateTargets, GuidanceMessage)
        """
        targets = ctx.available_targets
        dest_clean = (explicit_destination or "").lower().strip()

        # ---------------------------------------------------------------------
        # Case D — User specifies an explicit destination
        # ---------------------------------------------------------------------
        if dest_clean:
            # 1. Email field specifications
            if any(k in dest_clean for k in ["subject", "subject line", "email subject"]):
                subj_targets = [t for t in targets if t.control_type == ControlType.EMAIL_SUBJECT or "subject" in t.name.lower()]
                if subj_targets:
                    return TargetResolution.EXPLICIT_OVERRIDE, subj_targets[0], [], f"Targeting email subject field '{subj_targets[0].name}'."
                # Synthesize explicit target if in email context
                return TargetResolution.EXPLICIT_OVERRIDE, TargetControl(control_id="explicit_subject", name="Subject Field", control_type=ControlType.EMAIL_SUBJECT), [], "Targeting email subject."

            if any(k in dest_clean for k in ["body", "message body", "email body"]):
                body_targets = [t for t in targets if t.control_type == ControlType.EMAIL_BODY or "body" in t.name.lower()]
                if body_targets:
                    return TargetResolution.EXPLICIT_OVERRIDE, body_targets[0], [], f"Targeting email body field '{body_targets[0].name}'."
                return TargetResolution.EXPLICIT_OVERRIDE, TargetControl(control_id="explicit_body", name="Message Body", control_type=ControlType.EMAIL_BODY), [], "Targeting message body."

            # 2. ChatGPT prompt box specification
            if "chatgpt" in dest_clean or "prompt box" in dest_clean:
                cg_targets = [t for t in targets if t.control_type == ControlType.PROMPT_BOX or "prompt" in t.name.lower() or "ask anything" in t.name.lower()]
                if cg_targets:
                    return TargetResolution.EXPLICIT_OVERRIDE, cg_targets[0], [], "Targeting ChatGPT prompt box."
                return TargetResolution.EXPLICIT_OVERRIDE, TargetControl(control_id="explicit_chatgpt", name="ChatGPT Prompt Box", control_type=ControlType.PROMPT_BOX), [], "Targeting ChatGPT prompt box."

            # 3. Code editor specification
            if any(k in dest_clean for k in ["code editor", "editor", "code"]):
                code_targets = [t for t in targets if t.control_type == ControlType.CODE_EDITOR]
                if code_targets:
                    return TargetResolution.EXPLICIT_OVERRIDE, code_targets[0], [], "Targeting active code editor."
                return TargetResolution.EXPLICIT_OVERRIDE, TargetControl(control_id="explicit_editor", name="Code Editor", control_type=ControlType.CODE_EDITOR), [], "Targeting code editor."

            # 4. Search bar specification
            if any(k in dest_clean for k in ["search bar", "search field", "search box", "search"]):
                search_targets = [t for t in targets if t.control_type == ControlType.SEARCH_FIELD or "search" in t.name.lower()]
                if len(search_targets) == 1:
                    return TargetResolution.EXPLICIT_OVERRIDE, search_targets[0], [], f"Targeting search field '{search_targets[0].name}'."
                elif len(search_targets) > 1:
                    labels = [t.name or f"Search Field {i+1}" for i, t in enumerate(search_targets)]
                    msg = f"I found multiple search fields ({', '.join(labels)}). Which one should I use?"
                    return TargetResolution.AMBIGUOUS, None, search_targets, msg

            # 5. Generic label matching
            for t in targets:
                if dest_clean in t.name.lower() or (t.help_text and dest_clean in t.help_text.lower()):
                    return TargetResolution.EXPLICIT_OVERRIDE, t, [], f"Targeting requested field '{t.name}'."

        # ---------------------------------------------------------------------
        # Case A / B / C — Inferred resolution based on intent action and context
        # ---------------------------------------------------------------------
        # If action is 'search_in_app'
        if action == "search_in_app":
            search_targets = [t for t in targets if t.control_type == ControlType.SEARCH_FIELD or "search" in t.name.lower() or "find" in t.name.lower()]
            if len(search_targets) == 1:
                return TargetResolution.SINGLE_TARGET, search_targets[0], [], f"Targeting search bar '{search_targets[0].name}'."
            elif len(search_targets) > 1:
                labels = [t.name or f"Option {i+1}" for i, t in enumerate(search_targets[:3])]
                msg = f"I found {len(search_targets)} search fields ({', '.join(labels)}). Which one should I use?"
                return TargetResolution.AMBIGUOUS, None, search_targets, msg
            elif ctx.focused_element:
                return TargetResolution.SINGLE_TARGET, ctx.focused_element, [], f"Using currently focused field '{ctx.focused_element.name}'."
            else:
                return TargetResolution.NO_TARGET, None, [], f"I couldn't identify a search field in {ctx.window_title or 'the active application'}. Please click the intended field."

        # If action is 'write_reply' or messaging
        if action in ["write_reply", "reply"]:
            composer_targets = [t for t in targets if t.control_type in [ControlType.MESSAGE_COMPOSER, ControlType.PROMPT_BOX, ControlType.EMAIL_BODY]]
            if len(composer_targets) == 1:
                return TargetResolution.SINGLE_TARGET, composer_targets[0], [], f"Targeting composer '{composer_targets[0].name}'."
            elif len(composer_targets) > 1:
                labels = [t.name or f"Composer {i+1}" for i, t in enumerate(composer_targets[:2])]
                msg = f"Should I put this in {labels[0]} or {labels[1]}?"
                return TargetResolution.AMBIGUOUS, None, composer_targets, msg

        # General text entry: evaluate focused control vs available targets
        if ctx.focused_element and ctx.focused_element.is_focused:
            # If focused element is unambiguous and non-generic, Case A
            if len(targets) <= 1 or ctx.focused_element.confidence >= 0.9:
                return TargetResolution.SINGLE_TARGET, ctx.focused_element, [], f"Targeting focused field '{ctx.focused_element.name}'."

        # Multiple plausible targets check (Case B)
        plausible = [t for t in targets if t.control_type not in [ControlType.BUTTON, ControlType.UNKNOWN]]
        if len(plausible) > 1:
            # Check if there is a distinct composer vs search bar
            composers = [t for t in plausible if t.control_type in [ControlType.MESSAGE_COMPOSER, ControlType.PROMPT_BOX, ControlType.EMAIL_BODY]]
            searches = [t for t in plausible if t.control_type == ControlType.SEARCH_FIELD]
            
            if composers and searches:
                c_name = composers[0].name or "message composer"
                s_name = searches[0].name or "search field"
                msg = f"I found the {s_name} and the {c_name}. Which one should I use?"
                return TargetResolution.AMBIGUOUS, None, [searches[0], composers[0]], msg

            # Email subject vs email body
            subjects = [t for t in plausible if t.control_type == ControlType.EMAIL_SUBJECT]
            bodies = [t for t in plausible if t.control_type == ControlType.EMAIL_BODY]
            if subjects and bodies:
                msg = "Should I put this in the email subject or message body?"
                return TargetResolution.AMBIGUOUS, None, [subjects[0], bodies[0]], msg

            labels = [t.name or f"Field {i+1}" for i, t in enumerate(plausible[:3])]
            msg = f"I found multiple input fields ({', '.join(labels)}). Which one would you like me to use?"
            return TargetResolution.AMBIGUOUS, None, plausible[:3], msg

        elif len(plausible) == 1:
            return TargetResolution.SINGLE_TARGET, plausible[0], [], f"Targeting field '{plausible[0].name}'."

        # Case C — No reliable target found
        win_desc = f"in '{ctx.window_title}'" if ctx.window_title else "in the active window"
        msg = f"I couldn't identify a reliable text field {win_desc}. Please click or focus the intended field and tell me when you're ready."
        return TargetResolution.NO_TARGET, None, [], msg

    def enter_text(
        self,
        text: str,
        action: str = "enter_text",
        explicit_destination: Optional[str] = None,
        mode: str = "insert",
        submit: bool = False
    ) -> Dict[str, Any]:
        """Main entry point for intelligent context-aware text entry."""
        if not text or not text.strip():
            return {
                "success": False,
                "message": "No text provided to enter."
            }

        ctx = self.context_service.get_current_context(explicit_destination=explicit_destination)
        res_type, target, candidates, msg = self.resolve_target(ctx, action=action, explicit_destination=explicit_destination)

        # Case B: Ambiguous multiple targets -> Ask for clarification
        if res_type == TargetResolution.AMBIGUOUS:
            return {
                "success": True,
                "requires_clarification": True,
                "resolution": res_type.value,
                "message": msg,
                "candidates": [c.to_dict() for c in candidates],
                "pending_intent": {
                    "intent": "desktop_interaction.clarify_target",
                    "text": text,
                    "action": action,
                    "expected_hwnd": ctx.window_hwnd,
                    "expected_title": ctx.window_title,
                    "candidates": [c.to_dict() for c in candidates]
                }
            }

        # Case C: No reliable target -> Ask user to focus
        if res_type == TargetResolution.NO_TARGET:
            return {
                "success": True,
                "requires_focus": True,
                "resolution": res_type.value,
                "message": msg,
                "pending_intent": {
                    "intent": "desktop_interaction.await_focus",
                    "text": text,
                    "action": action,
                    "expected_hwnd": ctx.window_hwnd,
                    "expected_title": ctx.window_title
                }
            }

        # Case A or D: Single clear target or explicit override -> Execute insertion
        insert_res = self.context_service.adapter.insert_text(
            target=target,
            text=text,
            mode=mode,
            expected_hwnd=ctx.window_hwnd,
            expected_title=ctx.window_title
        )

        if not insert_res.get("success"):
            return insert_res

        target_name = target.name if target else "active field"

        # If action is search_in_app and submit is requested, press Enter
        if action == "search_in_app" or submit:
            try:
                import pyautogui
                time.sleep(0.05)
                pyautogui.press("enter")
                return {
                    "success": True,
                    "action_executed": "search_submitted",
                    "target": target_name,
                    "message": f"Searched for '{text}' in {target_name}."
                }
            except Exception as e:
                logger.debug(f"Search submit enter key failed: {e}")

        # CRITICAL SAFETY BOUNDARY: Distinguish text entry from sending
        # Text entry does NOT automatically submit or send!
        return {
            "success": True,
            "action_executed": "text_inserted",
            "target": target_name,
            "message": f"The draft is inserted into {target_name}. I haven't sent it.",
            "draft_text": text
        }

    def execute_send_message(self, confirm: bool = False) -> Dict[str, Any]:
        """Sends message or submits form only upon explicit confirmation."""
        if not confirm:
            return {
                "success": False,
                "pending_confirmation": True,
                "message": "Are you sure you want to send this message? Please confirm to proceed.",
                "pending_intent": {
                    "intent": "desktop_interaction.send_confirm"
                }
            }

        # Perform send via Enter or Ctrl+Enter depending on context
        try:
            import pyautogui
            pyautogui.press("enter")
            return {
                "success": True,
                "message": "Message sent, Sir."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to send message: {e}"
            }


# Global singleton instance
text_entry_service = TextEntryService()
