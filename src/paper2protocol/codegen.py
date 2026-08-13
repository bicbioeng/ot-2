"""Stage 04 — codegen. IR (+ validator feedback) -> Opentrons protocol via the
generator LLM, grounded on the M1-verified API facts and the admissible labware.

The generator is deliberately constrained to the aqueous slice; the loop's
deterministic judges do the checking. On a repair iteration the raw validator
feedback (real analyze/static/conformance output) is fed back verbatim.
"""
from __future__ import annotations

import re
from pathlib import Path

from .loop import Draft, Feedback
from .providers.base import LLMProvider

_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLIST = _ROOT / "data" / "allowlists" / "labware_loadnames.txt"


def _allowlist() -> list[str]:
    if not _ALLOWLIST.exists():
        return []
    return [ln.strip() for ln in _ALLOWLIST.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]


SYSTEM = """You are an expert Opentrons protocol engineer. Write ONE Python file for \
the Opentrons OT-2 that performs ONLY the aqueous liquid handling in the spec. \
Everything else (agar melting/casting, incubation, imaging) is done off the robot by \
a human — never attempt it.

HARD RULES (a deterministic validator will reject violations):
- Target apiLevel 2.20. Put apiLevel in EXACTLY ONE place. Use:
    requirements = {{"robotType": "OT-2", "apiLevel": "2.20"}}
  Do NOT also put apiLevel in metadata.
- Never use Opentrons API v1 syntax (no `from opentrons import robot/instruments/labware`,
  no `labware.load(...)`, no `instruments.*`). Everything comes off the ProtocolContext
  passed to `run(protocol)`.
- Use ONLY these labware load-names (never invent one): {allowlist}
- Single-channel GEN2 pipettes only. Volume bounds: p20_single_gen2 = 1-20 uL,
  p300_single_gen2 = 20-300 uL. Pick a pipette whose range covers each transfer volume.
  Load a matching tip rack for every pipette you load, and use every pipette you load.
- Every transfer that moves liquid to a DIFFERENT destination well must pass
  new_tip="always" (carryover between concentrations is silently wrong science).
- Only reference wells that exist on the chosen labware.
- Declare liquids with protocol.define_liquid(...) and well.load_liquid(liquid, volume=...)
  so volumes are tracked.
- NEVER aspirate or dispense agar or anything described as molten/80C.

OUTPUT: return ONLY the protocol as a single ```python fenced code block. No prose."""


def build_user_prompt(ir: dict, feedback: Feedback | None) -> str:
    dil = ir.get("dilution", {})
    parts = [
        "Write the protocol for this spec.",
        "",
        "SPEC (intermediate representation):",
        _spec_text(ir, dil),
    ]
    if feedback is not None:
        parts += [
            "",
            "YOUR PREVIOUS ATTEMPT FAILED these validator checks — fix ALL of them, "
            "keep everything that was correct:",
            feedback.as_text(),
        ]
        if feedback.reflexion_memo:
            parts += ["", "Do not reintroduce earlier fixes:", *["- " + m for m in feedback.reflexion_memo]]
    return "\n".join(parts)


def _spec_text(ir: dict, dil: dict) -> str:
    stock = dil.get("stock_source", {})
    dilu = dil.get("diluent_source", {})
    tgts = ", ".join(f"{t['well']}={t['vv']*100:.0f}% v/v" for t in dil.get("targets", []))
    return (
        f"- Robot: {ir.get('robot_type', 'OT-2')}, apiLevel {ir.get('api_level', '2.20')}\n"
        f"- Prepare a Pen-Strep dilution series into a {dil.get('dest_labware')} plate, "
        f"{dil.get('total_vol_ul', 200)} uL total per well.\n"
        f"- Source stock '{stock.get('liquid', 'PenStrep stock')}' in "
        f"{stock.get('labware')} well {stock.get('well')}; diluent "
        f"'{dilu.get('liquid', 'LB')}' in {dilu.get('labware')} well {dilu.get('well')}.\n"
        f"- Targets (v/v fraction of stock): {tgts}\n"
        f"- Fresh tip for every destination; declare the two source liquids."
    )


_FENCE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    m = _FENCE.search(text)
    if m:
        return m.group(1).strip() + "\n"
    # no fence — assume the whole thing is code if it looks like a protocol
    if "def run(" in text:
        return text.strip() + "\n"
    raise ValueError("generator returned no python code block")


def generate_protocol(provider: LLMProvider, ir: dict, feedback: Feedback | None) -> str:
    system = SYSTEM.format(allowlist=", ".join(_allowlist()))
    user = build_user_prompt(ir, feedback)
    result = provider.generate(system, user)
    return extract_code(result.text)


class LLMDraftProvider:
    """DraftProvider backed by a live generator model. Plugs into run_loop exactly
    where ScriptedProvider does — the loop, gate, and judges are unchanged."""

    def __init__(self, provider: LLMProvider, ir: dict, workdir: str | Path):
        self.provider = provider
        self.ir = ir
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    def __call__(self, feedback: Feedback | None, iteration: int) -> Draft | None:
        source = generate_protocol(self.provider, self.ir, feedback)
        path = self.workdir / f"llm_draft_{iteration}.py"
        path.write_text(source)
        note = ("generated by " + f"{self.provider.name}:{self.provider.model}"
                if feedback is None else "regenerated from validator feedback")
        return Draft(source=source, path=path, label=f"llm draft {iteration}", generator_note=note)
