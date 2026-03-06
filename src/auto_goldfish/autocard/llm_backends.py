"""LLM backend abstraction for card labeling (Ollama and Gemini)."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class LLMBackend(Protocol):
    """Interface for LLM backends used by the labeler."""

    def chat(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat request and return the raw response text."""
        ...


class OllamaBackend:
    """Ollama local model backend with JSON schema constrained decoding."""

    def __init__(self, model: str = "llama4:16x17b"):
        self.model = model

    def chat(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        import ollama

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0},
        }
        if json_schema is not None:
            kwargs["format"] = json_schema

        response = ollama.chat(**kwargs)
        return response["message"]["content"]

    def __repr__(self) -> str:
        return f"OllamaBackend(model={self.model!r})"


class GeminiBackend:
    """Google Gemini API backend with JSON schema constrained output.

    Reads the API key from the GEMINI_API_KEY environment variable.
    Supports structured JSON output via Gemini's responseMimeType.
    """

    def __init__(self, model: str = "gemini-2.0-flash", rate_limit: bool = False):
        self.model = model
        self.rate_limit = rate_limit
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set. "
                "Add it to your .env file."
            )
        from google import genai

        self.client = genai.Client(api_key=api_key)

    def chat(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        from google.genai import types

        config_kwargs: dict[str, Any] = {
            "temperature": 0,
            "system_instruction": system,
        }
        if json_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = json_schema

        config = types.GenerateContentConfig(**config_kwargs)
        return self._call_with_retry(config, user)

    def _call_with_retry(
        self, config: Any, contents: str, max_retries: int = 10,
    ) -> str:
        from google.genai import errors as genai_errors

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=contents, config=config,
                )
                return response.text
            except genai_errors.ClientError as exc:
                if not self.rate_limit or "429" not in str(exc):
                    raise
                delay = self._parse_retry_delay(str(exc))
                logger.warning(
                    "Rate limited (attempt %d/%d), waiting %.0fs...",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)

        raise RuntimeError(
            f"Gemini rate limit exceeded after {max_retries} retries"
        )

    @staticmethod
    def _parse_retry_delay(error_msg: str, default: float = 60.0) -> float:
        match = re.search(r"retry in ([\d.]+)s", error_msg, re.IGNORECASE)
        if match:
            return float(match.group(1)) + 1.0
        return default

    def __repr__(self) -> str:
        rl = ", rate_limit=True" if self.rate_limit else ""
        return f"GeminiBackend(model={self.model!r}{rl})"


def create_backend(
    api: str, model: str | None = None, rate_limit: bool = False,
) -> LLMBackend:
    """Factory to create an LLM backend.

    Args:
        api: "ollama" or "gemini"
        model: Model name override. If None, uses the default for the backend.
        rate_limit: If True, automatically retry on 429 rate-limit errors (Gemini free tier).
    """
    if api == "ollama":
        return OllamaBackend(model=model or "llama4:16x17b")
    elif api == "gemini":
        return GeminiBackend(
            model=model or "gemini-2.0-flash", rate_limit=rate_limit,
        )
    else:
        raise ValueError(f"Unknown API backend: {api!r}. Use 'ollama' or 'gemini'.")
