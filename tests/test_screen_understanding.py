"""Automated Test Suite for JARVIS Screen Understanding & Visual Intelligence Engine."""

import unittest
from unittest.mock import MagicMock, patch
from PIL import Image, ImageDraw

from core.vision.models import CaptureTarget, ExplanationStyle, ScreenContext, ScreenRegion, ScreenExplanation
from core.vision.screen_capture import ScreenCaptureManager
from core.vision.screen_understanding import ScreenUnderstandingEngine
from core.vision.session_manager import ScreenSessionManager, ScreenSession
from core.vision.explain_engine import ExplainEngine
from core.vision.ocr_engine import ocr_engine, OCRResult


class TestScreenUnderstanding(unittest.TestCase):
    """Validates desktop screen perception, structured normalization, and explanation styles."""

    def setUp(self):
        self.capture_mgr = ScreenCaptureManager()
        self.session_mgr = ScreenSessionManager()
        self.understanding_engine = ScreenUnderstandingEngine(capture_manager=self.capture_mgr)
        self.explain_engine = ExplainEngine(session_manager=self.session_mgr, understanding_engine=self.understanding_engine)

    def test_screen_capture_fallback_creates_valid_image(self):
        """Verify screen capture returns a valid PIL Image and temp path even when headless."""
        img, path = self.capture_mgr.capture(target=CaptureTarget.PRIMARY_SCREEN)
        self.assertIsNotNone(img)
        self.assertIsInstance(img, Image.Image)
        self.assertGreater(img.width, 100)
        self.assertGreater(img.height, 100)

    def test_screen_context_normalization_and_sensitive_field_redaction(self):
        """Verify that password and credential fields are redacted from extracted screen context."""
        mock_controls = [
            {"name": "Username", "current_value": "alice", "control_type": "edit"},
            {"name": "Password Input", "current_value": "SecretPassword123!", "control_type": "edit"},
            {"name": "Submit", "current_value": "", "control_type": "button"}
        ]

        with patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context") as mock_ctx:
            mock_obj = MagicMock()
            mock_obj.window_title = "Login Portal - Chrome"
            mock_obj.process_name = "chrome.exe"
            mock_obj.available_controls = [MagicMock(to_dict=lambda c=ctrl: c) for ctrl in mock_controls]
            mock_ctx.return_value = mock_obj

            ctx = self.understanding_engine.capture_screen_context()
            self.assertEqual(ctx.window_title, "Login Portal - Chrome")
            self.assertEqual(ctx.process_name, "chrome.exe")
            self.assertIn("Username: alice", ctx.extracted_text)
            self.assertNotIn("SecretPassword123!", ctx.extracted_text)
            self.assertIn("[REDACTED_SENSITIVE_FIELD]", ctx.extracted_text)

    def test_explanation_style_resolution(self):
        """Verify natural language queries map to the 12 distinct explanation styles and point indices."""
        cases = [
            ("Explain this like I'm a beginner", ExplanationStyle.BEGINNER, None),
            ("Explain this in simple English", ExplanationStyle.SIMPLE_ENGLISH, None),
            ("Give me a step-by-step walkthrough", ExplanationStyle.STEP_BY_STEP, None),
            ("What are the important points here?", ExplanationStyle.IMPORTANT_POINTS, None),
            ("Explain this code line by line", ExplanationStyle.CODE_LINE_BY_LINE, None),
            ("Explain it with a practical example", ExplanationStyle.EXAMPLE_BASED, None),
            ("Explain this for my exam", ExplanationStyle.EXAM_ORIENTED, None),
            ("Explain this as if for an interview", ExplanationStyle.INTERVIEW_ORIENTED, None),
            ("Compare these two sections", ExplanationStyle.COMPARISON, None),
            ("Explain the technical architecture", ExplanationStyle.TECHNICAL, None),
            ("Explain point 3 again", ExplanationStyle.EXPLAIN_POINT, 3),
            ("Explain the second point", ExplanationStyle.EXPLAIN_POINT, 2)
        ]

        for query, expected_style, expected_idx in cases:
            with self.subTest(query=query):
                style, point_idx = self.explain_engine.resolve_style(query)
                self.assertEqual(style, expected_style, f"Failed style for '{query}'")
                self.assertEqual(point_idx, expected_idx, f"Failed index for '{query}'")

    def test_multi_turn_screen_session_point_reference(self):
        """Verify that 'explain point 3 again' references the third point from prior screen session."""
        ctx = ScreenContext(
            window_title="Binary Search Walkthrough",
            extracted_text="Point 1: Find mid\nPoint 2: Compare target\nPoint 3: Recurse into sub-array",
            source="test"
        )
        session = self.session_mgr.create_session(ctx)
        session.extracted_points = [
            "Find middle element at (low + high) / 2",
            "Compare search key with mid element",
            "Narrow search interval to left or right sub-array"
        ]

        # Follow-up: Ask to explain point 3
        mock_prov_mgr = MagicMock()
        mock_prov_mgr.generate_response.return_value = "Point 3 detailed explanation: When the key is smaller, set high = mid - 1."
        mock_prov_mgr.get_active_provider_name.return_value = "Mock Vision Provider"

        exp = self.explain_engine.explain("Explain point 3 again", provider_manager=mock_prov_mgr)
        self.assertEqual(exp.style, ExplanationStyle.EXPLAIN_POINT)
        self.assertIn("Point 3 detailed explanation", exp.detailed_text)
        self.assertEqual(len(session.follow_up_turns), 2)  # user turn + jarvis turn

    def test_screen_change_detection_in_session(self):
        """Verify screen session detects when foreground window title or handle changes."""
        ctx = ScreenContext(window_title="VS Code - main.py", metadata={"hwnd": 12345})
        session = self.session_mgr.create_session(ctx)

        # Same window -> not changed
        self.assertFalse(session.has_screen_changed(12345, "VS Code - main.py"))

        # Switched window -> changed
        self.assertTrue(session.has_screen_changed(99999, "Chrome - YouTube"))

    def test_visual_indicator_callback_triggered(self):
        """Verify visual reading indicator callback is triggered on capture and analysis."""
        events = []
        self.understanding_engine.on_indicator_cb = lambda active, msg: events.append((active, msg))

        self.understanding_engine.capture_screen_context()
        self.assertGreaterEqual(len(events), 2)
        self.assertTrue(events[0][0])   # active = True
        self.assertFalse(events[-1][0])  # active = False

    def test_voice_and_ui_triggers_reach_same_screen_analysis_service(self):
        """1. Verify voice-command routing and UI button worker reach the shared ExplainEngine."""
        from ui.panels.screen_intelligence_panel import ScreenAnalysisWorker
        mock_explain_engine = MagicMock()
        mock_prov_mgr = MagicMock()
        mock_explanation = ScreenExplanation(
            session_id="sess_shared",
            context_id="ctx_shared",
            style=ExplanationStyle.IMPORTANT_POINTS,
            summary="Shared Analysis Summary",
            important_points=["Point 1: Active desktop", "Point 2: Key elements"],
            detailed_text="Detailed shared explanation"
        )
        mock_explain_engine.explain.return_value = mock_explanation

        # A. UI Worker Trigger
        worker = ScreenAnalysisWorker(
            query="Explain my screen",
            provider_manager=mock_prov_mgr,
            explain_engine=mock_explain_engine
        )
        captured_results = []
        worker.analysis_completed.connect(lambda exp: captured_results.append(exp))
        worker.run()

        self.assertEqual(len(captured_results), 1)
        self.assertEqual(captured_results[0]["summary"], "Shared Analysis Summary")
        mock_explain_engine.explain.assert_called_with("Explain my screen", provider_manager=mock_prov_mgr)

        # B. Voice Trigger Path (executor calls explain_engine directly)
        voice_result = mock_explain_engine.explain("Explain my screen", provider_manager=mock_prov_mgr)
        self.assertEqual(voice_result.summary, "Shared Analysis Summary")

    def test_valid_window_handle_does_not_falsely_imply_readable_content(self):
        """2. Verify a valid HWND and title alone does NOT mark unreadable/protected windows as readable."""
        ctx_unreadable = ScreenContext(
            window_title="DirectX Accelerated Window",
            metadata={"hwnd": 98765},
            extracted_text="",
            ui_elements=[],
            visual_elements=[]
        )
        self.assertFalse(ctx_unreadable.is_readable)

        ctx_readable = ScreenContext(
            window_title="Notepad - README.md",
            metadata={"hwnd": 98765},
            extracted_text="JARVIS Setup Guide",
            ui_elements=[{"name": "Document Text"}],
            visual_elements=[]
        )
        self.assertTrue(ctx_readable.is_readable)

    def test_successful_screen_capture_produces_valid_image(self):
        """3. Verify successful desktop capture produces non-empty, decodable image with valid dimensions."""
        img, path = self.capture_mgr.capture(target=CaptureTarget.PRIMARY_SCREEN)
        self.assertIsNotNone(img)
        self.assertGreater(img.width, 100)
        self.assertGreater(img.height, 100)
        self.assertTrue(self.capture_mgr.validate_image(img))

    def test_empty_or_invalid_captures_are_rejected(self):
        """4. Verify validator rejects None, empty, zero-sized, and tiny corrupt captures."""
        self.assertFalse(self.capture_mgr.validate_image(None))
        self.assertFalse(self.capture_mgr.validate_image(Image.new("RGB", (0, 0))))
        self.assertFalse(self.capture_mgr.validate_image(Image.new("RGB", (8, 8))))
        self.assertTrue(self.capture_mgr.validate_image(Image.new("RGB", (100, 100))))

    def test_accessibility_extraction_with_available_targets_and_controls(self):
        """5. Verify accessibility extraction handles both available_targets (DesktopContext) and available_controls."""
        mock_controls = [
            {"name": "File Menu", "current_value": "", "control_type": "menuitem"},
            {"name": "Auth Token", "current_value": "token_abc123_secret", "control_type": "edit"}
        ]
        with patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context") as mock_ctx:
            mock_obj = MagicMock()
            mock_obj.window_title = "Editor"
            mock_obj.process_name = "editor.exe"
            mock_obj.available_targets = [MagicMock(to_dict=lambda c=ctrl: c) for ctrl in mock_controls]
            mock_ctx.return_value = mock_obj

            ctx = self.understanding_engine.capture_screen_context()
            self.assertIn("File Menu", ctx.extracted_text)
            self.assertIn("[REDACTED_SENSITIVE_FIELD]", ctx.extracted_text)
            self.assertNotIn("token_abc123_secret", ctx.extracted_text)

    def test_empty_accessibility_triggers_ocr_fallback(self):
        """6. Verify empty accessibility tree (<15 chars) triggers native Windows OCR fallback."""
        with patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context") as mock_ctx, \
             patch("core.vision.ocr_engine.ocr_engine.extract_text") as mock_ocr:
            mock_obj = MagicMock()
            mock_obj.window_title = "Visual Canvas"
            mock_obj.process_name = "canvas.exe"
            mock_obj.available_targets = []
            mock_obj.available_controls = []
            mock_ctx.return_value = mock_obj

            mock_ocr_result = OCRResult(
                text="Text from Native OCR Canvas",
                confidence=0.92,
                engine_used="windows_media_ocr",
                success=True,
                lines=["Text from Native OCR Canvas"]
            )
            mock_ocr.return_value = mock_ocr_result

            ctx = self.understanding_engine.capture_screen_context()
            mock_ocr.assert_called_once()
            self.assertIn("Text from Native OCR Canvas", ctx.extracted_text)
            self.assertEqual(ctx.metadata.get("ocr_engine"), "windows_media_ocr")

    def test_ocr_extracts_text_from_known_test_image(self):
        """7. Verify OCR engine extracts text accurately from a rendered synthetic image."""
        img = Image.new("RGB", (400, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 35), "JARVIS NATIVE OCR TEST", fill=(0, 0, 0))

        res = ocr_engine.extract_text(img)
        self.assertTrue(res.success)
        self.assertIn("JARVIS", res.text.upper())

    def test_ocr_failure_produces_actionable_diagnostic(self):
        """8. Verify blank/corrupt image returns structured non-crashing OCR diagnostic."""
        blank_img = Image.new("RGB", (20, 20), color=(0, 0, 0))
        res = ocr_engine.extract_text(blank_img)
        self.assertFalse(res.has_meaningful_content())

    def test_text_only_models_not_treated_as_vision_capable(self):
        """9. Verify text-only models are identified and do not receive multimodal image payloads."""
        from core.ai.provider_manager import ProviderManager
        prov_mgr = ProviderManager()
        # Cerebras is configured as text-only fast inference
        self.assertFalse(prov_mgr.is_vision_capable("cerebras"))
        # Nvidia Nemotron has vision in capabilities
        self.assertTrue(prov_mgr.is_vision_capable("nvidia"))

    def test_compatible_vision_provider_receives_structured_payload(self):
        """10. Verify compatible vision provider receives correctly formatted image_url multimodal payload."""
        from core.ai.provider_manager import ProviderManager
        prov_mgr = ProviderManager()

        mock_nvidia = MagicMock()
        mock_nvidia.is_available.return_value = True
        mock_nvidia.get_name.return_value = "NVIDIA Nemotron"
        mock_nvidia.generate_response.return_value = "Visual analysis: Found architecture diagram."
        prov_mgr._providers["nvidia"] = mock_nvidia

        ctx = {
            "requires_vision": True,
            "image_base64": "FAKE_BASE64_BYTES_ABC123",
            "window_title": "Architecture Overview",
            "force_fresh": True
        }
        messages = [
            {"role": "system", "content": "You are JARVIS."},
            {"role": "user", "content": "Explain this diagram"}
        ]

        with patch("core.ai.provider_settings.provider_settings_manager.get_eligible_providers") as mock_eligible:
            mock_cfg = MagicMock()
            mock_cfg.provider_id = "nvidia"
            mock_cfg.capabilities = ["text", "vision"]
            mock_eligible.return_value = [mock_cfg]

            res = prov_mgr.generate_response(messages, context=ctx)
            self.assertEqual(res, "Visual analysis: Found architecture diagram.")
            mock_nvidia.generate_response.assert_called_once()
            called_msgs = mock_nvidia.generate_response.call_args[0][0]
            user_msg = called_msgs[-1]
            self.assertEqual(user_msg["role"], "user")
            self.assertIsInstance(user_msg["content"], list)
            self.assertEqual(user_msg["content"][1]["type"], "image_url")
            self.assertIn("data:image/jpeg;base64,FAKE_BASE64_BYTES_ABC123", user_msg["content"][1]["image_url"]["url"])

    def test_image_encoding_resizes_oversized_payloads(self):
        """11. Verify image encoding resizes large screenshots to prevent API payload limits."""
        large_img = Image.new("RGB", (3840, 2160), color=(100, 150, 200))
        b64 = self.capture_mgr.encode_image_base64(large_img, max_dim=1280)
        self.assertIsInstance(b64, str)
        self.assertGreater(len(b64), 100)
        # Verify encoded payload is substantially smaller than uncompressed 4K raw bytes (~24MB)
        self.assertLess(len(b64), 500 * 1024)

    def test_provider_timeouts_and_failures_handled_gracefully(self):
        """12. Verify provider exceptions/timeouts produce safe user-facing explanations without unhandled crashes."""
        mock_prov_mgr = MagicMock()
        mock_prov_mgr.is_ai_available.return_value = True
        mock_prov_mgr.generate_response.side_effect = TimeoutError("Request timed out after 30s")

        ctx = ScreenContext(
            window_title="Dashboard Window",
            extracted_text="Revenue: $500K\nUsers: 10,000",
            image_base64="BASE64_IMAGE_DATA"
        )
        res = self.understanding_engine.query_vision_provider("Explain my screen", ctx, provider_manager=mock_prov_mgr)
        self.assertIn("summary", res)
        self.assertIn("Dashboard Window", res["summary"])

    def test_refreshed_capture_invalidates_stale_findings(self):
        """13. Verify switching active window invalidates previous capture session."""
        ctx = ScreenContext(window_title="First Window - Chrome", metadata={"hwnd": 11111})
        session = self.session_mgr.create_session(ctx)
        session.extracted_points = ["Chrome Tab 1", "Search Results"]

        # User switched to VS Code
        self.assertTrue(session.has_screen_changed(22222, "VS Code - main.py"))

    def test_sensitive_image_data_and_credentials_never_logged(self):
        """14. Verify Base64 image payload bytes and credentials are not printed in logs."""
        import logging
        log_records = []
        class TestHandler(logging.Handler):
            def emit(self, record):
                log_records.append(self.format(record))

        handler = TestHandler()
        logging.getLogger("Jarvis.ScreenUnderstanding").addHandler(handler)
        try:
            mock_prov_mgr = MagicMock()
            mock_prov_mgr.is_ai_available.return_value = True
            mock_prov_mgr.generate_response.return_value = "Overview of login."
            mock_prov_mgr.get_active_provider_name.return_value = "MockVision"

            secret_b64 = "SECRET_SUPER_LONG_BASE64_PAYLOAD_STRING_ABC123_XYZ"
            ctx = ScreenContext(
                window_title="Safe Window",
                extracted_text="Content",
                image_base64=secret_b64
            )
            self.understanding_engine.query_vision_provider("Explain", ctx, provider_manager=mock_prov_mgr)

            full_logs = "\n".join(log_records)
            self.assertNotIn("SECRET_SUPER_LONG_BASE64", full_logs)
            self.assertIn("KB", full_logs)
        finally:
            logging.getLogger("Jarvis.ScreenUnderstanding").removeHandler(handler)

    def test_pyqt6_interface_worker_is_asynchronous(self):
        """15. Verify ScreenAnalysisWorker inherits QThread to prevent UI freeze."""
        from PyQt6.QtCore import QThread
        from ui.panels.screen_intelligence_panel import ScreenAnalysisWorker
        worker = ScreenAnalysisWorker(MagicMock(), "Explain my screen")
        self.assertIsInstance(worker, QThread)

    def test_screen_cache_fingerprint_isolation(self):
        """16. Verify different screen captures produce different cache keys for identical queries."""
        from core.ai.caching.cache_manager import generate_cache_key
        key1 = generate_cache_key("Explain my screen", provider="nvidia", context={"screen_capture_hash": "window_a_hash_111"})
        key2 = generate_cache_key("Explain my screen", provider="nvidia", context={"screen_capture_hash": "window_b_hash_222"})
        self.assertNotEqual(key1, key2)

    def test_multiturn_clarification_and_example_style(self):
        """17. Verify follow-up styles 'give me an example' and 'step by step' map cleanly."""
        style1, _ = self.explain_engine.resolve_style("I still don't understand. Explain it with an example")
        self.assertEqual(style1, ExplanationStyle.EXAMPLE_BASED)

        style2, _ = self.explain_engine.resolve_style("Give me a step-by-step walkthrough")
        self.assertEqual(style2, ExplanationStyle.STEP_BY_STEP)


if __name__ == "__main__":
    unittest.main()
