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
        """Resolves raw application name or alias to canonical application key."""
        if not raw:
            return ""
        clean = raw.lower().strip()
        # Direct lookup in alias registry
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

    def _resolve_search_provider_and_query(self, query: str) -> tuple[str, str, str]:
        """Resolves target provider, clean target, and exact query from extracted search query string."""
        q_strip = query.strip()

        # 1. Targeted site postfix: "search for Python tutorials on YouTube"
        on_match = re.match(r"^(?:for\s+)?(.+?)\s+on\s+(youtube|github|reddit|stackoverflow|stack overflow|google)$", q_strip, re.IGNORECASE)
        if on_match:
            prov = on_match.group(2).lower()
            if prov == "stack overflow":
                prov = "stackoverflow"
            extracted = on_match.group(1).strip()
            return prov, extracted.lower(), extracted

        # 2. Local project code search: "search my project for ...", "search this project for ..."
        proj_match = re.match(r"^(?:in\s+|for\s+)?(?:my\s+|this\s+)?project\s+for\s+(.+)$", q_strip, re.IGNORECASE)
        if proj_match:
            extracted = proj_match.group(1).strip()
            return "project", extracted, extracted

        # 3. Provider prefixes: "YouTube for ...", "for YouTube ...", "GitHub for ...", etc.
        prov_patterns = [
            (r"^(?:for\s+)?(?:google|chrome|the web)\s+for\s+(.+)$", "google"),
            (r"^(?:for\s+)?(?:youtube)\s+for\s+(.+)$", "youtube"),
            (r"^(?:for\s+)?(?:github)\s+for\s+(.+)$", "github"),
            (r"^(?:for\s+)?(?:reddit)\s+for\s+(.+)$", "reddit"),
            (r"^(?:for\s+)?(?:stackoverflow|stack overflow)\s+for\s+(.+)$", "stackoverflow"),
        ]
        for pat, prov in prov_patterns:
            m = re.match(pat, q_strip, re.IGNORECASE | re.DOTALL)
            if m:
                extracted = m.group(1).strip()
                return prov, extracted.lower(), extracted

        # 4. Clean leading "for " or "about " from general queries while preserving original casing
        clean_q = re.sub(r"^(?:for|about)\s+", "", q_strip, flags=re.IGNORECASE).strip()
        return "google", clean_q, clean_q

    def _is_informational_query(self, raw_text: str, clean_text: str) -> bool:
        """Strictly identifies questions and informational queries that must NOT trigger actions."""
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
        # 0. EXPLICIT SEARCH INTENT (HIGHEST PRIORITY)
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

            prov, target_q, exact_q = self._resolve_search_provider_and_query(clean_query)
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

            logger.info(f"[SEARCH] Route selected: BrowserManager.search ({prov})")
            return {
                "intent": "web_search",
                "action": "search",
                "provider": prov,
                "target": target_q,
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
        time_triggers = ["what time is it", "what's the time", "tell me the time", "current time", "what is the time", "time now", "time"]
        if clean in time_triggers or any(clean.startswith(t) for t in ["what time", "tell me the time"]):
            return {"intent": "time_query", "action": "get_time", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        if any(kw in clean for kw in ["today s date", "todays date", "today date", "what is the date", "what is today's date", "what day is it", "current date", "what is today", "which day is today", "what date is"]):
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
        # 4. IDENTITY, HELP & ABOUT INTENTS
        # -------------------------------------------------------------
        # -------------------------------------------------------------
        identity_queries = [
            "who are you", "who made you", "who built you", "who created you", 
            "who developed you", "who owns you", "who is your developer", 
            "who is your creator", "what is your name"
        ]
        if any(iq in clean for iq in identity_queries):
            return {"intent": "identity", "action": "explain_identity", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        help_queries = [
            "help", "help me", "what can you do", "what can jarvis do", "what do you do", "what do",
            "what are your capabilities", "what commands do you know", "show commands", 
            "commands", "capabilities", "show capabilities", "show me your capabilities",
            "what are your features", "how can you help me", "how can you help"
        ]
        raw_lower = raw_text.lower().strip('?!. ')
        is_action_request = any(clean.startswith(f"help me {v}") or raw_lower.startswith(f"help me {v}") for v in ["open", "launch", "start", "close", "find", "search", "run", "play"])
        if not is_action_request and (clean in help_queries or raw_lower in help_queries or any(clean == hq or clean.startswith(hq + " ") or raw_lower == hq or raw_lower.startswith(hq + " ") for hq in help_queries)):
            return {"intent": "help", "action": "show_help", "target": None, "confidence": 0.98, "query": clean, "raw_text": raw_text}

        about_queries = [
            "about", "about goliya", "about jarvis", "version", 
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
        if clean in ["play music", "pause music", "pause", "resume music", "play", "stop music", "resume"]:
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

        greetings = [
            "hello", "hi", "namaste", "good morning", "good evening", 
            "good afternoon", "good night", "yo", "hey buddy", "howdy", "hey",
            "what's up", "whats up", "what s up", "what is up"
        ]
        if clean in greetings or any(clean.startswith(g) for g in ["hello", "hi ", "namaste", "good morning", "good evening", "good afternoon", "good night", "hey "]):
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

        # 11.2 SLEEP_COMPUTER
        sleep_patterns = [
            r"^(?:put|send|make)\s+(?:my|the)?\s*(?:laptop|computer|pc|system)?\s*(?:to|into)?\s*sleep$",
            r"^(?:can\s+you|could\s+you|please)?\s*put\s+(?:my|the)?\s*(?:laptop|computer|pc)\s+to\s+sleep$",
            r"^(?:please\s+)?sleep(?:\s+(?:the|my)?\s*(?:computer|laptop|pc|system))?$",
            r"^go\s+to\s+sleep$",
            r"^sleep\s+computer$"
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

                if target_raw in ["it", "this", "this window", "the window", ""]:
                    target_app = self.last_app_target
                else:
                    target_app = self.resolve_app_name(target_raw)

                if "window" in target_raw and not target_app:
                    return {"intent": "window_control", "action": "close", "target": None, "confidence": 0.92, "query": clean, "raw_text": raw_text}

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
        open_patterns = [
            r"^(?:open|launch|start|run|begin|bring\s+up|fire\s+up|load|get\s+up|use|i\s+want\s+to\s+use|help\s+me\s+open|start\s+up)\s+(?:the\s+|my\s+)?(.+)$",
            r"^bring\s+(?:the\s+|my\s+)?(.+?)\s+up$",
            r"^get\s+(?:the\s+|my\s+)?(.+?)\s+(?:running|up)$"
        ]

        for pat in open_patterns:
            m = re.search(pat, clean)
            if m:
                target_raw = m.group(1).strip()
                
                # Check known folders
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

    def classify_intent(self, text: str) -> tuple:
        """Helper method returning (intent, target) tuple for concise evaluation."""
        node = self.parse(text)
        return node.get("intent"), node.get("target") or node.get("url")

intent_engine = IntentEngine()
