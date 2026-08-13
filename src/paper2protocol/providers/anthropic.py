"""Anthropic generator (Messages API). Note: same family as the validator, so
prefer a non-Claude default generator for uncorrelated blind spots."""
from __future__ import annotations

import os

from .base import DEFAULT_MODELS, GenResult


class AnthropicProvider:
    name = "anthropic"
    family = "anthropic"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODELS["anthropic"]
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to paper2protocol/.env")
        import anthropic
        self._client = anthropic.Anthropic(api_key=key)

    def generate(self, system: str, user: str, *, max_tokens: int = 8000) -> GenResult:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content
                       if getattr(b, "type", "") == "text")
        return GenResult(text=text, model=self.model, provider=self.name)
