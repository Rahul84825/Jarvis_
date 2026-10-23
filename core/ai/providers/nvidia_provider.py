import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Generator
import requests

from core.ai.base_provider import BaseAIProvider
from config import config

logger = logging.getLogger("Jarvis.NvidiaProvider")

class NvidiaNemotronProvider(BaseAIProvider):
    """NVIDIA Nemotron Cloud Reasoning Provider.
    Interfaces with NVIDIA's OpenAI-compatible API endpoint for Nemotron models
    (e.g. nvidia/nemotron-3.5-super-vl-120b-a12b).
    Features:
      - Configurable model and base URL
      - Safe credential isolation (never logs or reveals keys)
      - Non-blocking timeout and bounded exponential backoff retries for 429 / 5xx
      - Clean reasoning extraction (separating internal chain-of-thought from user content)
      - Native OpenAI-compatible tool call support
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None
    ):
        self.api_key = api_key if api_key is not None else (getattr(config, "nvidia_api_key", "") or os.environ.get("NVIDIA_API_KEY", ""))
        self.model = model or getattr(config, "nvidia_model", "nvidia/nemotron-3.5-super-vl-120b-a12b")
        self.base_url = (base_url or getattr(config, "nvidia_base_url", "https://integrate.api.nvidia.com/v1")).rstrip("/")
        self.timeout = timeout or getattr(config, "nvidia_timeout_sec", 25.0)
        self.max_retries = max_retries if max_retries is not None else getattr(config, "nvidia_max_retries", 3)
        self.temperature = getattr(config, "nvidia_temperature", 0.6)
        self.max_tokens = getattr(config, "nvidia_max_tokens", 2048)

    def get_name(self) -> str:
        return f"NVIDIA Nemotron ({self.model.split('/')[-1]})"

    def is_available(self) -> bool:
        key = self.api_key if self.api_key is not None else (getattr(config, "nvidia_api_key", "") or os.environ.get("NVIDIA_API_KEY", ""))
        return bool(key and len(key.strip()) > 10)

    def _sanitize_error_message(self, err_msg: str) -> str:
        """Ensures no API key or sensitive token appears in logs or error traces."""
        if not self.api_key:
            return err_msg
        clean_key = self.api_key.strip()
        if len(clean_key) > 5 and clean_key in err_msg:
            return err_msg.replace(clean_key, "[REDACTED_NVIDIA_KEY]")
        return err_msg

    def health_check(self) -> bool:
        """Lightweight connectivity check against NVIDIA models endpoint."""
        if not self.is_available():
            return False
        url = f"{self.base_url}/models"
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "User-Agent": "JARVIS-Assistant/1.1"
        }
        try:
            resp = requests.get(url, headers=headers, timeout=min(5.0, self.timeout))
            return resp.status_code == 200
        except Exception as e:
            logger.debug(f"[NVIDIA] Health check failed: {self._sanitize_error_message(str(e))}")
            return False

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Generates a text completion or tool call response from NVIDIA Nemotron.
        Handles reasoning model formatting, bounded retries, and network error categorization.
        """
        if not self.is_available():
            logger.debug("[NVIDIA] Provider unavailable (missing or empty NVIDIA_API_KEY).")
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "JARVIS-Assistant/1.1"
        }

        ctx = context or {}
        max_tokens = ctx.get("max_tokens", self.max_tokens)
        temperature = ctx.get("temperature", self.temperature)
        tools = ctx.get("tools")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        if tools and isinstance(tools, list):
            payload["tools"] = tools

        attempt = 0
        backoff_delay = 1.0

        while attempt < self.max_retries:
            attempt += 1
            try:
                t0 = time.time()
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                duration_ms = (time.time() - t0) * 1000

                # Case 1: Success (200 OK)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        logger.warning("[NVIDIA] Empty choices array returned by API.")
                        return None

                    msg_obj = choices[0].get("message", {})
                    content = msg_obj.get("content")
                    tool_calls = msg_obj.get("tool_calls")

                    logger.info(
                        f"[NVIDIA] Generation succeeded in {duration_ms:.1f}ms "
                        f"(Model: {self.model}, Attempt: {attempt}, ToolCalls: {bool(tool_calls)})"
                    )

                    # If model invoked a tool call in standard OpenAI format
                    if tool_calls and isinstance(tool_calls, list):
                        first_call = tool_calls[0]
                        fn_info = first_call.get("function", {})
                        fn_name = fn_info.get("name", "")
                        fn_args = fn_info.get("arguments", "{}")
                        # Return formatted Action string compatible with AgentBrain ReAct loop
                        return f"Action: {fn_name}\nAction Input: {fn_args}"

                    # If standard content is present
                    if content and isinstance(content, str) and content.strip():
                        return content.strip()

                    # Nemotron reasoning fallback: if content is empty but reasoning finished
                    reasoning_content = msg_obj.get("reasoning_content")
                    if reasoning_content and isinstance(reasoning_content, str):
                        # Extract the final concluding section from reasoning if content was omitted
                        logger.warning("[NVIDIA] Response content was empty; extracting summary from reasoning.")
                        lines = [line.strip() for line in reasoning_content.strip().split("\n") if line.strip()]
                        if lines:
                            return lines[-1]

                    return None

                # Case 2: Authentication / Authorization Errors (401, 403) - Non-retriable
                if resp.status_code in (401, 403):
                    logger.error(f"[NVIDIA] Authentication error ({resp.status_code}): Invalid or unauthorized API key.")
                    return None

                # Case 3: Rate Limiting (429) - Retriable with exponential backoff
                if resp.status_code == 429:
                    logger.warning(f"[NVIDIA] Rate limited (HTTP 429). Attempt {attempt}/{self.max_retries}. Backing off {backoff_delay}s...")
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
                    continue

                # Case 4: Server Errors (500, 502, 503, 504) - Retriable
                if resp.status_code >= 500:
                    logger.warning(f"[NVIDIA] Server error (HTTP {resp.status_code}). Attempt {attempt}/{self.max_retries}. Backing off {backoff_delay}s...")
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
                    continue

                # Other HTTP Errors
                logger.error(f"[NVIDIA] Request failed with HTTP {resp.status_code}: {resp.text[:200]}")
                return None

            except requests.exceptions.Timeout:
                logger.warning(f"[NVIDIA] Request timed out after {self.timeout}s (Attempt {attempt}/{self.max_retries}).")
                if attempt >= self.max_retries:
                    logger.error("[NVIDIA] All retry attempts exhausted due to timeouts.")
                    return None
                time.sleep(backoff_delay)
                backoff_delay *= 2.0

            except requests.exceptions.RequestException as e:
                clean_err = self._sanitize_error_message(str(e))
                logger.warning(f"[NVIDIA] Network error on attempt {attempt}/{self.max_retries}: {clean_err}")
                if attempt >= self.max_retries:
                    logger.error(f"[NVIDIA] Network failures persisted: {clean_err}")
                    return None
                time.sleep(backoff_delay)
                backoff_delay *= 2.0

            except Exception as e:
                clean_err = self._sanitize_error_message(str(e))
                logger.error(f"[NVIDIA] Unexpected error during generation: {clean_err}")
                return None

        return None

    def stream_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None,
        is_cancelled: Optional[Any] = None
    ) -> Generator[str, None, None]:
        """Streams response tokens from NVIDIA Nemotron endpoint with cancellation support."""
        if not self.is_available():
            return

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "JARVIS-Assistant/1.1"
        }
        ctx = context or {}
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": ctx.get("max_tokens", self.max_tokens),
            "temperature": ctx.get("temperature", self.temperature),
            "stream": True
        }

        resp = None
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout, stream=True)
            if resp.status_code != 200:
                logger.error(f"[NVIDIA Stream] Request failed with HTTP {resp.status_code}")
                return

            for line in resp.iter_lines():
                if is_cancelled and callable(is_cancelled) and is_cancelled():
                    logger.info("[NVIDIA Stream] Generation cancelled by caller (e.g. user barge-in). Aborting stream.")
                    break

                if line:
                    decoded = line.decode("utf-8").strip()
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_json = json.loads(data_str)
                            delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                            content_delta = delta.get("content")
                            if content_delta:
                                yield content_delta
                        except Exception:
                            continue
        except Exception as e:
            logger.error(f"[NVIDIA Stream] Error: {self._sanitize_error_message(str(e))}")
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
