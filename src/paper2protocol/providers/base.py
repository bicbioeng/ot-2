"""Provider abstraction — swap the generator by config, not code.

The generator defaults to a NON-Claude family (Gemini) so the generator differs
from Claude-Code-the-validator: two uncorrelated error detectors. Model IDs are
version-sensitive; override any default with PAPER2PROTOCOL_MODEL. On a bad model
id the provider surfaces the vendor's own error (which usually names valid ones).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

# Overridable defaults. google/openai are best-effort current ids; anthropic id
# is from this session's known-good list. Set PAPER2PROTOCOL_MODEL to pin.
DEFAULT_MODELS = {
    "google": "gemini-flash-latest",   # stable alias; versioned ids get retired for new keys
    "openai": "gpt-4.1",
    "anthropic": "claude-sonnet-5",
}


@dataclass
class GenResult:
    text: str
    model: str
    provider: str


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    family: str
    model: str

    def generate(self, system: str, user: str, *, max_tokens: int = 8000) -> GenResult: ...


def get_provider(name: str | None = None, model: str | None = None) -> LLMProvider:
    name = (name or os.environ.get("PAPER2PROTOCOL_GENERATOR", "google")).lower()
    model = model or os.environ.get("PAPER2PROTOCOL_MODEL")
    if name in ("google", "gemini"):
        from .google import GoogleProvider
        return GoogleProvider(model)
    if name in ("openai", "gpt"):
        from .openai import OpenAIProvider
        return OpenAIProvider(model)
    if name in ("anthropic", "claude"):
        from .anthropic import AnthropicProvider
        return AnthropicProvider(model)
    raise ValueError(f"unknown provider {name!r} (use google | openai | anthropic)")


def load_env(path: str | Path | None = None) -> None:
    """Minimal .env loader (no dependency). Loads KEY=VALUE lines into os.environ
    without overwriting already-set vars."""
    p = Path(path) if path else Path(__file__).resolve().parents[3] / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
