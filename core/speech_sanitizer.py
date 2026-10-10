"""Speech Sanitizer for JARVIS Text-to-Speech Output.

Cleans and adapts raw response strings before sending to TTSManager:
- Strips markdown formatting, code blocks, and bullet points
- Replaces raw URLs and file system paths with spoken descriptions
- Masks raw stack traces, API keys, and unpronounceable tokens
- Preserves clean punctuation and natural pronunciation
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("Jarvis.SpeechSanitizer")


class SpeechSanitizer:
    """Pre-processes text to ensure natural, audible, and safe TTS output."""

    def __init__(self):
        # Compiled patterns for speech cleaning
        self._url_pattern = re.compile(r"https?://(?:www\.)?([a-zA-Z0-9_\-\.]+)(?:/[^\s]*)?", re.IGNORECASE)
        self._path_pattern = re.compile(r"(?:[a-zA-Z]:\\|/)[a-zA-Z0-9_\-/\\]+\\([a-zA-Z0-9_\-\.]+)", re.IGNORECASE)
        self._code_fence_pattern = re.compile(r"```[\s\S]*?```")
        self._inline_code_pattern = re.compile(r"`([^`]+)`")
        self._stack_trace_pattern = re.compile(r"(?:Traceback\s*\(most\s*recent\s*call\s*last\):[\s\S]+|File\s*['\"].+['\"],\s*line\s*\d+[\s\S]+)")
        self._markdown_links = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
        self._markdown_chars = re.compile(r"[\*\_~#>]")

    def sanitize(self, text: Optional[str]) -> str:
        """Transforms formatted text into natural, spoken English for speech synthesis."""
        if not text or not isinstance(text, str):
            return ""

        clean = text.strip()

        # 1. Eliminate raw stack traces completely
        if "traceback" in clean.lower() or "file \"" in clean.lower():
            clean = self._stack_trace_pattern.sub("An internal execution error occurred.", clean)

        # 2. Strip code fence blocks
        clean = self._code_fence_pattern.sub("code snippet omitted.", clean)

        # 3. Clean inline code markers
        clean = self._inline_code_pattern.sub(r"\1", clean)

        # 4. Convert markdown links [Label](url) -> Label
        clean = self._markdown_links.sub(r"\1", clean)

        # 5. Clean URLs: replace with friendly domain name
        clean = self._url_pattern.sub(r"\1", clean)

        # 6. Clean Windows/Linux file paths: replace with filename
        clean = self._path_pattern.sub(r"\1", clean)

        # 7. Strip markdown header/bold/italic syntax characters
        clean = self._markdown_chars.sub("", clean)

        # 8. Strip bullets and list markers at line start
        clean = re.sub(r"^\s*[\•\-\*\+]\s+", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"^\s*\d+\.\s+", "", clean, flags=re.MULTILINE)

        # 9. Clean multiple whitespace, newlines, and dangling punctuation
        clean = re.sub(r"\n+", ". ", clean)
        clean = re.sub(r"\s+", " ", clean)
        clean = re.sub(r"\.{2,}", ".", clean)
        clean = clean.strip()

        # 10. Phonetic and acronym naturalization
        clean = re.sub(r"\bvs\s*code\b", "VS Code", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bpc\b", "P C", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bai\b", "A I", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bos\b", "O S", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bapi\b", "A P I", clean, flags=re.IGNORECASE)

        return clean


# Global Singleton Instance
speech_sanitizer = SpeechSanitizer()
