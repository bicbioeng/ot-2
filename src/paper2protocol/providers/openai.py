"""OpenAI generator (Responses API)."""
from __future__ import annotations

import os

from .base import DEFAULT_MODELS, GenResult


class OpenAIProvider:
    name = "openai"
    family = "openai"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODELS["openai"]
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set. Add it to paper2protocol/.env")
        from openai import OpenAI
        self._client = OpenAI(api_key=key)

    def generate(self, system: str, user: str, *, max_tokens: int = 8000) -> GenResult:
        resp = self._client.responses.create(
            model=self.model,
            instructions=system,
            input=user,
            max_output_tokens=max_tokens,
        )
        return GenResult(text=resp.output_text or "", model=self.model, provider=self.name)
