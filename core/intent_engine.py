import json
import logging
import re
from pathlib import Path
from core.command_normalizer import CommandNormalizer
from core.platform.platform_manager import platform_manager
from modules.browser.web_control import web_control
from core.apps.application_discovery import app_discovery
from core.custom_commands.command_manager import command_manager
from core.custom_commands.command_registry import custom_command_registry

logger = logging.getLogger("Jarvis.IntentEngine")

class IntentEngine:
    """Consumes normalized commands and classifies intents into structured action nodes.
    Supports natural conversation, greetings, identity queries, system help/about info,
    web links, command history, and cross-platform system control actions.
    """

    def __init__(self):
        logger.info("Initializing Intent Engine.")
        self.normalizer = CommandNormalizer()
        self.apps_json_path = Path(__file__).parent.parent / "config" / "applications.json"
        self.app_aliases = self._load_app_aliases()

    def _load_app_aliases(self) -> dict:
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
        clean = raw.lower().strip()
        best_app, _ = app_discovery.find_application(clean)
        if best_app:
            return best_app.app_id
        return self.app_aliases.get(clean, clean)

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

    def parse(self, text: str, raw_text: str = None) -> dict:
        """Analyzes transcription or normalized text and extracts intent."""
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
        norm_res = self.normalizer.normalize(text)
        clean = norm_res["normalized"]

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

        if any(term in clean for term in ["test microphone", "microphone test", "check microphone", "test my microphone"]):
            return {
                "intent": "test_microphone",
                "action": "run_microphone_diagnostics",
                "target": "microphone",
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if any(term in clean for term in ["test speech", "speech test", "test speaker", "test voice", "can you speak", "test audio"]):
            return {
                "intent": "test_speech",
                "action": "test_speech",
                "target": "speech",
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

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
        # TIME & DATE INTENTS
        # -------------------------------------------------------------
        time_triggers = ["what time is it", "what's the time", "tell me the time", "current time", "what is the time", "time now"]
        if clean in time_triggers or clean == "time" or any(clean.startswith(t) for t in ["what time", "tell me the time"]):
            return {
                "intent": "time_query",
                "action": "get_time",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if any(kw in clean for kw in ["today s date", "todays date", "today date", "what is the date", "what day is it", "current date", "what is today", "which day is today", "what date is"]):
            return {
                "intent": "date_query",
                "action": "get_date",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # MATH & CALCULATOR INTENTS
        # -------------------------------------------------------------
        if clean.startswith("calculate ") or clean.startswith("solve ") or clean.startswith("math ") or (
            any(kw in clean for kw in [" plus ", " minus ", " multiplied by ", " divided by ", " times ", " percent of ", " to the power of "])
            and any(char.isdigit() for char in clean)
        ):
            return {
                "intent": "math_calculation",
                "action": "calculate",
                "target": clean,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # MEDIA CONTROL INTENTS
        # -------------------------------------------------------------
        if clean in ["play music", "pause music", "pause", "resume music", "play", "stop music", "resume"]:
            return {
                "intent": "media_control",
                "action": "play_pause",
                "target": "media",
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["next song", "next track", "skip song", "skip track", "next"]:
            return {
                "intent": "media_control",
                "action": "next_track",
                "target": "media",
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["previous song", "previous track", "prev song", "prev track", "previous", "go back song"]:
            return {
                "intent": "media_control",
                "action": "previous_track",
                "target": "media",
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 1. GREETINGS & PERSONALITY INTENTS
        # -------------------------------------------------------------
        greetings = [
            "hello", "hi", "namaste", "good morning", "good evening", 
            "good afternoon", "good night", "yo", "hey buddy", "howdy", "hey",
            "how are you", "what's up", "whats up", "what s up", "what is up"
        ]
        if clean in greetings or any(clean.startswith(g) for g in ["hello", "hi ", "namaste", "good morning", "good evening", "good afternoon", "good night", "hey "]):
            return {
                "intent": "greeting",
                "action": "respond_greeting",
                "target": clean,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 2. IDENTITY & CREATOR INTENTS
        # -------------------------------------------------------------
        identity_queries = [
            "who are you", "who made you", "who built you", "who created you", 
            "who developed you", "who owns you", "who is your developer", 
            "who is your creator", "what is your name"
        ]
        if any(iq in clean for iq in identity_queries):
            return {
                "intent": "identity",
                "action": "explain_identity",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 3. HELP & CAPABILITIES INTENTS
        # -------------------------------------------------------------
        help_queries = [
            "help", "help me", "what can you do", "what do", "show commands", 
            "commands", "capabilities", "what are your features"
        ]
        if clean in help_queries:
            return {
                "intent": "help",
                "action": "show_help",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 4. ABOUT & SYSTEM INFO INTENTS
        # -------------------------------------------------------------
        about_queries = [
            "about", "about goliya", "about jarvis", "version", 
            "system info", "system information", "system details"
        ]
        if clean in about_queries:
            return {
                "intent": "about",
                "action": "show_about",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 5. COMMAND HISTORY & REPETITION INTENTS
        # -------------------------------------------------------------
        history_queries = [
            "what was my last command", "repeat last command", "repeat that", 
            "show history", "last command", "command history"
        ]
        if clean in history_queries:
            return {
                "intent": "history_query",
                "action": "show_history",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["repeat", "what did you say", "say again", "repeat response"]:
            return {
                "intent": "repeat_response",
                "action": "repeat_speech",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 6. SYSTEM CONTROL & POWER
        # -------------------------------------------------------------
        if clean in ["lock computer", "lock pc", "lock screen", "lock system", "lock workstation", "lock"]:
            return {
                "intent": "system_control",
                "action": "lock_pc",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["sleep computer", "sleep pc", "sleep system", "sleep"]:
            return {
                "intent": "system_control",
                "action": "sleep_pc",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["shutdown computer", "shutdown pc", "turn off computer", "turn off pc", "shutdown"]:
            return {
                "intent": "system_control",
                "action": "shutdown_pc",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["restart computer", "restart pc", "reboot computer", "reboot pc", "restart"]:
            return {
                "intent": "system_control",
                "action": "restart_pc",
                "target": None,
                "confidence": 0.98,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["volume up", "increase volume", "louder"]:
            return {
                "intent": "system_control",
                "action": "volume_up",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["volume down", "decrease volume", "quieter"]:
            return {
                "intent": "system_control",
                "action": "volume_down",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["mute", "mute volume", "mute audio", "silence"]:
            return {
                "intent": "system_control",
                "action": "mute",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["unmute", "unmute volume", "unmute audio"]:
            return {
                "intent": "system_control",
                "action": "unmute",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if any(kw in clean for kw in ["battery status", "battery level", "battery"]):
            return {
                "intent": "system_control",
                "action": "battery",
                "target": None,
                "confidence": 0.90,
                "query": clean,
                "raw_text": raw_text
            }

        if any(kw in clean for kw in ["system metrics", "resource usage"]):
            return {
                "intent": "system_control",
                "action": "metrics",
                "target": None,
                "confidence": 0.90,
                "query": clean,
                "raw_text": raw_text
            }

        # System Telemetry Specific Intents
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

        # Terminal Subsystem Intents
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
        # BROWSER & WEB SEARCH INTENTS
        # -------------------------------------------------------------
        # 1. YouTube Search
        yt_patterns = [
            r"^search youtube for (.+)$",
            r"^find (.+) on youtube$",
            r"^look for (.+) on youtube$",
            r"^youtube (.+)$"
        ]
        for pat in yt_patterns:
            m = re.search(pat, clean)
            if m:
                q = m.group(1).strip()
                return {"intent": "web_search", "action": "search", "provider": "youtube", "target": q, "query": q, "confidence": 0.95, "raw_text": raw_text}

        # 2. Google / Web / Chrome Search
        web_patterns = [
            r"^search google for (.+)$",
            r"^search chrome for (.+)$",
            r"^search the web for (.+)$",
            r"^find (.+) on google$",
            r"^google (.+)$",
            r"^look up (.+)$"
        ]
        for pat in web_patterns:
            m = re.search(pat, clean)
            if m:
                q = m.group(1).strip()
                return {"intent": "web_search", "action": "search", "provider": "google", "target": q, "query": q, "confidence": 0.95, "raw_text": raw_text}

        # 3. Other Search Providers (GitHub, Reddit, StackOverflow)
        for prov in ["github", "reddit", "stackoverflow", "stack overflow"]:
            p_clean = "stackoverflow" if prov == "stack overflow" else prov
            pat = rf"^search {prov} for (.+)$"
            m = re.search(pat, clean)
            if m:
                q = m.group(1).strip()
                return {"intent": "web_search", "action": "search", "provider": p_clean, "target": q, "query": q, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # LOCAL SEARCH INTENTS (Project code, downloads, local files)
        # -------------------------------------------------------------
        proj_code_patterns = [
            r"^search (?:my |this )?project for (.+)$",
            r"^find (.+) in (?:my |this )?project$",
            r"^search code for (.+)$",
            r"^find every reference to (.+)$"
        ]
        for pat in proj_code_patterns:
            m = re.search(pat, clean)
            if m:
                q = m.group(1).strip()
                return {"intent": "local_search", "action": "search_code", "target": q, "query": q, "confidence": 0.95, "raw_text": raw_text}

        if "downloaded" in clean or ("pdf" in clean and ("download" in clean or "find" in clean)):
            m = re.search(r"find (?:the |my )?(?:downloaded )?(.+?)(?:\s+i downloaded.*|\s+in downloads.*)?$", clean)
            target_q = m.group(1).strip() if m else "pdf"
            return {"intent": "local_search", "action": "find_file", "target": target_q, "folder": "downloads", "extension": ".pdf" if "pdf" in clean else None, "confidence": 0.95, "raw_text": raw_text}

        if re.search(r"^find (?:a )?file in (?:the |my )?project(?:\s+(.+))?$", clean):
            m = re.search(r"^find (?:a )?file in (?:the |my )?project(?:\s+(.+))?$", clean)
            q = m.group(1).strip() if (m and m.group(1)) else ""
            return {"intent": "local_search", "action": "find_file", "target": q, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # BROWSER & CHROME CONTROLS
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

        # Multi-tab opening: "open three specified websites in separate tabs"
        multi_tab_m = re.search(r"open (?:these )?(\w+) (?:websites?|sites?|urls?) in separate tabs(?::\s*(.+))?", clean)
        if multi_tab_m:
            sites_str = multi_tab_m.group(2) or "google.com, github.com, youtube.com"
            urls = [s.strip() for s in sites_str.split(",") if s.strip()]
            return {"intent": "browser_control", "action": "open_multiple", "target": urls[0] if urls else None, "urls": urls, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # YOUTUBE PLAYBACK CONTROLS
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
        # WRITING & CONTENT GENERATION INTENTS
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
        # FILESYSTEM FOLDER CREATION & SAVING INTENTS
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
        # DEVELOPER WORKFLOWS & TESTING
        # -------------------------------------------------------------
        if clean in ["run tests", "run the tests", "open tests", "open the tests", "run project tests", "test project", "open my project and run its tests", "open my project and run it"]:
            return {"intent": "developer_workflow", "action": "run_tests", "target": None, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # FOLLOW-UP & CONTEXT RESOLUTION (L2)
        # -------------------------------------------------------------
        if clean in ["open the second result", "open second result", "open result two", "open result 2"]:
            return {"intent": "follow_up", "action": "open_result_index", "target": "2", "confidence": 0.95, "raw_text": raw_text}

        if clean in ["open the first result", "open first result", "open result one", "open result 1"]:
            return {"intent": "follow_up", "action": "open_result_index", "target": "1", "confidence": 0.95, "raw_text": raw_text}

        if clean in ["open the file you just created", "open the created file", "open the file"]:
            return {"intent": "follow_up", "action": "open_last_created_file", "target": None, "confidence": 0.95, "raw_text": raw_text}

        # -------------------------------------------------------------
        # OBSERVABILITY & TRANSPARENCY INTENTS (Pattern 08: Ask Why)
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
        # PERSISTENT MEMORY & USER PROFILE INTENTS
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
        # PRIVACY MODE CONTROL INTENTS (STRICT / GUARDED / RELAXED)
        # -------------------------------------------------------------
        if clean.startswith("set privacy mode to ") or clean.startswith("switch privacy mode to "):
            target_mode = clean.replace("set privacy mode to ", "").replace("switch privacy mode to ", "").strip().upper()
            return {"intent": "privacy_control", "action": "set_mode", "target": target_mode, "confidence": 0.98, "raw_text": raw_text}

        if clean in ["what is my privacy mode", "check privacy mode", "privacy mode status", "privacy mode", "current privacy mode"]:
            return {"intent": "privacy_control", "action": "get_mode", "target": None, "confidence": 0.98, "raw_text": raw_text}

        # -------------------------------------------------------------
        # 7. SCREENSHOT INTENTS
        # -------------------------------------------------------------
        if clean in ["take screenshot", "take a screenshot", "screenshot", "capture screen", "snapshot"]:
            return {
                "intent": "screenshot",
                "action": "take_screenshot",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if clean in ["open screenshot folder", "open screenshots folder", "show screenshots"]:
            return {
                "intent": "screenshot",
                "action": "open_folder",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 8. WINDOW CONTROL INTENTS
        # -------------------------------------------------------------
        if clean in ["list open windows", "list windows", "show open windows", "open windows"]:
            return {
                "intent": "window_control",
                "action": "list_open",
                "target": None,
                "confidence": 0.92,
                "query": clean,
                "raw_text": raw_text
            }

        if clean.startswith("minimize window") or clean == "minimize":
            target = clean.replace("minimize window", "").replace("minimize", "").strip() or None
            return {
                "intent": "window_control",
                "action": "minimize",
                "target": target,
                "confidence": 0.90,
                "query": clean,
                "raw_text": raw_text
            }

        if clean.startswith("maximize window") or clean == "maximize":
            target = clean.replace("maximize window", "").replace("maximize", "").strip() or None
            return {
                "intent": "window_control",
                "action": "maximize",
                "target": target,
                "confidence": 0.90,
                "query": clean,
                "raw_text": raw_text
            }

        if clean.startswith("restore window") or clean == "restore":
            target = clean.replace("restore window", "").replace("restore", "").strip() or None
            return {
                "intent": "window_control",
                "action": "restore",
                "target": target,
                "confidence": 0.90,
                "query": clean,
                "raw_text": raw_text
            }

        if clean.startswith("switch to") or clean.startswith("focus"):
            target = clean.replace("switch to", "").replace("focus", "").strip()
            return {
                "intent": "window_control",
                "action": "switch",
                "target": self.resolve_app_name(target),
                "confidence": 0.90,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 9. WEB LINKS INTENTS
        # -------------------------------------------------------------
        supported_sites = web_control.get_supported_sites()
        default_link_keys = [
            "youtube", "google", "github", "gmail", "chatgpt", "claude", 
            "gemini", "spotify", "netflix", "prime video", "primevideo", 
            "discord", "reddit", "stackoverflow", "stack overflow", "linkedin", 
            "instagram", "facebook", "x", "twitter", "whatsapp", "whatsapp web"
        ]
        web_tlds = (".com", ".org", ".net", ".io", ".co", ".gov", ".edu", ".ai", ".app", ".dev", ".in", ".uk")
        for web_prefix in ["open ", "go to ", "navigate to "]:
            if clean.startswith(web_prefix):
                target_site = clean[len(web_prefix):].strip()
                if (target_site in supported_sites or 
                    target_site in default_link_keys or 
                    target_site.endswith(web_tlds) or 
                    target_site.startswith(("http://", "https://", "www."))):
                    return {
                        "intent": "open_website",
                        "action": "open_url",
                        "target": target_site,
                        "confidence": 0.96,
                        "query": clean,
                        "raw_text": raw_text
                    }

        # -------------------------------------------------------------
        # 10. APP CONTROL INTENTS (Open / Close)
        # -------------------------------------------------------------
        if clean in ["open", "launch", "open app", "start app"]:
            return {
                "intent": "open_app",
                "action": "open",
                "target": "",
                "missing_arg": "app",
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        for pfx in ["open ", "launch ", "start "]:
            if clean.startswith(pfx):
                target = clean[len(pfx):].strip()
                if not target:
                    return {
                        "intent": "open_app",
                        "action": "open",
                        "target": "",
                        "missing_arg": "app",
                        "confidence": 0.95,
                        "query": clean,
                        "raw_text": raw_text
                    }
                if target in ["downloads", "download", "documents", "document", "desktop", "pictures", "videos", "music"]:
                    return {
                        "intent": "file_access",
                        "action": "open_folder",
                        "target": target,
                        "confidence": 0.95,
                        "query": clean,
                        "raw_text": raw_text
                    }
                return {
                    "intent": "open_app",
                    "action": "open",
                    "target": self.resolve_app_name(target),
                    "confidence": 0.92,
                    "query": clean,
                    "raw_text": raw_text
                }

        if clean in ["close", "close app", "quit app", "exit app"]:
            return {
                "intent": "close_app",
                "action": "close",
                "target": "",
                "missing_arg": "app",
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        if clean.startswith("close "):
            target = clean[6:].strip()
            if not target:
                return {
                    "intent": "close_app",
                    "action": "close",
                    "target": "",
                    "missing_arg": "app",
                    "confidence": 0.95,
                    "query": clean,
                    "raw_text": raw_text
                }
            if "window" in target:
                win_target = target.replace("window", "").strip() or None
                return {
                    "intent": "window_control",
                    "action": "close",
                    "target": win_target,
                    "confidence": 0.90,
                    "query": clean,
                    "raw_text": raw_text
                }
            return {
                "intent": "close_app",
                "action": "close",
                "target": self.resolve_app_name(target),
                "confidence": 0.90,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 11. FILE ACCESS INTENTS
        # -------------------------------------------------------------
        if clean.startswith("open folder "):
            folder_name = clean[12:].strip()
            return {
                "intent": "file_access",
                "action": "open_folder",
                "target": folder_name,
                "confidence": 0.90,
                "query": clean,
                "raw_text": raw_text
            }

        if clean.startswith("search file") or clean.startswith("find file"):
            search_target = clean.replace("search file", "").replace("find file", "").strip()
            return {
                "intent": "file_access",
                "action": "search_file",
                "target": search_target,
                "confidence": 0.88,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # 12. STATUS REQUEST INTENTS
        # -------------------------------------------------------------
        if clean in ["status", "system status", "status request", "health check"]:
            return {
                "intent": "status_request",
                "action": "metrics",
                "target": None,
                "confidence": 0.95,
                "query": clean,
                "raw_text": raw_text
            }

        # -------------------------------------------------------------
        # UNSUPPORTED CAPABILITY INTENTS
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
        # 13. CONVERSATIONAL QUESTIONS & FALLBACK
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
