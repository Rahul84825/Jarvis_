import json
import logging
import re
from pathlib import Path
from core.command_normalizer import CommandNormalizer
from core.platform.platform_manager import platform_manager
from core.os.application_resolver import application_resolver, TargetType
from modules.browser.web_control import web_control
from core.apps.application_discovery import app_discovery
from core.custom_commands.command_manager import command_manager
from core.custom_commands.command_registry import custom_command_registry
from memory.persistent_memory import persistent_memory
from core.os.browser_intent import BrowserIntentParser, BrowserActionType
from core.os.browser_session import browser_session_manager

logger = logging.getLogger("Jarvis.IntentEngine")

class IntentEngine:
    """Consumes natural language speech transcripts or normalized commands and classifies
    them into deterministic, structured intent nodes.
    
    Features:
    - Action + Target vocabulary pattern matching
    - Strict distinction between Action Requests and Informational Questions (Safety First)
    - Pronominal context tracking ("close it", "minimize it")
    - Dedicated distinction between OPEN_NEW_CHROME_TAB, OPEN_NEW_CHROME_WINDOW, and OPEN_APP
    - Local execution with zero external LLM API latency (< 5ms)
    - Extensible application, website, and system action registry
    """

    def __init__(self):
        logger.info("Initializing Jarvis Deterministic Intent Engine.")
        self.normalizer = CommandNormalizer()
        self.apps_json_path = Path(__file__).parent.parent / "config" / "applications.json"
        self.app_aliases = self._load_app_aliases()
        self.last_app_target = None
        self.browser_intent_parser = BrowserIntentParser()

    def _load_app_aliases(self) -> dict:
        """Loads canonical application definitions and spoken aliases from applications.json."""
        aliases_map = {}
        if self.apps_json_path.exists():
            try:
                with open(self.apps_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for app_key, app_data in data.items():
                        aliases_map[app_key.lower()] = app_key
                        for alias in app_data.get("aliases", []):
                            aliases_map[alias.lower()] = app_key
            except Exception as e:
                logger.error(f"Failed to load applications.json in IntentEngine: {e}")
        return aliases_map

    def resolve_app_name(self, raw: str) -> str:
        """Resolves raw application name or alias to canonical application key, checking generic preferences and learned aliases."""
        if not raw:
            return ""
        clean = raw.lower().strip()

        # Check generic concepts and learned aliases first (Phase 4 & 6)
        try:
            if clean in ["browser", "web browser", "internet"]:
                learned_browser = persistent_memory.get_user_learned_preference("browser_preference", "default_browser") or persistent_memory.get_preference("preferred_browser")
                if learned_browser:
                    return learned_browser
            elif clean in ["editor", "text editor", "code editor"]:
                learned_editor = persistent_memory.get_user_learned_preference("editor_preference", "default_editor") or persistent_memory.get_preference("preferred_editor")
                if learned_editor:
                    return learned_editor

            learned_alias = persistent_memory.get_user_learned_preference("app_alias", clean)
            if learned_alias:
                return learned_alias
        except Exception:
            pass

        # Direct lookup in alias registry (canonical applications on OS: chrome, notepad, etc.)
        if clean in self.app_aliases:
            return self.app_aliases[clean]

        # Check multi-word alias matches
        for alias, app_key in self.app_aliases.items():
            if clean == alias or clean.endswith(" " + alias) or clean.startswith(alias + " "):
                return app_key

        best_app, _ = app_discovery.find_application(clean)
        if best_app:
            return best_app.app_id

        return clean

    def _resolve_search_provider_and_query(self, query: str) -> tuple[str, str, str, str]:
        """Resolves target provider, clean target, exact query, and browser from extracted search query string.
        Returns: (provider, target_q, exact_q, browser)
        """
        q_strip = query.strip()
        browser = "default"

        # 0. Check explicit browser postfix: "... in chrome", "... using brave", "... on brave", "... in brave"
        b_postfix_m = re.search(r"\b(?:in|using|with|on)\s+(chrome|chromium|edge|firefox|brave|opera)\s*$", q_strip, re.IGNORECASE)
        if b_postfix_m:
            browser = b_postfix_m.group(1).lower()
            q_strip = q_strip[:b_postfix_m.start()].strip()

        # Check explicit browser prefix: "brave for ...", "in brave for ...", "chrome for ..."
        b_prefix_m = re.match(r"^(?:in\s+|using\s+|on\s+)?(chrome|chromium|edge|firefox|brave|opera)\s+for\s+(.+)$", q_strip, re.IGNORECASE | re.DOTALL)
        if b_prefix_m:
            browser = b_prefix_m.group(1).lower()
            q_strip = b_prefix_m.group(2).strip()

        # 1. Targeted site postfix: "search for Python tutorials on YouTube"
        on_match = re.match(r"^(?:for\s+)?(.+?)\s+on\s+(youtube|github|reddit|stackoverflow|stack overflow|google)$", q_strip, re.IGNORECASE)
        if on_match:
            prov = on_match.group(2).lower()
            if prov == "stack overflow":
                prov = "stackoverflow"
            extracted = on_match.group(1).strip()
            return prov, extracted.lower(), extracted, browser

        # 2. Local project code search: "search my project for ...", "search this project for ..."
        proj_match = re.match(r"^(?:in\s+|for\s+)?(?:my\s+|this\s+)?project\s+for\s+(.+)$", q_strip, re.IGNORECASE)
        if proj_match:
            extracted = proj_match.group(1).strip()
            return "project", extracted, extracted, browser

        # 3. Provider prefixes: "YouTube for ...", "for YouTube ...", "GitHub for ...", etc.
        prov_patterns = [
            (r"^(?:for\s+)?(?:google|the web|web)\s+for\s+(.+)$", "google"),
            (r"^(?:for\s+)?(?:youtube)\s+for\s+(.+)$", "youtube"),
            (r"^(?:for\s+)?(?:github)\s+for\s+(.+)$", "github"),
            (r"^(?:for\s+)?(?:reddit)\s+for\s+(.+)$", "reddit"),
            (r"^(?:for\s+)?(?:stackoverflow|stack overflow)\s+for\s+(.+)$", "stackoverflow"),
        ]
        for pat, prov in prov_patterns:
            m = re.match(pat, q_strip, re.IGNORECASE | re.DOTALL)
            if m:
                extracted = m.group(1).strip()
                return prov, extracted.lower(), extracted, browser

        # 4. Clean leading "for " or "about " from general queries while preserving original casing
        clean_q = re.sub(r"^(?:for|about)\s+", "", q_strip, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r"^(?:the\s+web\s+for|web\s+for)\s+", "", clean_q, flags=re.IGNORECASE).strip()
        return "google", clean_q.lower(), clean_q, browser

    def _is_informational_query(self, raw_text: str, clean_text: str) -> bool:
        """Strictly identifies questions and informational queries that must NOT trigger actions."""
        # Bypass for desktop screen intelligence, explain engine, and file queries
        if re.search(r"^explain\s+(?:my\s+screen|this\s+page|the\s+screen|this\s+code|this\s+error|this\s+graph|this\s+pdf|point\s+\d+|the\s+\w+\s+point|this\s+like|it\s+with|the\s+second|the\s+third|the\s+first)\b", clean_text, re.IGNORECASE):
            return False
        if re.search(r"^(?:where\s+did\s+i\s+save|where\s+is\s+my\s+.*(?:program|file|code|repository|project)|search\s+my\s+files)\b", clean_text, re.IGNORECASE):
            return False
        if re.search(r"^(?:what\s+are\s+the\s+important\s+points|what\s+does\s+this\s+error\s+mean|what\s+does\s+that\s+error\s+mean|what\s+is\s+this\s+button\s+used\s+for|compare\s+these\s+two)\b", clean_text, re.IGNORECASE):
            return False

        if re.search(r"^(?:explain|describe|tell\s+me)\s+(?:what\s+is\s+on|what's\s+on)\s+(?:my\s+|this\s+|the\s+)?(?:screen|page)\b", clean_text, re.IGNORECASE):
            return False
        if re.search(r"^(?:explain|analyze|inspect|summarize)\s+(?:what\s+is\s+on\s+)?(?:my\s+|this\s+|the\s+|current\s+)?(?:screen|page|website|tab|code|error|visible\s+code)\b", clean_text, re.IGNORECASE):
            return False
        if re.search(r"^what\s+(?:is|'s)\s+on\s+(?:this|my|the)\s+screen\b", clean_text, re.IGNORECASE):
            return False
        if re.search(r"^explain\s+(?:the\s+)?code\s+visible\b", clean_text, re.IGNORECASE):
            return False

        if re.search(r"^explain\s+(?:this\s+)?(?:python\s+)?error\b", clean_text, re.IGNORECASE) or re.search(r"^explain\s+what\s+tools\b", clean_text, re.IGNORECASE):
            return False

        # Informational question starters (strictly information seeking, not polite requests)
        info_starters = [
            r"^how\s+(?:do\s+i|to|can\s+i|would\s+i|should\s+i)\b",
            r"^why\s+(?:does|do|is|should\s+i|would|did)\b",
            r"^what\s+(?:is|are|happens\s+if|happens\s+when|does)\b",
            r"^tell\s+me\s+(?:about|how\s+to)\b",
            r"^can\s+you\s+(?:explain|tell\s+me\s+about|tell\s+me\s+how)\b",
            r"^could\s+you\s+(?:explain|tell\s+me\s+about|tell\s+me\s+how)\b",
            r"^explain\b",
            r"^should\s+i\b",
            r"^is\s+(?:it\s+good\s+to|chrome\s+better|there)\b",
            r"^do\s+you\s+know\b",
            r"^which\s+way\s+to\b",
            r"^where\s+(?:are\s+my|is\s+my|are\s+downloaded)\b",
            r"^who\s+is\s+the\b"
        ]

        for q_pat in info_starters:
            if re.search(q_pat, clean_text, re.IGNORECASE) or re.search(q_pat, raw_text, re.IGNORECASE):
                return True

        return False

    def parse(self, text: str, raw_text: str = None) -> dict:
        """Analyzes speech transcript or text and extracts structured intent with confidence scoring."""
        if not text or not isinstance(text, str) or not text.strip():
            return {
                "intent": "unknown",
                "action": None,
                "target": None,
                "confidence": 0.0,
                "query": "",
                "raw_text": text or "",
                "fallback_message": "I didn't catch that. Please speak again."
            }

        effective_raw = raw_text or text
        raw_text = effective_raw.strip() if effective_raw else ""
        norm_res = self.normalizer.normalize(text)
        clean = norm_res["normalized"].lower().strip()

        # -------------------------------------------------------------
        # 0. UNIVERSAL INTENT-BASED BROWSER & WEBSITE AUTOMATION (PHASE 8)
        # -------------------------------------------------------------
        try:
            b_ctx = browser_session_manager.get_context_for_parser()
            b_res = self.browser_intent_parser.parse(effective_raw, session_context=b_ctx)
            if b_res.action_type != BrowserActionType.UNKNOWN:
                logger.info(f"[BROWSER_INTENT] Matched '{b_res.action_type.value}' for '{effective_raw}'")
                return b_res.to_dict()
        except Exception as b_err:
            logger.debug(f"[BROWSER_INTENT] Parser error: {b_err}")

        # -------------------------------------------------------------
        # 0A. DEDICATED YOUTUBE SEARCH INTENT (TOP PRECEDENCE)
        # -------------------------------------------------------------
        is_yt, yt_query, yt_browser = self.normalizer.extract_youtube_search(effective_raw)
        if not is_yt and clean:
            is_yt, yt_query, yt_browser = self.normalizer.extract_youtube_search(clean)

        if is_yt:
            clean_yt = yt_query.strip()
            logger.info(f"[SEARCH] Dedicated YouTube search intent recognized. Query: '{clean_yt}', Browser: '{yt_browser}'")
            return {
                "intent": "web_search",
                "action": "search",
                "provider": "youtube",
                "target": clean_yt,
                "query": clean_yt,
                "browser": yt_browser,
                "empty_query": not bool(clean_yt),
                "confidence": 1.0,
                "raw_text": effective_raw,
                "is_explicit_search": True
            }

        # -------------------------------------------------------------
        # 0B. GENERAL EXPLICIT SEARCH INTENT (HIGHEST PRIORITY)
        # -------------------------------------------------------------
        # Must be evaluated BEFORE question classification, local fallback, or other commands.
        is_search, extracted_query = self.normalizer.extract_explicit_search(effective_raw)
        if not is_search and clean:
            is_search, extracted_query = self.normalizer.extract_explicit_search(clean)

        if is_search:
            clean_query = extracted_query.strip()
            logger.info("[SEARCH] Explicit search prefix detected")
            logger.info(f"[SEARCH] Original input: '{effective_raw}'")
            logger.info(f"[SEARCH] Extracted query: '{clean_query}'")

            # Check for in-app search destination: "in this application", "in the current app", etc.
            m_app_search = re.search(r"\b(?:in|on)\s+(?:this\s+application|this\s+app|the\s+current\s+application|current\s+app)\s*$", clean_query, re.IGNORECASE)
            if not m_app_search:
                m_app_search = re.search(r"\b(?:in|on)\s+(chatgpt)\s*$", clean_query, re.IGNORECASE)
            if m_app_search:
                dest_found = m_app_search.group(1).lower() if m_app_search.lastindex and m_app_search.group(1) else "current_application"
                app_q = clean_query[:m_app_search.start()].strip()
                app_q = re.sub(r"^(?:for|about)\s+", "", app_q, flags=re.IGNORECASE).strip()
                logger.info(f"[DESKTOP] Explicit in-app search detected: query='{app_q}', destination='{dest_found}'")
                return {
                    "intent": "desktop_interaction.search_app",
                    "action": "search_in_app",
                    "query": app_q,
                    "text": app_q,
                    "target": app_q,
                    "destination": dest_found,
                    "confidence": 0.98,
                    "raw_text": effective_raw
                }

            if not clean_query:
                logger.info("[SEARCH] Route selected: BrowserManager.search (Empty query clarification)")
                return {
                    "intent": "web_search",
                    "action": "search",
                    "provider": "google",
                    "target": "",
                    "query": "",
                    "empty_query": True,
                    "confidence": 1.0,
                    "raw_text": effective_raw,
                    "is_explicit_search": True
                }

            prov, target_q, exact_q, browser_target = self._resolve_search_provider_and_query(clean_query)
            if prov == "project":
                logger.info(f"[SEARCH] Route selected: Local code search ({exact_q})")
                return {
                    "intent": "local_search",
                    "action": "search_code",
                    "target": target_q,
                    "query": exact_q,
                    "confidence": 1.0,
                    "raw_text": effective_raw,
                    "is_explicit_search": True
                }

            logger.info(f"[SEARCH] Route selected: BrowserManager.search ({prov}) | Browser: '{browser_target}'")
            return {
                "intent": "web_search",
                "action": "search",
                "provider": prov,
                "browser": browser_target,
                "target": exact_q,
                "query": exact_q,
                "empty_query": False,
                "confidence": 1.0,
                "raw_text": effective_raw,
                "is_explicit_search": True
            }

        logger.info(f"Intent Engine analyzing command: '{clean}' (Raw: '{effective_raw}')")

        if not clean:
            return {
                "intent": "unknown",
                "action": None,
                "target": None,
                "confidence": 0.0,
                "query": "",
                "raw_text": raw_text,
                "fallback_message": "I didn't catch that. Please speak again."
            }

        # Check Spotify Commands
        spotify_node = self._parse_spotify_command(raw_text, clean, effective_raw)
        if spotify_node:
            return spotify_node

        # Check Panel Visibility Commands (Show / Hide / Minimize / Restore Santra)
        panel_node = self._parse_panel_visibility_command(raw_text, clean, effective_raw)
        if panel_node:
            return panel_node

        # -------------------------------------------------------------
        # 1. DIAGNOSTICS & SYSTEM TESTING
        # -------------------------------------------------------------
        # 1. DIAGNOSTICS & SYSTEM TESTING
        # -------------------------------------------------------------
        if any(term in clean for term in ["test microphone", "microphone test", "check microphone", "test my microphone"]):
            return {"intent": "test_microphone", "action": "run_microphone_diagnostics", "target": "microphone", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(term in clean for term in ["test your speakers", "test speakers", "test speaker", "speaker test", "test audio output", "test audio", "test sound"]):
            return {"intent": "test_speakers", "action": "test_speakers", "target": "speakers", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(term in clean for term in ["test speech", "speech test", "test voice", "can you speak"]):
            return {"intent": "test_speech", "action": "test_speech", "target": "speech", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 4. EXPLICIT COMMAND-MANAGEMENT INTENTS
        # -------------------------------------------------------------
        if command_manager.is_command_management_query(clean) or command_manager.is_command_management_query(effective_raw):
            logger.info(f"[ROUTER] Command management query detected: '{clean}'")
            return {
                "intent": "command_management",
                "action": "manage_commands",
                "target": clean,
                "confidence": 0.98,
                "query": clean,
                "raw_text": effective_raw
            }

        # -------------------------------------------------------------
        # 5. VALIDATED CUSTOM COMMAND MATCHES
        # -------------------------------------------------------------
        custom_cmd, conf = custom_command_registry.find_matching_command(clean)
        if not custom_cmd and effective_raw:
            custom_cmd, conf = custom_command_registry.find_matching_command(effective_raw)

        if custom_cmd and conf >= 0.85:
            logger.info(f"[ROUTER] Validated custom command matched: '{custom_cmd.name}' (Confidence: {conf:.2f})")
            return {
                "intent": "custom_command",
                "action": "execute_workflow",
                "command_id": custom_cmd.command_id,
                "command_name": custom_cmd.name,
                "workflow": custom_cmd.workflow_definition,
                "risk_level": custom_cmd.risk_classification,
                "target": custom_cmd.name,
                "confidence": conf,
                "query": clean,
                "raw_text": effective_raw
            }

        # -------------------------------------------------------------
        # 1B. CAMERA & VISION PERCEPTION INTENTS
        # -------------------------------------------------------------
        if any(term in clean for term in [
            "turn on the camera", "turn on camera", "start camera", "enable camera",
            "start vision", "open vision", "turn on vision",
            "activate camera", "activate vision", "enable webcam", "turn on webcam", "start webcam"
        ]):
            return {"intent": "turn_on_camera", "action": "camera.start", "target": "camera", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(term in clean for term in [
            "turn off the camera", "turn off camera", "stop camera", "disable camera",
            "stop vision", "close vision", "turn off vision",
            "deactivate camera", "deactivate vision", "disable webcam", "turn off webcam", "stop webcam"
        ]):
            return {"intent": "turn_off_camera", "action": "camera.stop", "target": "camera", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(term in clean for term in [
            "start hand tracking", "open hand tracking", "track my hands",
            "enable hand tracking", "start gestures", "open gestures", "enable gestures", "watch my hands"
        ]):
            return {"intent": "start_hand_tracking", "action": "vision.start_hands", "target": "hands", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(term in clean for term in [
            "stop hand tracking", "close hand tracking", "disable hand tracking",
            "stop gestures", "close gestures", "disable gestures"
        ]):
            return {"intent": "stop_hand_tracking", "action": "vision.stop_hands", "target": "hands", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if ("screen" not in clean and "desktop" not in clean and "display" not in clean) and any(term in clean for term in [
            "take a photo", "take a camera picture", "take a picture", "take photo",
            "camera snapshot", "capture camera snapshot", "capture camera frame", "capture frame"
        ]):
            return {"intent": "camera_snapshot", "action": "camera.capture_frame", "target": "snapshot", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 2. TIME & DATE INTENTS
        # -------------------------------------------------------------
        time_triggers = ["what time is it", "what's the time", "tell me the time", "current time", "what is the time", "time now", "time", "the time", "what time do you have"]
        if clean in time_triggers or any(clean.startswith(t) for t in ["what time", "tell me what time", "tell me the time", "current time", "what is the current time"]):
            return {"intent": "time_query", "action": "get_time", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(kw in clean for kw in ["today s date", "todays date", "today date", "what is the date", "what is today's date", "what day is it", "current date", "what is today", "which day is today", "what date is", "tell me the date", "tell me today's date", "tell me todays date", "date today"]):
            return {"intent": "date_query", "action": "get_date", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 3. MATH & CALCULATOR INTENTS
        # -------------------------------------------------------------
        math_match = (
            clean.startswith("calculate ") or clean.startswith("solve ") or clean.startswith("math ") or
            re.search(r'\b\d+\s*[xX*+\-\/^%]\s*\d+\b', clean) or
            re.search(r'^(?:watch|what is|what\'s|whats|how much is)\s*\d+\s*[xX*+\-\/^%]\s*\d+', clean) or
            re.search(r'\b\d+\s*(?:times|plus|minus|divided by|multiplied by|to the power of|percent of)\s*\d+\b', clean) or
            (any(kw in clean for kw in [" plus ", " minus ", " multiplied by ", " divided by ", " times ", " percent of ", " to the power of ", "*", "+", "/", "% of"]) and any(char.isdigit() for char in clean))
        )
        if math_match:
            return {"intent": "math_calculation", "action": "calculate", "target": clean, "confidence": 0.96, "query": clean, "raw_text": raw_text}


        # -------------------------------------------------------------
        # 4. IDENTITY, PERSONALITY, HUMOR & DYNAMIC HELP INTENTS
        # -------------------------------------------------------------
        raw_clean = effective_raw.lower().strip()

        # 4.1 Personality & Tone Controls
        # Tone adjustments
        if any(p in clean or p in raw_clean for p in ["be more funny", "be funny", "talk funny", "more jokes", "tell more jokes"]):
            return {"intent": "social_personality", "action": "set_tone", "target": "funny", "tone": "funny", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(p in clean or p in raw_clean for p in ["stop being sarcastic", "be professional", "talk professionally", "professional mode", "act professional"]):
            return {"intent": "social_personality", "action": "set_tone", "target": "professional", "tone": "professional", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(p in clean or p in raw_clean for p in ["talk casually", "be casual", "use your normal personality", "be normal", "normal personality", "reset personality", "normal tone"]):
            return {"intent": "social_personality", "action": "set_tone", "target": "normal", "tone": "normal", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(p in clean or p in raw_clean for p in ["be more dramatic", "be dramatic", "be futuristic", "be more futuristic", "futuristic style", "dramatic mode"]):
            return {"intent": "social_personality", "action": "set_tone", "target": "dramatic", "tone": "dramatic", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # Response length
        if any(p in clean or p in raw_clean for p in ["keep it short", "be concise", "short responses", "keep responses short", "be brief"]):
            return {"intent": "social_personality", "action": "set_length", "target": "concise", "length": "concise", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if not ("short answer" in clean or "short answer" in raw_clean) and any(p in clean or p in raw_clean for p in ["explain things in detail", "be detailed", "give detailed responses", "be more detailed", "explain in detail"]):
            return {"intent": "social_personality", "action": "set_length", "target": "detailed", "length": "detailed", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # Humor toggle
        if any(p in clean or p in raw_clean for p in ["don't tell jokes", "dont tell jokes", "don t tell jokes", "disable humor", "turn off humor", "stop telling jokes", "no jokes", "no more jokes"]):
            return {"intent": "social_personality", "action": "toggle_humor", "target": "disable", "humor": False, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(p in clean or p in raw_clean for p in ["enable humor", "turn on humor", "start telling jokes", "allow humor"]):
            return {"intent": "social_personality", "action": "toggle_humor", "target": "enable", "humor": True, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 4.2 Humor, Jokes, Roasts & Fun Facts
        # Follow-up "another one"
        if clean in ["another one", "tell me another", "give me another", "give me another one", "one more", "tell another", "another"] or clean.startswith("another ") or raw_clean.startswith("another "):
            return {"intent": "social_humor", "action": "followup", "target": "another", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # Roasts
        if any(r in clean or r in raw_clean for r in ["roast my code", "roast this code", "roast the code", "roast code"]):
            return {"intent": "social_humor", "action": "roast", "target": "code", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(r in clean or r in raw_clean for r in ["roast me", "give me a savage reply", "be savage", "be sarcastic", "savage reply", "give me a roast"]):
            return {"intent": "social_humor", "action": "roast", "target": "user", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # Fun Facts & Trivia
        if any(f in clean or f in raw_clean for f in [
            "tell me a random fun fact", "tell me a fun fact", "give me a tech fact", 
            "give me a fun fact", "tell me a fact", "fun fact", "random fact", 
            "tech fact", "tell me something interesting"
        ]):
            cat = "tech" if "tech" in clean or "tech" in raw_clean else None
            return {"intent": "social_humor", "action": "fun_fact", "category": cat, "target": "fact", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # Dramatic Introduction
        if any(d in clean or d in raw_clean for d in [
            "introduce yourself dramatically", "say something that sounds like a futuristic ai", 
            "dramatic introduction", "dramatic intro", "introduce yourself"
        ]):
            return {"intent": "social_humor", "action": "dramatic_intro", "target": "intro", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # Jokes by category
        if any(j in clean or j in raw_clean for j in [
            "tell me a programming joke", "tell me a coding joke", "make a joke about programmers", 
            "coding joke", "programming joke", "give me a programming joke", "tell a programming joke"
        ]):
            return {"intent": "social_humor", "action": "tell_joke", "category": "programming", "target": "programming", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(j in clean or j in raw_clean for j in ["tell me a dark joke", "dark joke", "give me a dark joke"]):
            return {"intent": "social_humor", "action": "tell_joke", "category": "dark", "target": "dark", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(j in clean or j in raw_clean for j in [
            "tell me a nerdy joke", "give me a nerdy joke", "tell me a tech joke", 
            "tech joke", "nerdy joke"
        ]):
            return {"intent": "social_humor", "action": "tell_joke", "category": "tech", "target": "tech", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean == "joke" or raw_clean == "joke" or any(j in clean or j in raw_clean for j in [
            "tell me a joke", "tell a joke", "make me laugh", "say something funny", 
            "tell me another joke", "tell another joke", "crack a joke", "another joke"
        ]):
            return {"intent": "social_humor", "action": "tell_joke", "category": None, "target": "general", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 4.3 Casual Conversation Queries
        if any(b in clean or b in raw_clean for b in ["i'm bored", "im bored", "i am bored", "feeling bored"]):
            return {"intent": "social_chat", "action": "bored", "target": "bored", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(g in clean or g in raw_clean for g in ["guess what", "guess what?"]):
            return {"intent": "social_chat", "action": "guess_what", "target": "guess_what", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(s in clean or s in raw_clean for s in ["surprise me", "surprise me!"]):
            return {"intent": "social_chat", "action": "surprise_me", "target": "surprise_me", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(t in clean or t in raw_clean for t in ["let's talk", "lets talk"]):
            return {"intent": "social_chat", "action": "lets_talk", "target": "lets_talk", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(m in clean or m in raw_clean for m in ["nice to meet you", "good to see you", "pleasure to meet you"]):
            return {"intent": "social_chat", "action": "nice_to_meet", "target": "nice_to_meet", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 4.4 Identity & Truthful Self-Awareness Queries
        if any(q in clean or q in raw_clean for q in ["what does santra stand for", "what's santra stand for", "what does jarvis stand for", "what's jarvis stand for", "what does stand for", "what does the name santra stand for", "what does the name jarvis stand for", "what does your name stand for", "santra acronym", "jarvis acronym", "full form of santra", "full form of jarvis", "stand for"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "acronym", "target": "acronym", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(q in clean or q in raw_clean for q in ["who created you", "who built you", "who is your developer", "who developed you", "who made you", "who is your creator", "who designed you"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "creator", "target": "creator", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(q in clean or q in raw_clean for q in ["what is your purpose", "what's your purpose", "what is your objective", "what are you for", "why were you created"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "purpose", "target": "purpose", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(q in clean or q in raw_clean for q in ["are you a real person", "are you an ai", "are you real", "are you human", "are you a bot", "are you a robot"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "ai_nature", "target": "ai_nature", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(q in clean or q in raw_clean for q in ["are you like chatgpt", "what makes you different", "how are you different from chatgpt", "difference between you and chatgpt", "are you chatgpt"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "chatgpt_comparison", "target": "chatgpt_comparison", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(q in clean or q in raw_clean for q in ["what makes you intelligent", "how are you intelligent", "how do you work", "what is your architecture"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "intelligence_architecture", "target": "intelligence_architecture", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(q in clean or q in raw_clean for q in ["are you always listening", "are you recording me", "do you store my voice", "what about my privacy", "how do you listen"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "listening_privacy", "target": "listening_privacy", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(clean == q or clean.startswith(q + " ") or raw_clean == q or raw_clean.startswith(q + " ") for q in ["can you hear me", "can you hear me santra", "can you hear me jarvis", "hear me"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "can_you_hear_me", "target": "can_you_hear_me", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(q in clean or q in raw_clean for q in ["can you control my computer", "can you control this pc", "can you control the computer"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "computer_control", "target": "computer_control", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(q in clean or q in raw_clean for q in ["can you work without internet", "can you work without the internet", "can you work offline", "do you work offline", "do you need internet", "work without internet"]):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "offline_work", "target": "offline_work", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        identity_queries = [
            "who are you", "who owns you", "what is your name", "what's your name", "tell me about yourself"
        ]
        if any(iq in clean for iq in identity_queries):
            return {"intent": "identity", "action": "explain_identity", "sub_type": "general", "target": "general", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 4.5 Dynamic Help & Capability Queries
        # Specific capability inquiries
        if any(clean == q or clean.startswith(q + " ") for q in ["can you search youtube", "can you search youtube for videos", "do you support youtube search", "can you use youtube"]):
            return {"intent": "help", "action": "explain_capability", "scope": "youtube", "target": "youtube", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(clean == q or clean.startswith(q + " ") for q in ["can you open applications", "can you launch apps", "can you open apps", "can you open programs"]):
            return {"intent": "help", "action": "explain_capability", "scope": "applications", "target": "applications", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(clean == q or clean.startswith(q + " ") for q in ["can you search the web", "can you search google", "can you search internet", "can you search online"]):
            return {"intent": "help", "action": "explain_capability", "scope": "search", "target": "search", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(clean == q or clean.startswith(q + " ") for q in ["what can you do offline", "what can santra do offline", "what can jarvis do offline", "offline capabilities", "what can you do without internet", "show offline features"]):
            return {"intent": "help", "action": "explain_capability", "scope": "offline", "target": "offline", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(clean == q or clean.startswith(q + " ") for q in ["what features are currently unavailable", "what is unavailable", "unavailable features", "what features are disabled"]):
            return {"intent": "help", "action": "explain_capability", "scope": "unavailable", "target": "unavailable", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        raw_lower = raw_text.lower().strip('?!. ')

        # Scoped help / capability discovery
        scoped_patterns = [
            (r"^(?:list|show|what\s+are(?:\s+the)?)\s+(browser|chrome|web)\s+commands", "browser"),
            (r"^what\s+(browser|chrome|web)\s+commands\s+(?:can\s+you\s+perform|do\s+you\s+know|are\s+there)", "browser"),
            (r"^(?:list|show|what\s+are(?:\s+the)?)\s+(file|folder|filesystem)\s+(?:commands|operations)", "filesystem"),
            (r"^what\s+(file|folder|filesystem)\s+(?:operations|commands)\s+(?:can\s+you\s+perform|do\s+you\s+know|are\s+there)", "filesystem"),
            (r"^(?:list|show|what\s+are(?:\s+the)?)\s+(application|app)\s+commands", "applications"),
            (r"^(?:list|show|what\s+are(?:\s+the)?)\s+(system|os|computer)\s+commands", "system"),
            (r"^(?:list|show|what\s+are(?:\s+the)?)\s+search\s+commands", "search"),
            (r"^(?:list|show|what\s+are(?:\s+the)?)\s+(developer|dev|code)\s+commands", "developer"),
        ]
        for spat, sc in scoped_patterns:
            if re.search(spat, clean) or re.search(spat, raw_lower):
                return {
                    "intent": "help",
                    "action": "show_scoped_commands",
                    "scope": sc,
                    "target": sc,
                    "confidence": 0.98,
                    "query": clean,
                    "raw_text": raw_text
                }

        # Show all commands reference
        if any(re.search(pat, clean) or re.search(pat, raw_lower) for pat in [
            r"^(?:show|list)\s+all\s+commands",
            r"^all\s+commands$",
            r"^(?:show|list)\s+every\s+command",
            r"^full\s+command\s+(?:list|reference)"
        ]):
            return {
                "intent": "help",
                "action": "show_all_commands",
                "scope": "all",
                "target": "all",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        help_exact = {
            "help", "help me", "what can you do", "what can santra do", "what can jarvis do", "what do you do",
            "what are your capabilities", "what commands do you know", "show commands", 
            "commands", "capabilities", "show capabilities", "show me your capabilities",
            "what are your features", "how can you help me", "how can you help",
            "list commands", "list capabilities"
        }
        help_prefixes = (
            "show commands", "list commands", "show capabilities", "list capabilities",
            "show me your capabilities", "what are your capabilities", "what can you do"
        )
        is_action_request = any(clean.startswith(f"help me {v}") or raw_lower.startswith(f"help me {v}") for v in ["open", "launch", "start", "close", "find", "search", "run", "play"])
        if not is_action_request and (clean in help_exact or raw_lower in help_exact or any(clean.startswith(hp) for hp in help_prefixes)):
            return {"intent": "help", "action": "show_help", "target": None, "scope": "overview", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        about_queries = [
            "about", "about santra", "about goliya", "about jarvis", "version", 
            "system info", "system information", "system details"
        ]
        if clean in about_queries:
            return {"intent": "about", "action": "show_about", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 5. SYSTEM TELEMETRY INTENTS
        # -------------------------------------------------------------
        if "what cpu" in clean or "cpu am i using" in clean:
            return {"intent": "system_telemetry", "action": "cpu_info", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}
        if "how much ram" in clean or "ram do i have" in clean:
            return {"intent": "system_telemetry", "action": "ram_info", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}
        if "disk space" in clean or "how much disk" in clean:
            return {"intent": "system_telemetry", "action": "disk_info", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}
        if "what operating system" in clean or "what os" in clean:
            return {"intent": "system_telemetry", "action": "os_info", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}
        if "local ip" in clean or "my ip" in clean:
            return {"intent": "system_telemetry", "action": "ip_info", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}
        if "system uptime" in clean or "how long has the system" in clean or "system running" in clean:
            return {"intent": "system_telemetry", "action": "uptime_info", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}
        if any(b in clean for b in ["battery status", "battery level", "how much battery", "check battery", "battery percentage", "is the laptop charging", "battery info"]):
            return {"intent": "system_telemetry", "action": "battery_info", "target": "battery", "confidence": 0.95, "query": clean, "raw_text": raw_text}
        if any(p in clean for p in ["power profile", "power plan", "power scheme", "laptop power modes", "acer power", "performance mode status", "laptop performance profile"]):
            return {"intent": "power_control", "action": "report", "target": "power", "confidence": 0.95, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 6. COMMAND HISTORY & REPETITION INTENTS
        # -------------------------------------------------------------
        history_queries = [
            "what was my last command", "repeat last command", "repeat that", 
            "show history", "last command", "command history"
        ]
        if clean in history_queries:
            return {"intent": "history_query", "action": "show_history", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if clean in ["repeat", "what did you say", "say again", "repeat response"]:
            return {"intent": "repeat_response", "action": "repeat_speech", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 6.4 DESKTOP INTELLIGENCE, SCREEN UNDERSTANDING, FILE CREATION & AI PROVIDERS
        # -------------------------------------------------------------
        # AI Management / Provider Settings & Caching Controls
        if any(clean == s or clean.startswith(s + " ") for s in [
            "how many api calls did caching save", "how many api calls did cache save",
            "show my cache statistics", "show cache statistics", "cache statistics",
            "show cache stats", "cache stats", "cache metrics", "show ai cache statistics"
        ]):
            return {
                "intent": "ai_management.cache_stats",
                "action": "cache_stats",
                "target": "cache",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["clear cache", "clear ai cache", "clear all cache", "reset cache", "empty cache"]:
            return {
                "intent": "ai_management.clear_cache",
                "action": "clear_cache",
                "target": "cache",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if any(clean.startswith(f) for f in ["forget this cached answer", "forget cached answer", "forget that cached answer", "forget last cached answer", "dispute cached answer"]):
            target_str = clean
            for pref in ["forget this cached answer for", "forget cached answer for", "forget this cached answer", "forget cached answer"]:
                if clean.startswith(pref):
                    target_str = clean[len(pref):].strip()
                    break
            return {
                "intent": "ai_management.forget_cache",
                "action": "forget_cache",
                "target": target_str or "recent",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if (
            clean in ["list ai providers", "ai provider settings", "ai providers", "show ai providers", "configure ai providers", "ai settings"] or
            re.search(r"^(?:list|show|view|configure|manage|open)?\s*ai\s+provider(?:s|\s+settings)?\b", clean, re.IGNORECASE)
        ):
            return {
                "intent": "ai_management.list_providers",
                "action": "list_providers",
                "target": "ai_providers",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # Virtual Testing Room / Capability Lab
        if (
            clean in ["open virtual lab", "open virtual testing room", "virtual lab", "virtual testing room", "test lab", "run virtual tests", "capability lab"] or
            re.search(r"^(?:open|launch|start|show)?\s*(?:the\s+)?virtual\s+(?:testing\s+room|lab)\b", clean, re.IGNORECASE)
        ):
            return {
                "intent": "virtual_lab.open",
                "action": "open_virtual_lab",
                "target": "virtual_lab",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # Screen Analysis / Inspection
        if (
            clean in ["analyze my screen", "analyze screen", "what is on my screen", "what is on screen", "inspect screen", "inspect my screen"] or
            re.search(r"^(?:analyze|inspect)\s+(?:my\s+)?screen\b", clean, re.IGNORECASE) or
            re.search(r"^what\s+is\s+on\s+(?:my\s+)?screen\b", clean, re.IGNORECASE) or
            re.search(r"^(?:analyze|inspect)\s+(?:my\s+)?screen\b", effective_raw, re.IGNORECASE) or
            re.search(r"^what\s+is\s+on\s+(?:my\s+)?screen\b", effective_raw, re.IGNORECASE)
        ):
            return {
                "intent": "screen_understanding.analyze",
                "action": "analyze_screen",
                "target": "screen",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # Screen Explanation & Visual Interpretation
        screen_explain_patterns = [
            r"^explain\s+(?:my\s+|the\s+)?screen\b",
            r"^explain\s+this\s+page\b",
            r"^what\s+are\s+the\s+important\s+points\b",
            r"^explain\s+the\s+highlighted\s+section\b",
            r"^what\s+does\s+this\s+error\s+mean\b",
            r"^explain\s+this\s+code\b",
            r"^summarize\s+this\s+(?:pdf|page|document)\b",
            r"^explain\s+this\s+graph\b",
            r"^what\s+is\s+this\s+button\s+used\s+for\b",
            r"^compare\s+these\s+two\b",
            r"^explain\s+point\s+\d+\b",
            r"^explain\s+the\s+(?:first|second|third|fourth|fifth|last)\s+point\b",
            r"i\s+still\s+don't\s+understand",
            r"explain\s+it\s+with\s+an\s+example",
            r"short\s+answer\s+first",
            r"like\s+i'm\s+a\s+beginner",
            r"beginner\s+friendly"
        ]
        if any(re.search(pat, clean, re.IGNORECASE) for pat in screen_explain_patterns) or \
           any(re.search(pat, effective_raw, re.IGNORECASE) for pat in screen_explain_patterns):
            return {
                "intent": "screen_understanding.explain",
                "action": "explain_screen",
                "target": "screen",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # File Search & Discovery
        file_search_patterns = [
            r"^where\s+did\s+i\s+save\b",
            r"^where\s+is\s+my\s+.*(?:program|file|code|repository|project|folder|readme)\b",
            r"^find\s+(?:the\s+)?.*(?:created|saved|written)\b",
            r"^find\s+(?:the\s+)?(?:readme|file|document|script|project)\b",
            r"^search\s+(?:my\s+)?files\b"
        ]
        if any(re.search(pat, clean, re.IGNORECASE) for pat in file_search_patterns) or \
           any(re.search(pat, effective_raw, re.IGNORECASE) for pat in file_search_patterns):
            return {
                "intent": "file_management.search",
                "action": "search_files",
                "target": "files",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # Real File Creation & Code Generation
        file_create_patterns = [
            r"^(?:create|write|generate|save)\s+(?:a|an|the|this)?\s*(?:new\s+)?(?:(?:python|c\+\+|cpp|c|java|javascript|typescript|react|node\.?js|html|css|sql|rust|go|markdown)\s+)?(?:program|script|code|component|api\s+route|route|schema|explanation|readme|file)\b",
            r"^(?:create|write|generate|save)\s+(?:a\s+)?(?:new\s+)?(?:[a-zA-Z0-9_\-\.]+\.(?:py|cpp|cc|c|h|hpp|java|js|ts|jsx|tsx|html|css|sql|md|markdown|txt|json|sh|ps1))\b",
            r"^(?:create|write|generate)\s+(?:a\s+)?readme\b",
            r"^save\s+this\s+explanation\s+as\s+a\b"
        ]
        if any(re.search(pat, clean, re.IGNORECASE) for pat in file_create_patterns) or \
           any(re.search(pat, effective_raw, re.IGNORECASE) for pat in file_create_patterns):
            # Extract target filename if specified
            extracted_filename = ""
            m_fn = re.search(r"\b([a-zA-Z0-9_\-]+\.(?:py|cpp|cc|c|h|hpp|java|js|ts|jsx|tsx|html|css|sql|md|markdown|txt|json|sh|ps1))\b", effective_raw, re.IGNORECASE)
            if not m_fn:
                m_called = re.search(r"(?:called|named)\s+([a-zA-Z0-9_\-\.]+)", effective_raw, re.IGNORECASE)
                if m_called:
                    extracted_filename = m_called.group(1).strip()
            else:
                extracted_filename = m_fn.group(1).strip()

            # Extract destination folder if specified
            extracted_dest = ""
            m_dest = re.search(r"\b(?:in|on|into|to)\s+(?:my\s+|the\s+)?(desktop|documents|downloads|dsa)\b", effective_raw, re.IGNORECASE)
            if m_dest:
                dest_raw = m_dest.group(1).lower()
                extracted_dest = "Desktop" if dest_raw == "desktop" else ("Documents" if dest_raw == "documents" else ("Downloads" if dest_raw == "downloads" else "dsa"))

            if extracted_dest and extracted_filename:
                target_path = f"{extracted_dest}/{extracted_filename}"
            elif extracted_filename:
                target_path = extracted_filename
            else:
                target_path = "file"

            return {
                "intent": "file_management.create_file",
                "action": "create_file",
                "target": target_path,
                "filename": extracted_filename or "test.py",
                "destination": extracted_dest or "Desktop",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 6.5 CONTENT GENERATION & DRAFTING INTENTS
        # -------------------------------------------------------------
        err_m = re.match(r"^explain\s+(?:this\s+)?(?:python\s+)?error[:\s]+(.+)$", effective_raw, re.IGNORECASE) or re.match(r"^explain\s+(?:this\s+)?(?:python\s+)?error[:\s]+(.+)$", clean, re.IGNORECASE)
        if err_m:
            err_concept = err_m.group(1).strip()
            return {
                "intent": "content_generation",
                "action": "explain_concept",
                "target": err_concept,
                "concept": err_concept,
                "confidence": 0.96,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["summarize this webpage", "summarize the webpage", "summarize current webpage", "summarize webpage", "summarize this page", "summarize page"]:
            return {
                "intent": "content_generation",
                "action": "summarize_page",
                "target": "current_webpage",
                "confidence": 0.96,
                "query": clean,
                "raw_text": raw_text
            }

        em_match = re.match(r"^write\s+(?:a\s+)?professional\s+email\s+(?:about\s+)?(.+)$", clean, re.IGNORECASE)
        if em_match:
            topic = em_match.group(1).strip()
            return {
                "intent": "content_generation",
                "action": "draft_email",
                "target": topic,
                "confidence": 0.96,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 7. SAFETY FIRST: Filter Informational Questions
        # -------------------------------------------------------------
        if self._is_informational_query(raw_text, clean):
            logger.info(f"Classified as informational question: '{raw_text}'")
            return {
                "intent": "question",
                "action": "query",
                "target": None,
                "confidence": 0.90,
                "query": raw_text,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 8. MEDIA CONTROL INTENTS
        # -------------------------------------------------------------
        if clean in ["play music", "pause music", "pause", "resume music", "play", "stop music", "resume"] or clean.startswith("play music on ") or clean in ["play spotify", "play on spotify", "resume spotify", "pause spotify"]:
            return {"intent": "media_control", "action": "play_pause", "target": "media", "confidence": 0.96, "query": clean, "raw_text": raw_text}

        if clean in ["next song", "next track", "skip song", "skip track", "next"]:
            return {"intent": "media_control", "action": "next_track", "target": "media", "confidence": 0.96, "query": clean, "raw_text": raw_text}

        if clean in ["previous song", "previous track", "prev song", "prev track", "previous", "go back song"]:
            return {"intent": "media_control", "action": "previous_track", "target": "media", "confidence": 0.96, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 9. GREETINGS & PERSONALITY INTENTS
        # -------------------------------------------------------------
        if clean in ["thanks", "thank you", "thank you very much", "thanks a lot", "many thanks", "thx"]:
            return {"intent": "thank_you", "action": "respond_thanks", "target": clean, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean in ["bye", "goodbye", "see you", "see you later", "bye bye"]:
            return {"intent": "goodbye", "action": "respond_goodbye", "target": clean, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean in ["okay", "ok", "got it", "understood", "all right", "alright", "fine"]:
            return {"intent": "acknowledgement", "action": "respond_acknowledgement", "target": clean, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean in ["yes", "yeah", "yup", "sure", "correct", "affirmative"]:
            return {"intent": "affirmation", "action": "respond_affirmation", "target": clean, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean in ["no", "nope", "negative"]:
            return {"intent": "negation", "action": "respond_negation", "target": clean, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(h in clean for h in ["how are you", "how are you doing", "how's it going", "how is it going", "how r u"]):
            return {"intent": "how_are_you", "action": "respond_how_are_you", "target": clean, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(clean == s or clean.startswith(s + " ") for s in ["are you there", "are you online", "are you listening", "what are you doing", "you there"]):
            return {"intent": "status_check", "action": "respond_status_check", "target": clean, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(clean == s or clean.startswith(s + " ") for s in [
            "start session", "let's start", "lets start", "let's begin", "lets begin",
            "begin session", "start working", "let's get started", "lets get started"
        ]):
            return {"intent": "session_start", "action": "start_session", "target": "session", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        greetings = [
            "hello", "hi", "namaste", "good morning", "good evening", 
            "good afternoon", "good night", "yo", "hey buddy", "howdy", "hey",
            "what's up", "whats up", "what s up", "what is up"
        ]
        has_action_verb = any(v in clean for v in [" open ", " launch ", " start ", " close ", " search ", " find ", " lock ", " take screenshot", " play ", " mute "])
        if not has_action_verb and (clean in greetings or any(clean.startswith(g) for g in ["hello", "hi ", "namaste", "good morning", "good evening", "good afternoon", "good night", "hey "])):
            return {"intent": "greeting", "action": "respond_greeting", "target": clean, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 10. CHROME NEW TAB & NEW INDEPENDENT WINDOW INTENTS
        # -------------------------------------------------------------
        # 10.1 OPEN_NEW_CHROME_TAB
        tab_patterns = [
            r"^(?:open|create|start|make|give\s+me|i\s+need)?\s*(?:a\s+|another\s+|one\s+more\s+|fresh\s+|new\s+|a\s+new\s+)*(?:chrome\s+|browser\s+)?tab(?:\s+in\s+chrome)?(?:\s+for\s+me)?$",
            r"^(?:new\s+tab|another\s+tab|new\s+chrome\s+tab|another\s+chrome\s+tab|chrome\s+new\s+tab|open\s+one\s+more\s+tab|open\s+another\s+browser\s+tab)$",
            r"^chrome\s*,\s*new\s+tab$"
        ]
        for pat in tab_patterns:
            if re.search(pat, clean):
                self.last_app_target = "chrome"
                return {
                    "intent": "open_new_chrome_tab",
                    "action": "open_new_tab",
                    "target": "chrome",
                    "confidence": 0.98,
                    "query": clean,
                    "raw_text": raw_text
                }

        # 10.2 OPEN_NEW_CHROME_WINDOW
        window_patterns = [
            r"^(?:open|launch|start|create|make|give\s+me|i\s+want)?\s*(?:a\s+)?(?:another|a\s+new|new|a\s+second|second|a\s+separate|separate|fresh)\s+chrome(?:\s+window)?(?:\s+for\s+me)?$",
            r"^(?:open|launch|start|create)\s+chrome\s+in\s+(?:another|a\s+new|a\s+separate|a\s+second)\s+window$",
            r"^(?:open|launch|start|create)\s+(?:another|a\s+new|a\s+second|a\s+separate|fresh)\s+window\s+in\s+chrome$",
            r"^(?:new\s+chrome\s+window|another\s+chrome\s+window|another\s+chrome|fresh\s+chrome\s+window|separate\s+chrome\s+window|second\s+chrome\s+window|new\s+chrome)$",
            r"^open\s+a\s+separate\s+chrome$"
        ]
        for pat in window_patterns:
            if re.search(pat, clean):
                self.last_app_target = "chrome"
                return {
                    "intent": "open_new_chrome_window",
                    "action": "open_new_window",
                    "target": "chrome",
                    "confidence": 0.98,
                    "query": clean,
                    "raw_text": raw_text
                }

        # -------------------------------------------------------------
        # 11. SYSTEM POWER & SECURITY ACTIONS
        # -------------------------------------------------------------
        # 11.1 LOCK_COMPUTER
        lock_patterns = [
            r"^(?:please\s+)?lock(?:\s+(?:my|the|this)?\s*(?:pc|computer|laptop|screen|workstation|system|desktop))?$",
            r"^(?:can\s+you|could\s+you|i\s+need\s+to|please)?\s*lock(?:\s+(?:my|the|this)?\s*(?:pc|computer|laptop|screen|system))?.*$",
            r"^secure\s+(?:my|the|this)?\s*(?:laptop|pc|computer)$",
            r"^put\s+(?:my|the)?\s*(?:computer|pc|laptop)\s+on\s+lock$",
            r"^lock\s+computer$"
        ]
        for pat in lock_patterns:
            if re.search(pat, clean):
                return {"intent": "system_control", "action": "lock_pc", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 11.1.5 SLEEP_ASSISTANT (Assistant Sleep Mode)
        assistant_sleep_patterns = [
            r"^(?:please\s+)?(?:go\s+to\s+sleep|take\s+a\s+nap)$",
            r"^(?:please\s+)?enter\s+sleep(?:\s+mode)?$",
            r"^(?:please\s+)?sleep\s+mode$",
            r"^(?:please\s+)?(?:sleep|nap)(?:\s+(?:now|santra|jarvis|assistant))?$",
            r"^(?:santra|jarvis\s+)?(?:go\s+to\s+sleep|sleep|enter\s+sleep\s+mode)$",
            r"^(?:can\s+you|could\s+you|please)?\s*(?:go\s+to\s+sleep|take\s+a\s+nap|enter\s+sleep\s+mode)$"
        ]
        for pat in assistant_sleep_patterns:
            if re.search(pat, clean):
                return {"intent": "system_control", "action": "sleep_assistant", "target": None, "confidence": 0.99, "query": clean, "raw_text": raw_text}

        # 11.2 SLEEP_COMPUTER (OS Sleep / Suspend)
        sleep_patterns = [
            r"^(?:put|send|make)\s+(?:my|the)?\s*(?:laptop|computer|pc|system|machine)\s*(?:to|into)?\s*sleep$",
            r"^(?:can\s+you|could\s+you|please)?\s*put\s+(?:my|the)?\s*(?:laptop|computer|pc|system)\s+to\s+sleep$",
            r"^(?:please\s+)?sleep\s+(?:the|my)?\s*(?:computer|laptop|pc|system|machine)$",
            r"^(?:put|send)\s+(?:the|my)?\s*(?:computer|laptop|pc)\s+into\s+standby$",
            r"^sleep\s+(?:computer|pc|laptop|machine)$"
        ]
        for pat in sleep_patterns:
            if re.search(pat, clean):
                return {"intent": "system_control", "action": "sleep_pc", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 11.3 RESTART_COMPUTER
        restart_patterns = [
            r"^(?:please\s+)?(?:restart|reboot|power\s+cycle)(?:\s+(?:my|the|this)?\s*(?:pc|computer|laptop|system))?$",
            r"^(?:can\s+you|could\s+you|please)?\s*(?:restart|reboot)\s*(?:(?:my|the)?\s*(?:pc|computer|laptop|system))?.*$",
            r"^restart\s+computer$"
        ]
        for pat in restart_patterns:
            if re.search(pat, clean):
                return {"intent": "system_control", "action": "restart_pc", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 11.4 SHUTDOWN_COMPUTER (Requires PC/Computer/Laptop target, or exact "shutdown computer"/"turn off computer")
        shutdown_patterns = [
            r"^(?:please\s+)?(?:shut\s*down|turn\s+off|power\s+off|power\s+down)\s+(?:the\s+|my\s+|this\s+)?(?:pc|computer|laptop|system|machine|workstation)$",
            r"^(?:can\s+you|could\s+you|i\s+want\s+to|please)?\s*(?:shut\s*down|turn\s+off|power\s+off)\s+(?:the\s+|my\s+|this\s+)?(?:pc|computer|laptop|system|machine)$",
            r"^(?:shut\s*down|power\s+off|turn\s+off\s+computer|shutdown\s+computer|shutdown\s+pc)$"
        ]
        for pat in shutdown_patterns:
            if re.search(pat, clean):
                return {"intent": "system_control", "action": "shutdown_pc", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 11.5 HIBERNATE_COMPUTER
        hibernate_patterns = [
            r"^(?:please\s+)?hibernate(?:\s+(?:my|the|this)?\s*(?:pc|computer|laptop|system))?$",
            r"^(?:can\s+you|could\s+you|please)?\s*(?:put\s+(?:the|my)?\s*(?:computer|laptop|pc)\s+into\s+hibernation|hibernate\s*(?:(?:the|my)?\s*(?:pc|computer|laptop|system))?)$"
        ]
        for pat in hibernate_patterns:
            if re.search(pat, clean):
                return {"intent": "system_control", "action": "hibernate_pc", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 11.6 VOLUME & AUDIO CONTROLS
        if re.search(r"^(?:turn\s+up\s+the\s+volume|turn\s+volume\s+up|increase\s+(?:the\s+)?volume|raise\s+volume|make\s+it\s+louder|volume\s+up|louder)$", clean):
            return {"intent": "system_control", "action": "volume_up", "target": None, "confidence": 0.96, "query": clean, "raw_text": raw_text}

        if re.search(r"^(?:turn\s+down\s+the\s+volume|turn\s+volume\s+down|decrease\s+(?:the\s+)?volume|lower\s+volume|make\s+it\s+quieter|volume\s+down|quieter)$", clean):
            return {"intent": "system_control", "action": "volume_down", "target": None, "confidence": 0.96, "query": clean, "raw_text": raw_text}

        if re.search(r"^(?:mute(?:\s+(?:the\s+)?(?:volume|audio|sound))?|silence(?:\s+audio)?)$", clean):
            return {"intent": "system_control", "action": "mute", "target": None, "confidence": 0.96, "query": clean, "raw_text": raw_text}

        if re.search(r"^(?:unmute(?:\s+(?:the\s+)?(?:volume|audio|sound))?)$", clean):
            return {"intent": "system_control", "action": "unmute", "target": None, "confidence": 0.96, "query": clean, "raw_text": raw_text}

        if any(kw in clean for kw in ["battery status", "battery level", "battery"]):
            return {"intent": "system_control", "action": "battery", "target": None, "confidence": 0.92, "query": clean, "raw_text": raw_text}

        if any(kw in clean for kw in ["system metrics", "resource usage"]):
            return {"intent": "system_control", "action": "metrics", "target": None, "confidence": 0.92, "query": clean, "raw_text": raw_text}

        # 11.7 STARTUP CONTROLS
        if clean in ["enable startup", "start with windows", "launch on startup", "turn on startup", "enable auto start"]:
            return {"intent": "system_control", "action": "enable_startup", "target": "startup", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean in ["disable startup", "do not start with windows", "don't start with windows", "remove from startup", "turn off startup", "disable auto start"]:
            return {"intent": "system_control", "action": "disable_startup", "target": "startup", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean in ["check startup", "startup status", "is startup enabled", "check if startup is on"]:
            return {"intent": "system_control", "action": "startup_status", "target": "startup", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # 11.8 ASSISTANT STANDBY & PRIVACY LISTENING CONTROLS
        if clean in ["go to standby", "enter standby", "standby mode", "return to standby", "standby"]:
            return {"intent": "system_control", "action": "enter_standby", "target": "standby", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean in ["stop listening", "disable listening", "turn off listening", "mute microphone", "mute mic", "stop voice"]:
            return {"intent": "system_control", "action": "disable_listening", "target": "listening", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if clean in ["resume listening", "enable listening", "turn on listening", "unmute microphone", "unmute mic", "start listening"]:
            return {"intent": "system_control", "action": "enable_listening", "target": "listening", "confidence": 0.98, "query": clean, "raw_text": raw_text}


        # -------------------------------------------------------------
        # 12. SCREENSHOT INTENTS
        # -------------------------------------------------------------
        screenshot_patterns = [
            r"^(?:take\s+(?:a\s+)?screen\s*shot|take\s+(?:a\s+)?picture\s+of\s+(?:the|my)?\s*screen|capture\s+(?:my\s+|the\s+)?(?:screen|desktop)|screenshot\s+this|snapshot)$",
            r"^take\s+screenshot$"
        ]
        for pat in screenshot_patterns:
            if re.search(pat, clean):
                return {"intent": "screenshot", "action": "take_screenshot", "target": None, "confidence": 0.97, "query": clean, "raw_text": raw_text}

        if clean in ["open screenshot folder", "open screenshots folder", "show screenshots"]:
            return {"intent": "screenshot", "action": "open_folder", "target": None, "confidence": 0.96, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 13. BROWSER & WEB SEARCH INTENTS
        # -------------------------------------------------------------
        yt_patterns = [
            r"^search\s+youtube\s+for\s+(.+)$",
            r"^find\s+(.+)\s+on\s+youtube$",
            r"^look\s+for\s+(.+)\s+on\s+youtube$",
            r"^youtube\s+(.+)$"
        ]
        for pat in yt_patterns:
            m = re.search(pat, clean)
            if m:
                q = m.group(1).strip()
                return {"intent": "web_search", "action": "search", "provider": "youtube", "target": q, "query": q, "confidence": 0.95, "raw_text": raw_text}

        web_patterns = [
            r"^search\s+google\s+for\s+(.+)$",
            r"^search\s+chrome\s+for\s+(.+)$",
            r"^search\s+the\s+web\s+for\s+(.+)$",
            r"^search\s+for\s+(.+)$",
            r"^find\s+(.+)\s+on\s+google$",
            r"^google\s+(.+)$",
            r"^look\s+up\s+(.+)$"
        ]
        for pat in web_patterns:
            m = re.search(pat, clean)
            if m:
                q = m.group(1).strip()
                if any(p in clean for p in ["in this application", "in this app", "in the current application", "in current app", "in chatgpt"]):
                    continue
                return {"intent": "web_search", "action": "search", "provider": "google", "target": q, "query": q, "confidence": 0.95, "raw_text": raw_text}

        for prov in ["github", "reddit", "stackoverflow", "stack overflow"]:
            p_clean = "stackoverflow" if prov == "stack overflow" else prov
            pat = rf"^search\s+{prov}\s+for\s+(.+)$"
            m = re.search(pat, clean)
            if m:
                q = m.group(1).strip()
                return {"intent": "web_search", "action": "search", "provider": p_clean, "target": q, "query": q, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 14. WINDOW CONTROL ACTIONS
        # -------------------------------------------------------------
        if clean in ["list open windows", "list windows", "show open windows", "open windows"]:
            return {"intent": "window_control", "action": "list_open", "target": None, "confidence": 0.92, "query": clean, "raw_text": raw_text}

        # Specific tab switch: "switch to the Python tutorials tab", "switch to tab Python tutorials"
        switch_tab_m = re.match(r"^(?:switch|go)\s+to\s+(?:the\s+)?(.+?)\s+tab$", clean, re.IGNORECASE)
        if switch_tab_m:
            return {"intent": "browser_tab_control", "action": "switch_tab", "target": "chrome", "tab_target": switch_tab_m.group(1).strip(), "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        if clean.startswith("switch to") or clean.startswith("focus"):
            target = clean.replace("switch to", "").replace("focus", "").strip()
            resolved = self.resolve_app_name(target)
            self.last_app_target = resolved
            return {"intent": "window_control", "action": "switch", "target": resolved, "confidence": 0.92, "query": clean, "raw_text": raw_text}

        if clean.startswith("restore window") or clean == "restore":
            target = clean.replace("restore window", "").replace("restore", "").strip() or None
            return {"intent": "window_control", "action": "restore", "target": target, "confidence": 0.90, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 15. MINIMIZE APP & WINDOW INTENTS
        # -------------------------------------------------------------
        if clean.startswith("minimize") or "minimize" in clean or "in the background" in clean or "in background" in clean or "hide" in clean:
            target_raw = clean.replace("minimize", "").replace("hide", "").replace("put in the background", "").replace("put in background", "").replace("in the background", "").replace("in background", "").replace("put", "").replace("the", "").replace("my", "").strip()
            if target_raw in ["it", "this"]:
                target_app = self.last_app_target
            elif "window" in target_raw or not target_raw:
                target_app = None
            else:
                target_app = self.resolve_app_name(target_raw)

            if target_app:
                self.last_app_target = target_app
                return {"intent": "minimize_app", "action": "minimize", "target": target_app, "confidence": 0.94, "query": clean, "raw_text": raw_text}
            else:
                return {"intent": "window_control", "action": "minimize", "target": None, "confidence": 0.90, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 16. MAXIMIZE APP & WINDOW INTENTS
        # -------------------------------------------------------------
        if clean.startswith("maximize") or "maximize" in clean or "full screen" in clean or "bigger" in clean or "expand" in clean:
            target_raw = clean.replace("maximize", "").replace("make full screen", "").replace("make", "").replace("full screen", "").replace("bigger", "").replace("expand", "").replace("the", "").replace("my", "").strip()
            if target_raw in ["it", "this"]:
                target_app = self.last_app_target
            elif "window" in target_raw or not target_raw:
                target_app = None
            else:
                target_app = self.resolve_app_name(target_raw)

            if target_app:
                self.last_app_target = target_app
                return {"intent": "maximize_app", "action": "maximize", "target": target_app, "confidence": 0.94, "query": clean, "raw_text": raw_text}
            else:
                return {"intent": "window_control", "action": "maximize", "target": None, "confidence": 0.90, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 17. CLOSE APP INTENTS
        # -------------------------------------------------------------
        # Specific tab close: "close the current Chrome tab", "close the YouTube tab", "close the tab titled GitHub", "close the second Chrome tab", "close the tab showing my WellMeds dashboard"
        if re.match(r"^(?:close|shut)(?:\s+down)?\s+(?:the\s+)?(?:active\s+|current\s+|this\s+)?(?:chrome\s+|browser\s+)?tab$", clean, re.IGNORECASE) or \
           re.match(r"^(?:close|shut)(?:\s+down)?\s+(?:the\s+)?(?:active|current|this)\s+(?:chrome|browser)\s+tab$", clean, re.IGNORECASE) or \
           clean in ["close tab", "shut tab", "close active tab", "close current tab", "close this tab", "close the tab", "close current chrome tab", "close active chrome tab"]:
            return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "tab_target": "active", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Positional / Ordinal tab close: e.g. "close the second Chrome tab", "close tab 2"
        ordinal_close_m = re.match(r"^(?:close|shut)(?:\s+down)?\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last|\d+(?:st|nd|rd|th)?)\s+(?:chrome\s+|browser\s+)?tab$", clean, re.IGNORECASE)
        if ordinal_close_m:
            pos = ordinal_close_m.group(1).lower().strip()
            return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "tab_target": pos, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        pos_number_m = re.match(r"^(?:close|shut)(?:\s+down)?\s+(?:the\s+)?(?:chrome\s+|browser\s+)?tab\s+(?:number\s+|#\s*)?(\d+|first|second|third|fourth|fifth|last)$", clean, re.IGNORECASE)
        if pos_number_m:
            pos = pos_number_m.group(1).lower().strip()
            return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "tab_target": pos, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Tab with descriptive prefix: e.g. "close the tab titled GitHub", "close the tab showing my WellMeds dashboard"
        tab_desc_m = re.match(r"^(?:close|shut)(?:\s+down)?\s+(?:the\s+)?(?:chrome\s+|browser\s+)?tab\s+(?:titled|showing|named|called|with|about|for)\s+(.+)$", clean, re.IGNORECASE)
        if tab_desc_m:
            raw_target = tab_desc_m.group(1).strip()
            raw_target = re.sub(r"\s+tab$", "", raw_target, flags=re.IGNORECASE).strip()
            return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "tab_target": raw_target, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Named tab close with postfix "tab": e.g. "close the YouTube tab", "close the Python tutorials tab"
        close_named_tab_m = re.match(r"^(?:close|shut)(?:\s+down)?\s+(?:the\s+)?(.+?)\s+(?:chrome\s+|browser\s+)?tab$", clean, re.IGNORECASE)
        if close_named_tab_m:
            tab_target = close_named_tab_m.group(1).strip()
            if tab_target.lower() in ["active", "current", "chrome", "this", "current chrome", "active chrome", ""]:
                return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "tab_target": "active", "confidence": 0.98, "query": clean, "raw_text": effective_raw}
            return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "tab_target": tab_target, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # "close tab <target>": e.g. "close tab YouTube", "close tab GitHub"
        close_tab_prefix_m = re.match(r"^(?:close|shut)(?:\s+down)?\s+(?:chrome\s+|browser\s+)?tab\s+(.+)$", clean, re.IGNORECASE)
        if close_tab_prefix_m:
            tab_target = close_tab_prefix_m.group(1).strip()
            tab_target = re.sub(r"^(?:titled|showing|named|called|with)\s+", "", tab_target, flags=re.IGNORECASE).strip()
            if tab_target.lower() in ["active", "current", "chrome", "this", "current chrome", "active chrome", ""]:
                return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "tab_target": "active", "confidence": 0.98, "query": clean, "raw_text": effective_raw}
            return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "tab_target": tab_target, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Specific tab switch: "switch to the Python tutorials tab", "switch to tab Python tutorials"
        switch_tab_m = re.match(r"^(?:switch|go)\s+to\s+(?:the\s+)?(.+?)\s+tab$", clean, re.IGNORECASE)
        if switch_tab_m:
            return {"intent": "browser_tab_control", "action": "switch_tab", "target": "chrome", "tab_target": switch_tab_m.group(1).strip(), "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Tab listing: "list open tabs", "show open tabs", "list tabs"
        list_tabs_m = re.match(r"^(?:list|show|what\s+are)\s+(?:all\s+)?(?:the\s+)?(?:open\s+)?(?:browser\s+|chrome\s+)?tabs$", clean, re.IGNORECASE)
        if list_tabs_m:
            return {"intent": "browser_tab_control", "action": "list_tabs", "target": "chrome", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        close_patterns = [
            r"^(?:close|exit|quit|stop|shut\s*down|shut|terminate|end|kill|get\s+rid\s+of)\s+(?:the\s+|my\s+)?(.+)$",
            r"^get\s+(?:the\s+|my\s+)?(.+?)\s+out\s+of\s+here$",
            r"^(?:close|exit|quit)$"
        ]
        for pat in close_patterns:
            m = re.search(pat, clean)
            if m:
                target_raw = m.group(1).strip() if m.groups() and m.group(1) else ""
                target_raw = re.sub(r"\s+down$", "", target_raw).strip()

                if "window" in target_raw:
                    win_app_raw = re.sub(r"\b(?:this|the|my|current)?\s*window\b", "", target_raw, flags=re.IGNORECASE).strip()
                    win_target = self.resolve_app_name(win_app_raw) if win_app_raw else None
                    return {"intent": "window_control", "action": "close", "target": win_target, "confidence": 0.95, "query": clean, "raw_text": raw_text}

                if target_raw in ["it", "this", ""]:
                    target_app = self.last_app_target
                else:
                    target_app = self.resolve_app_name(target_raw)

                if target_app:
                    self.last_app_target = target_app
                    return {"intent": "close_app", "action": "close", "target": target_app, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 18. OPEN FOLDER & FILE INTENTS
        # -------------------------------------------------------------
        folder_match = re.search(r"^(?:open|show|go\s+to|take\s+me\s+to|show\s+me)\s+(?:the\s+|my\s+)?(downloads|documents|desktop|pictures|videos|music)(?:\s+folder)?$", clean)
        if folder_match:
            folder_target = folder_match.group(1).strip()
            return {"intent": "file_access", "action": "open_folder", "target": folder_target, "confidence": 0.96, "query": clean, "raw_text": raw_text}

        if clean.startswith("open folder "):
            folder_name = clean[12:].strip()
            return {"intent": "file_access", "action": "open_folder", "target": folder_name, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        file_match = re.search(r"^(?:open|view|show)\s+(?:the\s+|my\s+|that\s+)?([a-zA-Z0-9_\-\s]+\.(?:pdf|txt|docx?|xlsx?|pptx?|csv|json|py|html|png|jpg|jpeg|mp4|mp3|zip))$", clean)
        if file_match:
            file_name = file_match.group(1).strip()
            return {"intent": "file_access", "action": "open_file", "target": file_name, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if re.search(r"^(?:open|view|show)\s+(?:that|the|this)\s+pdf$", clean):
            return {"intent": "file_access", "action": "open_file", "target": "that.pdf", "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if clean.startswith("open file "):
            file_name = clean[10:].strip()
            return {"intent": "file_access", "action": "open_file", "target": file_name, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 18.5 MULTI-TAB, DEVELOPER, FOLLOW-UP & PROJECT SEARCH
        # -------------------------------------------------------------
        multi_tab_m = re.match(r"^open\s+(?:three|two|four|five|\d+)?\s*(?:websites|sites|urls)?\s*in\s+(?:separate|different)?\s*tabs[:\s]+(.+)$", clean, re.IGNORECASE)
        if not multi_tab_m and "in separate tabs" in clean:
            multi_tab_m = re.match(r"^open\s+(.+?)\s+in\s+separate\s+tabs[:\s]*(.*)$", clean, re.IGNORECASE)
        if multi_tab_m:
            raw_urls = multi_tab_m.group(1).strip()
            if len(multi_tab_m.groups()) > 1 and multi_tab_m.group(2).strip():
                raw_urls = multi_tab_m.group(2).strip()
            urls = [u.strip() for u in re.split(r"[,;]+|\s+and\s+", raw_urls) if u.strip()]
            return {
                "intent": "browser_control",
                "action": "open_multiple",
                "target": urls,
                "urls": urls,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["run tests", "run the tests", "open tests", "open the tests", "run project tests", "test project", "open my project and run its tests", "open my project and run it"] or clean.startswith("run tests") or clean.startswith("run the tests"):
            return {"intent": "developer_workflow", "action": "run_tests", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if clean in ["open the second result", "open second result", "open result two", "open result 2"]:
            return {"intent": "follow_up", "action": "open_result_index", "target": "2", "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if clean in ["open the first result", "open first result", "open result one", "open result 1"]:
            return {"intent": "follow_up", "action": "open_result_index", "target": "1", "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if clean in ["open the file you just created", "open the created file", "open the file"]:
            return {"intent": "follow_up", "action": "open_last_created_file", "target": None, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        find_proj_m = re.match(r"^find\s+(?:a\s+)?file\s+in\s+(?:the\s+)?project\s+(.+)$", clean, re.IGNORECASE)
        if not find_proj_m and clean.startswith("find file in project "):
            find_proj_m = re.match(r"^find\s+file\s+in\s+project\s+(.+)$", clean, re.IGNORECASE)
        if find_proj_m:
            filename = find_proj_m.group(1).strip()
            return {
                "intent": "local_search",
                "action": "find_file",
                "target": filename,
                "query": filename,
                "confidence": 0.96,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 19. OPEN APP & OPEN WEBSITE INTENTS
        # -------------------------------------------------------------
        # Open specific website in specific browser: e.g. "open ChatGPT in Chrome", "open YouTube in Chrome"
        browser_site_m = re.match(r"^(?:open|launch|navigate\s+to|go\s+to)\s+(.+?)\s+(?:in|on)\s+(chrome|edge|firefox|browser)$", clean, re.IGNORECASE)
        if browser_site_m:
            raw_site = browser_site_m.group(1).strip()
            raw_browser = browser_site_m.group(2).strip().lower()
            if raw_browser == "browser":
                raw_browser = "chrome"
            site_key = raw_site.lower()
            site_url = web_control.links.get(site_key)
            if not site_url and (site_key.startswith("http://") or site_key.startswith("https://") or ("." in site_key and " " not in site_key)):
                site_url = f"https://{site_key}" if not site_key.startswith("http") else site_key
            if not site_url:
                res_target = application_resolver.resolve(raw_site)
                if res_target.url:
                    site_url = res_target.url
            if not site_url:
                site_url = f"https://{site_key}.com"

            return {
                "intent": "open_website",
                "action": "open_in_browser",
                "target": raw_site,
                "url": site_url,
                "browser": raw_browser,
                "confidence": 0.98,
                "query": clean,
                "raw_text": effective_raw
            }

        # Browser Tab & Page Navigation Keywords
        if re.match(r"^(?:open\s+(?:a\s+)?)?new\s+(?:chrome\s+)?tab$", clean, re.IGNORECASE):
            return {"intent": "browser_tab_control", "action": "new_tab", "target": "chrome", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        if re.match(r"^(?:close|shut)\s+(?:the\s+)?(?:active\s+|current\s+)?(?:chrome\s+)?tab$", clean, re.IGNORECASE):
            return {"intent": "browser_tab_control", "action": "close_tab", "target": "chrome", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        if re.match(r"^(?:switch|next)\s+tab$", clean, re.IGNORECASE):
            return {"intent": "browser_tab_control", "action": "next_tab", "target": "chrome", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        if re.match(r"^(?:go\s+)?back(?:\s+in\s+chrome)?$", clean, re.IGNORECASE):
            return {"intent": "browser_tab_control", "action": "go_back", "target": "chrome", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        if re.match(r"^(?:go\s+)?forward(?:\s+in\s+chrome)?$", clean, re.IGNORECASE):
            return {"intent": "browser_tab_control", "action": "go_forward", "target": "chrome", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        if re.match(r"^(?:refresh|reload)(?:\s+(?:the\s+)?(?:current\s+)?page)?$", clean, re.IGNORECASE):
            return {"intent": "browser_tab_control", "action": "reload_page", "target": "chrome", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Page Reading, Summarization, and Deep Analysis
        page_analysis_pat = r"^(?:analyze|explain|inspect|summarize|read|tell\s+me\s+about)\s+(?:the\s+|this\s+|current\s+)?(?:web)?(?:page|website|tab|site)(?:\s+content)?$"
        if re.match(page_analysis_pat, clean, re.IGNORECASE) or clean in [
            "analyze this page", "analyze page", "explain this website", "explain this page",
            "explain the page", "summarize this page", "summarize the page", "summarize current tab",
            "summarize this tab", "summarize the current tab", "read this page", "read the page",
            "what does this page say", "what is on this page", "what does this website say",
            "read webpage", "read page"
        ]:
            return {"intent": "browser_action", "action": "analyze_page", "target": "current_page", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # In-page and Current Website Search Patterns
        page_search_m = re.match(r"^(?:search|find|look\s*up)\s+(?:(?:in|on|within)\s+(?:this|the|current)\s+(?:website|page|tab)|(?:this|the|current)\s+(?:website|page|tab)\s+(?:for|about))\s+(.+)$", clean, re.IGNORECASE)
        if not page_search_m:
            page_search_m = re.match(r"^(?:search|find)\s+(?:this|the)\s+(?:website|page)\s+for\s+(.+)$", clean, re.IGNORECASE)
        if page_search_m:
            search_q = page_search_m.group(1).strip()
            return {"intent": "browser_action", "action": "search_page", "target": "current_page", "query": search_q, "confidence": 0.98, "raw_text": effective_raw}

        # Screen Understanding & Visual Explanation Patterns
        if clean in [
            "explain what is on this screen", "explain what is on my screen", "explain what's on this screen",
            "explain what's on my screen", "explain this screen", "explain my screen", "what is on my screen",
            "what is on this screen", "what's on my screen", "what's on this screen", "describe my screen",
            "describe this screen", "read my screen", "read the screen", "analyze my screen", "analyze this screen",
            "tell me what is on my screen", "tell me what is on this screen"
        ]:
            return {"intent": "screen.explain", "action": "explain", "target": "primary_screen", "query": clean, "confidence": 0.98, "raw_text": effective_raw}

        if clean in ["what does this error mean", "what does that error mean", "explain this error", "explain that error", "explain the error"]:
            return {"intent": "screen.explain", "action": "explain_error", "target": "error", "query": clean, "confidence": 0.98, "raw_text": effective_raw}

        if clean in [
            "explain the code visible in the editor", "explain the code visible in editor",
            "explain the visible code", "explain the code on screen", "explain the code on my screen",
            "explain the code in vs code", "explain the code in vscode"
        ]:
            return {"intent": "screen.explain", "action": "explain_code", "target": "code", "query": clean, "confidence": 0.98, "raw_text": effective_raw}

        # Follow-up file saving to folder (e.g., "Save it in my DSA folder")
        save_dest_m = re.match(r"^(?:save|move|put)\s+(?:it|this|that|the\s+file)\s+(?:in|into|to)\s+(?:my\s+|the\s+)?(.+?)(?:\s+folder)?$", clean, re.IGNORECASE)
        if save_dest_m:
            dest_name = save_dest_m.group(1).strip()
            return {"intent": "file_management.create_file", "action": "save_file", "target": dest_name, "destination": dest_name, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Wake acknowledgment when assistant name is addressed alone
        if clean in ["santra", "samtra", "suntra", "jarvis", "hey santra", "hey samtra", "hey jarvis"]:
            return {"intent": "status_request", "action": "wake_acknowledgment", "target": "assistant", "confidence": 0.99, "query": clean, "raw_text": effective_raw}

        # Workspace Launch and Listing Patterns
        if clean in ["list workspaces", "show workspaces", "available workspaces", "what workspaces do i have", "my workspaces"]:
            return {"intent": "workspace.launch", "action": "list", "target": "all", "confidence": 0.98, "query": clean, "raw_text": raw_text}

        ws_match = re.match(r"^(?:open|launch|start|run|setup|prepare)\s+(?:the\s+|my\s+)?(development|dev|gaming|study|research|excel)\s+(?:workspace|mode|setup|profile)$", clean, re.IGNORECASE)
        if not ws_match:
            ws_match = re.match(r"^(?:open|launch|start|run)\s+(?:the\s+|my\s+)?(development|dev|gaming|study|research|excel)\s+mode$", clean, re.IGNORECASE)
        if not ws_match:
            ws_match = re.match(r"^(development|dev|gaming|study|research|excel)\s+(?:workspace|mode|setup)$", clean, re.IGNORECASE)
        if not ws_match and clean in ["start gaming mode", "gaming mode", "open gaming", "dev mode", "study mode"]:
            ws_raw = clean.replace("start ", "").replace("open ", "").replace(" mode", "").strip()
            return {"intent": "workspace.launch", "action": "launch", "target": ws_raw, "confidence": 0.98, "query": clean, "raw_text": raw_text}
        if ws_match:
            ws_target = ws_match.group(1).strip().lower()
            if ws_target == "dev":
                ws_target = "development"
            return {"intent": "workspace.launch", "action": "launch", "target": ws_target, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # Power Scheme switching patterns
        power_scheme_m = re.match(r"^(?:set|change|switch)\s+(?:the\s+)?(?:power\s+)?(?:plan|scheme|mode)\s+to\s+(.+)$", clean, re.IGNORECASE)
        if power_scheme_m:
            target_scheme = power_scheme_m.group(1).strip()
            return {"intent": "power_control", "action": "set_scheme", "target": target_scheme, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 18.8 UNIVERSAL APPLICATION DISCOVERY & DESKTOP CONTROL INTENTS
        # -------------------------------------------------------------
        # Listing installed applications
        if clean in [
            "list my installed applications", "list installed applications", "list installed apps",
            "what apps are installed", "what applications are installed", "show installed applications",
            "show my installed applications", "my installed applications", "installed applications",
            "list my apps", "show all installed applications"
        ]:
            return {"intent": "application.list_installed", "action": "list_all", "target": "all", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Available browsers
        if clean in [
            "find my available browsers", "what browsers are installed", "find available browsers",
            "list my browsers", "what browsers do i have", "available browsers", "my browsers",
            "list browsers", "show browsers", "find browsers", "which browsers do i have"
        ]:
            return {"intent": "application.list_installed", "action": "list_browsers", "category": "browser", "target": "browser", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Dynamic catalogue refresh
        if clean in [
            "scan applications", "refresh applications", "refresh installed apps",
            "scan for applications", "scan for new applications", "refresh app registry",
            "rescan applications", "scan for apps"
        ]:
            return {"intent": "application.refresh", "action": "refresh", "target": "applications", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Temporal application launch ("the application I installed yesterday")
        if clean in [
            "open the application i installed yesterday", "open the app i installed yesterday",
            "launch the app i installed yesterday", "launch the application i installed yesterday",
            "open the app installed yesterday", "open yesterday's app", "start the application i installed yesterday"
        ]:
            return {"intent": "open_app", "action": "open", "target": "installed_yesterday", "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Application Properties dialog
        prop_m = re.match(r"^(?:show|open|view|display)?\s*(?:the\s+)?properties\s+(?:of|for)\s+(.+)$", clean, re.IGNORECASE)
        if not prop_m:
            prop_m = re.match(r"^(?:show|open|view|display)?\s*(?:the\s+)?(.+?)(?:[\'s\s]+|\s+)properties(?:\s+dialog)?$", clean, re.IGNORECASE)
        if prop_m:
            raw_app = prop_m.group(1).strip()
            raw_app = re.sub(r"^(?:the\s+|my\s+)", "", raw_app).strip()
            resolved_app = self.resolve_app_name(raw_app)
            return {"intent": "application.properties", "action": "open_properties", "target": resolved_app, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Application Installation folder reveal
        dir_m = re.match(r"^(?:open|show|view|reveal|where\s+is)\s+(?:the\s+)?(?:installation\s+folder\s+of|installation\s+directory\s+of|install\s+folder\s+of|install\s+dir\s+of)\s+(.+)$", clean, re.IGNORECASE)
        if not dir_m:
            dir_m = re.match(r"^(?:open|show|view|reveal)?\s*(?:the\s+)?(.+?)(?:[\'s\s]+|\s+)(?:installation\s+folder|installation\s+directory|install\s+folder|install\s+dir)$", clean, re.IGNORECASE)
        if not dir_m:
            dir_m = re.match(r"^where\s+is\s+(.+?)\s+installed$", clean, re.IGNORECASE)
        if dir_m:
            raw_app = dir_m.group(1).strip()
            raw_app = re.sub(r"^(?:the\s+|my\s+)", "", raw_app).strip()
            resolved_app = self.resolve_app_name(raw_app)
            return {"intent": "application.install_dir", "action": "open_install_dir", "target": resolved_app, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Application Settings
        set_m = re.match(r"^(?:open|show|view)?\s*(?:the\s+)?(?:settings\s+for|settings\s+of)\s+(.+)$", clean, re.IGNORECASE)
        if not set_m:
            set_m = re.match(r"^(?:open|show|view)?\s*(?:the\s+)?(.+?)\'s\s+settings$", clean, re.IGNORECASE)
        if not set_m:
            set_m = re.match(r"^(?:open|show|view)\s+(.+?)\s+settings$", clean, re.IGNORECASE)
        if set_m:
            raw_app = set_m.group(1).strip()
            raw_app = re.sub(r"^(?:the\s+|my\s+)", "", raw_app).strip()
            if raw_app.lower() not in ["", "launch", "open", "start", "run", "windows", "system", "pc", "laptop"]:
                resolved_app = self.resolve_app_name(raw_app)
                return {"intent": "application.settings", "action": "open_settings", "target": resolved_app, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Application Version & Metadata
        ver_m = re.match(r"^what\s+version\s+of\s+(.+?)\s+is\s+installed$", clean, re.IGNORECASE)
        if not ver_m:
            ver_m = re.match(r"^(?:show|view|what\s+is|tell\s+me)\s+(?:the\s+)?version\s+of\s+(.+)$", clean, re.IGNORECASE)
        if not ver_m:
            ver_m = re.match(r"^(?:show|view|what\s+is|tell\s+me)?\s*(?:the\s+)?(.+?)(?:[\'s\s]+|\s+)version(?:\s+installed)?$", clean, re.IGNORECASE)
        if ver_m:
            raw_app = ver_m.group(1).strip()
            raw_app = re.sub(r"^(?:the\s+|my\s+)", "", raw_app).strip()
            resolved_app = self.resolve_app_name(raw_app)
            return {"intent": "application.metadata", "action": "get_metadata", "target": resolved_app, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # Application Installed / Availability Inquiry
        inst_m = re.match(r"^(?:is|check\s+if)\s+(.+?)\s+installed(?:\s+on\s+(?:this\s+|my\s+)?(?:computer|pc|laptop|system))?$", clean, re.IGNORECASE)
        if not inst_m:
            inst_m = re.match(r"^do\s+i\s+have\s+(.+?)(?:\s+installed)?$", clean, re.IGNORECASE)
        if inst_m:
            raw_app = inst_m.group(1).strip()
            raw_app = re.sub(r"^(?:the\s+|my\s+)", "", raw_app).strip()
            resolved_app = self.resolve_app_name(raw_app)
            return {"intent": "application.status", "action": "is_installed", "target": resolved_app, "confidence": 0.98, "query": clean, "raw_text": effective_raw}

        # -------------------------------------------------------------
        # 18.9 UNIVERSAL DESKTOP INTERACTION & CONTEXT-AWARE TEXT ENTRY
        # -------------------------------------------------------------
        # 1. Search in current application
        m_app_search = re.match(r"^(?:search\s+(?:for\s+)?(.+?)\s+(?:in|on)\s+(?:this\s+application|this\s+app|the\s+current\s+application|current\s+app))$", clean, re.IGNORECASE)
        if not m_app_search:
            m_app_search = re.match(r"^(?:search\s+(?:for\s+)?(.+?)\s+(?:in|on)\s+(chatgpt|youtube|whatsapp|editor))$", clean, re.IGNORECASE)
        if not m_app_search:
            m_app_search = re.match(r"^enter\s+(?:the\s+)?search\s+term(?:\s+(.+?))?\s+(?:in|on)\s+(.+)$", clean, re.IGNORECASE)
        if m_app_search:
            query_val = m_app_search.group(1).strip() if m_app_search.group(1) else "search term"
            dest_val = m_app_search.group(2).strip() if len(m_app_search.groups()) > 1 and m_app_search.group(2) else "current_application"
            return {
                "intent": "desktop_interaction.search_app",
                "action": "search_in_app",
                "query": query_val,
                "text": query_val,
                "target": query_val,
                "destination": dest_val,
                "confidence": 0.98,
                "raw_text": effective_raw
            }

        # 2. Write reply / response
        m_reply = re.match(r"^(?:write|draft)\s+(?:a\s+)?(?:[\w\-]+\s+)?(?:reply|response)\s+(?:saying|that)\s+(.+)$", clean, re.IGNORECASE)
        if not m_reply:
            m_reply = re.match(r"^(?:write|draft)\s+(?:a\s+)?(?:[\w\-]+\s+)?(?:reply|response)(?:\s+to\s+(?:this\s+|the\s+)?(?:message|email|chat))?(?:\s+(?:in|on)\s+(.+))?$", clean, re.IGNORECASE)
            if m_reply:
                dest_val = m_reply.group(1).strip() if m_reply.group(1) else ""
                return {
                    "intent": "desktop_interaction.write_reply",
                    "action": "write_reply",
                    "text": clean,
                    "target": clean,
                    "destination": dest_val,
                    "confidence": 0.98,
                    "raw_text": effective_raw
                }
        if not m_reply:
            m_reply = re.match(r"^reply(?:\s+to\s+(?:this\s+|the\s+)?(?:message|chat|email))?\s+(?:saying\s+)?(.+)$", clean, re.IGNORECASE)
        if m_reply:
            reply_text = m_reply.group(1).strip()
            dest_val = m_reply.group(2).strip() if len(m_reply.groups()) > 1 and m_reply.group(2) else ""
            return {
                "intent": "desktop_interaction.write_reply",
                "action": "write_reply",
                "text": reply_text,
                "target": reply_text,
                "destination": dest_val,
                "confidence": 0.98,
                "raw_text": effective_raw
            }

        # 3. Direct simple type command for current search bar
        if re.match(r"^(?:type\s+this\s+into\s+(?:the\s+)?current\s+search\s*bar|type\s+into\s+(?:the\s+)?search\s*bar)$", clean, re.IGNORECASE):
            return {
                "intent": "desktop_interaction.type_text",
                "action": "enter_text",
                "text": effective_raw,
                "destination": "search bar",
                "confidence": 0.98,
                "raw_text": effective_raw
            }

        # 4. Text entry into specific or current field
        m_type = re.match(r"^(?:type|paste|enter|put|write|fill\s+in)\s+(?:this\s+into|this\s+in|into|in)\s+(?:the\s+)?(?:current\s+)?(.+?)[:\s]+(.+)$", clean, re.IGNORECASE)
        if not m_type:
            m_type = re.match(r"^(?:type|paste|enter|put|write)\s+(.+?)\s+(?:into|in)\s+(?:the\s+)?(?:current\s+)?(.+)$", clean, re.IGNORECASE)
        if not m_type:
            m_type = re.match(r"^fill\s+in\s+(?:the\s+)?(.+?)\s+field(?:\s+with\s+(.+))?$", clean, re.IGNORECASE)
        if m_type:
            g1 = m_type.group(1).strip()
            g2 = m_type.group(2).strip() if len(m_type.groups()) > 1 and m_type.group(2) else ""
            if any(k in g1.lower() for k in ["search bar", "prompt box", "editor", "subject", "body", "field", "description"]):
                dest_val = g1
                text_val = g2 or g1
            else:
                text_val = g1
                dest_val = g2
            return {
                "intent": "desktop_interaction.type_text",
                "action": "enter_text",
                "text": text_val,
                "target": text_val,
                "destination": dest_val,
                "confidence": 0.98,
                "raw_text": effective_raw
            }

        # 5. Replace selected text
        m_replace = re.match(r"^replace\s+(?:the\s+)?(?:selected\s+text|selection)\s+with\s+(.+)$", clean, re.IGNORECASE)
        if m_replace:
            new_text = m_replace.group(1).strip()
            return {
                "intent": "desktop_interaction.replace_selection",
                "action": "replace_selection",
                "text": new_text,
                "target": new_text,
                "confidence": 0.98,
                "raw_text": effective_raw
            }

        # 6. Continue writing / Draft editing
        if clean in ["continue writing from where i left off", "continue writing", "continue from where i left off"]:
            return {
                "intent": "desktop_interaction.continue_writing",
                "action": "continue_writing",
                "target": "continue",
                "confidence": 0.98,
                "raw_text": effective_raw
            }

        m_edit_draft = re.match(r"^make\s+(?:the\s+)?(?:current\s+)?draft\s+(?:more\s+)?(.+)$", clean, re.IGNORECASE)
        if m_edit_draft:
            tone = m_edit_draft.group(1).strip()
            return {
                "intent": "desktop_interaction.edit_draft",
                "action": "edit_draft",
                "tone": tone,
                "target": tone,
                "confidence": 0.98,
                "raw_text": effective_raw
            }

        # 7. Send message / Submit form
        if clean in ["send the message", "send message", "send this message", "send it", "submit the form", "submit form"]:
            return {
                "intent": "desktop_interaction.send_message",
                "action": "send_message",
                "target": "send",
                "confidence": 0.98,
                "raw_text": effective_raw
            }

        open_patterns = [
            r"^(?:open|launch|start|run|begin|bring\s+up|fire\s+up|load|get\s+up|use|i\s+want\s+to\s+use|help\s+me\s+open|start\s+up)\s+(?:the\s+|my\s+)?(.+)$",
            r"^bring\s+(?:the\s+|my\s+)?(.+?)\s+up$",
            r"^get\s+(?:the\s+|my\s+)?(.+?)\s+(?:running|up)$"
        ]

        for pat in open_patterns:
            m = re.search(pat, clean)
            if m:
                target_raw = m.group(1).strip()

                # Check ambiguous pronoun without antecedent
                if target_raw.lower() in ["it", "that", "this", "that one", "the thing"]:
                    if not getattr(self, "last_app_target", None):
                        return {
                            "intent": "clarification_needed",
                            "action": "clarification_needed",
                            "target": target_raw,
                            "clarification_prompt": "Which application or website would you like me to open?",
                            "confidence": 1.0,
                            "raw_text": raw_text
                        }
                    else:
                        target_raw = self.last_app_target
                if target_raw in ["downloads", "download", "documents", "document", "desktop", "pictures", "videos", "music"]:
                    return {"intent": "file_access", "action": "open_folder", "target": target_raw, "confidence": 0.96, "query": clean, "raw_text": raw_text}

                # Check known files
                if re.search(r"\.(?:pdf|txt|docx?|xlsx?|pptx?|csv|json|py|html|png|jpg|jpeg|mp4|mp3|zip)$", target_raw) or "pdf" in target_raw:
                    return {"intent": "file_access", "action": "open_file", "target": target_raw, "confidence": 0.95, "query": clean, "raw_text": raw_text}

                # Use ApplicationResolver for intelligent target classification (App-First Priority)
                resolved_target = application_resolver.resolve(target_raw)

                if resolved_target.target_type == TargetType.DOMAIN_URL:
                    return {
                        "intent": "open_website",
                        "action": "open_url",
                        "target": resolved_target.url,
                        "url": resolved_target.url,
                        "confidence": 0.98,
                        "query": clean,
                        "raw_text": raw_text
                    }

                if resolved_target.target_type == TargetType.NATIVE_APP:
                    self.last_app_target = resolved_target.canonical_name
                    return {
                        "intent": "open_app",
                        "action": "open",
                        "target": resolved_target.canonical_name,
                        "confidence": 0.96,
                        "query": clean,
                        "raw_text": raw_text
                    }

                if resolved_target.target_type == TargetType.WEBSITE:
                    if resolved_target.canonical_name in self.app_aliases:
                        self.last_app_target = resolved_target.canonical_name
                        return {
                            "intent": "open_app",
                            "action": "open",
                            "target": resolved_target.canonical_name,
                            "confidence": 0.95,
                            "query": clean,
                            "raw_text": raw_text
                        }
                    return {
                        "intent": "open_website",
                        "action": "open_url",
                        "target": resolved_target.canonical_name,
                        "url": resolved_target.url,
                        "confidence": 0.96,
                        "query": clean,
                        "raw_text": raw_text
                    }

                resolved = self.resolve_app_name(target_raw)
                self.last_app_target = resolved
                return {"intent": "open_app", "action": "open", "target": resolved, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 20. TERMINAL EXECUTION & PROJECT CONTROL
        # -------------------------------------------------------------
        if clean.startswith("run ") or clean.startswith("execute ") or clean.startswith("terminal "):
            cmd_body = clean.replace("run ", "", 1).replace("execute ", "", 1).replace("terminal ", "", 1).strip()
            return {"intent": "terminal_execute", "action": "execute", "target": cmd_body, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if "check port" in clean:
            port_match = re.search(r"port\s+(\d+)", clean)
            port_num = port_match.group(1) if port_match else "5000"
            return {"intent": "terminal_execute", "action": "check_port", "target": port_num, "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if "show running node" in clean or "node processes" in clean:
            return {"intent": "terminal_execute", "action": "node_processes", "target": "node", "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if "list files in this folder" in clean or "show current directory" in clean or "list files" in clean:
            return {"intent": "filesystem_control", "action": "list_directory", "target": ".", "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if "open my jarvis project" in clean or "go to my jarvis project" in clean or "open jarvis project" in clean:
            return {"intent": "project_control", "action": "switch_project", "target": "jarvis", "confidence": 0.95, "query": clean, "raw_text": raw_text}

        if "go to" in clean and "project" in clean:
            proj_target = clean.split("go to")[-1].replace("project", "").strip()
            return {"intent": "project_control", "action": "switch_project", "target": proj_target, "confidence": 0.90, "query": clean, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 21. CONVERSATIONAL FALLBACK & UNRECOGNIZED INPUT
        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # 21. YOUTUBE PLAYBACK CONTROLS
        # -------------------------------------------------------------
        if clean in ["pause video", "pause the video", "pause youtube", "play video", "play the video", "play youtube", "resume video"]:
            return {"intent": "youtube_control", "action": "play_pause", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["skip forward", "skip 30 seconds", "fast forward video", "seek forward", "forward 30 seconds"]:
            return {"intent": "youtube_control", "action": "seek_forward", "target": "30", "confidence": 0.98, "raw_text": raw_text}

        if clean in ["skip backward", "rewind video", "rewind", "seek backward"]:
            return {"intent": "youtube_control", "action": "seek_backward", "target": "10", "confidence": 0.98, "raw_text": raw_text}

        if clean in ["mute video", "unmute video"]:
            return {"intent": "youtube_control", "action": "mute", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["fullscreen video", "video fullscreen"]:
            return {"intent": "youtube_control", "action": "fullscreen", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["toggle captions", "turn on captions", "turn off captions", "subtitles"]:
            return {"intent": "youtube_control", "action": "captions", "target": None, "confidence": 0.98, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 22. WRITING & CONTENT GENERATION INTENTS
        # -------------------------------------------------------------
        if clean.startswith("write an email") or clean.startswith("draft an email") or clean.startswith("write a professional email") or clean == "write email":
            topic = re.sub(r"^(?:write an email|draft an email|write a professional email|write email)\s*(?:about|for|to)?\s*", "", clean).strip() or "Professional Communication"
            return {"intent": "content_generation", "action": "draft_email", "target": topic, "content_type": "email", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("write a readme") or clean.startswith("create a readme") or clean.startswith("generate a readme") or clean == "write a project readme":
            topic = re.sub(r"^(?:write a readme|create a readme|generate a readme|write a project readme)\s*(?:for|about)?\s*", "", clean).strip() or "Project Documentation"
            return {"intent": "content_generation", "action": "draft_readme", "target": topic, "content_type": "readme", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("write python code") or clean.startswith("generate code") or clean.startswith("generate python code") or clean.startswith("write code for") or clean == "write python code":
            topic = re.sub(r"^(?:write python code|generate code|generate python code|write code for|write code)\s*", "", clean).strip() or "Python Utility"
            return {"intent": "content_generation", "action": "generate_code", "target": topic, "content_type": "code", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("create a report") or clean.startswith("write a report") or clean.startswith("generate a report"):
            topic = re.sub(r"^(?:create a report|write a report|generate a report)\s*(?:on|about|for)?\s*", "", clean).strip() or "Analysis Report"
            return {"intent": "content_generation", "action": "draft_report", "target": topic, "content_type": "report", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("create a checklist") or clean.startswith("make a checklist"):
            topic = re.sub(r"^(?:create a checklist|make a checklist)\s*(?:for|about)?\s*", "", clean).strip() or "Action Items"
            return {"intent": "content_generation", "action": "draft_checklist", "target": topic, "content_type": "checklist", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("explain this error") or clean.startswith("explain error") or clean.startswith("explain this python error"):
            err_text = re.sub(r"^(?:explain this error|explain error|explain this python error)\s*[:\s]*", "", effective_raw, flags=re.IGNORECASE).strip() or "Application Exception"
            return {"intent": "content_generation", "action": "explain_concept", "target": err_text, "content_type": "explanation", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("summarize this webpage") or clean.startswith("summarize this page") or clean == "summarize page":
            return {"intent": "content_generation", "action": "summarize_page", "target": "current_webpage", "content_type": "summary", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("compare these two products") or clean.startswith("compare options"):
            return {"intent": "content_generation", "action": "compare_options", "target": clean, "content_type": "comparison", "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 23. FILESYSTEM FOLDER CREATION & SAVING INTENTS
        # -------------------------------------------------------------
        if clean in ["create folder", "create a folder", "make a folder", "make folder", "new folder"]:
            return {"intent": "filesystem_control", "action": "create_folder", "target": "", "missing_arg": "folder_name", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("create a folder for ") or clean.startswith("create folder ") or clean.startswith("make a folder for "):
            folder_name = re.sub(r"^(?:create a folder for|create folder|make a folder for)\s*", "", clean).strip()
            if not folder_name:
                return {"intent": "filesystem_control", "action": "create_folder", "target": "", "missing_arg": "folder_name", "confidence": 0.95, "raw_text": raw_text}
            return {"intent": "filesystem_control", "action": "create_folder", "target": folder_name, "confidence": 0.95, "raw_text": raw_text}

        if clean in ["write document", "write a document", "write content", "draft document", "draft content"]:
            return {"intent": "content_generation", "action": "write", "target": "", "missing_arg": "topic", "confidence": 0.95, "raw_text": raw_text}

        if clean in ["save file", "save the file", "save document", "save a file"]:
            return {"intent": "filesystem_control", "action": "save_file", "target": "", "missing_arg": "destination", "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("save to ") or clean.startswith("save this file as ") or clean.startswith("save a readme"):
            file_target = re.sub(r"^(?:save to|save this file as|save a readme to|save a readme in|save a readme)\s*", "", clean).strip() or "README.md"
            return {"intent": "filesystem_control", "action": "save_file", "target": file_target, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 24. DEVELOPER WORKFLOWS & TESTING
        # -------------------------------------------------------------
        if clean in ["run tests", "run the tests", "open tests", "open the tests", "run project tests", "test project", "open my project and run its tests", "open my project and run it"]:
            return {"intent": "developer_workflow", "action": "run_tests", "target": None, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 25. FOLLOW-UP & CONTEXT RESOLUTION
        # -------------------------------------------------------------
        if clean in ["open the second result", "open second result", "open result two", "open result 2"]:
            return {"intent": "follow_up", "action": "open_result_index", "target": "2", "confidence": 0.95, "raw_text": raw_text}

        if clean in ["open the first result", "open first result", "open result one", "open result 1"]:
            return {"intent": "follow_up", "action": "open_result_index", "target": "1", "confidence": 0.95, "raw_text": raw_text}

        if clean in ["open the file you just created", "open the created file", "open the file"]:
            return {"intent": "follow_up", "action": "open_last_created_file", "target": None, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 26. OBSERVABILITY & TRANSPARENCY INTENTS (Pattern 08: Ask Why)
        # -------------------------------------------------------------
        if any(clean.startswith(kw) for kw in [
            "explain what tools you just called and why",
            "explain what tools you called",
            "explain tool execution",
            "why did you use that tool",
            "why did you run that tool",
            "what tools did you run",
            "what tools were called",
            "explain your decisions",
            "explain recent tools"
        ]) or clean in ["why did you do that", "explain actions", "explain decisions"]:
            return {"intent": "explain_tool_execution", "action": "explain", "target": None, "confidence": 0.98, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 27. PERSISTENT MEMORY & USER PROFILE INTENTS
        # -------------------------------------------------------------
        if clean.startswith("save this to memory:") or clean.startswith("save to memory:") or clean.startswith("remember this:"):
            mem_body = re.sub(r"^(?:save this to memory:|save to memory:|remember this:)\s*", "", effective_raw, flags=re.IGNORECASE).strip()
            return {"intent": "memory_control", "action": "save", "target": mem_body, "confidence": 0.98, "raw_text": raw_text}

        if any(clean.startswith(kw) for kw in ["what decisions have i made about", "recall my notes about", "what did i decide about", "recall notes about"]):
            topic = re.sub(r"^(?:what decisions have i made about|recall my notes about|what did i decide about|recall notes about)\s*", "", clean).strip(" ?")
            return {"intent": "memory_control", "action": "recall", "target": topic, "confidence": 0.95, "raw_text": raw_text}

        if clean.startswith("forget the note about") or clean.startswith("forget note about") or clean.startswith("forget memory"):
            topic = re.sub(r"^(?:forget the note about|forget note about|forget memory)\s*", "", clean).strip()
            return {"intent": "memory_control", "action": "forget", "target": topic, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 28. PRIVACY MODE CONTROL INTENTS
        # -------------------------------------------------------------
        if clean.startswith("set privacy mode to ") or clean.startswith("switch privacy mode to "):
            target_mode = clean.replace("set privacy mode to ", "").replace("switch privacy mode to ", "").strip().upper()
            return {"intent": "privacy_control", "action": "set_mode", "target": target_mode, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["what is my privacy mode", "check privacy mode", "privacy mode status", "privacy mode", "current privacy mode"]:
            return {"intent": "privacy_control", "action": "get_mode", "target": None, "confidence": 0.98, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 29. BROWSER TAB CONTROLS
        # -------------------------------------------------------------
        if clean in ["close tab", "close active tab", "close this tab", "close the tab"]:
            return {"intent": "browser_control", "action": "close_tab", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["new tab", "open new tab", "open a new tab", "open tab"]:
            return {"intent": "browser_control", "action": "new_tab", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["reopen tab", "reopen closed tab", "restore tab", "reopen the tab"]:
            return {"intent": "browser_control", "action": "reopen_tab", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["next tab", "switch to next tab", "go to next tab"]:
            return {"intent": "browser_control", "action": "next_tab", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["previous tab", "prev tab", "switch to previous tab", "go to previous tab"]:
            return {"intent": "browser_control", "action": "prev_tab", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["reload page", "reload the page", "refresh page", "refresh the page", "reload", "refresh"]:
            return {"intent": "browser_control", "action": "reload_page", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["go back", "navigate back", "page back", "browser back"]:
            return {"intent": "browser_control", "action": "go_back", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["go forward", "navigate forward", "page forward", "browser forward"]:
            return {"intent": "browser_control", "action": "go_forward", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["list tabs", "show open tabs", "list open tabs", "what tabs are open"]:
            return {"intent": "browser_control", "action": "list_tabs", "target": None, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["browser fullscreen", "toggle fullscreen", "exit fullscreen"]:
            return {"intent": "browser_control", "action": "toggle_fullscreen", "target": None, "confidence": 0.98, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 30. UNSUPPORTED CAPABILITY INTENTS
        # -------------------------------------------------------------
        unsupported_patterns = [
            r"^(?:order|buy)\s+(?:pizza|food|groceries|tickets?|stuff)",
            r"^(?:book)\s+(?:a\s+)?(?:flight|hotel|cab|uber|taxi|ride)",
            r"^(?:call|phone)\s+(?:mom|dad|anyone|someone|\w+)",
            r"^(?:send)\s+(?:sms|text\s+message)",
            r"^(?:turn\s+(?:on|off))\s+(?:the\s+)?(?:lights?|fan|ac|thermostat)",
        ]
        if any(re.search(pat, clean, re.IGNORECASE) for pat in unsupported_patterns):
            return {
                "intent": "unsupported_capability",
                "action": "unsupported",
                "target": clean,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 31. CONVERSATIONAL QUESTIONS & FALLBACK
        # -------------------------------------------------------------
        if clean in ["invalid command", "unknown command"]:
            return {
                "intent": "invalid_command",
                "action": "invalid_command",
                "target": None,
                "confidence": 0.95,
                "query": raw_text,
                "raw_text": raw_text,
                "fallback_message": "I couldn't complete that request, Sir. Try another command."
            }

        question_starters = ["what", "who", "where", "when", "why", "how", "which", "can", "could", "is", "do", "explain", "tell me"]
        if clean.endswith("?") or any(clean.startswith(qw) for qw in question_starters):
            return {
                "intent": "question",
                "action": "query",
                "target": None,
                "confidence": 0.80,
                "query": raw_text,
                "raw_text": raw_text
            }
        logger.info(f"Unmapped command falling back to conversation: '{clean}'")
        return {
            "intent": "conversation",
            "action": "chat",
            "target": None,
            "confidence": 0.50,
            "query": raw_text,
            "raw_text": raw_text
        }

    def _parse_spotify_command(self, raw_text: str, clean: str, effective_raw: str) -> Optional[dict]:
        """Parses natural-language Spotify commands for playback, playlists, and device management."""
        import re

        # Exclude OS-level app launching or closing commands
        if re.match(r"^(?:open|launch|start|run|close|terminate|kill|switch to)\s+spotify\b", clean, re.IGNORECASE):
            return None

        # 1. Liked songs
        if clean in ["play my liked songs", "play liked songs", "play my saved tracks", "play saved tracks", "play liked songs on spotify", "play my liked songs on spotify"]:
            return {
                "intent": "spotify_control",
                "action": "play_liked",
                "target": "liked_songs",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 2. Currently playing / Which song is playing?
        current_playing_phrases = [
            "which song is playing", "what song is playing", "what song is this",
            "what's playing", "whats playing", "what is playing", "which track is playing",
            "what track is playing", "which song is this", "what is currently playing",
            "what song is currently playing", "current song", "currently playing",
            "what's playing on spotify", "what is playing on spotify", "which song is playing on spotify",
            "what track is this", "who is singing this song", "who is singing this", "song name"
        ]
        clean_no_q = clean.rstrip("?").strip()
        if clean_no_q in current_playing_phrases or any(clean_no_q == p for p in current_playing_phrases):
            return {
                "intent": "spotify_control",
                "action": "current_track",
                "target": "player",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 3. Show / List playlists
        list_playlist_phrases = [
            "show my playlists", "show playlists", "list my playlists", "list playlists",
            "show spotify playlists", "list spotify playlists", "what playlists do i have",
            "what are my playlists", "view my playlists", "get my playlists", "display my playlists",
            "my playlists", "spotify playlists"
        ]
        if clean_no_q in list_playlist_phrases or any(clean_no_q == p for p in list_playlist_phrases):
            return {
                "intent": "spotify_control",
                "action": "list_playlists",
                "target": "playlists",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 4. Device Transfer: "play this on my laptop", "play on my laptop", "transfer playback to laptop"
        dev_match = re.match(r"^(?:play\s+this\s+on\s+(?:my\s+)?|play\s+on\s+(?:my\s+)?|transfer\s+(?:playback\s+)?to\s+(?:my\s+)?|switch\s+playback\s+to\s+(?:my\s+)?)(.+)$", clean_no_q, re.IGNORECASE)
        if dev_match:
            device_name = dev_match.group(1).strip()
            if device_name not in ["youtube", "chrome", "google", "edge", "browser"]:
                return {
                    "intent": "spotify_control",
                    "action": "transfer_device",
                    "device_name": device_name,
                    "target": device_name,
                    "confidence": 0.98,
                    "query": clean,
                    "raw_text": raw_text
                }

        # 5. Playback controls on Spotify: "pause spotify", "resume spotify", "shuffle my current playlist"
        if clean in ["pause spotify", "stop spotify"]:
            return {
                "intent": "spotify_control",
                "action": "pause",
                "target": "spotify",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }
        if clean in ["resume spotify", "unpause spotify"]:
            return {
                "intent": "spotify_control",
                "action": "resume",
                "target": "spotify",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # Contextual "Now play it" / "Play it now" / "Play it"
        if clean in ["now play it", "play it now", "play it", "play that playlist", "play this playlist"]:
            return {
                "intent": "spotify_control",
                "action": "play_current_context",
                "target": "active_playlist",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # Shuffle controls
        if clean in ["shuffle my current playlist", "shuffle current playlist", "shuffle the playlist", "shuffle playlist", "turn on shuffle", "shuffle on", "enable shuffle"]:
            return {
                "intent": "spotify_control",
                "action": "shuffle",
                "state": True,
                "target": "current_playlist",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }
        if clean in ["turn off shuffle", "shuffle off", "disable shuffle"]:
            return {
                "intent": "spotify_control",
                "action": "shuffle",
                "state": False,
                "target": "current_playlist",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 6. Create Playlist: "Create a playlist called Night Drive", "Create playlist Night Drive"
        create_match = re.match(r"^(?:create|make|start|build)\s+(?:a\s+)?(?:new\s+)?playlist\s+(?:called|named)?\s*(.+)$", clean, re.IGNORECASE)
        if create_match:
            p_name = create_match.group(1).strip()
            raw_match = re.match(r"^(?:create|make|start|build)\s+(?:a\s+)?(?:new\s+)?playlist\s+(?:called|named)?\s*(.+)$", effective_raw, re.IGNORECASE)
            if raw_match:
                p_name = raw_match.group(1).strip()
            return {
                "intent": "spotify_control",
                "action": "create_playlist",
                "playlist_name": p_name,
                "target": p_name,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 7. Rename Playlist: "Rename Night Drive to Midnight Vibes"
        rename_match = re.match(r"^(?:rename|change\s+the\s+name\s+of)\s+(?:playlist\s+)?(.+?)\s+to\s+(.+)$", clean, re.IGNORECASE)
        if rename_match:
            old_name = rename_match.group(1).strip()
            new_name = rename_match.group(2).strip()
            raw_rename = re.match(r"^(?:rename|change\s+the\s+name\s+of)\s+(?:playlist\s+)?(.+?)\s+to\s+(.+)$", effective_raw, re.IGNORECASE)
            if raw_rename:
                old_name = raw_rename.group(1).strip()
                new_name = raw_rename.group(2).strip()
            return {
                "intent": "spotify_control",
                "action": "rename_playlist",
                "playlist_name": old_name,
                "new_name": new_name,
                "target": old_name,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 8. Delete / Remove Playlist: "Delete my old playlist", "Delete playlist Night Drive", "Remove playlist Night Drive"
        delete_match = re.match(r"^(?:delete|remove|unfollow|destroy)\s+(?:my\s+)?(?:old\s+)?playlist\s*(?:called|named)?\s*(.*)$", clean, re.IGNORECASE)
        if delete_match:
            target_p = delete_match.group(1).strip()
            raw_del = re.match(r"^(?:delete|remove|unfollow|destroy)\s+(?:my\s+)?(?:old\s+)?playlist\s*(?:called|named)?\s*(.*)$", effective_raw, re.IGNORECASE)
            if raw_del and raw_del.group(1).strip():
                target_p = raw_del.group(1).strip()
            if not target_p:
                target_p = "old playlist"
            return {
                "intent": "spotify_control",
                "action": "delete_playlist",
                "playlist_name": target_p,
                "target": target_p,
                "requires_confirmation": True,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 9. Clean up duplicates: "clean up duplicates in Night Drive", "find duplicates in Night Drive", "find duplicates"
        dup_match = re.match(r"^(?:clean\s*up|remove|find|check)\s+(?:for\s+)?duplicate(?:s|\s+tracks)?(?:\s+(?:in|from)\s+(?:playlist\s+)?(.+))?$", clean, re.IGNORECASE)
        if dup_match:
            p_name = dup_match.group(1).strip() if dup_match.group(1) else None
            return {
                "intent": "spotify_control",
                "action": "cleanup_duplicates",
                "playlist_name": p_name,
                "target": p_name or "active_playlist",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        word_num_map = {
            "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
            "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
            "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9,
            "tenth": 10, "10th": 10, "one": 1, "two": 2, "three": 3, "four": 4,
            "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "a": 1, "an": 1
        }

        # 10. Reorder Track: "Move this song to the top", "Move the second song to the top", "Move track 3 to the top"
        reorder_match = re.match(r"^move\s+(?:the\s+)?(this|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|\d+)?(?:\s*(?:song|track|one))?\s+to\s+the\s+top$", clean, re.IGNORECASE)
        if reorder_match:
            ord_word = (reorder_match.group(1) or "this").lower()
            idx = 1
            if ord_word in word_num_map:
                idx = word_num_map[ord_word]
            elif ord_word.isdigit():
                idx = int(ord_word)
            return {
                "intent": "spotify_control",
                "action": "reorder_track",
                "from_index": idx,
                "to_index": 1,
                "target": "active_playlist",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 11. Remove Track:
        # e.g. "Remove the second song from Night Drive"
        # e.g. "Remove the second one" / "Remove the 2nd song"
        remove_match = re.match(r"^remove\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|\d+)\s*(?:song|track|one)?(?:\s+from\s+(?:playlist\s+)?(.+))?$", clean, re.IGNORECASE)
        if remove_match:
            ord_word = remove_match.group(1)
            p_name = remove_match.group(2).strip() if remove_match.group(2) else None
            idx = word_num_map.get(ord_word.lower()) if ord_word and ord_word.lower() in word_num_map else (int(ord_word) if ord_word and ord_word.isdigit() else 1)
            return {
                "intent": "spotify_control",
                "action": "remove_track",
                "index": idx,
                "playlist_name": p_name,
                "target": p_name or "active_playlist",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        remove_named_match = re.match(r"^remove\s+(?:track\s+|song\s+)?(.+?)\s+from\s+(?:playlist\s+)?(.+)$", clean, re.IGNORECASE)
        if remove_named_match:
            t_name = remove_named_match.group(1).strip()
            p_name = remove_named_match.group(2).strip()
            return {
                "intent": "spotify_control",
                "action": "remove_track",
                "track_name": t_name,
                "playlist_name": p_name,
                "target": p_name,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 12. Add tracks by artist / count: "Add five songs by The Weeknd", "Add 5 songs by The Weeknd"
        artist_add_match = re.match(r"^add\s+(first|second|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+songs?\s+by\s+(.+?)(?:\s+to\s+(?:playlist\s+)?(.+))?$", clean, re.IGNORECASE)
        if artist_add_match:
            cnt_word = artist_add_match.group(1).lower()
            count = word_num_map.get(cnt_word, int(cnt_word) if cnt_word.isdigit() else 1)
            artist_name = artist_add_match.group(2).strip()
            p_name = artist_add_match.group(3).strip() if artist_add_match.group(3) else None
            raw_art = re.match(r"^add\s+.+?\s+songs?\s+by\s+(.+?)(?:\s+to\s+(?:playlist\s+)?(.+))?$", effective_raw, re.IGNORECASE)
            if raw_art:
                artist_name = raw_art.group(1).strip()
                if raw_art.group(2):
                    p_name = raw_art.group(2).strip()

            return {
                "intent": "spotify_control",
                "action": "add_tracks_by_artist",
                "count": count,
                "artist": artist_name,
                "query": artist_name,
                "playlist_name": p_name,
                "target": p_name or "active_playlist",
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 13. Add specific track to playlist: "Add Blinding Lights to Night Drive"
        add_track_match = re.match(r"^add\s+(?:the\s+song\s+|track\s+|song\s+)?(.+?)\s+to\s+(?:playlist\s+)?(.+)$", clean, re.IGNORECASE)
        if add_track_match:
            t_name = add_track_match.group(1).strip()
            p_name = add_track_match.group(2).strip()
            raw_add = re.match(r"^add\s+(?:the\s+song\s+|track\s+|song\s+)?(.+?)\s+to\s+(?:playlist\s+)?(.+)$", effective_raw, re.IGNORECASE)
            if raw_add:
                t_name = raw_add.group(1).strip()
                p_name = raw_add.group(2).strip()
            return {
                "intent": "spotify_control",
                "action": "add_track",
                "track_name": t_name,
                "playlist_name": p_name,
                "target": p_name,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # 14. Play Playlist: "Play my workout playlist", "Play workout playlist", "Play playlist Night Drive"
        play_p_match = re.match(r"^play\s+(?:my\s+)?(?:the\s+)?(?:playlist\s+(?:called\s+)?)?(.+?)(?:\s+playlist)?$", clean, re.IGNORECASE)
        if play_p_match and not any(kw in clean for kw in ["on youtube", "youtube", "video", "browser", "chrome"]):
            p_cand = play_p_match.group(1).strip()
            if p_cand not in ["music", "song", "audio", "spotify", "it"]:
                raw_p = re.match(r"^play\s+(?:my\s+)?(?:the\s+)?(?:playlist\s+(?:called\s+)?)?(.+?)(?:\s+playlist)?$", effective_raw, re.IGNORECASE)
                if raw_p:
                    p_cand = raw_p.group(1).strip()
                return {
                    "intent": "spotify_control",
                    "action": "play_playlist",
                    "playlist_name": p_cand,
                    "target": p_cand,
                    "confidence": 0.96,
                    "query": clean,
                    "raw_text": raw_text
                }

        return None

    def _parse_panel_visibility_command(self, raw_text: str, clean: str, effective_raw: str) -> Optional[dict]:
        """Parses voice and text commands for showing, hiding, minimizing, and restoring Santra HUD panel."""
        import re

        clean_clean = clean.lower().strip()
        norm_raw = re.sub(r"[^\w\s]", "", effective_raw or "").lower().strip()
        raw_clean = (effective_raw or "").lower().strip()

        candidates = [t for t in (clean_clean, norm_raw, raw_clean) if t]

        # 1. SHOW / OPEN / RESTORE COMMANDS
        # "Open Santra panel.", "Show Santra.", "Show Santra dashboard.", "Restore Santra."
        show_patterns = [
            r"^(?:open|show|restore)\s+(?:the\s+)?santra\s+(?:panel|dashboard)\.?$",
            r"^(?:open|show|restore)\s+santra\.?$",
            r"^(?:open|show|restore)\s+(?:the\s+)?(?:dashboard|panel|hud)\.?$",
            r"^(?:show|restore)\s+(?:the\s+)?(?:window|ui)\.?$",
            r"^(?:bring\s+up|open\s+up)\s+(?:the\s+)?(?:santra|dashboard|panel)\.?$"
        ]

        for cand in candidates:
            for pat in show_patterns:
                if re.search(pat, cand, re.IGNORECASE):
                    return {
                        "intent": "panel_visibility",
                        "action": "show_panel",
                        "target": "santra_panel",
                        "confidence": 1.0,
                        "query": cand,
                        "raw_text": effective_raw,
                        "spoken": True
                    }

        # 2. HIDE / MINIMIZE COMMANDS
        # "Hide Santra panel.", "Hide Santra.", "Minimize Santra.", "Hide Santra dashboard."
        hide_patterns = [
            r"^(?:hide|minimize)\s+(?:the\s+)?santra\s+(?:panel|dashboard)\.?$",
            r"^(?:hide|minimize)\s+santra\.?$",
            r"^(?:hide|minimize)\s+(?:the\s+)?(?:dashboard|panel|hud)\.?$",
            r"^(?:hide|minimize)\s+(?:the\s+)?(?:window|ui)\.?$",
            r"^(?:send\s+to\s+tray|minimize\s+to\s+tray)\.?$"
        ]

        for cand in candidates:
            for pat in hide_patterns:
                if re.search(pat, cand, re.IGNORECASE):
                    return {
                        "intent": "panel_visibility",
                        "action": "hide_panel",
                        "target": "santra_panel",
                        "confidence": 1.0,
                        "query": cand,
                        "raw_text": effective_raw,
                        "spoken": True
                    }

        # 3. EXPLICIT EXIT / SHUTDOWN COMMANDS
        # "Exit Santra", "Shut down Santra", "Quit Santra"
        exit_patterns = [
            r"^(?:exit|shut\s*down|quit|kill)\s+santra\.?$",
            r"^(?:shut\s*down|exit|quit)\s+(?:the\s+)?assistant\.?$"
        ]
        for cand in candidates:
            for pat in exit_patterns:
                if re.search(pat, cand, re.IGNORECASE):
                    return {
                        "intent": "panel_visibility",
                        "action": "exit_assistant",
                        "target": "santra",
                        "confidence": 1.0,
                        "query": cand,
                        "raw_text": effective_raw,
                        "spoken": True
                    }

        return None

    def classify_intent(self, text: str) -> tuple:
        """Helper method returning (intent, target) tuple for concise evaluation."""
        node = self.parse(text)
        return node.get("intent"), node.get("target") or node.get("url")

intent_engine = IntentEngine()
