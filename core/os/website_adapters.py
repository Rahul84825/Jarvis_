"""Reusable Website Interaction Layer and Adapters for JARVIS Browser Automation.
Generic websites work out-of-the-box using universal DOM discovery and heuristics.
Optional specialized adapters provide enhanced selectors, prompt box identifiers,
search URL templates, and result verification indicators for complex single-page apps.
"""

import urllib.parse
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger("Jarvis.WebsiteAdapters")


class BaseWebsiteAdapter(ABC):
    """Abstract base adapter for website-specific interaction hints."""

    name: str = "base"
    domains: List[str] = []
    search_selectors: List[str] = []
    prompt_selectors: List[str] = []
    submit_method: str = "enter_key"  # enter_key, click_button, form_submit
    result_indicators: List[str] = []
    requires_login: bool = False

    def supports_domain(self, domain_or_url: str) -> bool:
        """Checks if this adapter explicitly handles the given domain or URL."""
        if not domain_or_url:
            return False
        clean = domain_or_url.lower().strip()
        if "://" in clean:
            clean = urllib.parse.urlparse(clean).netloc
        clean = clean.replace("www.", "")
        for d in self.domains:
            d_clean = d.lower().replace("www.", "")
            if clean == d_clean or clean.endswith("." + d_clean):
                return True
        return False

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        """Optionally generates a direct search query URL if supported."""
        return None

    def get_search_selectors(self) -> List[str]:
        """Returns ordered list of DOM selectors for search inputs."""
        return list(self.search_selectors)

    def get_prompt_selectors(self) -> List[str]:
        """Returns ordered list of DOM selectors for AI prompt or messaging boxes."""
        return list(self.prompt_selectors)

    def get_result_indicators(self) -> List[str]:
        """Returns DOM selectors or text fragments indicating successful search/response."""
        return list(self.result_indicators)


class GenericWebsiteAdapter(BaseWebsiteAdapter):
    """Universal fallback adapter that works on any website using accessibility and DOM patterns."""

    name = "generic"
    domains = ["*"]

    # Layered universal search input selectors ordered by specificity
    search_selectors = [
        "input[type='search']",
        "input[role='searchbox']",
        "input[name='q']",
        "input[name='query']",
        "input[name='search']",
        "input[name='keyword']",
        "input[name='s']",
        "input[id*='search' i]",
        "input[class*='search' i]",
        "input[placeholder*='search' i]",
        "input[placeholder*='find' i]",
        "input[aria-label*='search' i]",
        "textarea[placeholder*='search' i]",
        "input[type='text'][name*='search' i]",
        "form[role='search'] input[type='text']",
        "form[action*='search'] input[type='text']"
    ]

    prompt_selectors = [
        "textarea[placeholder*='message' i]",
        "textarea[placeholder*='prompt' i]",
        "textarea[placeholder*='ask' i]",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "textarea"
    ]

    result_indicators = [
        "[role='main']",
        ".search-results",
        "#search-results",
        ".results",
        "#results",
        ".content",
        "article",
        "main"
    ]

    def supports_domain(self, domain_or_url: str) -> bool:
        return True  # Fallback matches all domains

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        """Generic heuristic search URL builder for sites that use standard /search?q= or ?s=."""
        if not base_url:
            return None
        parsed = urllib.parse.urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        encoded = urllib.parse.quote_plus(query)
        return f"{parsed.scheme}://{parsed.netloc}/search?q={encoded}"


class HiAnimeAdapter(BaseWebsiteAdapter):
    """Adapter for HiAnime streaming website (hianime.to / hianime.at / hianime.tv)."""

    name = "hianime"
    domains = ["hianime.to", "hianime.at", "hianime.tv", "hianime.is", "hianime.ru"]

    search_selectors = [
        "#search-suggest",
        "input[name='keyword']",
        "input.search-input",
        "input[placeholder*='Search anime' i]",
        "input[placeholder*='Search' i]"
    ]

    result_indicators = [
        ".film_list-wrap",
        ".film-detail",
        ".block_area-search",
        ".flw-item"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        domain = "hianime.to"
        if base_url:
            parsed = urllib.parse.urlparse(base_url)
            if parsed.netloc:
                domain = parsed.netloc
        return f"https://{domain}/search?keyword={encoded}"


class YouTubeAdapter(BaseWebsiteAdapter):
    """Adapter for YouTube (desktop & mobile web)."""

    name = "youtube"
    domains = ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"]

    search_selectors = [
        "input#search",
        "input[name='search_query']",
        "input[placeholder*='Search' i]",
        "input[aria-label*='Search' i]"
    ]

    result_indicators = [
        "ytd-video-renderer",
        "ytd-search",
        "#contents",
        "ytd-item-section-renderer"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        return f"https://www.youtube.com/results?search_query={encoded}"


class ChatGPTAdapter(BaseWebsiteAdapter):
    """Adapter for OpenAI ChatGPT interface."""

    name = "chatgpt"
    domains = ["chatgpt.com", "chat.openai.com"]

    prompt_selectors = [
        "#prompt-textarea",
        "div#prompt-textarea",
        "textarea[placeholder*='Ask anything' i]",
        "textarea[placeholder*='Message ChatGPT' i]",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']"
    ]

    submit_method = "enter_key"

    result_indicators = [
        "[data-message-author-role='assistant']",
        ".agent-turn",
        ".markdown",
        "[data-testid='conversation-turn-3']"
    ]


class GitHubAdapter(BaseWebsiteAdapter):
    """Adapter for GitHub."""

    name = "github"
    domains = ["github.com", "www.github.com"]

    search_selectors = [
        "input[name='q']",
        "input[data-target='qbsearch-input.input']",
        "input[placeholder*='Search or jump to' i]",
        "input[placeholder*='Search GitHub' i]",
        "button[data-target='qbsearch-input.inputButton']"
    ]

    result_indicators = [
        "[data-testid='results-list']",
        ".repo-list",
        ".search-title",
        ".Box"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        return f"https://github.com/search?q={encoded}"


class RedditAdapter(BaseWebsiteAdapter):
    """Adapter for Reddit."""

    name = "reddit"
    domains = ["reddit.com", "www.reddit.com", "old.reddit.com"]

    search_selectors = [
        "input[name='q']",
        "reddit-search-bar input",
        "input[placeholder*='Search Reddit' i]",
        "input[type='search']"
    ]

    result_indicators = [
        "[data-testid='search-results']",
        "shreddit-feed",
        ".search-result-group"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        return f"https://www.reddit.com/search/?q={encoded}"


class GoogleAdapter(BaseWebsiteAdapter):
    """Adapter for Google Search."""

    name = "google"
    domains = ["google.com", "www.google.com"]

    search_selectors = [
        "textarea[name='q']",
        "input[name='q']",
        "input[title='Search']"
    ]

    result_indicators = [
        "#search",
        "#rso",
        ".g",
        "#center_col"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        return f"https://www.google.com/search?q={encoded}"


class WebsiteAdapterRegistry:
    """Registry managing available website adapters with fallback to GenericWebsiteAdapter."""

    def __init__(self):
        self._generic_adapter = GenericWebsiteAdapter()
        self._adapters: List[BaseWebsiteAdapter] = [
            HiAnimeAdapter(),
            YouTubeAdapter(),
            ChatGPTAdapter(),
            GitHubAdapter(),
            RedditAdapter(),
            GoogleAdapter(),
        ]

    def register_adapter(self, adapter: BaseWebsiteAdapter):
        """Adds a specialized adapter to the front of the registry."""
        self._adapters.insert(0, adapter)
        logger.info(f"Registered website adapter '{adapter.name}' for domains {adapter.domains}")

    def get_adapter(self, domain_or_url: Optional[str]) -> BaseWebsiteAdapter:
        """Returns specialized adapter if matched, otherwise GenericWebsiteAdapter."""
        if not domain_or_url:
            return self._generic_adapter

        for adapter in self._adapters:
            if adapter.supports_domain(domain_or_url):
                return adapter

        return self._generic_adapter


# Global singleton registry
website_adapter_registry = WebsiteAdapterRegistry()
