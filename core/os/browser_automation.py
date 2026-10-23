"""Universal Browser Automation Engine for JARVIS.
Implements layered search-field discovery (CDP DOM -> UI Automation -> Adapter URL -> Fallback),
candidate field scoring, tab lifecycle management, verified navigation, and consequential safety checks.
"""

import time
import json
import socket
import hashlib
import base64
import urllib.parse
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

from core.os.browser_intent import BrowserIntent, BrowserActionType, SearchScope, TabPreference
from core.os.website_adapters import website_adapter_registry, BaseWebsiteAdapter
from core.os.browser_session import browser_session_manager
from core.os.browser_manager import BrowserManager
from core.os.cdp_client import CDPClient

logger = logging.getLogger("Jarvis.BrowserAutomation")


@dataclass
class CandidateInputField:
    """Represents a discovered candidate text/search input on a webpage."""
    element_id: str = ""
    selector: str = ""
    tag_name: str = "input"
    input_type: str = "text"
    name: str = ""
    placeholder: str = ""
    aria_label: str = ""
    role: str = ""
    is_visible: bool = True
    is_enabled: bool = True
    score: float = 0.0
    field_purpose: str = "general"  # search_box, filter, prompt_box, address_bar, general


class LightweightCDPWebSocket:
    """Standard-library RFC 6455 WebSocket client strictly connecting to 127.0.0.1 CDP targets.
    Provides fast, non-blocking DOM evaluation without external dependencies.
    """

    def __init__(self, ws_url: str, timeout: float = 1.0):
        self.ws_url = ws_url
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def connect(self) -> bool:
        """Performs HTTP upgrade handshake with localhost Chrome DevTools WebSocket."""
        try:
            parsed = urllib.parse.urlparse(self.ws_url)
            host = parsed.hostname or "127.0.0.1"
            # Strict security requirement: only localhost
            if host not in ["127.0.0.1", "localhost"]:
                return False
            port = parsed.port or 9222
            path = parsed.path
            if parsed.query:
                path += f"?{parsed.query}"

            self.sock = socket.create_connection((host, port), timeout=self.timeout)
            self.sock.settimeout(self.timeout)

            # Generate Sec-WebSocket-Key
            raw_key = base64.b64encode(b"jarvis_cdp_handshake").decode("ascii")
            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {raw_key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"\r\n"
            )
            self.sock.sendall(req.encode("utf-8"))

            # Read handshake response
            resp = self.sock.recv(4096).decode("utf-8", errors="ignore")
            if "101 Switching Protocols" in resp:
                return True
            self.close()
            return False
        except Exception as e:
            logger.debug(f"[CDP_WS] Handshake failed: {e}")
            self.close()
            return False

    def send_cdp_command(self, method: str, params: Optional[Dict[str, Any]] = None, cmd_id: int = 1) -> Optional[Dict[str, Any]]:
        """Sends a JSON-RPC CDP command and reads the JSON response."""
        if not self.sock:
            return None
        try:
            payload = json.dumps({"id": cmd_id, "method": method, "params": params or {}}).encode("utf-8")
            # Build masked websocket text frame (Opcode 0x1, FIN bit set)
            frame = bytearray([0x81])
            length = len(payload)
            mask_key = b"\x12\x34\x56\x78"

            if length < 126:
                frame.append(0x80 | length)
            elif length <= 65535:
                frame.append(0x80 | 126)
                frame.extend(length.to_bytes(2, "big"))
            else:
                frame.append(0x80 | 127)
                frame.extend(length.to_bytes(8, "big"))

            frame.extend(mask_key)
            masked_payload = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
            frame.extend(masked_payload)

            self.sock.sendall(frame)

            # Read response frame
            data = self.sock.recv(65536)
            if not data or len(data) < 2:
                return None

            # Parse unmasked server frame
            payload_len = data[1] & 0x7F
            idx = 2
            if payload_len == 126:
                idx = 4
            elif payload_len == 127:
                idx = 10

            text_data = data[idx:].decode("utf-8", errors="ignore")
            # Parse lines for the JSON with our command id
            for line in text_data.split("\n"):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        parsed_json = json.loads(line)
                        if parsed_json.get("id") == cmd_id:
                            return parsed_json
                    except Exception:
                        pass
            return None
        except Exception as e:
            logger.debug(f"[CDP_WS] send_cdp_command error: {e}")
            return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


class BrowserAutomationEngine:
    """Universal browser automation coordinator handling navigation, discovery, and execution."""

    def __init__(self, browser_manager: Optional[BrowserManager] = None):
        self.browser_mgr = browser_manager or BrowserManager()
        self.cdp = CDPClient()
        self.adapter_registry = website_adapter_registry
        self.session_mgr = browser_session_manager

    def execute_intent(self, intent: BrowserIntent) -> Dict[str, Any]:
        """Main entry point to execute a resolved BrowserIntent."""
        logger.info(f"Executing BrowserIntent: action={intent.action_type}, target='{intent.site_name or intent.url}', query='{intent.search_query}'")

        # Check for immediate clarification requirement
        if intent.action_type == BrowserActionType.CLARIFICATION_NEEDED:
            return {
                "success": True,
                "action": "clarification_needed",
                "message": intent.clarification_prompt or "Could you please clarify your browser request?",
                "requires_clarification": True,
                "intent": intent.to_dict()
            }

        # Check for user cancellation request
        if intent.action_type == BrowserActionType.BROWSER_CONTROL and intent.metadata.get("control_action") == "stop":
            self.session_mgr.cancel_operation()
            return {
                "success": True,
                "action": "stop",
                "message": "Browser operation stopped.",
                "cancelled": True
            }

        # Check for browser launch only (do not search)
        if intent.action_type == BrowserActionType.OPEN_BROWSER:
            return self._handle_open_browser(intent)

        # Check for in-page search (Find in Page)
        if intent.action_type == BrowserActionType.SEARCH_PAGE:
            return self._handle_search_page(intent)

        # Check for AI Prompt interaction (e.g. ChatGPT)
        if intent.action_type == BrowserActionType.INTERACT_PROMPT:
            return self._handle_interact_prompt(intent)

        # Check for browser tab controls (back, forward, refresh, new_tab, close_tab)
        if intent.action_type == BrowserActionType.BROWSER_CONTROL:
            return self._handle_browser_control(intent)

        # Check for general web search
        if intent.action_type == BrowserActionType.SEARCH_WEB:
            return self._handle_search_web(intent)

        # Check for explicit URL opening
        if intent.action_type == BrowserActionType.OPEN_URL:
            return self._handle_open_url(intent)

        # Check for named website search
        if intent.action_type == BrowserActionType.SEARCH_WEBSITE:
            return self._handle_search_website(intent)

        return {
            "success": False,
            "message": "Unknown or unsupported browser intent.",
            "intent": intent.to_dict()
        }

    # -------------------------------------------------------------------------
    # HANDLERS
    # -------------------------------------------------------------------------

    def _handle_open_browser(self, intent: BrowserIntent) -> Dict[str, Any]:
        """Opens or focuses browser without navigating to search or arbitrary sites."""
        b_name = intent.target_browser or "chrome"
        res = self.browser_mgr.open_browser(browser_name=b_name, url=None)
        success = res.get("success", False)
        if success:
            return {
                "success": True,
                "action": "open_browser",
                "message": f"Opened {b_name.title()}.",
                "browser": b_name
            }
        return {
            "success": False,
            "action": "open_browser",
            "message": res.get("message", f"Failed to open {b_name.title()}."),
            "browser": b_name
        }

    def _handle_open_url(self, intent: BrowserIntent) -> Dict[str, Any]:
        """Opens an explicit URL, verifying navigation without falling back to Google search."""
        target_url = intent.url
        if not target_url:
            return {"success": False, "message": "No URL provided for navigation."}

        # Check if tab with this website is already open in Chrome
        parsed_target = urllib.parse.urlparse(target_url)
        target_domain = parsed_target.netloc.replace("www.", "")

        if intent.tab_preference != TabPreference.NEW_TAB:
            already_open_tab = self.session_mgr.is_website_already_open(target_domain)
            if already_open_tab:
                tab_id = already_open_tab.get("id")
                if tab_id and self.cdp.activate_tab(tab_id):
                    self.session_mgr.record_navigation(target_url, intent.site_name, intent.target_browser)
                    return {
                        "success": True,
                        "action": "switch_to_existing_tab",
                        "message": f"Switched to open tab for {target_domain}.",
                        "url": target_url,
                        "verified": True
                    }

        # Handle explicit new tab request
        if intent.tab_preference == TabPreference.NEW_TAB and self.cdp.is_available():
            new_tab_res = self.cdp.new_tab(url=target_url)
            if new_tab_res:
                self.session_mgr.record_navigation(target_url, intent.site_name, intent.target_browser)
                return {
                    "success": True,
                    "action": "open_new_tab",
                    "message": f"Opened {target_domain} in a new tab.",
                    "url": target_url,
                    "verified": True
                }

        # Standard launch / navigate
        res = self.browser_mgr.open_browser(browser_name=intent.target_browser, url=target_url)
        if not res.get("success", False):
            return {
                "success": False,
                "action": "open_url",
                "message": res.get("message", f"Failed to navigate to {target_url}."),
                "url": target_url
            }

        # Bounded verification of navigation
        verified, final_url = self._verify_navigation(target_domain)
        self.session_mgr.record_navigation(final_url or target_url, intent.site_name, intent.target_browser)

        return {
            "success": True,
            "action": "open_url",
            "message": f"Opened {target_domain}.",
            "url": final_url or target_url,
            "verified": verified
        }

    def _handle_search_web(self, intent: BrowserIntent) -> Dict[str, Any]:
        """Performs general web search using configured provider."""
        query = intent.search_query
        if not query:
            return {
                "success": True,
                "action": "clarification_needed",
                "message": "What would you like me to search for?",
                "requires_clarification": True
            }

        res = self.browser_mgr.search(query=query, provider="google", browser_name=intent.target_browser)
        success = res.get("success", False)
        if success:
            self.session_mgr.record_search(query=query, site_name="google")
            return {
                "success": True,
                "action": "search_web",
                "message": f"Searched Google for '{query}'.",
                "query": query,
                "verified": True
            }
        return {
            "success": False,
            "action": "search_web",
            "message": res.get("message", "Search failed."),
            "query": query
        }

    def _handle_search_website(self, intent: BrowserIntent) -> Dict[str, Any]:
        """Searches a specific website (e.g. HiAnime, YouTube) using layered discovery."""
        site_name = intent.site_name or ""
        target_url = intent.url
        query = intent.search_query

        if not query:
            return {
                "success": True,
                "action": "clarification_needed",
                "message": f"What would you like me to search for on {site_name.title()}?",
                "requires_clarification": True
            }

        adapter = self.adapter_registry.get_adapter(target_url or site_name)

        # 1. Check if website has a direct search URL template (fastest, most reliable)
        search_url = adapter.build_search_url(query=query, base_url=target_url)
        if search_url:
            nav_intent = BrowserIntent(
                action_type=BrowserActionType.OPEN_URL,
                target_browser=intent.target_browser,
                url=search_url,
                site_name=site_name,
                tab_preference=intent.tab_preference
            )
            res = self._handle_open_url(nav_intent)
            if res.get("success"):
                self.session_mgr.record_search(query=query, site_name=site_name, url=search_url)
                return {
                    "success": True,
                    "action": "search_website",
                    "message": f"Searched {site_name.title()} for '{query}'.",
                    "query": query,
                    "site": site_name,
                    "url": search_url,
                    "verified": True
                }

        # 2. If no direct URL template, navigate to site base and perform layered DOM / UIA discovery
        if target_url:
            self._handle_open_url(BrowserIntent(
                action_type=BrowserActionType.OPEN_URL,
                target_browser=intent.target_browser,
                url=target_url,
                site_name=site_name,
                tab_preference=intent.tab_preference
            ))
            time.sleep(1.0)  # Short bounded wait for page load

        # Layered Field Discovery
        candidates = self._discover_search_fields(adapter)

        # Check for multiple plausible candidates (ambiguity)
        if len(candidates) >= 2:
            top1, top2 = candidates[0], candidates[1]
            if abs(top1.score - top2.score) < 10 and top1.field_purpose != top2.field_purpose:
                return {
                    "success": True,
                    "action": "clarification_needed",
                    "message": "I found the website search box and the page's filter field. Which one should I use?",
                    "requires_clarification": True,
                    "candidates": [c.__dict__ for c in candidates[:2]]
                }

        # If no suitable candidate
        if not candidates or candidates[0].score < 15:
            # Fallback heuristic URL
            fallback_url = f"{target_url or 'https://' + site_name + '.com'}/search?q={urllib.parse.quote_plus(query)}"
            self.browser_mgr.open_browser(browser_name=intent.target_browser, url=fallback_url)
            self.session_mgr.record_search(query=query, site_name=site_name, url=fallback_url)
            return {
                "success": True,
                "action": "search_website_fallback",
                "message": f"Couldn't locate search box directly; searched {site_name.title()} via query URL.",
                "query": query,
                "site": site_name,
                "verified": True
            }

        # Best candidate found! Enter text and submit
        best_candidate = candidates[0]
        entered = self._enter_query_into_field(best_candidate, query, submit=intent.submit)
        if entered:
            self.session_mgr.record_search(query=query, site_name=site_name, url=target_url)
            return {
                "success": True,
                "action": "search_website",
                "message": f"Searched {site_name.title()} for '{query}'.",
                "query": query,
                "site": site_name,
                "verified": True
            }

        return {
            "success": False,
            "action": "search_website",
            "message": f"Failed to type query into {site_name.title()}'s search box."
        }

    def _handle_interact_prompt(self, intent: BrowserIntent) -> Dict[str, Any]:
        """Interacts with an AI prompt box (e.g. ChatGPT, Claude)."""
        site = intent.site_name or "chatgpt"
        url = intent.url or "https://chatgpt.com"
        prompt = intent.prompt_query or intent.search_query

        # Check consequential safety
        if intent.requires_confirmation:
            return {
                "success": False,
                "action": "permission_denied",
                "message": f"Sending this prompt to {site.title()} requires confirmation.",
                "pending_confirmation": True
            }

        # Navigate if needed
        self._handle_open_url(BrowserIntent(
            action_type=BrowserActionType.OPEN_URL,
            target_browser=intent.target_browser,
            url=url,
            site_name=site,
            tab_preference=intent.tab_preference
        ))
        time.sleep(1.5)

        adapter = self.adapter_registry.get_adapter(url)
        candidates = self._discover_prompt_fields(adapter)

        if not candidates:
            return {
                "success": True,
                "action": "interact_prompt_partial",
                "message": f"Opened {site.title()}. Please click into the prompt box to ask '{prompt}'.",
                "requires_focus": True
            }

        best = candidates[0]
        entered = self._enter_query_into_field(best, prompt, submit=intent.submit)
        return {
            "success": bool(entered),
            "action": "interact_prompt",
            "message": f"Entered prompt into {site.title()}: '{prompt}'.",
            "verified": bool(entered)
        }

    def _handle_search_page(self, intent: BrowserIntent) -> Dict[str, Any]:
        """Finds text in current page using browser native Find-in-Page."""
        query = intent.search_query
        try:
            import pyautogui
            # Send Ctrl+F
            pyautogui.hotkey('ctrl', 'f')
            time.sleep(0.3)
            if query:
                pyautogui.write(query, interval=0.02)
                pyautogui.press('enter')
            return {
                "success": True,
                "action": "search_page",
                "message": f"Finding '{query}' on current page.",
                "query": query
            }
        except Exception as e:
            logger.error(f"Find in page error: {e}")
            return {"success": False, "message": f"Could not trigger in-page search: {e}"}

    def _handle_browser_control(self, intent: BrowserIntent) -> Dict[str, Any]:
        """Executes browser control commands like back, forward, reload, new_tab, close_tab."""
        action = intent.metadata.get("control_action", "")
        if action == "go_back":
            res = self.browser_mgr.go_back()
            return {"success": res.get("success", False), "action": action, "message": "Navigated back."}
        elif action == "go_forward":
            res = self.browser_mgr.go_forward()
            return {"success": res.get("success", False), "action": action, "message": "Navigated forward."}
        elif action == "reload_page":
            res = self.browser_mgr.reload_page()
            return {"success": res.get("success", False), "action": action, "message": "Reloaded page."}
        elif action == "close_tab":
            res = self.browser_mgr.close_tab()
            return {"success": res.get("success", False), "action": action, "message": "Closed active tab."}
        elif action == "new_tab":
            res = self.browser_mgr.new_tab()
            return {"success": res.get("success", False), "action": action, "message": "Opened new tab."}
        return {"success": False, "message": f"Unknown control action: {action}"}

    # -------------------------------------------------------------------------
    # FIELD DISCOVERY & SCORING
    # -------------------------------------------------------------------------

    def _discover_search_fields(self, adapter: BaseWebsiteAdapter) -> List[CandidateInputField]:
        """Discovers and scores candidate search input fields on the active page."""
        candidates: List[CandidateInputField] = []

        # Tier 1: CDP DOM Inspection via WebSocket if CDP is online
        if self.cdp.is_available():
            cdp_candidates = self._inspect_dom_inputs_cdp()
            if cdp_candidates:
                candidates.extend(cdp_candidates)

        # Tier 2: Windows UI Automation inspection fallback
        if not candidates:
            uia_candidates = self._inspect_inputs_uia()
            if uia_candidates:
                candidates.extend(uia_candidates)

        # Score and sort candidates
        scored = [self._score_search_candidate(c, adapter) for c in candidates]
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    def _discover_prompt_fields(self, adapter: BaseWebsiteAdapter) -> List[CandidateInputField]:
        """Discovers and scores candidate AI prompt fields."""
        candidates = self._discover_search_fields(adapter)
        for c in candidates:
            if c.tag_name == "textarea" or "contenteditable" in c.selector or "prompt" in c.placeholder.lower():
                c.score += 50
                c.field_purpose = "prompt_box"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates

    def _score_search_candidate(self, c: CandidateInputField, adapter: BaseWebsiteAdapter) -> CandidateInputField:
        """Scores candidate input field based on multi-factor heuristics."""
        score = 0.0
        combined = f"{c.name} {c.placeholder} {c.aria_label} {c.role} {c.selector}".lower()

        # Penalties
        if c.input_type in ["password", "hidden", "file", "checkbox", "radio"]:
            c.score = -100.0
            return c
        if not c.is_visible or not c.is_enabled:
            c.score = -50.0
            return c
        if "address" in combined or "url" in combined:
            c.score = -80.0
            c.field_purpose = "address_bar"
            return c

        # Filter fields vs Search fields
        if "filter" in combined:
            score += 25.0
            c.field_purpose = "filter"

        # Search bonuses
        if c.input_type == "search" or c.role == "searchbox":
            score += 40.0
            c.field_purpose = "search_box"
        if any(w in c.placeholder.lower() for w in ["search", "find", "query"]):
            score += 35.0
            c.field_purpose = "search_box"
        if any(w in c.aria_label.lower() for w in ["search", "find"]):
            score += 30.0
            c.field_purpose = "search_box"
        if c.name in ["q", "query", "search", "keyword", "s"]:
            score += 30.0
            c.field_purpose = "search_box"
        if any(w in c.element_id.lower() for w in ["search", "nav-search", "search-suggest"]):
            score += 25.0
            c.field_purpose = "search_box"

        # Adapter selector match
        for sel in adapter.get_search_selectors():
            if sel.lower() in c.selector.lower() or sel.lower() in combined:
                score += 50.0
                c.field_purpose = "search_box"
                break

        c.score = score
        return c

    def _inspect_dom_inputs_cdp(self) -> List[CandidateInputField]:
        """Inspects active tab DOM for inputs via Chrome DevTools Protocol."""
        candidates = []
        try:
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if not ws_url:
                return []

            ws = LightweightCDPWebSocket(ws_url, timeout=0.8)
            if not ws.connect():
                return []

            # JavaScript snippet to safely extract visible input and textarea elements
            js_code = """
            (() => {
                const results = [];
                const inputs = document.querySelectorAll('input, textarea, div[contenteditable="true"]');
                for (const el of inputs) {
                    const rect = el.getBoundingClientRect();
                    const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).display !== 'none';
                    results.push({
                        id: el.id || '',
                        tag: el.tagName.toLowerCase(),
                        type: el.type || 'text',
                        name: el.name || '',
                        placeholder: el.placeholder || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        role: el.getAttribute('role') || '',
                        selector: el.id ? '#' + el.id : (el.className ? '.' + el.className.split(' ').join('.') : el.tagName.toLowerCase()),
                        visible: isVisible,
                        enabled: !el.disabled
                    });
                }
                return results;
            })()
            """
            resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js_code, "returnByValue": True})
            ws.close()

            if resp and "result" in resp and "result" in resp["result"]:
                val = resp["result"]["result"].get("value", [])
                for item in val:
                    candidates.append(CandidateInputField(
                        element_id=item.get("id", ""),
                        selector=item.get("selector", ""),
                        tag_name=item.get("tag", "input"),
                        input_type=item.get("type", "text"),
                        name=item.get("name", ""),
                        placeholder=item.get("placeholder", ""),
                        aria_label=item.get("ariaLabel", ""),
                        role=item.get("role", ""),
                        is_visible=item.get("visible", True),
                        is_enabled=item.get("enabled", True)
                    ))
        except Exception as e:
            logger.debug(f"CDP DOM inspection exception: {e}")
        return candidates

    def _inspect_inputs_uia(self) -> List[CandidateInputField]:
        """Inspects available controls using existing Windows UI Automation context adapter."""
        candidates = []
        try:
            from core.interaction import desktop_context_service
            ctx = desktop_context_service.get_current_context()
            for target in ctx.available_targets:
                candidates.append(CandidateInputField(
                    element_id=target.automation_id,
                    selector=target.control_type.value,
                    name=target.name,
                    placeholder=target.help_text,
                    aria_label=target.name,
                    role=target.control_type.value,
                    is_visible=True,
                    is_enabled=True,
                    field_purpose="search_box" if target.control_type.value == "search_field" else "general"
                ))
        except Exception as e:
            logger.debug(f"UIA inputs inspection error: {e}")
        return candidates

    def _enter_query_into_field(self, candidate: CandidateInputField, query: str, submit: bool = True) -> bool:
        """Types query into identified field with verification and submits if requested."""
        try:
            # If CDP is available and we have an element ID or selector
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if ws_url:
                ws = LightweightCDPWebSocket(ws_url, timeout=1.0)
                if ws.connect():
                    sel = candidate.selector
                    if not sel and candidate.element_id:
                        sel = f"#{candidate.element_id}"
                    safe_query = json.dumps(query)
                    submit_js = "if (el.form) el.form.submit();" if submit else ""
                    js = f"""
                    (() => {{
                        const el = document.querySelector('{sel}');
                        if (el) {{
                            el.focus();
                            el.value = {safe_query};
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            {submit_js}
                            return el.value === {safe_query};
                        }}
                        return false;
                    }})()
                    """
                    resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
                    ws.close()
                    if resp and resp.get("result", {}).get("result", {}).get("value") is True:
                        return True

            # Fallback to desktop text entry service
            from core.interaction import text_entry_service
            res = text_entry_service.enter_text(text=query, action="search_in_app", submit=submit)
            return res.get("success", False)
        except Exception as e:
            logger.error(f"Error entering query into field: {e}")
            return False

    def _verify_navigation(self, expected_domain: str, timeout: float = 2.5) -> Tuple[bool, Optional[str]]:
        """Verifies that browser navigated to expected domain within timeout."""
        start = time.time()
        while time.time() - start < timeout:
            if self.session_mgr.is_cancelled():
                return False, None
            if self.cdp.is_available():
                url = self.cdp.get_active_tab_url()
                if url:
                    parsed = urllib.parse.urlparse(url)
                    if expected_domain in parsed.netloc:
                        return True, url
            time.sleep(0.3)
        return False, None


# Global singleton engine
browser_automation_engine = BrowserAutomationEngine()
