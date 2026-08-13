"""Gemini generator (google-genai). Default generator family."""
from __future__ import annotations

import os
import time

from .base import DEFAULT_MODELS, GenResult


class GoogleProvider:
    name = "google"
    family = "google"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODELS["google"]
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GOOGLE_API_KEY (or GEMINI_API_KEY) not set. Add it to paper2protocol/.env")
        from google import genai
        self._genai = genai
        self._client = genai.Client(api_key=key)

    def generate(self, system: str, user: str, *, max_tokens: int = 8000) -> GenResult:
        from google.genai import errors as gerr
        from google.genai import types
        cfg = types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=max_tokens, temperature=0)
        last: Exception | None = None
        for attempt in range(4):  # free-tier is flaky (429 quota, intermittent 400)
            try:
                resp = self._client.models.generate_content(
                    model=self.model, contents=user, config=cfg)
                return GenResult(text=resp.text or "", model=self.model, provider=self.name)
            except gerr.APIError as e:
                last = e
                if getattr(e, "code", None) in (400, 429, 500, 503):
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        raise last  # type: ignore[misc]
