"""Low-level Spotify Web API v1 HTTP Client for Santra.

Provides:
- Reusable connection pooling via requests.Session.
- Automatic Bearer token management & refresh on HTTP 401.
- Spotify rate limit handling (HTTP 429 with Retry-After).
- Fine-grained exception & error classification (PREMIUM_REQUIRED, NO_ACTIVE_DEVICE, etc.).
- Short-lived TTL caching for non-sensitive metadata (devices, profile).
- Explicit cache invalidation on mutations.
"""

import time
import logging
from typing import Optional, Dict, Any, List, Union
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from modules.spotify.oauth_manager import SpotifyOAuthManager, spotify_oauth

logger = logging.getLogger("Jarvis.Spotify.Client")

BASE_API_URL = "https://api.spotify.com/v1"


class SpotifyApiError(Exception):
    """Base exception for Spotify Web API failures."""
    def __init__(self, message: str, status_code: int = 0, reason: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class SpotifyPremiumRequiredError(SpotifyApiError):
    """Raised when an operation (such as player controls) requires a Spotify Premium subscription."""
    def __init__(self, message: str = "This playback feature requires a Spotify Premium account."):
        super().__init__(message, status_code=403, reason="PREMIUM_REQUIRED")


class SpotifyNoActiveDeviceError(SpotifyApiError):
    """Raised when no active Spotify Connect playback device is currently running or reachable."""
    def __init__(self, message: str = "No active Spotify device found. Please open Spotify on your PC or phone."):
        super().__init__(message, status_code=404, reason="NO_ACTIVE_DEVICE")


class SpotifyRateLimitError(SpotifyApiError):
    """Raised when Spotify rate limit is exceeded."""
    def __init__(self, retry_after: int = 1):
        super().__init__(f"Spotify rate limit exceeded. Retry after {retry_after}s.", status_code=429, reason="RATE_LIMITED")
        self.retry_after = retry_after


class SpotifyClient:
    """Robust HTTP client for Spotify Web API."""

    def __init__(self, oauth_manager: Optional[SpotifyOAuthManager] = None):
        self.oauth = oauth_manager or spotify_oauth
        self._session = requests.Session()
        
        # Configure connection pool with subtle socket-level retries
        retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

        # Non-sensitive short-lived caches: key -> (timestamp, data)
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._default_timeout = 10.0

    def _get_cached(self, key: str, ttl_sec: float) -> Optional[Any]:
        if key in self._cache:
            ts, val = self._cache[key]
            if time.time() - ts < ttl_sec:
                return val
            del self._cache[key]
        return None

    def _set_cached(self, key: str, val: Any):
        self._cache[key] = (time.time(), val)

    def invalidate_cache(self, prefix: Optional[str] = None):
        """Invalidates cache entries matching the given prefix or all entries if None."""
        if prefix is None:
            self._cache.clear()
        else:
            keys_to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_del:
                del self._cache[k]

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        use_cache_ttl: Optional[float] = None,
        retry_on_401: bool = True
    ) -> Any:
        """Executes an authenticated HTTP request to Spotify Web API."""
        url = endpoint if endpoint.startswith("http") else f"{BASE_API_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        cache_key = f"{method}:{url}:{str(params)}"

        if method.upper() == "GET" and use_cache_ttl:
            cached = self._get_cached(cache_key, use_cache_ttl)
            if cached is not None:
                return cached

        token = self.oauth.get_valid_token()
        if not token:
            raise SpotifyApiError("Spotify account is not connected or authorization is expired.", status_code=401)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            resp = self._session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_data,
                headers=headers,
                timeout=self._default_timeout
            )
        except requests.RequestException as e:
            logger.error(f"Network error communicating with Spotify API: {e}")
            raise SpotifyApiError(f"Network error communicating with Spotify: {e}", status_code=0)

        # Handle 401 Unauthorized (attempt token refresh once)
        if resp.status_code == 401 and retry_on_401:
            logger.info("Received HTTP 401 from Spotify. Refreshing token and retrying request...")
            if self.oauth.refresh_access_token():
                return self.request(
                    method=method,
                    endpoint=endpoint,
                    params=params,
                    json_data=json_data,
                    use_cache_ttl=use_cache_ttl,
                    retry_on_401=False
                )
            raise SpotifyApiError("Spotify session expired. Please reconnect in settings.", status_code=401)

        # Handle 429 Rate Limit
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 1))
            logger.warning(f"Spotify rate limited us! Retry-After: {retry_after}s")
            if retry_after <= 3:
                time.sleep(retry_after)
                return self.request(
                    method=method,
                    endpoint=endpoint,
                    params=params,
                    json_data=json_data,
                    use_cache_ttl=use_cache_ttl,
                    retry_on_401=retry_on_401
                )
            raise SpotifyRateLimitError(retry_after)

        # Handle 204 No Content (standard for player control and track modify endpoints)
        if resp.status_code == 204:
            return {"status": "success", "status_code": 204}

        # Handle 403 Forbidden
        if resp.status_code == 403:
            err_json = {}
            try:
                err_json = resp.json().get("error", {})
            except Exception:
                pass
            msg = err_json.get("message", "Forbidden")
            reason = err_json.get("reason", "")
            if "PREMIUM_REQUIRED" in reason or "Premium required" in msg or "Restriction violated" in msg:
                raise SpotifyPremiumRequiredError()
            raise SpotifyApiError(f"Spotify permission error: {msg}", status_code=403, reason=reason)

        # Handle 404 Not Found
        if resp.status_code == 404:
            err_json = {}
            try:
                err_json = resp.json().get("error", {})
            except Exception:
                pass
            msg = err_json.get("message", "Not Found")
            reason = err_json.get("reason", "")
            if "NO_ACTIVE_DEVICE" in reason or "No active device" in msg or "Device not found" in msg:
                raise SpotifyNoActiveDeviceError()
            raise SpotifyApiError(f"Spotify resource not found: {msg}", status_code=404, reason=reason)

        # Other HTTP errors
        if not (200 <= resp.status_code < 300):
            err_text = resp.text
            try:
                err_text = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                pass
            raise SpotifyApiError(f"Spotify API error ({resp.status_code}): {err_text}", status_code=resp.status_code)

        # Successful response
        try:
            data = resp.json()
        except ValueError:
            data = {"status": "success", "status_code": resp.status_code}

        if method.upper() == "GET" and use_cache_ttl:
            self._set_cached(cache_key, data)

        return data

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, cache_ttl: Optional[float] = None) -> Any:
        return self.request("GET", endpoint, params=params, use_cache_ttl=cache_ttl)

    def post(self, endpoint: str, json_data: Optional[Any] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        self.invalidate_cache()
        return self.request("POST", endpoint, params=params, json_data=json_data)

    def put(self, endpoint: str, json_data: Optional[Any] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        self.invalidate_cache()
        return self.request("PUT", endpoint, params=params, json_data=json_data)

    def delete(self, endpoint: str, json_data: Optional[Any] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        self.invalidate_cache()
        return self.request("DELETE", endpoint, params=params, json_data=json_data)


# Global singleton instance
spotify_client = SpotifyClient()
