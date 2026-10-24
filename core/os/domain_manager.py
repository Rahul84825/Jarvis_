import re
import urllib.parse
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set

logger = logging.getLogger("Jarvis.DomainManager")

# RFC 1123 / RFC 3986 Hostname validation regex
HOSTNAME_REGEX = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,10}$",
    re.IGNORECASE
)

# Common Top-Level Domains (TLDs) for domain extraction
KNOWN_TLDS = {
    "com", "org", "net", "at", "to", "tv", "io", "ai", "co", "me", "dev", "app",
    "edu", "gov", "in", "uk", "ca", "de", "jp", "fr", "au", "ch", "ru", "live", "site"
}

@dataclass
class DomainEntry:
    """Structured representation of a recognized website domain."""
    canonical_domain: str            # e.g. "hianime.at"
    site_name: str                   # e.g. "HiAnime"
    speech_aliases: List[str]        # Phonetic variants e.g. ["high-anime", "high anime", "hi anime"]
    navigation_hostname: str         # Actual hostname to navigate to e.g. "hianime.at"
    default_scheme: str = "https"
    verified: bool = True

@dataclass
class DomainResolutionResult:
    """Outcome of resolving a speech or text domain candidate."""
    status: str                      # "EXACT_MATCH" | "CONFIRMATION_REQUIRED" | "VALID_ARBITRARY" | "INVALID"
    hostname: str                    # Target hostname
    canonical_hostname: Optional[str] = None
    site_name: Optional[str] = None
    clarification_prompt: Optional[str] = None
    confidence: float = 1.0
    error_reason: Optional[str] = None

    @property
    def is_navigable(self) -> bool:
        return self.status in ["EXACT_MATCH", "VALID_ARBITRARY"]

    @property
    def requires_clarification(self) -> bool:
        return self.status in ["CONFIRMATION_REQUIRED", "INVALID"]


class DomainManager:
    """Manages domain preservation, speech-to-URL accuracy, contextual vocabulary biasing,
    and confidence-aware domain verification.
    """

    def __init__(self):
        self._registry: Dict[str, DomainEntry] = {}
        self._alias_to_canonicals: Dict[str, List[str]] = {}
        self._load_default_registry()

    def _load_default_registry(self):
        """Initializes canonical domain entries, keeping canonical domain, site name,
        speech aliases, and navigation hostname cleanly separated.
        """
        entries = [
            DomainEntry(
                canonical_domain="hianime.at",
                site_name="HiAnime",
                speech_aliases=["high-anime", "high anime", "hi anime", "hianime"],
                navigation_hostname="hianime.at"
            ),
            DomainEntry(
                canonical_domain="hianime.to",
                site_name="HiAnime",
                speech_aliases=["high-anime", "high anime", "hi anime", "hianime"],
                navigation_hostname="hianime.to"
            ),
            DomainEntry(
                canonical_domain="youtube.com",
                site_name="YouTube",
                speech_aliases=["you tube", "u tube", "utube"],
                navigation_hostname="www.youtube.com"
            ),
            DomainEntry(
                canonical_domain="github.com",
                site_name="GitHub",
                speech_aliases=["git hub", "get hub"],
                navigation_hostname="github.com"
            ),
            DomainEntry(
                canonical_domain="google.com",
                site_name="Google",
                speech_aliases=["google"],
                navigation_hostname="www.google.com"
            ),
            DomainEntry(
                canonical_domain="reddit.com",
                site_name="Reddit",
                speech_aliases=["read it"],
                navigation_hostname="www.reddit.com"
            ),
            DomainEntry(
                canonical_domain="wikipedia.org",
                site_name="Wikipedia",
                speech_aliases=["wiki pedia"],
                navigation_hostname="www.wikipedia.org"
            ),
        ]
        for entry in entries:
            self.register_domain(entry)

    def register_domain(self, entry: DomainEntry):
        """Registers a domain entry into canonical registry and speech alias index."""
        canon_key = entry.canonical_domain.lower()
        self._registry[canon_key] = entry
        for alias in entry.speech_aliases:
            a_clean = alias.lower()
            if a_clean not in self._alias_to_canonicals:
                self._alias_to_canonicals[a_clean] = []
            if canon_key not in self._alias_to_canonicals[a_clean]:
                self._alias_to_canonicals[a_clean].append(canon_key)

    def get_vocabulary_prompt(self) -> str:
        """Returns vocabulary prompt hints for Faster-Whisper initial_prompt biasing."""
        vocab_tokens = []
        for entry in self._registry.values():
            if entry.canonical_domain not in vocab_tokens:
                vocab_tokens.append(entry.canonical_domain)
            if entry.site_name not in vocab_tokens:
                vocab_tokens.append(entry.site_name)
        return ", ".join(vocab_tokens)

    def get_hotwords_string(self) -> str:
        """Returns hotwords string for Faster-Whisper decoder vocabulary biasing."""
        return " ".join([e.canonical_domain for e in self._registry.values()])

    def extract_domain_candidates(self, text: str) -> List[str]:
        """Extracts valid or potential domain tokens from text (e.g. 'hianime.at', 'example.com')."""
        if not text:
            return []
        # Pattern captures: scheme://domain or domain.tld (with optional port/path)
        pattern = r"\b(?:https?://)?([a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-\.]{2,10}(?::\d+)?)\b"
        matches = re.findall(pattern, text, re.IGNORECASE)
        # Filter and strip trailing punctuation
        results = []
        for m in matches:
            clean_m = re.sub(r"[\.\,\?\!\;:]+$", "", m).strip()
            if "." in clean_m:
                results.append(clean_m)
        return results

    def validate_domain(self, domain_candidate: str) -> Tuple[bool, str, Optional[str]]:
        """Validates a domain string against RFC hostname rules.
        
        Returns:
            Tuple[bool, str, Optional[str]]: (is_valid, cleaned_hostname, error_reason)
        """
        if not domain_candidate or not isinstance(domain_candidate, str):
            return False, "", "Empty or non-string domain candidate"

        # Strip schemes and paths if present
        raw = domain_candidate.strip()
        if "://" in raw:
            try:
                parsed = urllib.parse.urlsplit(raw)
                hostname = parsed.hostname or ""
            except Exception:
                return False, raw, "Malformed URL structure"
        else:
            hostname = raw.split("/")[0].split("?")[0].split("#")[0].strip()

        # Strip trailing punctuation
        hostname = re.sub(r"[\.\,\?\!\;:]+$", "", hostname).strip().lower()

        if not hostname:
            return False, "", "Empty hostname after normalization"

        if ".." in hostname:
            return False, hostname, "Consecutive dots in hostname"

        if hostname.startswith(".") or hostname.endswith(".") or hostname.startswith("-") or hostname.endswith("-"):
            return False, hostname, "Hostname cannot start or end with a dot or hyphen"

        parts = hostname.split(".")
        if len(parts) < 2:
            return False, hostname, "Missing top-level domain extension"

        tld = parts[-1]
        if not tld.isalpha() or len(tld) < 2 or len(tld) > 10:
            return False, hostname, f"Invalid top-level domain '{tld}'"

        if not HOSTNAME_REGEX.match(hostname):
            return False, hostname, "Hostname characters violate RFC 1123"

        return True, hostname, None

    def resolve_domain(
        self,
        candidate_domain: str,
        confidence: float = 1.0,
        is_spoken: bool = True
    ) -> DomainResolutionResult:
        """Confidence-aware domain resolution adhering to strict non-guessing policies:
        - Exact matches: navigate directly.
        - Valid arbitrary domains: navigate directly preserving exact hostname.
        - Speech alias confusion (e.g. 'high-anime.at' for 'hianime.at') with uncertainty:
          ask confirmation rather than silently guessing or navigating to wrong domain.
        - Invalid domains: ask safe, actionable clarification.
        """
        is_valid, cleaned_host, err = self.validate_domain(candidate_domain)
        if not is_valid:
            logger.info(f"[DOMAIN_TRACE][DOMAIN_RESOLUTION] candidate='{candidate_domain}', status='INVALID', reason='{err}'")
            return DomainResolutionResult(
                status="INVALID",
                hostname=cleaned_host or candidate_domain,
                clarification_prompt=f"That website domain seems incomplete or invalid ('{candidate_domain}'). Which website would you like me to open?",
                confidence=confidence,
                error_reason=err
            )

        # 1. Exact match in canonical registry
        if cleaned_host in self._registry:
            entry = self._registry[cleaned_host]
            logger.info(f"[DOMAIN_TRACE][DOMAIN_RESOLUTION] candidate='{candidate_domain}', status='EXACT_MATCH', hostname='{entry.navigation_hostname}'")
            return DomainResolutionResult(
                status="EXACT_MATCH",
                hostname=entry.navigation_hostname,
                canonical_hostname=entry.canonical_domain,
                site_name=entry.site_name,
                confidence=confidence
            )

        # 2. Check if candidate hostname base is a speech-recognition alias of a known site
        # e.g. candidate is 'high-anime.at', base is 'high-anime', tld is 'at'
        parts = cleaned_host.split(".")
        base_name = parts[0]
        tld = parts[-1]

        # Check if base_name is an alias of a known site with matching TLD
        if base_name in self._alias_to_canonicals:
            for canon_match_key in self._alias_to_canonicals[base_name]:
                canon_entry = self._registry.get(canon_match_key)
                if canon_entry:
                    canon_tld = canon_entry.canonical_domain.split(".")[-1]
                    # If TLD matches (e.g. .at) but the hostname was transcribed as alias (e.g. 'high-anime')
                    if tld == canon_tld:
                        # Require confirmation if low confidence or spoken ambiguity exists
                        logger.info(f"[DOMAIN_TRACE][DOMAIN_RESOLUTION] candidate='{candidate_domain}', status='CONFIRMATION_REQUIRED', canonical='{canon_entry.canonical_domain}', alias='{base_name}'")
                        return DomainResolutionResult(
                            status="CONFIRMATION_REQUIRED",
                            hostname=cleaned_host,
                            canonical_hostname=canon_entry.canonical_domain,
                            site_name=canon_entry.site_name,
                            clarification_prompt=f"Did you mean '{canon_entry.canonical_domain}' or '{cleaned_host}'?",
                            confidence=confidence
                        )

        # 3. Valid arbitrary domain (e.g. 'example.com', 'example.org', or explicitly requested custom domain)
        # NEVER invent or replace with a different domain!
        logger.info(f"[DOMAIN_TRACE][DOMAIN_RESOLUTION] candidate='{candidate_domain}', status='VALID_ARBITRARY', hostname='{cleaned_host}'")
        return DomainResolutionResult(
            status="VALID_ARBITRARY",
            hostname=cleaned_host,
            confidence=confidence
        )

    def construct_validated_url(self, hostname: str, scheme: str = "https") -> Tuple[bool, str, Optional[str]]:
        """Constructs a validated URL using standard urllib.parse without arbitrary rewriting."""
        is_valid, clean_host, err = self.validate_domain(hostname)
        if not is_valid:
            return False, "", err

        parsed = urllib.parse.urlsplit(f"{scheme}://{clean_host}")
        constructed_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))
        logger.info(f"[DOMAIN_TRACE][URL_CONSTRUCT] input_hostname='{hostname}', validated_url='{constructed_url}'")
        return True, constructed_url, None


# Global singleton instance
domain_manager = DomainManager()
