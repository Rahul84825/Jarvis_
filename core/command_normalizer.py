import re
import logging

logger = logging.getLogger("Jarvis.CommandNormalizer")

class CommandNormalizer:
    """Normalizes natural language inputs into standardized canonical text before intent parsing.
    Strips wake words (Jarvis & aliases), polite phrases, filler words, punctuation, duplicate words, maps synonyms,
    and splits multi-command chains.
    """

    def __init__(self):
        logger.info("Initializing Command Normalizer.")

        # Wake word variations for Santra (with greetings and Indian accent variants)
        self.wake_words = [
            r"\b(?:hey|hello|hi|namaste|yo|good morning|good evening|good afternoon)?\s*(?:santra|samtra|suntra|sumtra|santhra|san[\-\s]+tra|sandra|santram|shantra)(?:'s)?\b",
            r"\b(?:hey|hello|hi|namaste|yo|good morning|good evening|good afternoon)?\s*jarvis(?:'s)?\b",
            r"\b(?:hey|hello|hi|namaste|yo|good morning|good evening|good afternoon)?\s*goliya(?:'s)?\b",
            r"\bhey\s+buddy\b",
            r"\b(santa|santana|dervis|derbis|darwis|carves|gerald|jal|jals|goli)\b"
        ]

        # Polite phrases to remove (longer/more specific phrases first)
        self.polite_phrases = [
            r"\bbe so kind as to\b",
            r"\bi would like you to\b",
            r"\bwould you please\b",
            r"\bcould you please\b",
            r"\bcan you please\b",
            r"\bwould you mind\b",
            r"\bi want you to\b",
            r"\bcould you\b",
            r"\bwould you\b",
            r"\bcan you\b",
            r"\bplease\b",
            r"\bkindly\b",
            r"\bfor me\b",
            r"\bfor us\b"
        ]

        # Conversational filler words
        self.filler_words = [
            r"\bum\b", r"\buh\b", r"\bso\b", r"\bthen\b", r"\bjust\b",
            r"\bnow\b", r"\bbasically\b", r"\bactually\b", r"\balways\b",
            r"^\s*and\b"
        ]

        # Synonym and phrase replacements (order matters: longer/more specific phrases first)
        self.phrase_mappings = [
            # System power & lock actions
            (r"\bput\s+(my|the)?\s*(pc|computer|laptop)\s+on\s+lock\b", "lock computer"),
            (r"\b(make|send)\s+(my|the)?\s*(pc|computer|laptop)\s+(to\s+)?sleep\b", "sleep computer"),
            (r"\b(lock)\s+(my|the)?\s*(pc|computer|screen|system|workstation)\b", "lock computer"),
            (r"\b(sleep)\s+(my|the)?\s*(pc|computer|system)\b", "sleep computer"),
            (r"\bput\s+(my|the)?\s*(pc|computer|laptop)\s+to\s+sleep\b", "sleep computer"),
            (r"\b(reboot|restart)\s+(my|the)?\s*(pc|computer|system)\b", "restart computer"),
            (r"\b(turn off|power off|shutdown)\s+(my|the)?\s*(pc|computer|laptop)\b", "shutdown computer"),

            # Screenshots
            (r"\b(take a picture of my screen|take picture of my screen|take a picture of screen|take picture of screen|take screen shot|take a screenshot|capture screen|screen capture|snapshot)\b", "take screenshot"),

            # Volume control
            (r"\b(turn up the volume|turn volume up|increase the volume|increase volume|raise volume|make it louder|volume up)\b", "volume up"),
            (r"\b(turn down the volume|turn volume down|decrease the volume|decrease volume|lower volume|make it quieter|volume down)\b", "volume down"),
            (r"\b(mute volume|mute audio|mute sound|silence audio)\b", "mute"),
            (r"\b(unmute volume|unmute audio|unmute sound)\b", "unmute"),

            # Assistant Startup & Standby Controls
            (r"\b(disable\s+startup|do\s+not\s+start\s+with\s+windows|don\s*'?\s*t\s+start\s+with\s+windows|remove\s+from\s+startup|turn\s+off\s+startup|disable\s+auto\s+start|auto\s+start\s+off)\b", "disable startup"),
            (r"\b(enable\s+startup|start\s+with\s+windows|start\s+when\s+windows\s+starts|launch\s+on\s+startup|turn\s+on\s+startup|enable\s+auto\s+start|auto\s+start\s+on)\b", "enable startup"),

            (r"\b(check startup|startup status|is startup enabled|check if startup is on)\b", "check startup"),
            (r"\b(go to standby|enter standby|standby mode|return to standby)\b", "go to standby"),
            (r"\b(stop listening|disable listening|turn off listening|mute microphone|mute mic)\b", "stop listening"),
            (r"\b(resume listening|enable listening|turn on listening|unmute microphone|unmute mic)\b", "resume listening"),
            (r"\b(let\s*'?\s*s\s+start|lets\s+start|start\s+session|let\s*'?\s*s\s+begin|lets\s+begin|begin\s+session|start\s+working|let\s*'?\s*s\s+get\s+started|lets\s+get\s+started)\b", "start session"),


            # Developer test commands
            (r"\b(run the tests|run tests|run project tests|run my tests)\b", "run tests"),

            # App launches
            (r"\b(bring up|launch|open up|opening)\b", "open"),
            (r"\bstart\b(?!\s+(?:session|working)\b)", "open"),
            (r"\brun\b(?!\s+(?:the\s+)?tests\b)", "open"),


            # App name aliases & fuzzy command shortcuts
            (r"\b(visual studio code|vs code|vieskund|vees code|viscode|vies kund)\b", "vscode"),
            (r"\b(?:open|launch|bring up|start)\s+code\b", "open vscode"),
            (r"\b(?:(?:the\s+)?(?:google\s+)?chrome(?:\s+browser)?|krone|crome)\b", "chrome"),
            (r"\b(?:the\s+)?brave(?:\s+browser)?\b", "brave"),
            (r"\b(you\s+tube|u\s+tube|utube)\b", "youtube"),
            (r"\bspottify\b", "spotify"),
            (r"\bsteem\b", "steam"),
            (r"\bfire fox\b", "firefox"),
            (r"\bmicrosoft edge|msedge\b", "edge"),
            (r"\b(calc|calcilator|kalculator)\b", "calculator"),
            (r"\bnote pad|notebook|not pad\b", "notepad"),
            (r"\bfile explorer|windows explorer|my computer|this pc\b", "explorer"),
            (r"\bdownloads folder|download folder\b", "downloads"),
            (r"\bwhatsapp web\b", "whatsapp"),

            # Capabilities & Help
            (r"\b(what\s+can\s+(?:you|jarvis)\s+do|what\s+can\s+do|what\s+do\s+you\s+do|what\s+are\s+your\s+capabilities|show\s+capabilities|show\s+me\s+your\s+capabilities|what\s+commands\s+do\s+you\s+know|how\s+can\s+you\s+help\s+me)\b", "what can you do"),

            # Common phonetic fixes
            (r"\b(test my microphone|test microphone|check my microphone|check microphone|microphone test)\b", "test microphone"),
            (r"\bclothes\b", "close"),
            (r"\bclothe\b", "close"),
            (r"\bmanimai swindle\b", "minimize window"),
            (r"\bmanimai\b", "minimize"),
            (r"\bminivized\b", "minimize"),
            (r"\bminimized\b", "minimize"),
            (r"\bleast open windows\b", "list open windows"),
            (r"\bleast windows\b", "list open windows"),
            (r"\bshow screen show\b", "show screenshots"),
            (r"\bshow screen shot\b", "show screenshots")
        ]

    SEARCH_PREFIX_REGEX = re.compile(
        r"^\s*(?:(?:hey|hello|hi|namaste|yo|good morning|good evening|good afternoon)?\s*(?:jarvis|goliya|buddy)(?:'s)?\s*[,:]?\s*)*(?:\b(?:please|kindly)\b\s*)*\bsearch\b\s*[,:]?\s*(.*)$",
        re.IGNORECASE | re.DOTALL
    )

    @classmethod
    def extract_explicit_search(cls, text: str):
        """Detects standalone 'search' in prefix position and extracts query.
        
        Returns:
            Tuple[bool, str]: (is_search, extracted_query)
        """
        if not text or not isinstance(text, str):
            return False, ""
        m = cls.SEARCH_PREFIX_REGEX.match(text)
        if m:
            query = (m.group(1) or "").strip()
            return True, query
        return False, ""

    @classmethod
    def is_explicit_search(cls, text: str) -> bool:
        """Returns True if input text starts with the explicit search command prefix."""
        return cls.extract_explicit_search(text)[0]

    @classmethod
    def extract_youtube_search(cls, text: str):
        """Extracts deterministic YouTube search query and target browser from natural language input.
        Returns:
            Tuple[bool, str, str]: (is_youtube_search, extracted_query, requested_browser)
        """
        if not text or not isinstance(text, str):
            return False, "", "default"

        raw = text.strip()
        w_pat = r"^\s*(?:(?:hey|hello|hi|namaste|yo|good morning|good evening|good afternoon)?\s*(?:jarvis|goliya|buddy)(?:'s)?\s*[,:]?\s*)*(?:\b(?:please|kindly)\b\s*)*"
        cleaned = re.sub(w_pat, "", raw, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"[\.\?\!,]+$", "", cleaned).strip()

        # Extract explicit browser if requested ('in chrome', 'using firefox')
        browser = "default"
        b_match = re.search(r"\b(?:in|using|with|on)\s+(chrome|chromium|edge|firefox|brave|opera)\s*$", cleaned, re.IGNORECASE)
        if b_match:
            browser = b_match.group(1).lower()
            cleaned = cleaned[:b_match.start()].strip()

        # Check YouTube search command patterns
        # 1. Open YouTube and search for ...
        m = re.match(r"^(?:open\s+(?:up\s+)?youtube\s+(?:and\s+|,)\s*(?:search\s*(?:for|about)?|find|look\s*up))\s*(.+)$", cleaned, re.IGNORECASE)
        if not m:
            # 2. Search (anything) on YouTube for/about ...
            m = re.match(r"^(?:search\s*(?:for\s+)?(?:anything\s+)?(?:on\s+youtube|in\s+youtube|youtube\s+for|youtube\s+about|youtube)\s*(?:for|about|this\s+topic:?|topic:?)?)\s*(.+)$", cleaned, re.IGNORECASE)
        if not m:
            # 3. Look up / Find ... on YouTube
            m = re.match(r"^(?:look\s*up|find(?:\s+me)?)\s+(.+?)\s+(?:on\s+youtube|in\s+youtube)$", cleaned, re.IGNORECASE)
        if not m:
            # 4. Find a video / videos / lectures / tutorials about ... (optional and open the results)
            m = re.match(r"^(?:find(?:\s+me)?|look\s*up|search\s+for)\s+(?:a\s+video|videos?|lectures?|tutorials?)\s+(?:about|on|for)\s+(.+?)(?:\s+(?:on\s+youtube|and\s+open(?:\s+the)?\s+results))?$", cleaned, re.IGNORECASE)
        if not m:
            # 5. YouTube search for ...
            m = re.match(r"^(?:youtube\s+search(?:\s+for|\s+about)?)\s*(.+)$", cleaned, re.IGNORECASE)

        if not m:
            return False, "", "default"

        q = m.group(1).strip()
        # Clean query artifacts
        q = re.sub(r"\s+and\s+open(?:\s+the)?\s+results\s*$", "", q, flags=re.IGNORECASE).strip()
        q = re.sub(r"^(?:this\s+topic:?|topic:?)\s*", "", q, flags=re.IGNORECASE).strip()
        q = re.sub(r"^(?:for|about)\s+", "", q, flags=re.IGNORECASE).strip()
        q = re.sub(r"^(?:(?:a\s+)?videos?\s+(?:about|on|for)|(?:tutorials?|lectures?)\s+(?:about|on|for))\s*", "", q, flags=re.IGNORECASE).strip()
        q = re.sub(r"[\.\?\!,]+$", "", q).strip()

        return True, q, browser

    @classmethod
    def is_youtube_search(cls, text: str) -> bool:
        """Returns True if text is a YouTube search request."""
        return cls.extract_youtube_search(text)[0]

    def split_chained_commands(self, text: str) -> list[str]:
        """Splits multi-command natural speech into a sequence of individual command strings using MultiCommandParser.

        Examples:
            "Open Chrome and VS Code" -> ["open chrome", "open vscode"]
            "Close Calculator and Volume Up" -> ["close calculator", "volume up"]
            "Open Chrome, then open GitHub and increase volume" -> ["open chrome", "open github", "increase volume"]
        """
        if self.is_explicit_search(text) or self.is_youtube_search(text):
            return [text]

        # Do not split research and explain or AI reasoning compound requests
        clean_check = text.lower().strip()
        if re.search(r"\b(?:find|search)\b.*\band\b\s*(?:explain|summarize|tell)\b", clean_check, re.IGNORECASE):
            return [text]
        if re.search(r"\b(?:explain|solve|write|debug|compare)\b.*\band\b", clean_check, re.IGNORECASE):
            return [text]
        if re.search(r"\b(?:ask|tell|have)\s+(?:nvidia|nemotron)\b", clean_check, re.IGNORECASE):
            return [text]

        from core.multi_command_parser import multi_command_parser
        raw_commands = multi_command_parser.parse(text)
        result_commands = []
        for cmd in raw_commands:
            norm_res = self.normalize(cmd)
            norm_cmd = norm_res["normalized"] or cmd
            result_commands.append(norm_cmd)
        return result_commands if result_commands else [text]

    def extract_assistant_address(self, text: str) -> tuple[bool, str, str]:
        """Extracts whether Santra (or a validated variant) was addressed at the start of speech.

        Returns:
            tuple[bool, str, str]: (is_addressed, canonical_name, command)
        """
        from core.pronunciation_manager import pronunciation_manager
        return pronunciation_manager.extract_wake_and_command(text)

    def normalize(self, text: str) -> dict:
        """Normalizes user speech transcript.

        Args:
            text: Raw speech transcript string from Whisper or user input.

        Returns:
            Dictionary containing:
                - 'normalized': Standardized clean command string.
                - 'raw': Original raw input string.
                - 'removed_words': List of stripped filler/polite/wake words.
        """
        if not text or not isinstance(text, str):
            return {"normalized": "", "raw": text or "", "removed_words": []}

        # Explicit search shortcut: preserve query's casing, technical terms, and punctuation
        is_search, extracted_query = self.extract_explicit_search(text)
        if is_search:
            normalized_cmd = f"search {extracted_query}".strip()
            return {
                "normalized": normalized_cmd,
                "raw": text,
                "removed_words": ["jarvis", "search_prefix"],
                "is_explicit_search": True,
                "search_query": extracted_query
            }

        # Extract domain candidates before rewriting to preserve structured domain tokens
        from core.os.domain_manager import domain_manager
        preserved_domains = domain_manager.extract_domain_candidates(text)

        original_text = text
        normalized = text.lower().strip()

        # 1. Clean punctuation & special chars (preserve dashes for apps/urls and math operators)
        normalized = re.sub(r"[^\w\s\.\-\+\*\/\%\^]", " ", normalized)

        # 2. Strip wake words
        removed = []
        for pattern in self.wake_words:
            matches = re.findall(pattern, normalized, re.IGNORECASE)
            if matches:
                removed.extend([m if isinstance(m, str) else m[0] for m in matches])
            normalized = re.sub(pattern, " ", normalized, flags=re.IGNORECASE)

        # 3. Strip polite phrases (only if string contains other actionable words and is not a capability query)
        is_capability_query = bool(re.search(r"\b(what\s+can\s+(?:you|jarvis)?\s*do|what\s+are\s+your\s+capabilities|what\s+commands\s+do\s+you\s+know|how\s+can\s+you\s+help|what\s+can\s+do)\b", normalized, re.IGNORECASE))
        words_check = normalized.split()
        if len(words_check) > 1 and not is_capability_query:
            for pattern in self.polite_phrases:
                if re.search(pattern, normalized, re.IGNORECASE):
                    # Only strip if remaining string is not empty
                    test_sub = re.sub(pattern, " ", normalized, flags=re.IGNORECASE).strip()
                    if test_sub:
                        removed.append(pattern.replace(r"\b", "").strip())
                        normalized = test_sub

        # 4. Strip filler words (only if string contains other words and is not a capability query)
        words_check = normalized.split()
        if len(words_check) > 1 and not is_capability_query:
            for pattern in self.filler_words:
                if re.search(pattern, normalized, re.IGNORECASE):
                    test_sub = re.sub(pattern, " ", normalized, flags=re.IGNORECASE).strip()
                    if test_sub:
                        removed.append(pattern.replace(r"\b", "").strip())
                        normalized = test_sub

        # 5. Apply phrase mappings and synonym replacements
        for pattern, replacement in self.phrase_mappings:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        # 6. Apply single-token fuzzy shortcuts (e.g. standalone "chrome" -> "open chrome")
        single_token_shortcuts = {
            "chrome": "open chrome",
            "vscode": "open vscode",
            "vs": "open vscode",
            "screenshot": "take screenshot",
            "downloads": "open downloads",
            "lock": "lock computer"
        }
        clean_words = normalized.split()
        if len(clean_words) == 1 and clean_words[0] in single_token_shortcuts:
            normalized = single_token_shortcuts[clean_words[0]]

        # 7. Deduplicate repeated consecutive words and strip isolated punctuation
        words = normalized.split()
        dedup_words = []
        for word in words:
            # Strip trailing punctuation while safely preserving domains and decimal numbers
            cleaned_word = word
            if not re.match(r'^\d+\.\d+$', cleaned_word):
                # If word has domain ending followed by punctuation, strip trailing punctuation only
                cleaned_word = re.sub(r'[\.\,\?\!\;:]+$', '', cleaned_word)
            if cleaned_word and (not dedup_words or dedup_words[-1] != cleaned_word):
                dedup_words.append(cleaned_word)

        final_normalized = " ".join(dedup_words).strip()
        final_normalized = re.sub(r"\s*[\.\,\?\!]+$", "", final_normalized).strip()
        
        # If stripping wake words emptied a standalone greeting (e.g. "Namaste Goliya", "Hey buddy"), preserve greeting token
        if not final_normalized and original_text:
            clean_raw = original_text.lower().replace("goliya", "").replace("jarvis", "").strip()
            clean_raw = re.sub(r"\s*[\.\,\?\!]+$", "", clean_raw).strip()
            final_normalized = clean_raw if clean_raw else original_text.lower().strip()

        logger.debug(f"[DOMAIN_TRACE][NORMALIZER] input='{original_text}', preserved_domains={preserved_domains}, normalized='{final_normalized}'")
        logger.debug(f"Normalized: '{original_text}' -> '{final_normalized}' (Removed: {removed})")

        return {
            "normalized": final_normalized,
            "raw": original_text,
            "removed_words": [r for r in removed if r],
            "confidence": 1.0,
            "meaningful": bool(final_normalized)
        }
