"""Universal Natural-Language Browser Intent Parser for JARVIS.
Converts free-form spoken and typed commands into structured, validated BrowserIntent plans.
Distinguishes explicit URLs, website searches, general web searches, in-page searches,
application/prompt interactions, tab management, and conversational follow-ups.
"""

import re
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
import logging
from core.os.domain_manager import domain_manager

logger = logging.getLogger("Jarvis.BrowserIntent")


class BrowserActionType(str, Enum):
    OPEN_URL = "open_url"
    SEARCH_WEBSITE = "search_website"
    SEARCH_WEB = "search_web"
    SEARCH_PAGE = "search_page"
    INTERACT_PROMPT = "interact_prompt"
    BROWSER_CONTROL = "browser_control"
    OPEN_BROWSER = "open_browser"
    CLARIFICATION_NEEDED = "clarification_needed"
    UNKNOWN = "unknown"


class SearchScope(str, Enum):
    WEBSITE = "website"
    CURRENT_PAGE = "current_page"
    WEB_SEARCH = "web_search"
    APPLICATION = "application"


class TabPreference(str, Enum):
    CURRENT_TAB = "current_tab"
    NEW_TAB = "new_tab"
    DEFAULT = "default"


@dataclass
class BrowserIntent:
    """Structured action plan for browser automation operations."""
    action_type: BrowserActionType
    target_browser: str = "chrome"
    url: Optional[str] = None
    site_name: Optional[str] = None
    domain: Optional[str] = None
    search_query: str = ""
    prompt_query: str = ""
    search_scope: SearchScope = SearchScope.WEB_SEARCH
    tab_preference: TabPreference = TabPreference.DEFAULT
    input_purpose: str = "search_box"  # search_box, prompt_box, find_in_page, address_bar
    submit: bool = True
    requires_confirmation: bool = False
    confirmation_reason: Optional[str] = None
    clarification_prompt: Optional[str] = None
    verification_method: str = "cdp_or_title"
    confidence: float = 1.0
    raw_text: str = ""
    normalized_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        if self.action_type == BrowserActionType.OPEN_BROWSER:
            return {
                "intent": "open_app",
                "action": "open",
                "target": self.target_browser,
                "app_name": self.target_browser,
                "action_type": "open_browser",
                "confidence": 1.0,
                "raw_text": self.raw_text,
                "normalized_text": self.normalized_text,
                "metadata": {"launch_only": True}
            }

        if self.action_type == BrowserActionType.SEARCH_WEB or (self.action_type == BrowserActionType.SEARCH_WEBSITE and self.site_name in ["google", "youtube"]):
            prov = "youtube" if self.site_name == "youtube" else "google"
            browser_target = self.target_browser if self.metadata.get("explicit_browser") else "default"
            return {
                "intent": "web_search",
                "action": "search",
                "action_type": self.action_type.value,
                "provider": prov,
                "browser": browser_target,
                "target": self.search_query,
                "query": self.search_query,
                "site_name": self.site_name,
                "empty_query": not bool(self.search_query),
                "confidence": 1.0,
                "raw_text": self.raw_text,
                "is_explicit_search": True
            }

        return {
            "intent": "browser_action",
            "action_type": self.action_type.value,
            "action": self.action_type.value,
            "target_browser": self.target_browser,
            "browser": self.target_browser,
            "url": self.url,
            "site_name": self.site_name,
            "target": self.site_name or self.domain or self.search_query,
            "domain": self.domain,
            "search_query": self.search_query,
            "query": self.search_query or self.prompt_query,
            "prompt_query": self.prompt_query,
            "search_scope": self.search_scope.value,
            "tab_preference": self.tab_preference.value,
            "input_purpose": self.input_purpose,
            "submit": self.submit,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_reason": self.confirmation_reason,
            "clarification_prompt": self.clarification_prompt,
            "verification_method": self.verification_method,
            "confidence": self.confidence,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "metadata": self.metadata,
        }


class BrowserIntentParser:
    """Natural-language intent parser resolving spoken/typed browser requests into BrowserIntents."""

    # Common TLDs for spoken and typed domain detection
    KNOWN_TLDS = {
        "com", "org", "net", "at", "to", "tv", "io", "ai", "co", "me", "dev", "app",
        "edu", "gov", "in", "uk", "ca", "de", "jp", "fr", "au", "ch", "ru", "live", "site"
    }

    # Spoken domain representations: "dot at" -> ".at", "dot com" -> ".com", etc.
    SPOKEN_DOT_PATTERN = re.compile(r"\b(?:dot|\.|\s+dot\s+)\s*([a-z]{2,10})\b", re.IGNORECASE)

    # Browser names
    BROWSER_PATTERN = re.compile(r"\b(?:in|on|with|using)?\s*(chrome|chromium|edge|firefox|brave|opera)\b", re.IGNORECASE)

    # Known prompt-based AI services where "ask ... to ..." implies prompt box interaction
    AI_PROMPT_SITES = {
        "chatgpt": "https://chatgpt.com",
        "chat gpt": "https://chatgpt.com",
        "openai": "https://chatgpt.com",
        "claude": "https://claude.ai",
        "gemini": "https://gemini.google.com",
        "copilot": "https://copilot.microsoft.com",
        "perplexity": "https://www.perplexity.ai",
    }

    # Popular websites by canonical name
    POPULAR_SITES = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "reddit": "https://www.reddit.com",
        "stackoverflow": "https://stackoverflow.com",
        "stack overflow": "https://stackoverflow.com",
        "wikipedia": "https://www.wikipedia.org",
        "amazon": "https://www.amazon.com",
        "netflix": "https://www.netflix.com",
        "hianime": "https://hianime.to",
        "anime": "https://hianime.to",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "facebook": "https://www.facebook.com",
        "linkedin": "https://www.linkedin.com",
    }

    def __init__(self):
        pass

    def normalize_spoken_domain(self, text: str) -> str:
        """Normalizes spoken domain phrases like 'hianime dot at' -> 'hianime.at'."""
        if not text:
            return ""

        # Replace 'dot at' -> '.at', 'dot com' -> '.com', etc.
        def _dot_replacer(match: re.Match) -> str:
            tld = match.group(1).lower()
            if tld in self.KNOWN_TLDS or len(tld) <= 4:
                return f".{tld}"
            return match.group(0)

        cleaned = self.SPOKEN_DOT_PATTERN.sub(_dot_replacer, text)
        # Collapse spaces around dots: 'hianime . at' -> 'hianime.at' (avoid collapsing after command verbs like 'open')
        def _dot_collapse(m: re.Match) -> str:
            left = m.group(1)
            right = m.group(2)
            if left.lower() in ["open", "launch", "navigate", "to", "go", "visit", "browse", "search", "find", "and"]:
                return m.group(0)
            return f"{left}.{right}"

        cleaned = re.sub(r'([a-zA-Z0-9_\-]+)\s*\.\s*([a-zA-Z0-9_\-]+)', _dot_collapse, cleaned)
        return cleaned

    def extract_browser_target(self, text: str) -> Tuple[str, str, bool]:
        """Extracts specified browser (e.g. 'on Chrome') and returns (browser_name, remaining_text, is_explicit)."""
        b_match = re.search(r"\b(?:in|on|with|using)\s+(chrome|chromium|edge|firefox|brave|opera)\b", text, re.IGNORECASE)
        if b_match:
            browser = b_match.group(1).lower()
            # Remove the browser clause
            remaining = text[:b_match.start()] + text[b_match.end():]
            remaining = re.sub(r"\s+", " ", remaining).strip()
            return browser, remaining, True

        # Prefix browser pattern: "open chrome and go to...", "launch edge and open..."
        b_prefix_match = re.match(r"^(?:open|launch|start|focus)\s+(chrome|chromium|edge|firefox|brave|opera)\s+(?:and\s+)?(?:go\s+to|navigate\s+to|open|search)\s+(.+)$", text, re.IGNORECASE)
        if b_prefix_match:
            browser = b_prefix_match.group(1).lower()
            remainder = b_prefix_match.group(2).strip()
            return browser, remainder, True

        # Trailing browser without preposition: "... chrome"
        b_end_match = re.search(r"\b(chrome|chromium|edge|firefox|brave|opera)\s*$", text, re.IGNORECASE)
        if b_end_match and len(text.strip().split()) > 1:
            prefix = text[:b_end_match.start()].strip()
            if prefix.lower() not in ["open", "launch", "start", "focus"]:
                browser = b_end_match.group(1).lower()
                return browser, prefix, True

        return "chrome", text, False

    def is_explicit_url_or_domain(self, target: str) -> bool:
        """Determines if a target string represents an explicit URL or domain name."""
        clean = target.strip().lower()
        if clean.startswith("http://") or clean.startswith("https://"):
            return True
        if "." in clean and " " not in clean:
            parts = clean.split(".")
            if len(parts) >= 2 and parts[-1] in self.KNOWN_TLDS:
                return True
        return False

    def normalize_url(self, target: str) -> str:
        """Transforms a domain or URL string into a fully qualified HTTPS URL."""
        clean = target.strip()
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        return f"https://{clean}"

    def parse(self, text: str, session_context: Optional[Dict[str, Any]] = None) -> BrowserIntent:
        """Parses user command text into a structured BrowserIntent."""
        raw_text = text or ""
        norm_text = self.normalize_spoken_domain(raw_text).strip()
        # Clean trailing sentence punctuation (e.g. '.', '?', '!') from command processing
        clean = re.sub(r"[\.\?\!\,\;]+$", "", norm_text).strip().lower()
        session_context = session_context or {}

        # 0. Bypass browser intent parsing for desktop in-app commands (e.g. "in this application", "current app")
        if re.search(r"\b(?:in|on)\s+(?:this\s+application|this\s+app|the\s+current\s+application|current\s+app|this\s+window|current\s+window)\s*$", clean, re.IGNORECASE):
            return BrowserIntent(action_type=BrowserActionType.UNKNOWN, raw_text=raw_text, normalized_text=norm_text)

        # 1. Check for tab preference (new tab vs current tab)
        tab_pref = TabPreference.DEFAULT
        if re.search(r"\b(?:in\s+a\s+new\s+tab|in\s+another\s+tab|new\s+tab|another\s+tab)\b", clean):
            tab_pref = TabPreference.NEW_TAB
            clean = re.sub(r"\b(?:in\s+a\s+new\s+tab|in\s+another\s+tab|new\s+tab|another\s+tab)\b", "", clean).strip()
        elif re.search(r"\b(?:in\s+this\s+tab|in\s+current\s+tab|current\s+tab|this\s+tab|same\s+tab)\b", clean):
            tab_pref = TabPreference.CURRENT_TAB
            clean = re.sub(r"\b(?:in\s+this\s+tab|in\s+current\s+tab|current\s+tab|this\s+tab|same\s+tab)\b", "", clean).strip()

        # 2. Check for Browser Launch FIRST (e.g. "open chrome", "launch chrome")
        # Must take precedence before browser stripping or URL matching!
        browser_launch_match = re.match(r"^(?:open|launch|start|focus)\s+(chrome|chromium|edge|firefox|brave|opera|browser)$", clean, re.IGNORECASE)
        if browser_launch_match:
            b_target = browser_launch_match.group(1).lower()
            if b_target == "browser":
                b_target = "chrome"
            return BrowserIntent(
                action_type=BrowserActionType.OPEN_BROWSER,
                target_browser=b_target,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"launch_only": True}
            )

        # 3. Extract browser name if mentioned (e.g. "... on Chrome")
        browser_name, clean_no_browser, is_explicit_browser = self.extract_browser_target(clean)
        clean = re.sub(r"[\.\?\!\,\;]+$", "", clean_no_browser).strip()

        # -------------------------------------------------------------
        # A. CANCELLATION / STOP COMMAND
        # -------------------------------------------------------------
        if clean in ["stop", "cancel", "halt", "stop browser", "cancel search", "stop loading"]:
            return BrowserIntent(
                action_type=BrowserActionType.BROWSER_CONTROL,
                target_browser=browser_name,
                search_query="stop",
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"control_action": "stop"}
            )

        # -------------------------------------------------------------
        # B. BROWSER NAVIGATION / TAB CONTROL (Back, Forward, Refresh, etc.)
        # -------------------------------------------------------------
        if clean in ["go back", "back", "navigate back", "previous page"]:
            return BrowserIntent(
                action_type=BrowserActionType.BROWSER_CONTROL,
                target_browser=browser_name,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"control_action": "go_back"}
            )

        if clean in ["go forward", "forward", "navigate forward", "next page"]:
            return BrowserIntent(
                action_type=BrowserActionType.BROWSER_CONTROL,
                target_browser=browser_name,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"control_action": "go_forward"}
            )

        if clean in ["refresh", "reload", "refresh page", "reload page", "reload the page"]:
            return BrowserIntent(
                action_type=BrowserActionType.BROWSER_CONTROL,
                target_browser=browser_name,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"control_action": "reload_page"}
            )

        if clean in ["close tab", "close this tab", "close current tab", "shut tab"]:
            return BrowserIntent(
                action_type=BrowserActionType.BROWSER_CONTROL,
                target_browser=browser_name,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"control_action": "close_tab"}
            )

        if clean in ["open a new tab", "open another tab", "new tab", "create a tab"]:
            return BrowserIntent(
                action_type=BrowserActionType.BROWSER_CONTROL,
                target_browser=browser_name,
                tab_preference=TabPreference.NEW_TAB,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"control_action": "new_tab"}
            )

        # -------------------------------------------------------------
        # C. BROWSER LAUNCH (e.g. "open chrome", "launch chrome")
        # -------------------------------------------------------------
        # Must NOT trigger web search!
        browser_launch_match = re.match(r"^(?:open|launch|start|focus)\s+(chrome|chromium|edge|firefox|brave|opera|browser)$", clean, re.IGNORECASE)
        if browser_launch_match:
            b_target = browser_launch_match.group(1).lower()
            if b_target == "browser":
                b_target = "chrome"
            return BrowserIntent(
                action_type=BrowserActionType.OPEN_BROWSER,
                target_browser=b_target,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"launch_only": True}
            )

        # -------------------------------------------------------------
        # D. FIND IN CURRENT PAGE (e.g. "find the word installation on this page")
        # -------------------------------------------------------------
        find_in_page_match = re.match(
            r"^(?:find|search(?:\s+for)?)\s+(?:the\s+word\s+|the\s+text\s+|the\s+phrase\s+)?(.+?)\s+(?:on|in)\s+(?:this\s+page|the\s+page|current\s+page)$",
            clean,
            re.IGNORECASE
        )
        if find_in_page_match:
            q = find_in_page_match.group(1).strip()
            return BrowserIntent(
                action_type=BrowserActionType.SEARCH_PAGE,
                target_browser=browser_name,
                search_query=q,
                search_scope=SearchScope.CURRENT_PAGE,
                input_purpose="find_in_page",
                submit=False,
                raw_text=raw_text,
                normalized_text=norm_text
            )

        # In-page search (Find in Page) e.g. "search this page for X", "search current page for X"
        page_search_match = re.match(r"^(?:search\s+(?:the\s+)?current\s+(?:page|tab)(?:\s+for\s+(.+))?|search\s+(?:this|the)\s+(?:page|tab)\s+for\s+(.+))$", clean, re.IGNORECASE)
        if page_search_match:
            q = page_search_match.group(1) or page_search_match.group(2) or ""
            return BrowserIntent(
                action_type=BrowserActionType.SEARCH_PAGE,
                target_browser=browser_name,
                search_query=q.strip(),
                search_scope=SearchScope.CURRENT_PAGE,
                input_purpose="find_in_page",
                raw_text=raw_text,
                normalized_text=norm_text
            )

        # Website search on active/current site: "search this website for X", "search current website for X"
        site_search_match = re.match(r"^(?:search\s+(?:the\s+)?current\s+(?:website|site)(?:\s+for\s+(.+))?|search\s+(?:this|the)\s+(?:website|site)\s+for\s+(.+)|search\s+for\s+(.+?)\s+on\s+(?:this\s+website|the\s+current\s+website|current\s+website|this\s+site))$", clean, re.IGNORECASE)
        if site_search_match:
            q = (site_search_match.group(1) or site_search_match.group(2) or site_search_match.group(3) or "").strip().lower()
            active_site = session_context.get("active_site") or session_context.get("last_site")
            active_url = session_context.get("active_url") or session_context.get("last_url")
            if active_site or active_url:
                return BrowserIntent(
                    action_type=BrowserActionType.SEARCH_WEBSITE,
                    target_browser=browser_name,
                    url=active_url,
                    site_name=active_site or "current_website",
                    domain=urllib.parse.urlparse(active_url).netloc if active_url else None,
                    search_query=q.strip(),
                    search_scope=SearchScope.WEBSITE,
                    tab_preference=tab_pref,
                    input_purpose="search_box",
                    submit=True,
                    verification_method="search_results",
                    raw_text=raw_text,
                    normalized_text=norm_text,
                    metadata={"contextual_reuse": True}
                )
            else:
                return BrowserIntent(
                    action_type=BrowserActionType.CLARIFICATION_NEEDED,
                    target_browser=browser_name,
                    search_query=q.strip(),
                    clarification_prompt=f"Which website would you like me to search for '{q.strip()}'?",
                    raw_text=raw_text,
                    normalized_text=norm_text
                )

        # -------------------------------------------------------------
        # E. AI PROMPT INTERACTION (e.g. "open ChatGPT and ask it to explain binary search")
        # -------------------------------------------------------------
        ai_prompt_match = re.match(
            r"^(?:open\s+)?(chatgpt|claude|gemini|copilot|perplexity)\s+(?:and\s+)?(?:ask\s+(?:it\s+)?to|tell\s+(?:it\s+)?to|prompt\s+(?:it\s+)?with|ask)\s+(.+)$",
            clean,
            re.IGNORECASE
        )
        if ai_prompt_match:
            site = ai_prompt_match.group(1).lower()
            prompt = ai_prompt_match.group(2).strip()
            url = self.AI_PROMPT_SITES.get(site, f"https://{site}.com")
            return BrowserIntent(
                action_type=BrowserActionType.INTERACT_PROMPT,
                target_browser=browser_name,
                url=url,
                site_name=site,
                domain=urllib.parse.urlparse(url).netloc,
                prompt_query=prompt,
                search_query=prompt,
                search_scope=SearchScope.APPLICATION,
                tab_preference=tab_pref,
                input_purpose="prompt_box",
                submit=True,
                raw_text=raw_text,
                normalized_text=norm_text
            )

        # -------------------------------------------------------------
        # F. CONVERSATIONAL FOLLOW-UPS & CONTEXTUAL RESOLUTION
        # e.g. "Now search for One Piece", "Use the same website", "Search for a different anime"
        # -------------------------------------------------------------
        now_search_match = re.match(r"^(?:now\s+search\s+for|search\s+for|search)\s+(.+)$", clean, re.IGNORECASE)
        same_site_followup = bool(re.search(r"\b(?:use\s+the\s+same\s+website|same\s+site|same\s+website|on\s+the\s+same\s+website)\b", clean, re.IGNORECASE))
        current_site_ref = bool(re.search(r"\b(?:on\s+(?:the\s+)?website\s+already\s+open|on\s+current\s+website|on\s+this\s+website|in\s+this\s+website)\b", clean, re.IGNORECASE))

        # Check if user says "search for this anime on the website already open"
        if current_site_ref:
            extracted_q = re.sub(r"\b(?:on\s+(?:the\s+)?website\s+already\s+open|on\s+current\s+website|on\s+this\s+website|in\s+this\s+website)\b", "", clean).strip()
            extracted_q = re.sub(r"^(?:search(?:\s+for)?)\s+", "", extracted_q).strip()
            active_url = session_context.get("active_url") or session_context.get("last_url")
            active_site = session_context.get("active_site") or session_context.get("last_site")
            return BrowserIntent(
                action_type=BrowserActionType.SEARCH_WEBSITE,
                target_browser=browser_name,
                url=active_url,
                site_name=active_site or "current_website",
                domain=urllib.parse.urlparse(active_url).netloc if active_url else None,
                search_query=extracted_q,
                search_scope=SearchScope.WEBSITE,
                tab_preference=TabPreference.CURRENT_TAB,
                input_purpose="search_box",
                submit=True,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"contextual_reuse": True}
            )

        # Follow-up "now search for X" using remembered session website
        if clean.startswith("now search for ") or (same_site_followup and now_search_match):
            follow_q = clean.replace("now search for ", "").strip()
            follow_q = re.sub(r"\b(?:use\s+the\s+same\s+website|same\s+site|same\s+website|on\s+the\s+same\s+website)\b", "", follow_q).strip()
            last_site = session_context.get("last_site")
            last_url = session_context.get("last_url")
            last_domain = session_context.get("last_domain")

            if last_site or last_url:
                return BrowserIntent(
                    action_type=BrowserActionType.SEARCH_WEBSITE,
                    target_browser=browser_name,
                    url=last_url,
                    site_name=last_site,
                    domain=last_domain,
                    search_query=follow_q,
                    search_scope=SearchScope.WEBSITE,
                    tab_preference=tab_pref,
                    input_purpose="search_box",
                    submit=True,
                    raw_text=raw_text,
                    normalized_text=norm_text,
                    metadata={"follow_up": True}
                )

        # -------------------------------------------------------------
        # G. EXPLICIT URL / DOMAIN NAVIGATION
        # e.g. "open hianime.at on chrome", "navigate to https://hianime.to", "open google.com",
        # "search hianime.at", "search for hianime.at", "visit hianime.at", "hianime.at"
        # -------------------------------------------------------------
        domain_direct_match = re.match(r"^(?:open|launch|navigate\s+to|go\s+to|visit|browse\s+to|search(?:\s+for)?\s+)?([a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,10}|https?://\S+)$", clean, re.IGNORECASE)
        if domain_direct_match:
            candidate_target = domain_direct_match.group(1).strip()
            candidate_target = re.sub(r"[\.\,\?\!\;:]+$", "", candidate_target).strip()
            d_res = domain_manager.resolve_domain(candidate_target, confidence=1.0)
            if d_res.status == "CONFIRMATION_REQUIRED":
                return BrowserIntent(
                    action_type=BrowserActionType.CLARIFICATION_NEEDED,
                    target_browser=browser_name,
                    site_name=d_res.site_name or candidate_target,
                    clarification_prompt=d_res.clarification_prompt,
                    confidence=d_res.confidence,
                    raw_text=raw_text,
                    normalized_text=norm_text,
                    metadata={
                        "domain_confirmation": True,
                        "canonical_domain": d_res.canonical_hostname,
                        "candidate_domain": d_res.hostname,
                        "options": [d_res.canonical_hostname, d_res.hostname]
                    }
                )
            elif d_res.status == "INVALID":
                return BrowserIntent(
                    action_type=BrowserActionType.CLARIFICATION_NEEDED,
                    target_browser=browser_name,
                    clarification_prompt=d_res.clarification_prompt,
                    confidence=0.5,
                    raw_text=raw_text,
                    normalized_text=norm_text,
                    metadata={"invalid_domain": True, "reason": d_res.error_reason}
                )
            elif d_res.is_navigable:
                ok, resolved_url, err = domain_manager.construct_validated_url(d_res.hostname)
                if ok:
                    domain = urllib.parse.urlsplit(resolved_url).netloc
                    logger.info(f"[DOMAIN_TRACE][INTENT] action=OPEN_URL, target_hostname='{d_res.hostname}', url='{resolved_url}'")
                    return BrowserIntent(
                        action_type=BrowserActionType.OPEN_URL,
                        target_browser=browser_name,
                        url=resolved_url,
                        site_name=d_res.hostname,
                        domain=domain,
                        search_scope=SearchScope.WEBSITE,
                        tab_preference=tab_pref,
                        submit=False,
                        verification_method="cdp_or_title",
                        raw_text=raw_text,
                        normalized_text=norm_text
                    )

        open_site_match = re.match(r"^(?:open|launch|navigate\s+to|go\s+to|visit|browse\s+to)\s+(.+)$", clean, re.IGNORECASE)
        if open_site_match:
            candidate_target = open_site_match.group(1).strip()
            # Remove leading "the website" or "site"
            candidate_target = re.sub(r"^(?:the\s+website\s+|website\s+|site\s+)", "", candidate_target).strip()
            candidate_target = re.sub(r"[\.\,\?\!\;:]+$", "", candidate_target).strip()

            # Check if candidate looks like a domain attempt or full URL
            if ("." in candidate_target or candidate_target.startswith("http://") or candidate_target.startswith("https://")) and " " not in candidate_target:
                d_res = domain_manager.resolve_domain(candidate_target, confidence=1.0)
                if d_res.status == "CONFIRMATION_REQUIRED":
                    return BrowserIntent(
                        action_type=BrowserActionType.CLARIFICATION_NEEDED,
                        target_browser=browser_name,
                        site_name=d_res.site_name or candidate_target,
                        clarification_prompt=d_res.clarification_prompt,
                        confidence=d_res.confidence,
                        raw_text=raw_text,
                        normalized_text=norm_text,
                        metadata={
                            "domain_confirmation": True,
                            "canonical_domain": d_res.canonical_hostname,
                            "candidate_domain": d_res.hostname,
                            "options": [d_res.canonical_hostname, d_res.hostname]
                        }
                    )
                elif d_res.status == "INVALID":
                    return BrowserIntent(
                        action_type=BrowserActionType.CLARIFICATION_NEEDED,
                        target_browser=browser_name,
                        clarification_prompt=d_res.clarification_prompt,
                        confidence=0.5,
                        raw_text=raw_text,
                        normalized_text=norm_text,
                        metadata={"invalid_domain": True, "reason": d_res.error_reason}
                    )
                elif d_res.is_navigable:
                    ok, resolved_url, err = domain_manager.construct_validated_url(d_res.hostname)
                    if ok:
                        domain = urllib.parse.urlsplit(resolved_url).netloc
                        logger.info(f"[DOMAIN_TRACE][INTENT] action=OPEN_URL, target_hostname='{d_res.hostname}', url='{resolved_url}'")
                        return BrowserIntent(
                            action_type=BrowserActionType.OPEN_URL,
                            target_browser=browser_name,
                            url=resolved_url,
                            site_name=d_res.hostname,
                            domain=domain,
                            search_scope=SearchScope.WEBSITE,
                            tab_preference=tab_pref,
                            submit=False,
                            verification_method="cdp_or_title",
                            raw_text=raw_text,
                            normalized_text=norm_text
                        )

            # Check if it's a known popular site name without TLD (e.g. "open youtube")
            if candidate_target in self.POPULAR_SITES:
                resolved_url = self.POPULAR_SITES[candidate_target]
                return BrowserIntent(
                    action_type=BrowserActionType.OPEN_URL,
                    target_browser=browser_name,
                    url=resolved_url,
                    site_name=candidate_target,
                    domain=urllib.parse.urlparse(resolved_url).netloc,
                    search_scope=SearchScope.WEBSITE,
                    tab_preference=tab_pref,
                    submit=False,
                    verification_method="cdp_or_title",
                    raw_text=raw_text,
                    normalized_text=norm_text
                )

            # Check for ambiguous domain speech transcription (e.g. "open hianime dot")
            if candidate_target.endswith(" dot") or candidate_target.endswith("."):
                return BrowserIntent(
                    action_type=BrowserActionType.CLARIFICATION_NEEDED,
                    target_browser=browser_name,
                    clarification_prompt=f"Which website extension did you mean for '{candidate_target}'? (e.g., .to, .at, or .com)",
                    raw_text=raw_text,
                    normalized_text=norm_text
                )

        # -------------------------------------------------------------
        # H. NAMED WEBSITE SEARCH
        # Patterns:
        # - "search for Naruto on HiAnime"
        # - "search YouTube for Valorant highlights"
        # - "search HiAnime for Naruto"
        # - "search on GitHub for python asyncio"
        # -------------------------------------------------------------
        # Pattern 1: "search for <QUERY> on <WEBSITE>" or "find <QUERY> on <WEBSITE>"
        search_on_match = re.match(r"^(?:search(?:\s+for)?|find)\s+(.+?)\s+(?:on|in|using)\s+([a-zA-Z0-9_\-\.\s]+)$", clean, re.IGNORECASE)
        if search_on_match:
            query_part = search_on_match.group(1).strip().lower()
            site_part = search_on_match.group(2).strip()

            # Filter out non-website targets (e.g. "the web", "google search", in-app/desktop targets)
            non_website_targets = {
                "the web", "web", "internet", "google search",
                "this application", "this app", "the current application", "current app", "the current app",
                "app", "application", "this window", "current window", "window"
            }
            if site_part.lower() not in non_website_targets and not re.match(r"^(?:this|the\s+current|current)\s+(?:app|application|window)$", site_part.lower()):
                url, domain = self._resolve_site_destination(site_part)
                return BrowserIntent(
                    action_type=BrowserActionType.SEARCH_WEBSITE,
                    target_browser=browser_name,
                    url=url,
                    site_name=site_part,
                    domain=domain,
                    search_query=query_part,
                    search_scope=SearchScope.WEBSITE,
                    tab_preference=tab_pref,
                    input_purpose="search_box",
                    submit=True,
                    verification_method="search_results",
                    raw_text=raw_text,
                    normalized_text=norm_text
                )

        # Pattern 2: "search <WEBSITE> for <QUERY>" or "search Chrome for <QUERY>"
        search_site_for_match = re.match(r"^(?:search|find)\s+([a-zA-Z0-9_\-\.]+)\s+for\s+(.+)$", clean, re.IGNORECASE)
        if search_site_for_match:
            site_part = search_site_for_match.group(1).strip()
            query_part = search_site_for_match.group(2).strip().lower()

            if site_part.lower() in ["google", "chrome", "chromium", "edge", "firefox", "brave", "opera"]:
                b_dest = site_part.lower() if site_part.lower() != "google" else browser_name
                return BrowserIntent(
                    action_type=BrowserActionType.SEARCH_WEB,
                    target_browser=b_dest,
                    url=f"https://www.google.com/search?q={urllib.parse.quote_plus(query_part)}",
                    site_name="google",
                    domain="www.google.com",
                    search_query=query_part,
                    search_scope=SearchScope.WEB_SEARCH,
                    tab_preference=tab_pref,
                    input_purpose="search_box",
                    submit=True,
                    raw_text=raw_text,
                    normalized_text=norm_text
                )

            if site_part not in ["the", "this", "my", "web", "the web"]:
                url, domain = self._resolve_site_destination(site_part)
                return BrowserIntent(
                    action_type=BrowserActionType.SEARCH_WEBSITE,
                    target_browser=browser_name,
                    url=url,
                    site_name=site_part,
                    domain=domain,
                    search_query=query_part,
                    search_scope=SearchScope.WEBSITE,
                    tab_preference=tab_pref,
                    input_purpose="search_box",
                    submit=True,
                    verification_method="search_results",
                    raw_text=raw_text,
                    normalized_text=norm_text
                )

        # -------------------------------------------------------------
        # I. GENERAL SEARCH & AMBIGUITY HANDLING
        # e.g. "search for Naruto", "search python decorators"
        # -------------------------------------------------------------
        # "Search the web for X"
        web_search_match = re.match(r"^(?:search\s+(?:the\s+)?web\s+for|google\s+for|search\s+google\s+for)\s+(.+)$", clean, re.IGNORECASE)
        if web_search_match:
            q = web_search_match.group(1).strip()
            return BrowserIntent(
                action_type=BrowserActionType.SEARCH_WEB,
                target_browser=browser_name,
                url=f"https://www.google.com/search?q={urllib.parse.quote_plus(q)}",
                site_name="google",
                domain="www.google.com",
                search_query=q,
                search_scope=SearchScope.WEB_SEARCH,
                tab_preference=tab_pref,
                input_purpose="search_box",
                submit=True,
                raw_text=raw_text,
                normalized_text=norm_text
            )

        # Ambiguous search deictic pronoun (e.g. "search there", "search here", "search that")
        if re.match(r"^search\s+(?:for\s+)?(?:there|here|that|it)$", clean, re.IGNORECASE):
            return BrowserIntent(
                action_type=BrowserActionType.CLARIFICATION_NEEDED,
                target_browser=browser_name,
                clarification_prompt="Where would you like me to search, and what would you like me to search for?",
                raw_text=raw_text,
                normalized_text=norm_text
            )

        # "Search for X" without explicit destination: ambiguous destination
        bare_search_for_match = re.match(r"^search\s+for\s+(.+)$", clean, re.IGNORECASE)
        if bare_search_for_match:
            q = bare_search_for_match.group(1).strip().lower()
            # Clean deictic references like "there", "on it", "in it" (e.g. "search for Naruto there")
            if re.search(r"\bthere\b", q, re.IGNORECASE) or re.search(r"\b(?:on|in)\s+it\b", q, re.IGNORECASE):
                q = re.sub(r"\bthere\b", "", q, flags=re.IGNORECASE).strip()
                q = re.sub(r"\b(?:on|in)\s+it\b", "", q, flags=re.IGNORECASE).strip()
                q = re.sub(r"\s+", " ", q).strip()

            active_site = session_context.get("active_site") or session_context.get("last_site")
            active_url = session_context.get("active_url") or session_context.get("last_url")

            # Destination cannot be determined from explicit wording or reliable context -> ask clarification!
            if not active_site and not active_url:
                return BrowserIntent(
                    action_type=BrowserActionType.CLARIFICATION_NEEDED,
                    target_browser=browser_name,
                    search_query=q,
                    clarification_prompt=f"Where would you like me to search for '{q}'? (e.g., on Google, YouTube, or a specific website)",
                    raw_text=raw_text,
                    normalized_text=norm_text
                )
            else:
                return BrowserIntent(
                    action_type=BrowserActionType.SEARCH_WEBSITE,
                    target_browser=browser_name,
                    url=active_url,
                    site_name=active_site,
                    domain=urllib.parse.urlparse(active_url).netloc if active_url else None,
                    search_query=q,
                    search_scope=SearchScope.WEBSITE,
                    tab_preference=tab_pref,
                    input_purpose="search_box",
                    submit=True,
                    raw_text=raw_text,
                    normalized_text=norm_text,
                    metadata={"contextual_search": True}
                )

        # General explicit web search without "for": "search AI news", "search quantum computing"
        general_search_match = re.match(r"^(?:search|look\s+up|find)\s+(.+)$", clean, re.IGNORECASE)
        if general_search_match:
            # Extract preserving case from norm_text
            m_orig = re.match(r"^(?:search|look\s+up|find)\s+(.+)$", norm_text.rstrip(".?!,; "), re.IGNORECASE)
            q = m_orig.group(1).strip() if m_orig else general_search_match.group(1).strip()
            return BrowserIntent(
                action_type=BrowserActionType.SEARCH_WEB,
                target_browser=browser_name,
                url=f"https://www.google.com/search?q={urllib.parse.quote_plus(q)}",
                site_name="google",
                domain="www.google.com",
                search_query=q,
                search_scope=SearchScope.WEB_SEARCH,
                tab_preference=tab_pref,
                input_purpose="search_box",
                submit=True,
                raw_text=raw_text,
                normalized_text=norm_text,
                metadata={"explicit_browser": is_explicit_browser}
            )

        # Fallback unknown
        return BrowserIntent(
            action_type=BrowserActionType.UNKNOWN,
            target_browser=browser_name,
            confidence=0.0,
            raw_text=raw_text,
            normalized_text=norm_text
        )

    def _resolve_site_destination(self, site_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Resolves site name or domain to (URL, domain). Never invents arbitrary URLs."""
        clean = site_name.strip().lower()

        # Direct popular site mapping
        if clean in self.POPULAR_SITES:
            url = self.POPULAR_SITES[clean]
            return url, urllib.parse.urlparse(url).netloc

        # AI prompt sites
        if clean in self.AI_PROMPT_SITES:
            url = self.AI_PROMPT_SITES[clean]
            return url, urllib.parse.urlparse(url).netloc

        # If it's already a domain with TLD (e.g. hianime.to, hianime.at)
        if self.is_explicit_url_or_domain(clean):
            url = self.normalize_url(clean)
            return url, urllib.parse.urlparse(url).netloc

        # If it's a known domain format without protocol
        if "." in clean and " " not in clean:
            url = f"https://{clean}"
            return url, clean

        # Default fallback for named website: synthesize standard domain
        url = f"https://www.{clean}.com"
        return url, f"www.{clean}.com"
