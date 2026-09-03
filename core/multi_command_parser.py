import re
import logging
from typing import List

logger = logging.getLogger("Jarvis.MultiCommandParser")

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

        # Normalize delimiter separators: 'after that', 'then', 'also', ','
        norm = raw
        norm = re.sub(r'\b(after that|then|also)\b', '|', norm, flags=re.IGNORECASE)
        norm = norm.replace(',', '|')

        clauses = [c.strip() for c in norm.split('|') if c.strip()]
        final_commands = []

        for clause in clauses:
            if re.search(r'\band\b', clause, flags=re.IGNORECASE):
                sub_parts = [p.strip() for p in re.split(r'\band\b', clause, flags=re.IGNORECASE) if p.strip()]

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

multi_command_parser = MultiCommandParser()
