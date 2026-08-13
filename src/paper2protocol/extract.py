"""Stage 1-3 — ingest an actual paper: PDF -> methods text -> structured IR.

This is the front of the pipeline: it turns a real PDF into the spec (IR) that
the generate -> validate -> repair loop compiles into a protocol. Scope is the
locked one: the robot does the AQUEOUS liquid handling (a dilution / concentration
series). If a paper has no such step, extraction says so (dilution=null) instead
of hallucinating one. Ambiguities (units, plate format) are surfaced, not guessed.

The extraction LLM is the same provider abstraction as the generator; give it a
different family from the validator for the cross-check.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .providers.base import LLMProvider

_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLIST = _ROOT / "data" / "allowlists" / "labware_loadnames.txt"
_MAX_CHARS = 24000


def allowlist() -> list[str]:
    if not _ALLOWLIST.exists():
        return []
    return [ln.strip() for ln in _ALLOWLIST.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]


def pdf_to_text(pdf_path: str | Path) -> str:
    """Extract text from a PDF (PyMuPDF primary, pdfplumber fallback)."""
    p = Path(pdf_path)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(p)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text
    except Exception:  # noqa: BLE001
        pass
    import pdfplumber
    with pdfplumber.open(p) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _methods_window(text: str) -> str:
    """Prefer the methods/materials region; fall back to the head of the paper."""
    low = text.lower()
    for kw in ("material and methods", "materials and methods", "methods", "experimental"):
        i = low.find(kw)
        if i != -1:
            return text[i:i + _MAX_CHARS]
    return text[:_MAX_CHARS]


_SYSTEM = """You extract an automatable Opentrons liquid-handling spec from a scientific \
paper's methods. The robot (Opentrons OT-2) performs ONLY aqueous liquid handling: \
preparing a dilution / concentration series and dispensing reagents. It does NOT melt \
or cast agar, image, incubate, or measure OD — those are external human/instrument steps.

Return ONE JSON object, nothing else (no prose, no code fence), with this shape:

{
  "protocol_name": "short name",
  "paper": {"title": "...", "assay_type": "..."},
  "api_level": "2.20",
  "robot_type": "OT-2",
  "dilution": {
    "stock_source":   {"labware": "<from allowlist>", "well": "A1", "liquid": "name",
                       "stock_conc": {"<unit e.g. penicillin_U_per_mL>": <number>}},
    "diluent_source": {"labware": "<from allowlist>", "well": "A2", "liquid": "diluent name"},
    "dest_labware": "<from allowlist>",
    "targets": [{"well": "A1", "vv": 0.0}, {"well": "A2", "vv": 0.15}, {"well": "A3", "vv": 0.25}],
    "total_vol_ul": 200,
    "tolerance_vv": 0.01
  },
  "gates": [{"id": "G1", "kind": "pause", "prompt": "human handoff instruction"}],
  "off_deck": ["melt agar", "incubate", "image", "..."],
  "open_clarifications": ["anything ambiguous the paper does not pin down"]
}

RULES:
- "vv" is the volume fraction of STOCK in each destination well (0.0 = pure diluent).
  Convert the paper's concentrations to v/v fractions of the named stock.
- Use load-names ONLY from this allowlist (never invent one): {allowlist}
  Pick a well plate for dest_labware and a reservoir for the sources.
- Put the stock's real concentration + explicit UNITS in stock_conc. If the paper's
  concentration basis is ambiguous (e.g. "% v/v" vs "U/mL"), record BOTH readings in
  open_clarifications and pick the most-supported one for vv.
- Add a human GATE for any external handoff the aqueous prep implies (e.g. handing the
  plate to an agar caster). Put agar melting/casting, incubation, imaging in off_deck.
- If the paper has NO automatable aqueous dilution/concentration series, set
  "dilution": null and explain why in open_clarifications. Do NOT invent one.
- Flag plate-format and volume ambiguities in open_clarifications; never silently guess."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    if "{" in text:
        text = text[text.index("{"):text.rindex("}") + 1]
    return json.loads(text)


def extract_ir(methods_text: str, provider: LLMProvider) -> dict:
    """LLM: methods text -> IR dict (validated/normalized). Retries once on bad JSON."""
    system = _SYSTEM.replace("{allowlist}", ", ".join(allowlist()))
    user = "PAPER METHODS (extract the spec from this):\n\n" + _methods_window(methods_text)
    last: Exception | None = None
    for attempt in range(2):
        result = provider.generate(system, user, max_tokens=8000)
        try:
            return normalize(_extract_json(result.text))
        except (json.JSONDecodeError, ValueError) as e:
            last = e
            user += ("\n\nYour previous reply was not valid JSON. Return ONE STRICT JSON object "
                     "only: every key/string double-quoted, no trailing commas, no comments, "
                     "no text before or after the object.")
    raise ValueError(f"could not parse extraction JSON: {last}")


def normalize(ir: dict) -> dict:
    """Fill defaults + light validation so the IR is loop-ready."""
    ir.setdefault("api_level", "2.20")
    ir.setdefault("robot_type", "OT-2")
    ir.setdefault("open_clarifications", [])
    allow = set(allowlist())
    dil = ir.get("dilution")
    if dil:
        dil.setdefault("tolerance_vv", 0.01)
        dil.setdefault("total_vol_ul", 200)
        # labware sanity — flag (don't silently fix) unknown load-names
        for role in ("stock_source", "diluent_source"):
            lw = (dil.get(role) or {}).get("labware")
            if lw and lw not in allow:
                ir["open_clarifications"].append(f"{role} labware '{lw}' not in verified allowlist")
        if dil.get("dest_labware") and dil["dest_labware"] not in allow:
            ir["open_clarifications"].append(f"dest_labware '{dil['dest_labware']}' not in verified allowlist")
        if not dil.get("targets"):
            ir["open_clarifications"].append("no dilution targets extracted")
    return ir


def ingest(pdf_path: str | Path, provider: LLMProvider) -> dict:
    """PDF -> IR. The end-to-end front of the pipeline."""
    text = pdf_to_text(pdf_path)
    if not text.strip():
        raise ValueError(f"no extractable text in {pdf_path} (scanned/image PDF?)")
    return extract_ir(text, provider)
