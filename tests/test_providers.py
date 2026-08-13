"""Provider layer: factory + graceful no-key errors + codegen prompt/extraction.

No network calls — the live generate() path needs a key and is exercised via
`paper2protocol run --live`, not in unit tests.
"""
import json
from pathlib import Path

import pytest

from paper2protocol import codegen
from paper2protocol.providers.base import get_provider

ROOT = Path(__file__).resolve().parents[1]
IR = json.loads((ROOT / "examples" / "chemotaxis_penstrep" / "ir.json").read_text())


def test_unknown_provider():
    with pytest.raises(ValueError):
        get_provider("bogus")


def test_missing_key_raises_clearly(monkeypatch):
    for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for name in ("google", "openai", "anthropic"):
        with pytest.raises(RuntimeError, match="not set"):
            get_provider(name)


def test_codegen_user_prompt_and_feedback():
    from paper2protocol.loop import Feedback
    from paper2protocol.static_checks import StaticFinding

    u = codegen.build_user_prompt(IR, None)
    assert "25% v/v" in u and "corning_24_wellplate_3.4ml_flat" in u
    fb = Feedback(1, static_failures=[StaticFinding("new_tip_policy", 7, "carryover")])
    u2 = codegen.build_user_prompt(IR, fb)
    assert "FAILED" in u2 and "new_tip_policy" in u2


def test_extract_code_from_fence():
    assert codegen.extract_code("prose\n```python\ndef run(p):\n    pass\n```\nmore").startswith("def run(")
    assert codegen.extract_code("def run(ctx):\n    pass").startswith("def run(")
    with pytest.raises(ValueError):
        codegen.extract_code("no code here")
