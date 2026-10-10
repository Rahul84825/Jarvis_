import re
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

logger = logging.getLogger("Jarvis.TranscriptValidator")

class ValidationStatus:
    VALID = "VALID"
    EMPTY = "EMPTY"
    TOO_SHORT = "TOO_SHORT"
    REPETITIVE_HALLUCINATION = "REPETITIVE_HALLUCINATION"
    LIKELY_HALLUCINATION = "LIKELY_HALLUCINATION"

@dataclass
class ValidationResult:
    """Standardized validation result for Whisper speech transcripts."""
    raw_text: str
    cleaned_text: str
    status: str  # VALID, EMPTY, TOO_SHORT, REPETITIVE_HALLUCINATION, LIKELY_HALLUCINATION
    is_valid: bool
    is_command_candidate: bool
    repetition_detected: bool
    repetition_ratio: float = 0.0
    original_repetition_count: int = 1
    confidence: float = 1.0
    is_hallucination_compressed: bool = False

class TranscriptValidator:
    """Validates Whisper transcription outputs, detects hallucinations,
    compresses repetitive loops, and filters empty/noise artifacts.
    """

    KNOWN_CONVERSATIONAL_WORDS = {
        "okay", "ok", "yes", "yeah", "yup", "no", "nope", "please", "thanks", 
        "thank you", "bye", "goodbye", "hello", "hi", "hey", "what", "oh",
        "jarvis", "goliya", "buddy"
    }

    ACTION_VERBS = {
        "open", "launch", "start", "close", "exit", "terminate",
        "lock", "sleep", "restart", "shutdown", "reboot", "turn",
        "increase", "decrease", "mute", "unmute", "take",
        "show", "list", "search", "find", "minimize", "maximize", "restore",
        "run", "calculate", "solve", "play", "pause", "resume"
    }

    def __init__(self):
        logger.info("Initializing Jarvis Transcript Validator & Hallucination Filter.")

    def validate(self, raw_text: Optional[str], confidence: float = 1.0, audio_duration: float = 0.0) -> ValidationResult:
        """Evaluates raw Whisper transcript text and returns a ValidationResult."""
        if raw_text is None:
            return ValidationResult(
                raw_text="",
                cleaned_text="",
                status="EMPTY",
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=False
            )

        text = raw_text.strip()
        if not text:
            return ValidationResult(
                raw_text=raw_text,
                cleaned_text="",
                status="EMPTY",
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=False
            )

        # Check single non-word characters, pure punctuation or isolated 1-char noise
        alphanumeric = re.sub(r'[^\w\s]', '', text).strip()
        if not alphanumeric or len(alphanumeric) <= 1:
            return ValidationResult(
                raw_text=raw_text,
                cleaned_text="",
                status=ValidationStatus.TOO_SHORT,
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=False
            )

        # 1. Repetitive Loop & Hallucination Analysis
        cleaned_text, rep_detected, rep_count, rep_ratio = self._analyze_and_compress_repetitions(text)

        # 2. Check for Hallucination Signatures (e.g. 5+ repetitions of short words)
        status = "VALID"
        if rep_detected and rep_count >= 4 and len(cleaned_text.split()) <= 2:
            status = "REPETITIVE_HALLUCINATION"
        elif rep_detected:
            status = "VALID"

        # 3. Determine if candidate looks like an actionable command
        words = cleaned_text.lower().split()
        first_word = words[0] if words else ""
        has_action = (
            first_word in self.ACTION_VERBS or
            any(w in self.ACTION_VERBS for w in words[:3]) or
            any(kw in cleaned_text.lower() for kw in ["volume", "screenshot", "lock", "sleep", "restart", "shutdown", "tab", "window"])
        )

        logger.debug(f"[VALIDATOR] Raw: '{raw_text}' -> Cleaned: '{cleaned_text}' | Status: {status} | RepCount: {rep_count} | CommandCandidate: {has_action}")

        return ValidationResult(
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            status=status,
            is_valid=True,
            is_command_candidate=has_action,
            repetition_detected=rep_detected,
            repetition_ratio=rep_ratio,
            original_repetition_count=rep_count,
            confidence=confidence,
            is_hallucination_compressed=rep_detected
        )

    def _analyze_and_compress_repetitions(self, text: str) -> (str, bool, int, float):
        """Detects word or phrase-level looping repetitions (e.g., 'okay okay okay', 'oh please oh please')
        and compresses them into a single clean semantic representation.
        """
        # Split on sentence/phrase punctuation: commas, periods, exclamation marks, question marks
        raw_phrases = [p.strip() for p in re.split(r'[,.!?]+', text) if p.strip()]
        if len(raw_phrases) >= 2:
            normalized_phrases = [re.sub(r'[^\w\s]', '', p).lower().strip() for p in raw_phrases if p.strip()]
            # If all sub-phrases are identical
            if normalized_phrases and all(p == normalized_phrases[0] for p in normalized_phrases):
                rep_count = len(normalized_phrases)
                compressed = raw_phrases[0]
                ratio = rep_count / float(len(text.split()))
                return compressed, True, rep_count, ratio

        # Word-level repetition check (e.g. "okay okay okay okay", "bye bye bye")
        words = text.split()
        if len(words) >= 3:
            norm_words = [re.sub(r'[^\w]', '', w).lower() for w in words]
            # Check 1-word loop
            if all(w == norm_words[0] for w in norm_words):
                return words[0].strip(' ,.!?'), True, len(words), 1.0

            # Check 2-word loop (e.g. "oh please oh please oh please")
            if len(norm_words) >= 4 and len(norm_words) % 2 == 0:
                pattern = norm_words[:2]
                all_match = True
                for i in range(0, len(norm_words), 2):
                    if norm_words[i:i+2] != pattern:
                        all_match = False
                        break
                if all_match:
                    compressed_phrase = " ".join(words[:2]).strip(' ,.!?')
                    rep_count = len(norm_words) // 2
                    return compressed_phrase, True, rep_count, 1.0

            # Check multi-word phrase loop (e.g., "What do you want to do? What do you want to do?")
            half = len(words) // 2
            p1 = " ".join(norm_words[:half])
            p2 = " ".join(norm_words[half:half*2])
            if p1 == p2 and half >= 2:
                compressed_phrase = " ".join(words[:half]).strip(' ,.!?')
                return compressed_phrase, True, 2, 0.5

        return text, False, 1, 0.0

transcript_validator = TranscriptValidator()
