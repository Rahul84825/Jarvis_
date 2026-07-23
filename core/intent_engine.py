import json
import logging
import re

logger = logging.getLogger("Jarvis.IntentEngine")

class IntentEngine:
    """Deterministic, rule-based intent engine that parses user transcripts
    into structured JSON action nodes.
    """
    
    def __init__(self):
        logger.info("Initializing Jarvis Deterministic Intent Engine.")

    def _resolve_app_alias(self, app_name: str) -> str:
        if not app_name:
            return app_name
        name = app_name.lower().strip()
        aliases = {
            "vieskund": "vscode",
            "vees code": "vscode",
            "viscode": "vscode",
            "vies kund": "vscode",
            "code": "vscode",
            "crome": "chrome",
            "google chrome": "chrome",
            "spottify": "spotify",
            "steem": "steam",
            "fire fox": "firefox",
            "microsoft edge": "edge",
            "msedge": "edge",
            "calculator": "calculator",
            "calc": "calculator",
            "note pad": "notepad",
            "notebook": "notepad",
            "not pad": "notepad",
            "room": "chrome",
            "cru": "chrome",
            "open-cru": "chrome"
        }
        return aliases.get(name, name)

    def parse(self, text: str) -> dict:
        """Analyzes transcription and extracts intent.
        
        Args:
            text: Raw speech transcription string.
        Returns:
            Dictionary representing structured JSON output.
        """
        clean_text = text.lower().strip()
        logger.info(f"Analyzing speech text: '{text}'")
        
        if not clean_text:
            decision = {"intent": "unknown", "query": ""}
            self._log_decision(text, decision)
            return decision

        # Remove trailing and leading punctuation/special characters
        clean_text = clean_text.strip(",.?!;:- ")
        # Replace commas and dashes with spaces to handle pause punctuation
        clean_text = clean_text.replace(",", " ").replace("-", " ")
        
        # Replace common phonetic speech recognition mistakes for action verbs and terms
        clean_text = clean_text.replace("clothes", "close")
        clean_text = clean_text.replace("clothe", "close")
        clean_text = clean_text.replace("manimai swindle", "minimize window")
        clean_text = clean_text.replace("manimai", "minimize")
        clean_text = clean_text.replace("minivized", "minimize")
        clean_text = clean_text.replace("minimized", "minimize")
        clean_text = clean_text.replace("least open windows", "list open windows")
        clean_text = clean_text.replace("least windows", "list open windows")
        clean_text = clean_text.replace("show screen show", "show screenshots")
        clean_text = clean_text.replace("show screen shot", "show screenshots")
        clean_text = clean_text.replace("dot pdf", ".pdf")
        clean_text = clean_text.replace("dot exe", ".exe")
        clean_text = clean_text.replace("dot txt", ".txt")
        clean_text = clean_text.replace("dot docx", ".docx")
        clean_text = clean_text.replace("increase volume", "volume up")
        clean_text = clean_text.replace("increased volume", "volume up")
        clean_text = clean_text.replace("decrease volume", "volume down")
        clean_text = clean_text.replace("decreased volume", "volume down")
        clean_text = clean_text.replace("lock pc", "lock pc")
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        # Strip common wake word prefixes (and phonetic variants from transcribers)
        # Includes optional conversational filler word prefixes (e.g. "and Jarvis", "so Jarvis")
        wake_word_patterns = [
            r"^(?:and|so|then|ok|okay|just|always|is|this|with|going\s+to\s+be|always)?\s*(?:hey\s+)?jarvis(?:'s)?\s*",
            r"^(?:and|so|then|ok|okay|just|always|is|this|with)?\s*hello\s+jarvis(?:'s)?\s*",
            r"^(?:and|so|then|ok|okay|just|always|is|this|with)?\s*hjrb(?:\s+is|'s)?\s*",
            r"^(?:and|so|then|ok|okay|just|always|is|this|with)?\s*(?:service|derbis|dervis|darwis|carves|charles|gerald|travis|garbage|device|assistant|always|jal|jals)(?:\s+is|'s|'|s)?\s*"
        ]
        for pattern in wake_word_patterns:
            clean_text = re.sub(pattern, "", clean_text).strip()

        # ==========================================
        # 1. System Actions (Deterministic mappings for shutdown/restart/lock)
        # ==========================================
        shutdown_phrases = ["shutdown the pc", "shutdown computer", "turn off pc", "turn off computer"]
        if any(phrase in clean_text for phrase in shutdown_phrases):
            decision = {"intent": "system_action", "action": "shutdown", "query": text}
            self._log_decision(text, decision)
            return decision

        restart_phrases = ["restart the pc", "restart computer", "reboot pc", "reboot computer"]
        if any(phrase in clean_text for phrase in restart_phrases):
            decision = {"intent": "system_action", "action": "restart", "query": text}
            self._log_decision(text, decision)
            return decision

        lock_phrases = ["lock the pc", "lock computer", "lock screen", "lock system", "lock my computer"]
        if any(phrase in clean_text for phrase in lock_phrases):
            decision = {"intent": "system_action", "action": "lock", "query": text}
            self._log_decision(text, decision)
            return decision

        # ==========================================
        # 2. File Access Intent
        # ==========================================
        # e.g., "Open Downloads", "Open my Documents", "Find resume.pdf"
        if "downloads" in clean_text and any(w in clean_text for w in ["open", "show", "go to"]):
            decision = {"intent": "file_access", "action": "open_folder", "target": "downloads", "query": text}
            self._log_decision(text, decision)
            return decision
            
        if "documents" in clean_text and any(w in clean_text for w in ["open", "show", "go to"]):
            decision = {"intent": "file_access", "action": "open_folder", "target": "documents", "query": text}
            self._log_decision(text, decision)
            return decision

        if "desktop" in clean_text and any(w in clean_text for w in ["open", "show", "go to"]):
            decision = {"intent": "file_access", "action": "open_folder", "target": "desktop", "query": text}
            self._log_decision(text, decision)
            return decision

        if "project folder" in clean_text and any(w in clean_text for w in ["open", "show", "go to"]):
            decision = {"intent": "file_access", "action": "open_folder", "target": "project folder", "query": text}
            self._log_decision(text, decision)
            return decision

        # "find resume.pdf" / "search for resume.pdf"
        find_match = re.match(r"^(?:find|search for|search|find file)\s+(.+)$", clean_text)
        if find_match:
            search_term = find_match.group(1).strip()
            decision = {"intent": "file_access", "action": "search_file", "target": search_term, "query": text}
            self._log_decision(text, decision)
            return decision

        # Generic open folder/file
        open_folder_match = re.match(r"^open\s+folder\s+(.+)$", clean_text)
        if open_folder_match:
            folder_target = open_folder_match.group(1).strip()
            decision = {"intent": "file_access", "action": "open_folder", "target": folder_target, "query": text}
            self._log_decision(text, decision)
            return decision

        open_file_match = re.match(r"^open\s+file\s+(.+)$", clean_text)
        if open_file_match:
            file_target = open_file_match.group(1).strip()
            decision = {"intent": "file_access", "action": "open_file", "target": file_target, "query": text}
            self._log_decision(text, decision)
            return decision

        # ==========================================
        # 3. Screenshot Intent
        # ==========================================
        if any(phrase in clean_text for phrase in ["take a screenshot", "take screenshot", "capture screen", "screenshot"]):
            decision = {"intent": "screenshot", "action": "take_screenshot", "query": text}
            self._log_decision(text, decision)
            return decision

        if any(phrase in clean_text for phrase in ["show screenshots", "open screenshots folder", "open screenshot folder", "show screenshot"]):
            decision = {"intent": "screenshot", "action": "open_folder", "query": text}
            self._log_decision(text, decision)
            return decision

        # ==========================================
        # 4. Open / Close App Intent
        # ==========================================
        open_match = re.match(r"^(?:open|launch|run|start)\s+([a-z0-9\s\.\-_]+)$", clean_text)
        if open_match:
            target_app = open_match.group(1).strip()
            target_app = self._resolve_app_alias(target_app)
            # If target ends with "folder" or "documents" etc., do not process as open_app
            if target_app not in ["downloads", "documents", "desktop", "project folder", "screenshots folder", "screenshot folder", "screenshots", "screenshot"]:
                decision = {"intent": "open_app", "target": target_app, "query": text}
                self._log_decision(text, decision)
                return decision

        close_match = re.match(r"^(?:close|exit|quit|terminate|kill)\s+([a-z0-9\s\.\-_]+)$", clean_text)
        if close_match:
            target_app = close_match.group(1).strip()
            target_app = self._resolve_app_alias(target_app)
            if target_app not in ["current window", "active window"]:
                decision = {"intent": "close_app", "target": target_app, "query": text}
                self._log_decision(text, decision)
                return decision

        # ==========================================
        # 5. Window Control Intent
        # ==========================================
        # e.g., "Minimize Chrome", "Maximize VS Code", "Close active window", "Switch to VS Code"
        if clean_text.startswith("minimize"):
            target = clean_text.replace("minimize", "").replace("active window", "").replace("window", "").strip()
            target = self._resolve_app_alias(target) if target else None
            decision = {"intent": "window_control", "action": "minimize", "target": target or None, "query": text}
            self._log_decision(text, decision)
            return decision
            
        if clean_text.startswith("maximize"):
            target = clean_text.replace("maximize", "").replace("active window", "").replace("window", "").strip()
            target = self._resolve_app_alias(target) if target else None
            decision = {"intent": "window_control", "action": "maximize", "target": target or None, "query": text}
            self._log_decision(text, decision)
            return decision
            
        if clean_text.startswith("restore"):
            target = clean_text.replace("restore", "").replace("active window", "").replace("window", "").strip()
            target = self._resolve_app_alias(target) if target else None
            decision = {"intent": "window_control", "action": "restore", "target": target or None, "query": text}
            self._log_decision(text, decision)
            return decision

        if clean_text.startswith("switch to") or clean_text.startswith("switch") or clean_text.startswith("focus"):
            target = clean_text.replace("switch to", "").replace("switch", "").replace("focus", "").strip()
            target = self._resolve_app_alias(target)
            decision = {"intent": "window_control", "action": "switch", "target": target, "query": text}
            self._log_decision(text, decision)
            return decision

        if clean_text in ["close current window", "close active window", "close window"]:
            decision = {"intent": "window_control", "action": "close", "target": None, "query": text}
            self._log_decision(text, decision)
            return decision
            
        if clean_text.startswith("close") and any(w in clean_text for w in ["window", "active", "current"]):
            target = clean_text.replace("close", "").replace("current window", "").replace("active window", "").replace("window", "").strip()
            target = self._resolve_app_alias(target) if target else None
            decision = {"intent": "window_control", "action": "close", "target": target or None, "query": text}
            self._log_decision(text, decision)
            return decision

        if clean_text in ["list open windows", "list windows", "show open windows", "show windows"]:
            decision = {"intent": "window_control", "action": "list_open", "target": None, "query": text}
            self._log_decision(text, decision)
            return decision

        # ==========================================
        # 6. System Volume, Power, and Telemetry Metrics
        # ==========================================
        # Volume Up
        if any(phrase in clean_text for phrase in ["volume up", "increase volume", "louder", "make it louder"]):
            decision = {"intent": "system_control", "action": "volume_up", "query": text}
            self._log_decision(text, decision)
            return decision
            
        # Volume Down
        if any(phrase in clean_text for phrase in ["volume down", "decrease volume", "quieter", "make it quieter"]):
            decision = {"intent": "system_control", "action": "volume_down", "query": text}
            self._log_decision(text, decision)
            return decision
            
        # Mute
        if any(phrase in clean_text for phrase in ["mute volume", "mute", "silence"]):
            decision = {"intent": "system_control", "action": "mute", "query": text}
            self._log_decision(text, decision)
            return decision
            
        # Unmute
        if any(phrase in clean_text for phrase in ["unmute volume", "unmute"]):
            decision = {"intent": "system_control", "action": "unmute", "query": text}
            self._log_decision(text, decision)
            return decision

        # Power actions sleep (shutdown/restart/lock handled above)
        if any(phrase in clean_text for phrase in ["sleep my computer", "sleep the pc", "sleep computer", "sleep system"]):
            decision = {"intent": "system_control", "action": "sleep", "query": text}
            self._log_decision(text, decision)
            return decision

        # Battery check
        if any(phrase in clean_text for phrase in ["battery percentage", "battery status", "battery level", "what's my battery percentage", "check battery"]):
            decision = {"intent": "status_request", "action": "battery", "query": text}
            self._log_decision(text, decision)
            return decision

        # Metrics check
        metrics_keywords = ["cpu usage", "ram usage", "disk usage", "system metrics", "check system status", "system status", "metrics", "resource usage"]
        if any(phrase in clean_text for phrase in metrics_keywords):
            decision = {"intent": "status_request", "action": "metrics", "query": text}
            self._log_decision(text, decision)
            return decision

        # ==========================================
        # 7. Conversational greetings, pleasantries, questions, fallback
        # ==========================================
        convo_greetings = [
            "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
            "thanks", "thank you", "bye", "goodbye", "how are you", "what's up"
        ]
        for word in convo_greetings:
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, clean_text):
                decision = {"intent": "conversation", "query": text}
                self._log_decision(text, decision)
                return decision

        question_words = [
            "what", "who", "how", "when", "where", "why", "which",
            "tell me", "show me", "can you", "could you", "is there"
        ]
        is_question = (
            any(clean_text.startswith(word) for word in question_words) or 
            text.strip().endswith("?")
        )
        if is_question:
            decision = {"intent": "question", "query": text}
            self._log_decision(text, decision)
            return decision

        # Fallback
        decision = {"intent": "conversation", "query": text}
        logger.info(f"Unrecognized phrasing, defaulting to conversation: '{clean_text}'")
        self._log_decision(text, decision)
        return decision

    def _log_decision(self, query: str, decision: dict):
        logger.info(f"Intent Decision: Input='{query}' -> JSON={json.dumps(decision)}")
