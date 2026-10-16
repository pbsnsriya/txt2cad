"""One adapter for OpenAI-style chat endpoints. Used for Gemini through its OpenAI-compatible URL.

JSON is requested with response_format json_schema first; endpoints that reject it get a retry with json_object and then with
plain text (the reply is validated on our side either way). Streaming deltas are accumulated and passed to on_text.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .base import LLMError, LLMRequest, TextCallback, extract_json

DEFAULT_TIMEOUT_S = 600.0
CONNECT_TIMEOUT_S = 10.0


class OpenAICompatLLM:
    vision = False

    def __init__(self, base_url: str, model: str, api_key_env: str = "", options: dict[str, Any] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.options = options or {}
        self.name = f"openai_compat/{model or 'default'}"
        self.vision = bool(self.options.get("vision", False))

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        if self.api_key_env and not key:
            raise LLMError(f"environment variable {self.api_key_env} is not set; set it and restart the backend")
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _body(self, request: LLMRequest, mode: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model, "stream": True,
            "messages": [{"role": "system", "content": request.system}, {"role": "user", "content": request.user}],
        }
        if "temperature" in self.options:
            body["temperature"] = self.options["temperature"]
        if self.options.get("reasoning_effort"):          # Gemini and other reasoning models: less thinking = much faster first token
            body["reasoning_effort"] = self.options["reasoning_effort"]
        if mode == "schema":
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": request.schema_name, "schema": request.schema}}
        elif mode == "object":
            body["response_format"] = {"type": "json_object"}
        return body

    def complete(self, request: LLMRequest, on_text: TextCallback | None = None) -> dict[str, Any]:
        last_error = ""
        for mode in ("schema", "object", "none"):
            try:
                text = self._stream(request, mode, on_text)
            except _Rejected as exc:          # 400/422: this endpoint does not accept that response_format
                last_error = str(exc)
                continue
            return extract_json(text)
        raise LLMError(f"the endpoint rejected every request format: {last_error}")

    def _stream(self, request: LLMRequest, mode: str, on_text: TextCallback | None) -> str:
        url = f"{self.base_url}/chat/completions"
        timeout = httpx.Timeout(float(self.options.get("timeout", DEFAULT_TIMEOUT_S)), connect=CONNECT_TIMEOUT_S)
        text = ""
        try:
            with httpx.stream("POST", url, headers=self._headers(), json=self._body(request, mode), timeout=timeout) as resp:
                if resp.status_code in (400, 422):
                    raise _Rejected(resp.read().decode("utf-8", "replace")[:300])
                if resp.status_code >= 400:
                    raise LLMError(f"model endpoint answered HTTP {resp.status_code}: {resp.read().decode('utf-8', 'replace')[:300]}")
                for line in resp.iter_lines():
                    if request.stop is not None and request.stop.is_set():
                        break
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        delta = json.loads(payload)["choices"][0].get("delta", {}).get("content") or ""
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta:
                        text += delta
                        if on_text:
                            on_text(text)
        except httpx.ConnectError as exc:
            raise LLMError(f"cannot reach the model at {self.base_url}: is it running?") from exc
        except httpx.TimeoutException as exc:
            raise LLMError("the model took too long to answer") from exc
        return text


class _Rejected(Exception):
    pass
