"""Load the conformance-ledger chemistry for a bundle, for the render overlay.

The twin proves the robot CAN run the moves; this pulls the other half — what
each destination well actually ends up holding, reconstructed from the
commands[] ledger by conformance.py — so both show up in one frame.
"""
from __future__ import annotations

import json
from pathlib import Path

# short unit labels for the panel
_UNIT = {
    "penicillin_U_per_mL": "U/mL pen",
    "streptomycin_ug_per_mL": "ug/mL strep",
}


def short_unit(key: str) -> str:
    return _UNIT.get(key, key)


def load_chem(analysis_path: str | Path) -> dict | None:
    """Return {well: {vv, ok, conc:{unit:val}}, ...} + summary, or None if no bundle."""
    d = Path(analysis_path).parent
    conf_p, ir_p = d / "conformance.json", d / "ir.json"
    if not (conf_p.exists() and ir_p.exists()):
        return None
    ir = json.loads(ir_p.read_text())
    stock = (ir.get("dilution") or {}).get("stock_source", {}).get("stock_conc", {})
    conf = json.loads(conf_p.read_text())
    wells: dict[str, dict] = {}
    for c in conf.get("checks", []):
        name = c.get("name", "")
        if "[" not in name:
            continue
        well = name.split("[", 1)[1].rstrip("]")
        vv = float(c.get("found", 0.0))
        wells[well] = {
            "vv": vv,
            "ok": bool(c.get("ok")),
            "conc": {u: round(v * vv, 1) for u, v in stock.items()},
        }
    if not wells:
        return None
    n_ok = sum(1 for w in wells.values() if w["ok"])
    return {
        "wells": wells,
        "stock": stock,
        "vmax": max((w["vv"] for w in wells.values()), default=0.0),
        "all_ok": bool(conf.get("ok")) and n_ok == len(wells),
        "n_ok": n_ok,
        "n": len(wells),
    }


def conc_color(vv: float, vmax: float):
    """Cool (low) -> warm (high). Returns (mjcf_rgba_str, (r,g,b) 0-255)."""
    t = 0.0 if vmax <= 0 else min(1.0, vv / vmax)
    lo, hi = (0.35, 0.55, 0.85), (0.93, 0.28, 0.24)
    rgb = tuple(lo[i] + (hi[i] - lo[i]) * t for i in range(3))
    return (f"{rgb[0]:.2f} {rgb[1]:.2f} {rgb[2]:.2f} 1",
            tuple(int(c * 255) for c in rgb))


def caption(well: str, chem: dict) -> str:
    """One-line realized-concentration caption for a dispense into `well`."""
    w = chem["wells"].get(well)
    if not w:
        return ""
    pen = w["conc"].get("penicillin_U_per_mL")
    return f"{well}: {w['vv']*100:g}% v/v" + (f"  ~ {pen:g} U/mL PenStrep" if pen else "  (diluent only)")
