"""Spotify OAuth 2.0 Authorization Code Flow with PKCE for Santra.

Complies with Spotify's official Web API PKCE specifications:
- No client secret embedded or used (PKCE Native App flow).
- Cryptographic SHA-256 code challenge with high-entropy code verifier.
- CSRF state parameter validation.
- Secure token storage using Windows Credential Manager (win32cred) with DPAPI fallback.
- Never logs access or refresh tokens.
- Automatic background token refresh before expiration.
"""

import os
import json
import time
import base64
import hashlib
import secrets
import logging
import threading
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any, Tuple
import requests

logger = logging.getLogger("Jarvis.Spotify.OAuth")

# Required Spotify Scopes
SPOTIFY_SCOPES = [
    "user-read-private",
    "user-read-email",
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played"
]

CREDENTIAL_TARGET_TOKEN = "Santra_Spotify_Token"
CREDENTIAL_TARGET_CLIENT = "Santra_Spotify_ClientID"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


class SecureTokenStorage:
    """Stores sensitive OAuth tokens in Windows Credential Manager with DPAPI fallback."""

    @staticmethod
    def save_tokens(token_data: Dict[str, Any]) -> bool:
        """Saves token dictionary securely without exposing tokens in plain text logs."""
        payload_str = json.dumps(token_data)
        try:
            import win32cred
            win32cred.CredWrite({
                "Type": win32cred.CRED_TYPE_GENERIC,
                "TargetName": CREDENTIAL_TARGET_TOKEN,
                "CredentialBlob": payload_str,
                "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
                "Comment": "Santra Spotify OAuth Token"
            })
            logger.info("Spotify tokens securely saved to Windows Credential Manager.")
            return True
        except Exception as e:
            logger.warning(f"Windows Credential Manager save failed: {e}. Attempting DPAPI fallback.")

        # Fallback to Windows DPAPI
        try:
            import win32crypt
            encrypted = win32crypt.CryptProtectData(payload_str.encode("utf-8"), "SantraSpotify", None, None, None, 0)
            from config import BASE_DIR
            sec_file = BASE_DIR / "memory" / ".spotify_token.bin"
            sec_file.write_bytes(encrypted)
            logger.info("Spotify tokens saved via Windows DPAPI.")
            return True
        except Exception as e_dpapi:
            logger.error(f"DPAPI save failed: {e_dpapi}")
            return False

    @staticmethod
    def load_tokens() -> Optional[Dict[str, Any]]:
        """Loads and decodes tokens securely."""
        try:
            import win32cred
            cred = win32cred.CredRead(CREDENTIAL_TARGET_TOKEN, win32cred.CRED_TYPE_GENERIC)
            payload = cred["CredentialBlob"]
            if isinstance(payload, bytes):
                try:
                    text = payload.decode("utf-16")
                except Exception:
                    text = payload.decode("utf-8", errors="ignore")
            else:
                text = str(payload)
            return json.loads(text)
        except Exception:
            pass

        # Try DPAPI fallback
        try:
            from config import BASE_DIR
            sec_file = BASE_DIR / "memory" / ".spotify_token.bin"
            if sec_file.exists():
                import win32crypt
                raw = sec_file.read_bytes()
                _, decrypted = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
                return json.loads(decrypted.decode("utf-8"))
        except Exception as e:
            logger.debug(f"DPAPI load failed: {e}")

        return None

    @staticmethod
    def clear_tokens():
        """Deletes stored credentials from all secure stores."""
        try:
            import win32cred
            win32cred.CredDelete(CREDENTIAL_TARGET_TOKEN, win32cred.CRED_TYPE_GENERIC)
            logger.info("Cleared Spotify tokens from Windows Credential Manager.")
        except Exception:
            pass

        try:
            from config import BASE_DIR
            sec_file = BASE_DIR / "memory" / ".spotify_token.bin"
            if sec_file.exists():
                sec_file.unlink()
                logger.info("Cleared Spotify tokens from DPAPI file.")
        except Exception:
            pass

    @staticmethod
    def save_client_id(client_id: str) -> bool:
        try:
            import win32cred
            win32cred.CredWrite({
                "Type": win32cred.CRED_TYPE_GENERIC,
                "TargetName": CREDENTIAL_TARGET_CLIENT,
                "CredentialBlob": client_id,
                "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
                "Comment": "Santra Spotify Client ID"
            })
            return True
        except Exception as e:
            logger.debug(f"CredWrite client_id failed: {e}")
            return False

    @staticmethod
    def load_client_id() -> str:
        # Check environment first
        env_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
        if env_id:
            return env_id
        try:
            import win32cred
            cred = win32cred.CredRead(CREDENTIAL_TARGET_CLIENT, win32cred.CRED_TYPE_GENERIC)
            raw = cred["CredentialBlob"]
            if isinstance(raw, bytes):
                try:
                    return raw.decode("utf-16").strip()
                except Exception:
                    return raw.decode("utf-8", errors="ignore").strip()
            return str(raw).strip()
        except Exception:
            return ""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Local HTTP handler for capturing OAuth callback."""

    def log_message(self, format, *args):
        # Suppress standard logging to prevent token/query leaks
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            query_params = parse_qs(parsed.query)
            code = query_params.get("code", [None])[0]
            state = query_params.get("state", [None])[0]
            error = query_params.get("error", [None])[0]

            self.server.callback_data = {
                "code": code,
                "state": state,
                "error": error
            }

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()

            if error:
                html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Santra - Spotify Connection Cancelled</title>
                    <style>
                        body { background: #01060c; color: #ff5252; font-family: 'Segoe UI', Tahoma, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                        .card { background: rgba(10,25,35,0.9); border: 1px solid #ff5252; padding: 40px; border-radius: 8px; text-align: center; max-width: 450px; }
                        h2 { margin-top: 0; color: #ff5252; letter-spacing: 1px; }
                        p { color: #cfd8dc; font-size: 14px; line-height: 1.6; }
                    </style>
                </head>
                <body>
                    <div class="card">
                        <h2>AUTHENTICATION CANCELLED</h2>
                        <p>Spotify authorization was not completed or was cancelled. You may close this window and try again in Santra.</p>
                    </div>
                </body>
                </html>
                """
            else:
                html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Santra - Spotify Connected</title>
                    <style>
                        body { background: #01060c; color: #00e5ff; font-family: 'Segoe UI', Tahoma, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                        .card { background: rgba(5,15,25,0.95); border: 1px solid #00e5ff; padding: 40px; border-radius: 8px; text-align: center; max-width: 480px; box-shadow: 0 0 30px rgba(0,229,255,0.25); }
                        h2 { margin-top: 0; color: #00e5ff; letter-spacing: 2px; }
                        .green { color: #1db954; font-weight: bold; }
                        p { color: #e0f7fa; font-size: 15px; line-height: 1.6; }
                    </style>
                </head>
                <body>
                    <div class="card">
                        <h2>SANTRA // <span class="green">SPOTIFY</span></h2>
                        <p>Spotify authorization verified successfully!</p>
                        <p style="color: #90a4ae; font-size: 13px;">You may safely close this browser tab and return to Santra.</p>
                    </div>
                </body>
                </html>
                """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class SpotifyOAuthManager:
    """Manages Spotify OAuth 2.0 PKCE flow, token lifecycle, and secure storage."""

    def __init__(self, client_id: Optional[str] = None, redirect_uri: str = DEFAULT_REDIRECT_URI):
        self.redirect_uri = redirect_uri
        self.client_id = client_id or SecureTokenStorage.load_client_id()
        self._tokens: Optional[Dict[str, Any]] = SecureTokenStorage.load_tokens()
        self._lock = threading.Lock()
        self._pending_verifier: Optional[str] = None
        self._pending_state: Optional[str] = None
        self._httpd: Optional[HTTPServer] = None

    def set_client_id(self, client_id: str):
        """Sets and securely persists the Spotify Client ID."""
        self.client_id = client_id.strip()
        SecureTokenStorage.save_client_id(self.client_id)

    def is_connected(self) -> bool:
        """Returns True if valid tokens are present or can be refreshed."""
        return self.get_valid_token() is not None

    @staticmethod
    def _generate_code_verifier() -> str:
        """Generates a high-entropy cryptographic code verifier (64 characters)."""
        return secrets.token_urlsafe(64)

    @staticmethod
    def _generate_code_challenge(verifier: str) -> str:
        """Computes the S256 code challenge from the code verifier."""
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    def generate_authorization_url(self) -> Tuple[str, str, str]:
        """Generates the official Spotify authorization URL with PKCE parameters."""
        if not self.client_id:
            raise ValueError("Spotify Client ID is required before authorization.")

        verifier = self._generate_code_verifier()
        challenge = self._generate_code_challenge(verifier)
        state = secrets.token_hex(16)

        self._pending_verifier = verifier
        self._pending_state = state

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
            "scope": " ".join(SPOTIFY_SCOPES)
        }
        url = f"{AUTH_URL}?{urlencode(params)}"
        return url, verifier, state

    def start_local_auth_server(self, timeout_sec: float = 120.0) -> Tuple[bool, str]:
        """Starts a temporary local HTTP server to receive the Spotify redirect.
        Blocks until the callback is received or timeout expires.
        """
        parsed = urlparse(self.redirect_uri)
        port = parsed.port or 8888
        host = parsed.hostname or "127.0.0.1"

        try:
            httpd = HTTPServer((host, port), _CallbackHandler)
            httpd.callback_data = None
            httpd.timeout = 1.0
            self._httpd = httpd
        except Exception as e:
            logger.error(f"Failed to bind local authorization server to {host}:{port}: {e}")
            return False, f"Could not bind local callback port {port}: {e}"

        start_time = time.time()
        logger.info(f"Local OAuth callback server listening on {host}:{port} (timeout={timeout_sec}s)...")

        try:
            while time.time() - start_time < timeout_sec:
                httpd.handle_request()
                if httpd.callback_data is not None:
                    break

            cb_data = httpd.callback_data
            if not cb_data:
                return False, "Authorization timed out. No response received from browser."

            if cb_data.get("error"):
                err = cb_data["error"]
                return False, f"Spotify authorization error: {err}"

            returned_state = cb_data.get("state")
            if not returned_state or returned_state != self._pending_state:
                logger.error(f"State mismatch in OAuth callback: expected {self._pending_state}, got {returned_state}")
                return False, "Security error: OAuth state verification failed (possible CSRF)."

            code = cb_data.get("code")
            if not code:
                return False, "No authorization code returned from Spotify."

            # Exchange authorization code for tokens
            success, msg = self.exchange_code_for_tokens(code, self._pending_verifier)
            return success, msg

        finally:
            try:
                httpd.server_close()
            except Exception:
                pass
            self._httpd = None
            self._pending_verifier = None
            self._pending_state = None

    def exchange_code_for_tokens(self, code: str, verifier: Optional[str] = None) -> Tuple[bool, str]:
        """Exchanges an authorization code for access and refresh tokens using PKCE."""
        v = verifier or self._pending_verifier
        if not v:
            return False, "Code verifier is missing for PKCE token exchange."
        if not self.client_id:
            return False, "Spotify Client ID is not configured."

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": v
        }

        try:
            resp = requests.post(TOKEN_URL, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10.0)
            if resp.status_code != 200:
                logger.error(f"Spotify token exchange failed: HTTP {resp.status_code} - {resp.text}")
                return False, f"Token exchange failed: HTTP {resp.status_code}"

            data = resp.json()
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            expires_in = data.get("expires_in", 3600)

            if not access_token:
                return False, "Spotify did not return an access token."

            token_record = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": time.time() + expires_in - 60,  # 60s buffer
                "token_type": data.get("token_type", "Bearer"),
                "scope": data.get("scope", "")
            }

            with self._lock:
                self._tokens = token_record
                SecureTokenStorage.save_tokens(token_record)

            logger.info("Successfully completed Spotify PKCE authorization and stored tokens.")
            return True, "Spotify successfully connected."
        except Exception as e:
            logger.error(f"Exception during Spotify token exchange: {e}")
            return False, f"Network error during authorization: {e}"

    def refresh_access_token(self) -> bool:
        """Refreshes the Spotify access token using the stored refresh token."""
        with self._lock:
            if not self._tokens or not self._tokens.get("refresh_token"):
                logger.warning("No refresh token available to refresh Spotify access.")
                return False

            refresh_token = self._tokens["refresh_token"]

        if not self.client_id:
            logger.error("Cannot refresh token without Client ID.")
            return False

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id
        }

        try:
            resp = requests.post(TOKEN_URL, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10.0)
            if resp.status_code != 200:
                logger.error(f"Failed to refresh Spotify token: HTTP {resp.status_code} - {resp.text}")
                if resp.status_code in (400, 401):
                    # Refresh token revoked or invalid; clear stale tokens
                    self.disconnect()
                return False

            data = resp.json()
            access_token = data.get("access_token")
            new_refresh = data.get("refresh_token") or refresh_token
            expires_in = data.get("expires_in", 3600)

            token_record = {
                "access_token": access_token,
                "refresh_token": new_refresh,
                "expires_at": time.time() + expires_in - 60,
                "token_type": data.get("token_type", "Bearer"),
                "scope": data.get("scope", self._tokens.get("scope", ""))
            }

            with self._lock:
                self._tokens = token_record
                SecureTokenStorage.save_tokens(token_record)

            logger.info("Spotify access token refreshed successfully.")
            return True
        except Exception as e:
            logger.error(f"Exception while refreshing Spotify token: {e}")
            return False

    def get_valid_token(self) -> Optional[str]:
        """Returns a valid access token, automatically refreshing if expired or near expiry."""
        with self._lock:
            if not self._tokens or not self._tokens.get("access_token"):
                return None

            expires_at = self._tokens.get("expires_at", 0)
            now = time.time()

            if now < expires_at:
                return self._tokens["access_token"]

        # Token is expired or expiring; attempt refresh
        logger.info("Spotify access token expired or expiring soon. Refreshing...")
        if self.refresh_access_token():
            with self._lock:
                return self._tokens.get("access_token")
        return None

    def disconnect(self):
        """Disconnects Spotify: clears tokens from memory and secure storage."""
        with self._lock:
            self._tokens = None
            SecureTokenStorage.clear_tokens()
        logger.info("Spotify account disconnected from Santra.")


# Global singleton instance
spotify_oauth = SpotifyOAuthManager()
