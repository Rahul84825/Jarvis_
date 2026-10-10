import re

def sanitize_speech_text(text: str) -> str:
    """Converts raw LLM markdown, URLs, code blocks, bullet points, and technical
    artifacts into clean, natural spoken English prose suited for TTS synthesis.
    """
    if not text:
        return ""

    s = text.strip()

    # 1. Remove markdown code blocks and inline code
    s = re.sub(r'```[\s\S]*?```', '', s)
    s = re.sub(r'`([^`]+)`', r'\1', s)

    # 2. Convert markdown links [Text](URL) -> Text
    s = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', s)

    # 3. Strip standalone URLs (http://, https://, www.)
    s = re.sub(r'https?://\S+|www\.\S+', '', s)

    # 4. Remove markdown headers (#, ##, ###) and bold/italic asterisks
    s = re.sub(r'^#{1,6}\s+', '', s, flags=re.MULTILINE)
    s = re.sub(r'[*_]{1,3}([^*_]+)[*_]{1,3}', r'\1', s)

    # 5. Remove bullet markers and numbering at line starts (-, *, 1., 2.)
    s = re.sub(r'^\s*[-*+]\s+', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*\d+\.\s+', '', s, flags=re.MULTILINE)
    s = re.sub(r'[*_]+', '', s)

    # 6. Remove HTML tags
    s = re.sub(r'<[^>]+>', '', s)

    # 7. Convert technical characters & symbols into speakable phrases
    s = s.replace('&', ' and ')
    s = s.replace('@', ' at ')
    s = s.replace('%', ' percent')
    s = s.replace('$', ' dollars ')
    s = s.replace('€', ' euros ')
    s = s.replace('£', ' pounds ')
    s = s.replace('°C', ' degrees celsius')
    s = s.replace('°F', ' degrees fahrenheit')
    s = s.replace('°', ' degrees')

    # 8. Collapse multiple whitespace, newlines, and dangling punctuation
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'\s*([,\.!\?;:])\s*', r'\1 ', s)
    s = re.sub(r'\s+', ' ', s).strip()

    return s


def enforce_conversational_brevity(text: str, max_sentences: int = 2) -> str:
    """Ensures spoken response stays within natural spoken conversational length limits."""
    if not text:
        return ""

    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) <= max_sentences:
        return text

    return ' '.join(sentences[:max_sentences])
