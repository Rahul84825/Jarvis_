import re
import difflib
import logging
from typing import Tuple, List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.PronunciationManager")

class PronunciationManager:
    """Acoustic Pronunciation Intelligence & Variant Management for SANTRA.
    Handles Indian English accent adaptations, phonetic variations,
    negative confuser rejection, and context-safe STT normalization.
    """

    CANONICAL_NAME = "Santra"

    # Acoustically validated pronunciation variants for Indian English accent
    DEFAULT_VARIANTS = [
        "santra",
        "samtra",
        "suntra",
        "sumtra",
        "santhra",
        "san tra",
        "san-tra",
        "sandra",
        "santram",
        "shantra"
    ]

    # Legacy/Secondary aliases for backward compatibility
    LEGACY_ALIASES = [
        "jarvis",
        "hey jarvis",
        "goliya",
        "hey buddy"
    ]

    # Greeting prefixes commonly used before the wake word
    GREETING_PREFIXES = [
        "hey",
        "hello",
        "hi",
        "namaste",
        "yo",
        "good morning",
        "good evening",
        "good afternoon"
    ]

    # Negative confusers: words that sound superficially similar but MUST NOT trigger the assistant
    NEGATIVE_CONFUSERS = {
        "santa",
        "santa claus",
        "secret santa",
        "centre",
        "center",
        "sutra",
        "kama sutra",
        "yoga sutra",
        "mantra",
        "tantra",
        "yantra",
        "device",
        "garbage",
        "travis",
        "charles",
        "assistant",
        "disadvantage",
        "sample",
        "sent",
        "central",
        "century"
    }

    def __init__(self, custom_variants: Optional[List[str]] = None, min_confidence: float = 0.45):
        self.variants = list(custom_variants or self.DEFAULT_VARIANTS)
        self.min_confidence = min_confidence
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compiles regex patterns for high-throughput zero-latency matching."""
        # Clean variant list and sort longest first for greedy matching
        clean_variants = sorted(list(set(v.lower().strip() for v in self.variants + ["santra"])), key=len, reverse=True)
        # Escape for regex and allow hyphen/space flexibility
        variant_escaped = []
        for v in clean_variants:
            escaped = re.escape(v).replace(r"\ ", r"[\s\-]+").replace(r"\-", r"[\s\-]+")
            variant_escaped.append(escaped)
        variants_regex = "|".join(variant_escaped)

        greetings_regex = "|".join(re.escape(g) for g in self.GREETING_PREFIXES)

        # Pattern for assistant address at the beginning of an utterance
        # e.g., "Hey Santra, ...", "Samtra: ...", "Namaste Suntra ..."
        self.prefix_pattern = re.compile(
            rf"^\s*(?:({greetings_regex})\s+)?({variants_regex})(?:'s)?\b\s*[,:]?\s*(.*)$",
            re.IGNORECASE | re.DOTALL
        )

        # Pattern for wake word anywhere in a short candidate burst
        self.burst_pattern = re.compile(
            rf"\b(?:({greetings_regex})\s+)?({variants_regex})\b",
            re.IGNORECASE
        )

    def is_negative_confuser(self, text: str) -> bool:
        """Returns True if the text or phrase represents a known negative confuser word."""
        if not text:
            return False
        clean = text.lower().strip()
        # Direct exact match or word-bounded match
        if clean in self.NEGATIVE_CONFUSERS:
            return True
        for confuser in self.NEGATIVE_CONFUSERS:
            if re.search(rf"\b{re.escape(confuser)}\b", clean):
                # Ensure it's not a legitimate "Hey Santra" utterance that also mentions "center"
                # If the confuser is the sole or dominant token, flag it
                tokens = clean.split()
                if len(tokens) <= 3 and confuser in clean and not any(v in clean for v in ["santra", "samtra", "suntra"]):
                    return True
        return False

    def phonetic_similarity(self, candidate: str, target: str = "santra") -> float:
        """Calculates normalized phonetic/string similarity ratio."""
        c = re.sub(r"[^a-z]", "", candidate.lower())
        t = re.sub(r"[^a-z]", "", target.lower())
        if not c or not t:
            return 0.0
        return difflib.SequenceMatcher(None, c, t).ratio()

    def evaluate_candidate(self, text: str, confidence: float = 1.0) -> Tuple[bool, str, float]:
        """Evaluates whether candidate transcribed text contains a valid wake phrase.

        Args:
            text: Transcribed speech burst or keyword candidate.
            confidence: ASR segment confidence score (0.0 to 1.0).

        Returns:
            Tuple[bool, str, float]: (is_wake, detected_variant, effective_confidence)
        """
        if not text or not isinstance(text, str):
            return False, "", 0.0

        clean = text.lower().strip()

        # Reject negative confusers immediately
        if self.is_negative_confuser(clean):
            logger.debug(f"[PRONUNCIATION_REJECTED] Rejected negative confuser in: '{clean}'")
            return False, "", 0.0

        # Check prefix pattern
        m = self.prefix_pattern.match(clean)
        if m:
            detected_variant = m.group(2).lower()
            return True, detected_variant, max(confidence, 0.90)

        # Check burst pattern
        m_burst = self.burst_pattern.search(clean)
        if m_burst:
            detected_variant = m_burst.group(2).lower()
            return True, detected_variant, max(confidence, 0.85)

        # Check fuzzy phonetic similarity for single tokens or short phrases
        tokens = [re.sub(r"[^a-z]", "", tok) for tok in clean.split()]
        for tok in tokens:
            if len(tok) >= 4 and not self.is_negative_confuser(tok):
                for target_variant in self.variants:
                    sim = self.phonetic_similarity(tok, target_variant)
                    if sim >= 0.82 and confidence >= self.min_confidence:
                        logger.info(f"[PRONUNCIATION_FUZZY_MATCH] Token '{tok}' matched '{target_variant}' (sim={sim:.2f})")
                        return True, target_variant, float(sim * confidence)

        # Legacy backward-compatibility check
        for alias in self.LEGACY_ALIASES:
            if re.search(rf"\b{re.escape(alias)}\b", clean):
                return True, alias, confidence

        return False, "", 0.0

    def extract_wake_and_command(self, text: str) -> Tuple[bool, str, str]:
        """Extracts assistant address status, canonical name, and trailing command.

        Examples:
            "Santra, open Chrome" -> (True, "Santra", "open Chrome")
            "Hey Samtra, explain this code" -> (True, "Santra", "explain this code")
            "Open Chrome" -> (False, "", "Open Chrome")

        Returns:
            Tuple[bool, str, str]: (is_addressed, canonical_name, command)
        """
        if not text:
            return False, "", ""

        raw = text.strip()
        m = self.prefix_pattern.match(raw)
        if m:
            greeting = m.group(1) or ""
            variant = m.group(2) or ""
            trailing = (m.group(3) or "").strip()
            # Clean trailing punctuation
            trailing_clean = re.sub(r"^[,:\-\s]+", "", trailing).strip()
            return True, self.CANONICAL_NAME, trailing_clean

        # Check legacy patterns
        for alias in self.LEGACY_ALIASES:
            pat = rf"^\s*(?:(?:hey|hello|hi|namaste|yo)?\s*)?{re.escape(alias)}\b\s*[,:]?\s*(.*)$"
            m_leg = re.match(pat, raw, re.IGNORECASE)
            if m_leg:
                trailing = (m_leg.group(1) or "").strip()
                trailing_clean = re.sub(r"^[,:\-\s]+", "", trailing).strip()
                return True, self.CANONICAL_NAME, trailing_clean

        return False, "", raw

    def contextual_normalize(self, text: str) -> Tuple[str, Dict[str, Any]]:
        """Contextually normalizes assistant-addressing variants to canonical 'Santra'
        while preserving all subsequent command arguments, technical words, and code intact.

        Args:
            text: Raw speech transcription from STT.

        Returns:
            Tuple[str, dict]: (normalized_text, metadata)
        """
        if not text or not isinstance(text, str):
            return "", {"is_addressed": False, "canonical": "", "variant": ""}

        is_addressed, canonical_name, command = self.extract_wake_and_command(text)
        if is_addressed:
            # Reconstruct clean text: "Santra, <command>" or "Santra" if standalone greeting
            if command:
                normalized_text = f"Santra, {command}"
            else:
                normalized_text = "Santra"
            return normalized_text, {
                "is_addressed": True,
                "canonical": canonical_name,
                "command": command,
                "original": text
            }

        return text, {
            "is_addressed": False,
            "canonical": "",
            "command": text,
            "original": text
        }

# Global singleton instance
pronunciation_manager = PronunciationManager()
