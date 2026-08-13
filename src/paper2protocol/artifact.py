"""Export the converged run as a portable artifact bundle.

Writes everything a human (or LABA's actuation layer) needs to review and, after
sign-off, dispatch to the robot:

  protocol.py            the converged Opentrons protocol (the exportable file)
  ir.json                the spec it was compiled from
  analysis.json          the full opentrons-analyze result (the dry run)
  conformance.json       realized-vs-target dilution from the command ledger
  run_log.json           the full iteration trace (every draft, every catch)
  signoff.md             the human wet-lab sign-off checklist
  MANIFEST.json          status + realized concentrations + file list + engine
"""
from __future__ import annotations

import json
from pathlib import Path

from .conformance import realized_final_concentration


def _engine_info(root: Path) -> dict:
    c = root / "captured" / "analyze_contract.json"
    if c.exists():
        d = json.loads(c.read_text())
        return {k: d[k] for k in ("opentrons_version", "python_version", "max_supported_apiLevel")
                if k in d}
    return {}


def write_bundle(outdir: str | Path, ir: dict, outcome, *, project_root: Path | None = None) -> dict:
    """Write the artifact bundle for a converged (or blocked) outcome. Returns the manifest."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    root = project_root or Path(__file__).resolve().parents[2]

    files: dict[str, str] = {}

    # 1) the protocol file — the thing people actually want to export
    if outcome.final is not None:
        (out / "protocol.py").write_text(outcome.final.source)
        files["protocol.py"] = "converged Opentrons protocol (OT-2, apiLevel {})".format(
            ir.get("api_level", "2.20"))

    # 2) the spec
    (out / "ir.json").write_text(json.dumps(ir, indent=2))
    files["ir.json"] = "intermediate spec compiled from the paper"

    # 3) analysis + conformance from the converged iteration
    last = outcome.iterations[-1] if outcome.iterations else None
    if last and last.analyze_result is not None:
        (out / "analysis.json").write_text(json.dumps(last.analyze_result.raw, indent=2))
        files["analysis.json"] = "opentrons analyze dry-run (result={}, {} commands)".format(
            last.analyze_result.result, last.analyze_result.n_commands)
    if last and last.conformance is not None:
        (out / "conformance.json").write_text(json.dumps({
            "ok": last.conformance.ok,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail,
                        "expected": c.expected, "found": c.found}
                       for c in last.conformance.checks],
        }, indent=2))
        files["conformance.json"] = "realized-vs-target dilution from the command ledger"

    # 4) full iteration trace
    (out / "run_log.json").write_text(json.dumps(_run_log(outcome), indent=2))
    files["run_log.json"] = "every draft and every deterministic catch"

    # 5) realized concentrations
    realized = _realized(ir)

    # 6) sign-off sheet
    (out / "signoff.md").write_text(_signoff(ir, outcome, realized))
    files["signoff.md"] = "human wet-lab sign-off checklist (gate before dispatch)"

    manifest = {
        "status": outcome.status,
        "reason": outcome.reason,
        "iterations": len(outcome.iterations),
        "paper": ir.get("paper", {}),
        "realized_concentrations": realized,
        "files": files,
        "engine": _engine_info(root),
        "note": "validated = static + analyze + conformance pass; NOT 'safe to run'. "
                "Dispatch to the robot only after the sign-off below is complete.",
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _run_log(outcome) -> list:
    log = []
    for r in outcome.iterations:
        log.append({
            "iteration": r.iteration,
            "stage_reached": r.stage_reached,
            "passed": r.passed,
            "static_errors": [f"{f.rule} L{f.line}: {f.message}"
                              for f in r.static_findings if f.severity == "error"],
            "analyze": None if r.analyze_result is None else {
                "result": r.analyze_result.result,
                "errors": [e.hint() for e in r.analyze_result.errors],
            },
            "conformance_failures": [] if r.conformance is None else
                [c.detail for c in r.conformance.failures()],
        })
    return log


def _realized(ir: dict) -> list:
    dil = ir.get("dilution", {})
    stock = dil.get("stock_source", {}).get("stock_conc")
    out = []
    for t in dil.get("targets", []):
        row = {"well": t["well"], "vv": t["vv"]}
        if stock:
            row["final_concentration"] = realized_final_concentration(t["vv"], stock)
        out.append(row)
    return out


def _signoff(ir: dict, outcome, realized: list) -> str:
    paper = ir.get("paper", {})
    lines = [
        f"# Wet-lab sign-off — {ir.get('protocol_name', 'protocol')}",
        "",
        f"**Paper:** {paper.get('title', '')}",
        f"**Status:** {outcome.status.upper()} ({outcome.reason})",
        "",
        "> The automated gates (static + opentrons analyze + conformance) have passed. "
        "That means the protocol is API-legal, simulates clean, and realizes the extracted "
        "spec. It does **not** mean it is safe to run. A wet-lab-literate reviewer must "
        "confirm the items below before the protocol is dispatched to the robot.",
        "",
        "## Realized concentrations (from the command ledger)",
        "",
    ]
    units = list((realized[0].get("final_concentration") or {}).keys()) if realized else []
    lines.append("| well | v/v | " + " | ".join(units) + " |")
    lines.append("|---|---|" + "|".join(["---"] * max(len(units), 1)) + "|")
    for r in realized:
        fc = r.get("final_concentration", {})
        lines.append(f"| {r['well']} | {r['vv']*100:.0f}% | "
                     + " | ".join(f"{fc.get(u, '?')}" for u in units) + " |")
    lines += [
        "",
        "## Reviewer checklist (blocking)",
        "- [ ] Dilution series matches the paper's intent (0 / 15 / 25 %).",
        "- [ ] Concentration **basis + units** confirmed (v/v of the 10,000 U/mL stock vs. the "
        "abstract's 1500 / 2500 / 10,000 U/mL framing).",
        "- [ ] Assay plate identity confirmed (12-well vs 24-well).",
        "- [ ] Transfer volumes are plausible for the chosen labware.",
        "- [ ] Culture OD normalization is in the linear regime; instrument/pathlength recorded.",
        "- [ ] **Sterility:** OT-2 in an enclosure/HEPA for live-culture steps; sterile single-use "
        "labware; reservoirs covered; negative (uninoculated) control well present.",
        "- [ ] External handoffs understood: agar melt/cast, culture add, seal, incubate, imaging "
        "are done off the OT-2.",
        "",
        "**Reviewer:** ______________________   **Date:** ____________   **Signature:** ____________",
        "",
        "_Only after every box is checked should the protocol be dispatched to the robot._",
    ]
    return "\n".join(lines) + "\n"
