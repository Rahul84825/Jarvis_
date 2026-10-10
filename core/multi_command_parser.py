import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.MultiCommandParser")

@dataclass
class StructuredMultiAction:
    raw_text: str
    commands: List[str]
    actions: List[Dict[str, Any]]
    is_multi: bool

class MultiCommandParser:
    """Parses multi-command compound sentences into individual sequential executable commands."""

    ACTION_VERBS = [
        "open", "launch", "start", "close", "exit", "terminate",
        "lock", "sleep", "restart", "shutdown", "reboot", "turn",
        "increase", "decrease", "mute", "unmute", "take",
        "show", "list", "search", "find", "minimize", "maximize", "restore"
    ]

    SYSTEM_KEYWORDS = [
        "volume", "mute", "unmute", "screenshot", "lock", "sleep",
        "shutdown", "restart", "reboot", "battery", "metrics", "status"
    ]

    def parse(self, text: str) -> List[str]:
        """Parses compound sentences into sequential single commands."""
        if not text or not isinstance(text, str):
            return []

        raw = text.strip()
        if not raw:
            return []

        # Strip leading wake word prefix if present (e.g. "Jarvis, ", "Hey Jarvis, ", "Jarvis - ")
        # so "Jarvis, close Chrome" is treated as single command "close Chrome"
        clean = re.sub(r'^(hey|hello|hi|namaste|yo|good morning|good evening|good afternoon)?\s*(jarvis|goliya|buddy)\s*[,:\-]?\s*', '', raw, flags=re.IGNORECASE).strip()
        if not clean:
            clean = raw

        # Normalize delimiter separators: 'after that', 'then', 'also'
        norm = clean
        norm = re.sub(r'[,;\s]*\b(after that|then|also)\b', '|', norm, flags=re.IGNORECASE)

        # For commas, only split if followed by an action verb or system keyword
        # e.g., "open chrome, close notepad" -> split
        # e.g., "launch, anti-gravity" -> do NOT split
        def _comma_splitter(match):
            after = match.group(1).strip().lower()
            first_word = after.split()[0] if after.split() else ""
            if first_word in self.ACTION_VERBS or first_word in self.SYSTEM_KEYWORDS:
                return f"| {match.group(1)}"
            return f" {match.group(1)}"

        norm = re.sub(r',\s*([a-zA-Z0-9_\-]+)', _comma_splitter, norm)

        clauses = [c.strip(' ,;:') for c in norm.split('|') if c.strip(' ,;:')]
        final_commands = []

        for clause in clauses:
            if re.search(r'\band\b', clause, flags=re.IGNORECASE):
                sub_parts = [p.strip(' ,;:') for p in re.split(r'\band\b', clause, flags=re.IGNORECASE) if p.strip(' ,;:')]
                
                # Check if any sub-part contains actionable intent
                has_any_action = any(
                    any(w in self.ACTION_VERBS or w in self.SYSTEM_KEYWORDS for w in part.lower().split())
                    for part in sub_parts
                )

                if not has_any_action:
                    # Purely conversational conjunction (e.g., 'okay and please', 'yes and yes') -> do not split
                    final_commands.append(clause)
                    continue

                first_verb = None
                words = sub_parts[0].lower().split()
                if words and words[0] in self.ACTION_VERBS:
                    first_verb = words[0]

                for idx, part in enumerate(sub_parts):
                    part_words = part.lower().split()
                    has_action = any(w in self.ACTION_VERBS or w in self.SYSTEM_KEYWORDS for w in part_words)

                    if idx > 0 and first_verb and not has_action:
                        final_commands.append(f"{first_verb} {part}")
                    else:
                        final_commands.append(part)
            else:
                final_commands.append(clause)

        cleaned = [c for c in final_commands if len(c.strip()) > 1]
        logger.info(f"MultiCommandParser parsed '{text}' into {len(cleaned)} commands: {cleaned}")
        return cleaned if cleaned else [raw]

    def parse_structured(self, text: str) -> StructuredMultiAction:
        """Parses compound sentences into structured multi-action representations."""
        from core.intent_engine import intent_engine
        commands = self.parse(text)
        actions = []
        for cmd in commands:
            node = intent_engine.parse(cmd)
            actions.append({
                "type": node.get("intent"),
                "action": node.get("action"),
                "target": node.get("target"),
                "provider": node.get("provider", "google"),
                "query": node.get("query") or node.get("target", ""),
                "raw_command": cmd
            })
        return StructuredMultiAction(
            raw_text=text,
            commands=commands,
            actions=actions,
            is_multi=len(commands) > 1
        )

multi_command_parser = MultiCommandParser()
