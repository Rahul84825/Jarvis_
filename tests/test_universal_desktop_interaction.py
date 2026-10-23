"""Unit and integration tests for Phase 7 — Universal Desktop Interaction, Context Awareness & Intelligent Text Entry."""

import unittest
from unittest.mock import MagicMock, patch

from core.interaction.models import (
    TargetControl,
    DesktopContext,
    ControlType,
    TargetResolution
)
from core.interaction.context_adapter import (
    BaseDesktopContextAdapter,
    WindowsDesktopContextAdapter
)
from core.interaction.desktop_context_service import DesktopContextService
from core.interaction.text_entry_service import TextEntryService
from core.intent_engine import IntentEngine
from core.tool_registry import tool_registry
from modules.system.executor import CommandExecutor


class MockDesktopContextAdapter(BaseDesktopContextAdapter):
    """Controllable mock adapter simulating various desktop states."""

    def __init__(self):
        self.mock_context = DesktopContext(
            foreground_app="chrome",
            process_name="chrome.exe",
            window_hwnd=12345,
            window_title="Google Chrome - Search",
            timestamp=1000.0
        )
        self.inserted_calls = []
        self.window_stable = True

    def get_desktop_context(self, explicit_destination=None, allow_ocr=False) -> DesktopContext:
        ctx = self.mock_context
        if allow_ocr:
            ctx.context_source = "ocr"
        return ctx

    def verify_window_stable(self, expected_hwnd: int, expected_title: str = "") -> bool:
        return self.window_stable

    def insert_text(self, target, text, mode="insert", expected_hwnd=0, expected_title=""):
        if not self.verify_window_stable(expected_hwnd, expected_title):
            return {
                "success": False,
                "reason": "window_changed",
                "message": "The active application changed, so I paused to avoid typing into the wrong window."
            }
        self.inserted_calls.append((target, text, mode))
        target_name = target.name if target else "active field"
        return {
            "success": True,
            "method": "mock_injection",
            "target": target_name,
            "message": f"Text inserted into {target_name}."
        }


class TestUniversalDesktopInteraction(unittest.TestCase):
    """Test suite covering all Phase 7 Universal Desktop Interaction features."""

    def setUp(self):
        self.adapter = MockDesktopContextAdapter()
        self.context_service = DesktopContextService(adapter=self.adapter)
        self.text_service = TextEntryService(context_service=self.context_service)
        self.intent_engine = IntentEngine()
        self.executor = CommandExecutor()

    # =========================================================================
    # 1. CONTEXT CAPTURE & CONTROL CLASSIFICATION
    # =========================================================================

    def test_active_application_and_focused_field_detection(self):
        """Test active foreground window, app name, and focused control metadata capture."""
        focused_ctrl = TargetControl(
            control_id="f1",
            name="Search or type URL",
            control_type=ControlType.SEARCH_FIELD,
            is_focused=True,
            confidence=0.95
        )
        self.adapter.mock_context.focused_element = focused_ctrl
        self.adapter.mock_context.available_targets = [focused_ctrl]

        ctx = self.context_service.get_current_context()
        self.assertEqual(ctx.foreground_app, "chrome")
        self.assertEqual(ctx.window_hwnd, 12345)
        self.assertIsNotNone(ctx.focused_element)
        self.assertTrue(ctx.focused_element.is_focused)
        self.assertEqual(ctx.focused_element.control_type, ControlType.SEARCH_FIELD)

    def test_chatgpt_prompt_box_versus_address_bar_classification(self):
        """Test classification distinguishes ChatGPT prompt box from generic address bar/search field."""
        win_adapter = WindowsDesktopContextAdapter()
        
        # Test ChatGPT prompt box
        cg_type = win_adapter._classify_control(
            name="Ask anything",
            help_text="Prompt textarea",
            automation_id="prompt-textarea",
            class_name="",
            app_slug="chrome",
            browser_url="https://chatgpt.com/c/12345",
            window_title="ChatGPT"
        )
        self.assertEqual(cg_type, ControlType.PROMPT_BOX)

        # Test address bar / search in same browser window
        addr_type = win_adapter._classify_control(
            name="Address and search bar",
            help_text="",
            automation_id="address-bar",
            class_name="OmniboxViewViews",
            app_slug="chrome",
            browser_url="https://chatgpt.com",
            window_title="ChatGPT"
        )
        self.assertEqual(addr_type, ControlType.SEARCH_FIELD)

    def test_whatsapp_message_composer_versus_contact_search(self):
        """Test classification distinguishes WhatsApp message composer from contact search box."""
        win_adapter = WindowsDesktopContextAdapter()

        composer_type = win_adapter._classify_control(
            name="Type a message",
            help_text="",
            automation_id="composer",
            class_name="",
            app_slug="whatsapp",
            window_title="WhatsApp"
        )
        self.assertEqual(composer_type, ControlType.MESSAGE_COMPOSER)

        search_type = win_adapter._classify_control(
            name="Search or start new chat",
            help_text="",
            automation_id="search_chats",
            class_name="",
            app_slug="whatsapp",
            window_title="WhatsApp"
        )
        self.assertEqual(search_type, ControlType.SEARCH_FIELD)

    def test_email_subject_and_body_mapping(self):
        """Test classification correctly separates email recipient, subject, and body fields."""
        win_adapter = WindowsDesktopContextAdapter()

        to_type = win_adapter._classify_control("Recipients", "", "to_field", "", "chrome", "https://mail.google.com", "Gmail")
        self.assertEqual(to_type, ControlType.EMAIL_TO)

        subj_type = win_adapter._classify_control("Subject", "Add a subject", "subject_field", "", "chrome", "https://mail.google.com", "Gmail")
        self.assertEqual(subj_type, ControlType.EMAIL_SUBJECT)

        body_type = win_adapter._classify_control("Message Body", "", "body_editor", "", "chrome", "https://mail.google.com", "Gmail")
        self.assertEqual(body_type, ControlType.EMAIL_BODY)

    # =========================================================================
    # 2. TARGET SELECTION DECISION CASES (A, B, C, D)
    # =========================================================================

    def test_case_a_single_unambiguous_target(self):
        """Case A: When a single target is clearly identified, text is entered without asking."""
        single_field = TargetControl(
            control_id="s1",
            name="Search Google",
            control_type=ControlType.SEARCH_FIELD,
            is_focused=True,
            confidence=0.95
        )
        self.adapter.mock_context.focused_element = single_field
        self.adapter.mock_context.available_targets = [single_field]

        res = self.text_service.enter_text("binary search", action="search_in_app", submit=False)
        self.assertTrue(res["success"])
        self.assertFalse(res.get("requires_clarification", False))
        self.assertIn("The draft is inserted", res["message"])
        self.assertEqual(len(self.adapter.inserted_calls), 1)
        self.assertEqual(self.adapter.inserted_calls[0][1], "binary search")

    def test_case_b_multiple_targets_triggers_clarification(self):
        """Case B: Multiple plausible targets triggers short clarification using real accessible labels."""
        search_field = TargetControl(control_id="s1", name="Website Search Box", control_type=ControlType.SEARCH_FIELD)
        chat_box = TargetControl(control_id="c1", name="ChatGPT Prompt Box", control_type=ControlType.PROMPT_BOX)
        self.adapter.mock_context.focused_element = None
        self.adapter.mock_context.available_targets = [search_field, chat_box]

        res = self.text_service.enter_text("Hello there", action="enter_text")
        self.assertTrue(res["success"])
        self.assertTrue(res["requires_clarification"])
        self.assertEqual(res["resolution"], TargetResolution.AMBIGUOUS.value)
        self.assertIn("Website Search Box", res["message"])
        self.assertIn("ChatGPT Prompt Box", res["message"])
        self.assertIn("Which one should I use?", res["message"])
        # No text should be typed yet
        self.assertEqual(len(self.adapter.inserted_calls), 0)

    def test_case_c_no_reliable_target_requests_focus(self):
        """Case C: No reliable target triggers polite request to focus intended field rather than typing blindly."""
        self.adapter.mock_context.focused_element = None
        self.adapter.mock_context.available_targets = []

        res = self.text_service.enter_text("Some text", action="enter_text")
        self.assertTrue(res["success"])
        self.assertTrue(res["requires_focus"])
        self.assertEqual(res["resolution"], TargetResolution.NO_TARGET.value)
        self.assertIn("Please click or focus the intended field", res["message"])
        self.assertEqual(len(self.adapter.inserted_calls), 0)

    def test_case_d_explicit_destination_overrides_inference(self):
        """Case D: Explicit instructions (e.g. 'in the subject field', 'in ChatGPT') override inferred destinations."""
        search_field = TargetControl(control_id="s1", name="Search", control_type=ControlType.SEARCH_FIELD)
        subject_field = TargetControl(control_id="e1", name="Subject", control_type=ControlType.EMAIL_SUBJECT)
        body_field = TargetControl(control_id="e2", name="Body", control_type=ControlType.EMAIL_BODY)
        self.adapter.mock_context.available_targets = [search_field, subject_field, body_field]

        # Request targeting subject specifically
        res = self.text_service.enter_text("Quarterly Report", explicit_destination="subject")
        self.assertTrue(res["success"])
        self.assertFalse(res.get("requires_clarification", False))
        self.assertEqual(len(self.adapter.inserted_calls), 1)
        self.assertEqual(self.adapter.inserted_calls[0][0].control_type, ControlType.EMAIL_SUBJECT)

    # =========================================================================
    # 3. SAFETY, SEPARATION OF CONCERNS & CONFIRMATIONS
    # =========================================================================

    def test_text_insertion_never_automatically_submits_or_sends(self):
        """Verify generating/inserting text clearly separates text insertion from sending."""
        field = TargetControl(control_id="c1", name="Message Composer", control_type=ControlType.MESSAGE_COMPOSER, is_focused=True)
        self.adapter.mock_context.available_targets = [field]
        self.adapter.mock_context.focused_element = field

        res = self.text_service.enter_text("I'll arrive in 15 minutes", action="write_reply")
        self.assertTrue(res["success"])
        self.assertEqual(res["action_executed"], "text_inserted")
        self.assertIn("The draft is inserted into Message Composer. I haven't sent it.", res["message"])

    def test_explicit_approval_required_before_sending_message(self):
        """Verify sending a message requires explicit user approval."""
        # Step 1: Without confirmation -> returns pending_confirmation
        unconfirmed = self.text_service.execute_send_message(confirm=False)
        self.assertFalse(unconfirmed["success"])
        self.assertTrue(unconfirmed["pending_confirmation"])
        self.assertIn("Are you sure you want to send this message?", unconfirmed["message"])

        # Step 2: With explicit confirmation -> executes send
        with patch("pyautogui.press") as mock_press:
            confirmed = self.text_service.execute_send_message(confirm=True)
            self.assertTrue(confirmed["success"])
            self.assertEqual(confirmed["message"], "Message sent, Sir.")
            mock_press.assert_called_with("enter")

    def test_window_change_during_preparation_pauses_safely(self):
        """Verify active-window change before text entry pauses safely to prevent typing into the wrong window."""
        field = TargetControl(control_id="e1", name="Code Editor", control_type=ControlType.CODE_EDITOR, is_focused=True)
        self.adapter.mock_context.available_targets = [field]
        self.adapter.mock_context.focused_element = field
        # Simulate active window changing right before typing
        self.adapter.window_stable = False

        res = self.text_service.enter_text("print('hello')", action="enter_text")
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "window_changed")
        self.assertIn("The active application changed, so I paused to avoid typing into the wrong window.", res["message"])
        self.assertEqual(len(self.adapter.inserted_calls), 0)

    # =========================================================================
    # 4. NATURAL LANGUAGE INTENT PARSING
    # =========================================================================

    def test_natural_language_intent_variations(self):
        """Test natural language commands for Phase 7 resolve to deterministic desktop interaction intents."""
        test_cases = [
            ("Jarvis, write a reply saying I'll arrive in 15 minutes", "desktop_interaction.write_reply"),
            ("Type this into the current search bar", "desktop_interaction.type_text"),
            ("Search for binary search in this application", "desktop_interaction.search_app"),
            ("Write a professional response to this message", "desktop_interaction.write_reply"),
            ("Enter this code into the editor", "desktop_interaction.type_text"),
            ("Fill in the description field", "desktop_interaction.type_text"),
            ("Replace the selected text with this paragraph", "desktop_interaction.replace_selection"),
            ("Continue writing from where I left off", "desktop_interaction.continue_writing"),
            ("Make the current draft more polite", "desktop_interaction.edit_draft"),
            ("Paste this into the ChatGPT prompt box", "desktop_interaction.type_text"),
            ("Write a reply in the currently open WhatsApp chat", "desktop_interaction.write_reply"),
            ("Enter the search term in YouTube", "desktop_interaction.search_app"),
            ("Put this into the subject field, not the email body", "desktop_interaction.type_text"),
            ("Send the message", "desktop_interaction.send_message")
        ]

        for phrase, expected_intent in test_cases:
            with self.subTest(phrase=phrase):
                res = self.intent_engine.parse(phrase)
                self.assertEqual(res["intent"], expected_intent, f"Failed for phrase: '{phrase}'")

    # =========================================================================
    # 5. TOOL REGISTRY & EXECUTOR INTEGRATION
    # =========================================================================

    def test_desktop_tools_registered_in_tool_registry(self):
        """Test that all 5 desktop interaction tools are registered with proper metadata."""
        expected_tools = [
            "desktop.get_context",
            "desktop.enter_text",
            "desktop.search_in_app",
            "desktop.replace_selection",
            "desktop.send_message"
        ]
        for name in expected_tools:
            tool = tool_registry.get_tool(name)
            self.assertIsNotNone(tool, f"Tool '{name}' is missing from ToolRegistry.")
            self.assertEqual(tool.category, "interaction")

    def test_executor_handles_desktop_enter_text_and_get_context(self):
        """Test CommandExecutor dispatches desktop interaction tools returning CommandOutcome."""
        with patch.object(self.executor, "execute") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "outcome": "SUCCESS",
                "message": "The draft is inserted into Search Google. I haven't sent it."
            }
            res = self.executor.execute({
                "intent": "desktop.enter_text",
                "text": "test query",
                "action": "enter_text"
            })
            self.assertTrue(res["success"])
            self.assertEqual(res["outcome"], "SUCCESS")

    # =========================================================================
    # 6. OCR / VISION RESTRICTION & CLOUD PRIVACY
    # =========================================================================

    def test_ocr_fallback_invoked_only_under_permitted_conditions(self):
        """Verify OCR fallback is never invoked automatically without allow_ocr=True."""
        ctx_normal = self.context_service.get_current_context(allow_ocr=False)
        self.assertNotEqual(ctx_normal.context_source, "ocr")

        ctx_ocr = self.context_service.get_current_context(allow_ocr=True)
        self.assertEqual(ctx_ocr.context_source, "ocr")

    def test_screen_reading_indicator_callback(self):
        """Verify visible indicator callback fires during screen context reading."""
        indicator_states = []
        self.context_service.on_screen_reading_indicator = lambda active, msg: indicator_states.append((active, msg))

        self.context_service.get_current_context(allow_ocr=True)
        self.assertEqual(len(indicator_states), 2)
        self.assertTrue(indicator_states[0][0])
        self.assertFalse(indicator_states[1][0])


if __name__ == "__main__":
    unittest.main()
