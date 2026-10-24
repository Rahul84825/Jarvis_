"""Chrome DevTools Protocol (CDP) Client.
Provides native interaction with Chromium/Chrome instances launched with remote debugging
(e.g., --remote-debugging-port=9222) with graceful, verified error handling when CDP is unavailable.
Strictly restricted to localhost (127.0.0.1) for security.
"""

import os
import json
import socket
import struct
import base64
import logging
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.CDPClient")

class CDPClient:
    """Manages HTTP inspection, diagnostics, and control of running Chrome via Chrome DevTools Protocol."""

    def __init__(self, port: int = 9222, host: str = "127.0.0.1"):
        # Security restriction: Only allow loopback interface
        if host not in ["127.0.0.1", "localhost"]:
            logger.warning(f"[CDP] Untrusted host '{host}' requested. Forcing loopback 127.0.0.1.")
            host = "127.0.0.1"

        self.port = port
        self.host = host
        self.base_url = f"http://{host}:{port}"
        self.timeout = 0.8  # Fast non-blocking timeout

    def is_chrome_running(self) -> bool:
        """Detects whether a Chrome browser process is currently active on the host OS."""
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                name = (p.info.get("name") or "").lower()
                if name in ("chrome.exe", "chrome", "google-chrome"):
                    return True
        except Exception as e:
            logger.debug(f"[CDP] Process detection check failed: {e}")
        return False

    def is_available(self) -> bool:
        """Checks if Chrome DevTools Protocol HTTP port is actively responding with fast socket check and caching."""
        import time
        now = time.time()
        if hasattr(self, "_last_avail_check") and (now - self._last_avail_check) < 1.0:
            return getattr(self, "_last_avail_val", False)

        self._last_avail_check = now
        # Fast socket pre-check avoids 800ms urllib timeouts when port is closed
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.04)
        try:
            if sock.connect_ex((self.host, self.port)) != 0:
                self._last_avail_val = False
                return False
        except Exception:
            self._last_avail_val = False
            return False
        finally:
            try:
                sock.close()
            except Exception:
                pass

        try:
            req = urllib.request.Request(f"{self.base_url}/json/version", headers={"User-Agent": "Jarvis-Assistant"})
            with urllib.request.urlopen(req, timeout=0.2) as resp:
                self._last_avail_val = (resp.status == 200)
                return self._last_avail_val
        except Exception:
            self._last_avail_val = False
            return False

    def get_endpoint_diagnostics(self) -> Dict[str, Any]:
        """Provides actionable diagnostics on Chrome and CDP endpoint status."""
        chrome_open = self.is_chrome_running()
        port_open = False
        cdp_online = False
        port_conflict = False

        # 1. Check if port is open locally
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        try:
            res = sock.connect_ex((self.host, self.port))
            port_open = (res == 0)
        except Exception:
            port_open = False
        finally:
            sock.close()

        # 2. Check if CDP version endpoint responds
        version_info = None
        if port_open:
            version_info = self.get_version_info()
            if version_info and isinstance(version_info, dict) and "Browser" in version_info:
                cdp_online = True
            else:
                port_conflict = True

        if cdp_online:
            guidance = "CDP is connected and ready for page inspection and tab management."
            status = "online"
        elif port_conflict:
            guidance = "The debugging port is already in use by another process."
            status = "port_conflict"
        elif chrome_open:
            guidance = "Chrome is open, but this session does not expose a local debugging endpoint."
            status = "chrome_running_no_cdp"
        else:
            guidance = "Chrome is not currently running."
            status = "chrome_closed"

        return {
            "cdp_available": cdp_online,
            "chrome_running": chrome_open,
            "port_open": port_open,
            "port_conflict": port_conflict,
            "status": status,
            "host": self.host,
            "port": self.port,
            "browser_version": version_info.get("Browser") if version_info else None,
            "guidance": guidance
        }

    def get_status_report(self) -> Dict[str, Any]:
        """Returns diagnostic report of CDP availability with actionable guidance."""
        diag = self.get_endpoint_diagnostics()
        return {
            "available": diag["cdp_available"],
            "host": self.host,
            "port": self.port,
            "browser_version": diag.get("browser_version"),
            "guidance": diag["guidance"],
            "diagnostics": diag
        }

    def get_version_info(self) -> Optional[Dict[str, Any]]:
        """Fetches browser version and CDP endpoints."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/version", headers={"User-Agent": "Jarvis-Assistant"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"[CDP] Version check failed: {e}")
            return None

    def list_tabs(self) -> List[Dict[str, Any]]:
        """Returns list of open page tabs with title and URL."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/list", headers={"User-Agent": "Jarvis-Assistant"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = [tab for tab in data if tab.get("type") == "page"]
                return pages
        except Exception as e:
            logger.debug(f"[CDP] Tab listing unavailable: {e}")
            return []

    def get_active_tab(self) -> Optional[Dict[str, Any]]:
        """Gets currently active tab or first open page."""
        tabs = self.list_tabs()
        if tabs:
            return tabs[0]
        return None

    def get_active_tab_title(self) -> Optional[str]:
        """Returns the title of the active tab."""
        tab = self.get_active_tab()
        return tab.get("title") if tab else None

    def get_active_tab_url(self) -> Optional[str]:
        """Returns the URL of the active tab."""
        tab = self.get_active_tab()
        return tab.get("url") if tab else None

    def evaluate_script(self, script: str, timeout: float = 1.0) -> Dict[str, Any]:
        """Evaluates JavaScript expression in active tab via CDP WebSocket using standard library."""
        tab = self.get_active_tab()
        if not tab or not tab.get("webSocketDebuggerUrl"):
            return {"success": False, "error": "No active tab WebSocket URL available."}

        ws_url = tab["webSocketDebuggerUrl"]
        parsed = urllib.parse.urlparse(ws_url)
        path = parsed.path
        if parsed.query:
            path += f"?{parsed.query}"

        # Connect strictly to localhost socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self.host, self.port))
            # 1. RFC 6455 Handshake
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n\r\n"
            )
            sock.sendall(req.encode("ascii"))
            resp_header = b""
            while b"\r\n\r\n" not in resp_header:
                chunk = sock.recv(512)
                if not chunk:
                    break
                resp_header += chunk
            if b"101 Switching Protocols" not in resp_header:
                return {"success": False, "error": "WebSocket handshake failed"}

            # 2. Build payload and masked frame
            payload = json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": script, "returnByValue": True}
            }).encode("utf-8")
            mask = os.urandom(4)
            length = len(payload)
            if length < 126:
                header = bytes([0x81, 0x80 | length]) + mask
            elif length < 65536:
                header = bytes([0x81, 0x80 | 126]) + struct.pack("!H", length) + mask
            else:
                header = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", length) + mask
            masked = bytes([b ^ mask[i % 4] for i, b in enumerate(payload)])
            sock.sendall(header + masked)

            # 3. Read response frame
            data = sock.recv(4096)
            if len(data) >= 2:
                b2 = data[1]
                is_m = bool(b2 & 0x80)
                l = b2 & 0x7F
                off = 2
                if l == 126:
                    l = struct.unpack("!H", data[off:off+2])[0]
                    off += 2
                elif l == 127:
                    l = struct.unpack("!Q", data[off:off+8])[0]
                    off += 8
                if is_m:
                    m = data[off:off+4]
                    off += 4
                    raw_p = bytes([b ^ m[i % 4] for i, b in enumerate(data[off:off+l])])
                else:
                    raw_p = data[off:off+l]

                res = json.loads(raw_p.decode("utf-8", errors="replace"))
                val = res.get("result", {}).get("result", {}).get("value")
                return {"success": True, "value": val}
            return {"success": False, "error": "Empty WebSocket response frame"}
        except Exception as e:
            logger.debug(f"[CDP] Script evaluation over WebSocket error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def inspect_active_page(self) -> Dict[str, Any]:
        """Performs verified page inspection via CDP, extracting DOM text and semantic metadata."""
        diag = self.get_endpoint_diagnostics()
        if not diag["cdp_available"]:
            msg = diag["guidance"]
            if "--remote-debugging-port=9222" not in msg:
                msg = f"{msg} Launch Chrome with '--remote-debugging-port=9222' on localhost to enable CDP page inspection."
            return {
                "success": False,
                "cdp_available": False,
                "chrome_running": diag["chrome_running"],
                "port_conflict": diag["port_conflict"],
                "status": diag["status"],
                "message": msg
            }

        tab = self.get_active_tab()
        if not tab:
            return {
                "success": False,
                "cdp_available": True,
                "message": "I connected to Chrome, but no open web pages were found."
            }

        title = tab.get("title", "Untitled")
        url = tab.get("url", "")

        # Evaluate extraction script to get headings and clean body text
        js_extract = """
        (() => {
            try {
                const title = document.title || "";
                const url = window.location.href || "";
                const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
                    .map(h => (h.innerText || "").trim())
                    .filter(t => t.length > 0)
                    .slice(0, 10);
                const bodyClone = document.body ? document.body.cloneNode(true) : null;
                let text = "";
                if (bodyClone) {
                    const toRemove = bodyClone.querySelectorAll('script, style, noscript, svg, nav, footer');
                    toRemove.forEach(el => el.remove());
                    text = (bodyClone.innerText || "").replace(/\\s+/g, ' ').trim().slice(0, 4000);
                }
                return { title, url, headings, text };
            } catch(e) {
                return { error: String(e) };
            }
        })()
        """
        eval_res = self.evaluate_script(js_extract, timeout=1.0)
        headings: List[str] = []
        content = ""
        if eval_res.get("success") and isinstance(eval_res.get("value"), dict):
            val = eval_res["value"]
            title = val.get("title") or title
            url = val.get("url") or url
            headings = val.get("headings") or []
            content = val.get("text") or ""

        return {
            "success": True,
            "cdp_available": True,
            "tab_id": tab.get("id"),
            "title": title,
            "url": url,
            "headings": headings,
            "content": content,
            "source": "cdp",
            "message": f"Active page: '{title}' ({url})."
        }

    def new_tab(self, url: str = "") -> Optional[Dict[str, Any]]:
        """Creates a new browser tab via CDP."""
        try:
            target = f"{self.base_url}/json/new"
            if url:
                target += f"?{urllib.parse.quote(url, safe=':/?=&')}"
            req = urllib.request.Request(target, method="PUT", headers={"User-Agent": "Jarvis-Assistant"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"[CDP] New tab creation via CDP failed: {e}")
            return None

    def activate_tab(self, tab_id: str) -> bool:
        """Focuses/activates a specific tab by ID."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/activate/{tab_id}", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug(f"[CDP] Tab activation failed: {e}")
            return False

    def close_tab(self, tab_id: str) -> bool:
        """Closes a specific tab by ID."""
        try:
            req = urllib.request.Request(f"{self.base_url}/json/close/{tab_id}", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug(f"[CDP] Tab close failed: {e}")
            return False

    def verify_tab_closed(self, tab_id: str) -> bool:
        """Verifies that a specific tab ID is no longer present in open tabs."""
        try:
            tabs = self.list_tabs()
            return not any(t.get("id") == tab_id for t in tabs)
        except Exception as e:
            logger.debug(f"[CDP] Tab close verification error: {e}")
            return False

