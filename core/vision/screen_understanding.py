"""Screen Understanding & Multimodal Visual Analysis Engine for JARVIS.

Integrates:
- Screen capture (desktop, window, region, file)
- Windows UI Automation structured element metadata
- Chrome CDP web tab metadata
- Multimodal Vision AI reasoning (NVIDIA Nemotron Super VL, GPT-4o, Gemini)
- Sensitive data masking and privacy controls
"""

import re
import time
import logging
from typing import Optional, Callable, Dict, Any, List

from core.vision.models import CaptureTarget, ScreenRegion, ScreenContext, VisualElement
from core.vision.screen_capture import screen_capture_manager, ScreenCaptureManager
from core.vision.ocr_engine import ocr_engine
from core.interaction.desktop_context_service import desktop_context_service

logger = logging.getLogger("Jarvis.ScreenUnderstanding")


class ScreenUnderstandingEngine:
    """Orchestrates desktop screen perception, structured accessibility metadata,
    OCR text extraction, and visual reasoning via multimodal AI models.
    """

    def __init__(self, capture_manager: Optional[ScreenCaptureManager] = None):
        self.capture_mgr = capture_manager or screen_capture_manager
        self._last_context: Optional[ScreenContext] = None
        self._is_analyzing: bool = False
        self._stop_requested: bool = False

        # Visual indicator callback: (is_active: bool, message: str)
        self.on_indicator_cb: Optional[Callable[[bool, str], None]] = None

    def request_stop(self):
        """Signals active screen analysis to cancel."""
        logger.info("[VISION] User requested stop for screen analysis.")
        self._stop_requested = True

    def _notify_indicator(self, active: bool, message: str):
        if self.on_indicator_cb:
            try:
                self.on_indicator_cb(active, message)
            except Exception as e:
                logger.debug(f"Indicator callback error: {e}")

    def capture_screen_context(
        self,
        target: CaptureTarget = CaptureTarget.PRIMARY_SCREEN,
        region: Optional[ScreenRegion] = None,
        hwnd: Optional[int] = None,
        custom_image_path: Optional[str] = None,
        include_base64: bool = True
    ) -> ScreenContext:
        """Captures screen image and merges with accessibility & desktop context,
        falling back to local OCR when accessibility text is missing or incomplete.
        """
        self._stop_requested = False
        self._notify_indicator(True, "Reading screen context...")

        try:
            # 1. Capture visual image
            image, file_path = self.capture_mgr.capture(
                target=target,
                region=region,
                hwnd=hwnd,
                custom_image_path=custom_image_path
            )

            # 2. Get desktop accessibility context
            window_title = "Active Desktop"
            process_name = "explorer.exe"
            raw_controls = []
            try:
                desktop_ctx = desktop_context_service.get_current_context()
                if desktop_ctx:
                    window_title = desktop_ctx.window_title or window_title
                    process_name = desktop_ctx.process_name or process_name
                    # DesktopContext model has 'available_targets', legacy or test mocks may have 'available_controls'
                    targets = []
                    for attr_name in ["available_controls", "available_targets"]:
                        candidate = getattr(desktop_ctx, attr_name, None)
                        if isinstance(candidate, (list, tuple)) and len(candidate) > 0:
                            targets = candidate
                            break

                    if not targets:
                        candidate = getattr(desktop_ctx, "available_targets", None) or getattr(desktop_ctx, "available_controls", None)
                        if isinstance(candidate, (list, tuple)):
                            targets = candidate

                    raw_controls = []
                    for c in targets:
                        if hasattr(c, "to_dict") and callable(c.to_dict):
                            raw_controls.append(c.to_dict())
                        elif isinstance(c, dict):
                            raw_controls.append(c)
                        elif hasattr(c, "__dict__"):
                            raw_controls.append(c.__dict__)
                        else:
                            try:
                                raw_controls.append(dict(c))
                            except Exception:
                                pass
            except Exception as e:
                logger.debug(f"Could not retrieve desktop accessibility context: {e}")

            # 3. Extract text from accessible controls (excluding password fields)
            extracted_lines = []
            sanitized_ui_elements = []

            for ctrl in raw_controls:
                name = str(ctrl.get("name", "") or "").strip()
                val = str(ctrl.get("current_value", "") or "").strip()
                ctrl_type = str(ctrl.get("control_type", "") or "").lower()

                # Sensitive field exclusion
                if any(k in name.lower() or k in ctrl_type for k in ["password", "pin", "credential", "token"]):
                    val = "[REDACTED_SENSITIVE_FIELD]"

                if name:
                    extracted_lines.append(f"{name}: {val}" if val and val != name else name)

                sanitized_ui_elements.append(ctrl)

            uia_text = "\n".join(extracted_lines)

            # 4. OCR Fallback if accessible text is missing or minimal (< 15 chars)
            ocr_text = ""
            ocr_conf = 1.0
            ocr_engine_used = "none"
            if (not uia_text or len(uia_text.strip()) < 15) and image:
                logger.info("[VISION] Accessible UI text is minimal. Attempting OCR on captured screenshot...")
                try:
                    ocr_res = ocr_engine.extract_text(image)
                    if ocr_res.success and ocr_res.has_meaningful_content():
                        ocr_text = ocr_res.text
                        ocr_conf = ocr_res.confidence
                        ocr_engine_used = ocr_res.engine_used
                        logger.info(f"[VISION] OCR fallback succeeded ({ocr_engine_used}): {len(ocr_text)} characters extracted.")
                except Exception as ex:
                    logger.debug(f"OCR fallback error: {ex}")

            # Combine UIA and OCR text cleanly
            if uia_text and ocr_text:
                combined_text = f"Accessible Controls:\n{uia_text}\n\nVisible Screen Text (OCR):\n{ocr_text}"
                source = "desktop_uia+ocr"
            elif ocr_text:
                combined_text = ocr_text
                source = f"desktop_ocr_{ocr_engine_used}"
            elif uia_text:
                combined_text = uia_text
                source = "desktop_uia"
            else:
                combined_text = ""
                source = "desktop_visual_only"

            # 5. Generate base64 representation if requested
            base64_str = None
            if include_base64 and image:
                base64_str = self.capture_mgr.encode_image_base64(image)

            context = ScreenContext(
                target=target,
                window_title=window_title,
                process_name=process_name,
                app_identity=process_name.replace(".exe", ""),
                region=region,
                image_path=file_path,
                image_base64=base64_str,
                extracted_text=combined_text,
                ui_elements=sanitized_ui_elements,
                ocr_confidence=ocr_conf,
                is_fresh=True,
                source=source,
                metadata={
                    "hwnd": getattr(desktop_ctx, "window_hwnd", 0) if desktop_ctx else (hwnd or 0),
                    "ocr_engine": ocr_engine_used,
                    "has_ocr": bool(ocr_text),
                    "has_uia": bool(uia_text),
                    "image_size": image.size if image else (0, 0)
                }
            )

            self._last_context = context
            return context

        finally:
            self._notify_indicator(False, "")

    def analyze_screen(
        self,
        prompt: str = "Explain what is on my screen in simple terms.",
        context: Optional[ScreenContext] = None,
        provider_manager: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Performs multimodal visual analysis on the captured screen context."""
        ctx = context or self.capture_screen_context()
        self._notify_indicator(True, "Analyzing screen with AI vision...")

        try:
            # Check for cancellation
            if self._stop_requested:
                return {
                    "summary": "Screen analysis was cancelled by the user.",
                    "important_points": [],
                    "code_snippets": [],
                    "error_diagnosis": None,
                    "model_used": "local_cancellation"
                }

            # Build multimodal prompt
            analysis_prompt = (
                f"You are JARVIS, an expert desktop visual assistant.\n"
                f"The user is viewing the window '{ctx.window_title}' (Application: {ctx.app_identity}).\n"
                f"User request: {prompt}\n\n"
            )
            if ctx.extracted_text:
                analysis_prompt += (
                    f"Visible Content & Extracted Text:\n"
                    f"\"\"\"\n{ctx.extracted_text[:2500]}\n\"\"\"\n\n"
                )

            analysis_prompt += (
                "Provide a clear, structured response with:\n"
                "1. Direct, concise overview of what is currently displayed.\n"
                "2. Key points / takeaways.\n"
                "3. Explanation of any code, diagrams, charts, or errors visible.\n"
                "4. Practical guidance or answers to the user's question."
            )

            # Ensure provider manager instance is available
            prov_mgr = provider_manager
            if not prov_mgr:
                from core.ai.provider_manager import ProviderManager
                prov_mgr = ProviderManager()

            # Query AI Provider
            response_text = None
            model_name = "local_heuristic"

            if prov_mgr and prov_mgr.is_ai_available():
                # Build vision-capable message structure
                messages = [
                    {"role": "system", "content": "You are JARVIS, an intelligent and polite desktop companion."},
                    {"role": "user", "content": analysis_prompt}
                ]

                # Pass image context for multimodal models if supported
                ai_context = {
                    "requires_vision": True,
                    "image_base64": ctx.image_base64,
                    "window_title": ctx.window_title,
                    "capture_id": ctx.context_id,
                    "max_tokens": 2048
                }

                # Safe telemetry log (never log base64 data)
                b64_len = len(ctx.image_base64) if ctx.image_base64 else 0
                logger.info(
                    f"[VISION] Submitting multimodal request to ProviderManager: "
                    f"Title='{ctx.window_title}', ImageB64={b64_len/1024:.1f} KB, "
                    f"ExtractedTextLen={len(ctx.extracted_text)}"
                )

                try:
                    response_text = prov_mgr.generate_response(messages, context=ai_context)
                    if response_text:
                        model_name = prov_mgr.get_active_provider_name()
                except Exception as e:
                    logger.error(f"Multimodal vision query failed: {e}")

            if not response_text:
                # Deterministic fallback response based on UIA + OCR extracted content
                response_text = self._generate_fallback_explanation(ctx, prompt)

            # Parse structured elements (points, code, errors)
            parsed_result = self._parse_structured_analysis(response_text, model_name)
            return parsed_result

        finally:
            self._notify_indicator(False, "")

    def _generate_fallback_explanation(self, ctx: ScreenContext, prompt: str) -> str:
        """Generates a truthful local fallback explanation when cloud vision AI is offline or unavailable."""
        lines = [
            f"Here is what is currently visible in **{ctx.window_title}** ({ctx.app_identity}):\n"
        ]
        if ctx.extracted_text:
            lines.append("### Key Visible Elements & Text:")
            for item in ctx.extracted_text.splitlines()[:12]:
                if item.strip():
                    lines.append(f"- {item.strip()}")
            lines.append("\n*Note:* Screen text was extracted via local accessibility and Windows OCR.")
        else:
            lines.append("- The active window is open, but did not expose readable accessibility elements or text.")
            lines.append("- The window may be protected, minimized, or purely visual graphic content without text.")

        lines.append(f"\n*Summary:* Displaying active window '{ctx.window_title}'.")
        return "\n".join(lines)

    def _parse_structured_analysis(self, raw_text: str, model_used: str) -> Dict[str, Any]:
        """Extracts bullet points, code snippets, and error notes from text output."""
        points = []
        for line in raw_text.splitlines():
            line_str = line.strip()
            if re.match(r"^[\*\-\•\d+\.]\s+(.+)$", line_str):
                cleaned = re.sub(r"^[\*\-\•\d+\.]\s+", "", line_str).strip()
                if len(cleaned) > 5 and not cleaned.startswith("#"):
                    points.append(cleaned)

        code_snippets = []
        for match in re.finditer(r"```([a-zA-Z0-9_\-\+]*)\n(.*?)```", raw_text, re.DOTALL):
            lang = match.group(1).strip() or "text"
            code = match.group(2).strip()
            code_snippets.append({"language": lang, "code": code})

        error_diagnosis = None
        err_m = re.search(r"(?:error|exception|failure|bug)[:\s]+([^\n\.]+)", raw_text, re.IGNORECASE)
        if err_m:
            error_diagnosis = err_m.group(0).strip()

        return {
            "full_text": raw_text,
            "summary": raw_text.split("\n\n")[0] if "\n\n" in raw_text else raw_text[:200],
            "important_points": points[:8],
            "code_snippets": code_snippets,
            "error_diagnosis": error_diagnosis,
            "model_used": model_used
        }

    def get_last_context(self) -> Optional[ScreenContext]:
        """Returns the most recent screen context captured."""
        return self._last_context

    # Alias for multimodal vision queries
    query_vision_provider = analyze_screen


# Global singleton instance
screen_understanding_engine = ScreenUnderstandingEngine()
