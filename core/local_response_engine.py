import json
import random
import logging
from pathlib import Path
from config import config

logger = logging.getLogger("Jarvis.LocalResponseEngine")

class LocalResponseEngine:
    """Local-first response engine providing fast, deterministic, and natural spoken outputs.
    Eliminates external LLM API dependencies and latency for core Jarvis interactions.
    """

    def __init__(self, responses_path: str = None):
        if responses_path is None:
            self.responses_path = config.BASE_DIR / "config" / "responses.json"
        else:
            self.responses_path = Path(responses_path)

        self.responses = self._load_responses()

    def _load_responses(self) -> dict:
        """Loads response template registry from JSON file with fallback defaults."""
        defaults = {
            "greeting": ["Hello.", "Hello! How can I help?", "Yes, I'm here.", "Hi. What can I do for you?"],
            "namaste": ["Namaste.", "Namaste! How can I help?"],
            "wake_response": ["Yes?", "I'm listening.", "Go ahead."],
            "thank_you": ["You're welcome.", "Anytime.", "Happy to help."],
            "goodbye": ["Goodbye.", "See you later."],
            "help": ["I can open applications, manage your computer, control volume, open folders and websites, take screenshots, and execute multiple commands."],
            "identity": ["I'm {assistant_name}, your personal desktop assistant.", "I'm {assistant_name}, built as a personal AI assistant project for {owner_name}."],
            "open_app": ["Opening {app}.", "Sure, opening {app}."],
            "close_app": ["Closing {app}."],
            "screenshot": ["Taking a screenshot.", "Screenshot saved."],
            "volume_up": ["Volume increased."],
            "volume_down": ["Volume decreased."],
            "mute": ["Muted."],
            "unmute": ["Unmuted."],
            "lock_pc": ["Locking the computer."],
            "open_website": ["Opening {site}.", "Sure, opening {site}."],
            "file_access": ["Opening {folder}."],
            "window_control": ["Window updated."],
            "system_control": ["System setting updated."],
            "system_action": ["Executing system action."],
            "cancellation": ["Action canceled. Standby."],
            "error_generic": ["I couldn't complete that."],
            "error_not_found": ["I couldn't find that application."],
            "error_unsupported": ["That action isn't supported on this system."],
            "unknown": ["I'm not sure how to help with that yet, but I can open apps, websites, control volume, or take screenshots."]
        }

        if self.responses_path.exists():
            try:
                with open(self.responses_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    defaults.update(data)
                    logger.info("Successfully loaded local response templates from config/responses.json.")
            except Exception as e:
                logger.warning(f"Error reading responses.json ({e}). Using default local responses.")

        return defaults

    def get_template(self, intent_key: str) -> str:
        """Returns a random response template string for a given intent key."""
        templates = self.responses.get(intent_key, self.responses.get("error_generic"))
        if isinstance(templates, list) and len(templates) > 0:
            return random.choice(templates)
        elif isinstance(templates, str):
            return templates
        return "Done."

    def get_wake_response(self) -> str:
        """Returns a fast, concise wake word acknowledgment."""
        return self.get_template("wake_response")

    def get_identity_response(self) -> str:
        """Returns identity information formatted with system configuration."""
        tmpl = self.get_template("identity")
        assistant_name = getattr(config, "assistant_name", "Jarvis")
        owner_name = getattr(config, "owner_name", "Active Gamer")
        return tmpl.format(assistant_name=assistant_name, owner_name=owner_name)

    def get_help_response(self) -> str:
        """Returns concise help documentation."""
        return self.get_template("help")

    def format_intent_response(self, intent_node: dict, execution_result: dict = None) -> str:
        """Formats a local natural response for a given intent node and optional execution result."""
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action", "")
        target = intent_node.get("target", "")

        # Target formatting helpers
        target_lower = (target or "").lower()
        if target_lower == "youtube":
            clean_target = "YouTube"
        elif target_lower in ["vscode", "vs code"]:
            clean_target = "VS Code"
        else:
            clean_target = (target or "").replace("_", " ").title()

        if intent == "greeting":
            raw_text = intent_node.get("raw", "").lower()
            if "namaste" in raw_text:
                return self.get_template("namaste")
            if "good morning" in raw_text:
                return "Good morning! How can I help?"
            if "good evening" in raw_text:
                return "Good evening! How can I help?"
            if "good afternoon" in raw_text:
                return "Good afternoon! How can I help?"
            if "good night" in raw_text:
                return "Good night!"
            return self.get_template("greeting")

        if intent == "thank_you":
            return self.get_template("thank_you")

        if intent == "goodbye":
            return self.get_template("goodbye")

        if intent == "help":
            return self.get_help_response()

        if intent == "identity":
            return self.get_identity_response()

        if intent == "open_app":
            app_name = clean_target or "Application"
            return self.get_template("open_app").format(app=app_name)

        if intent == "close_app":
            app_name = clean_target or "Application"
            return self.get_template("close_app").format(app=app_name)

        if intent == "open_website":
            site_name = clean_target or "Website"
            return self.get_template("open_website").format(site=site_name)

        if intent == "file_access":
            folder_name = clean_target or "Folder"
            return self.get_template("file_access").format(folder=folder_name)

        if intent == "screenshot":
            return self.get_template("screenshot")

        if action == "volume_up":
            return self.get_template("volume_up")

        if action == "volume_down":
            return self.get_template("volume_down")

        if action == "mute":
            return self.get_template("mute")

        if action == "unmute":
            return self.get_template("unmute")

        if action == "lock_pc":
            return self.get_template("lock_pc")

        if execution_result:
            if not execution_result.get("success", True):
                msg = execution_result.get("message", "")
                if "not found" in msg.lower():
                    return self.get_template("error_not_found")
                return self.get_template("error_generic")

            msg = execution_result.get("message")
            if msg:
                return msg

        return self.get_template(intent)

    def format_multi_command_response(self, sub_results: list) -> str:
        """Synthesizes a single concise summary response for sequential multi-command executions."""
        if not sub_results:
            return "Done."

        phrases = []
        all_success = True
        for res in sub_results:
            if not res.get("success"):
                all_success = False
            msg = res.get("message", "")
            if msg:
                # Strip leading "Sure." or "Done." for clean chaining
                msg_clean = msg.replace("Sure, ", "").replace("Sure. ", "").replace("Done. ", "")
                phrases.append(msg_clean)

        if len(phrases) == 1:
            return phrases[0]

        prefix = "Done." if all_success else "Completed with warnings."
        summary = ", and ".join(phrases) if len(phrases) <= 2 else ", ".join(phrases)
        return f"{prefix} {summary}"
