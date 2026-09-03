import json
import logging
import re
from pathlib import Path
from core.command_normalizer import CommandNormalizer
from core.platform.platform_manager import platform_manager
from modules.browser.web_control import web_control

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
        return self.app_aliases.get(clean, clean)

    def parse(self, text: str) -> dict:
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

        raw_text = text
        norm_res = self.normalizer.normalize(text)
        clean = norm_res["normalized"]

        logger.info(f"Intent Engine analyzing command: '{clean}' (Raw: '{raw_text}')")

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
            "good afternoon", "good night", "yo", "hey buddy", "howdy", "hey"
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
        if clean.startswith("open "):
            target = clean[5:].strip()
            if target in supported_sites or target in default_link_keys:
                return {
                    "intent": "open_website",
                    "action": "open_url",
                    "target": target,
                    "confidence": 0.96,
                    "query": clean,
                    "raw_text": raw_text
                }

        # -------------------------------------------------------------
        # 10. APP CONTROL INTENTS (Open / Close)
        # -------------------------------------------------------------
        if clean.startswith("open "):
            target = clean[5:].strip()
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

        if clean.startswith("close "):
            target = clean[6:].strip()
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
        # 13. CONVERSATIONAL QUESTIONS & FALLBACK
        # -------------------------------------------------------------
        question_starters = ["what is", "what are", "who is", "where is", "when is", "why is", "how to", "which way", "can you", "could you", "is there", "do you", "explain"]
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
            "raw_text": raw_text,
            "fallback_message": "I'm not sure what you meant, but I can discuss that with you."
        }
