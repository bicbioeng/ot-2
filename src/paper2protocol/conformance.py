"""Stage 5c — spec-conformance from the analyze commands[] ledger.

The panel's rule: conformance must be reconstructed from what the protocol
ACTUALLY does (the aspirate/dispense volume ledger), never by grepping the code
for the right literal (trivially reward-hacked). So we:

  1. pair each aspirate with the next dispense on the same pipette -> a volume
     movement (src well -> dst well),
  2. build a per-destination-well ledger {source_liquid: volume},
  3. derive the REALIZED v/v fraction and, using the IR's stock concentration +
     units, the REALIZED FINAL concentration,
  4. compare to the IR's declared targets within tolerance, binding each
     concentration to its named source well.

This is codegen-fidelity to the IR (that the code realizes the intent) — NOT a
proof the extraction matched the paper (that is the extraction oracle + human
sign-off). Stated plainly per the review.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConformanceCheck:
    name: str
    ok: bool
    detail: str
    expected: object = None
    found: object = None

    def signature(self) -> str:
        return f"conformance:{self.name}"


@dataclass
class ConformanceReport:
    checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def failures(self) -> list[ConformanceCheck]:
        return [c for c in self.checks if not c.ok]


def _id_to_loadname(labware: list[dict]) -> dict[str, str]:
    return {l.get("id"): l.get("loadName") for l in labware}


def build_transfer_ledger(commands: list[dict], labware: list[dict]) -> list[tuple]:
    """Return list of (src_loadname, src_well, dst_loadname, dst_well, volume).

    Pairs each aspirate with the next dispense on the same pipette (single-channel
    aqueous). Self-transfers (mix within a well) are included but net to the same
    well; callers filter src==dst.
    """
    id2name = _id_to_loadname(labware)
    pending: dict[str, tuple] = {}
    out: list[tuple] = []
    for c in commands:
        t = c.get("commandType")
        p = c.get("params", {})
        pid = p.get("pipetteId")
        if t == "aspirate":
            pending[pid] = (p.get("labwareId"), p.get("wellName"), p.get("volume", 0.0))
        elif t == "dispense":
            src = pending.pop(pid, None)
            if src is None:
                continue
            s_lw, s_well, s_vol = src
            vol = min(float(p.get("volume", 0.0)), float(s_vol))
            out.append((id2name.get(s_lw), s_well, id2name.get(p.get("labwareId")),
                        p.get("wellName"), vol))
    return out


def dest_ledger(commands: list[dict], labware: list[dict], dest_loadname: str) -> dict:
    """{dest_well: {(src_loadname, src_well): volume}} for a destination labware,
    excluding self-mixing."""
    led: dict[str, dict] = {}
    for s_lw, s_well, d_lw, d_well, vol in build_transfer_ledger(commands, labware):
        if d_lw != dest_loadname:
            continue
        if (s_lw, s_well) == (d_lw, d_well):  # mixing within the dest well
            continue
        led.setdefault(d_well, {})
        key = (s_lw, s_well)
        led[d_well][key] = led[d_well].get(key, 0.0) + vol
    return led


def check_dilution(analyze_raw: dict, ir: dict) -> ConformanceReport:
    """Check the realized PenStrep dilution series against the IR.

    IR["dilution"] = {
        stock_source:   {labware, well, [stock_conc: {unit: value}]},
        diluent_source: {labware, well},
        dest_labware:   loadName,
        targets:        [{well, vv}],           # v/v fraction of stock
        tolerance_vv:   float,
    }
    """
    rep = ConformanceReport()
    dil = ir.get("dilution")
    if not dil:
        rep.checks.append(ConformanceCheck("dilution_present", False, "IR has no 'dilution' block"))
        return rep

    commands = analyze_raw.get("commands", [])
    labware = analyze_raw.get("labware", [])
    stock = dil["stock_source"]
    diluent = dil["diluent_source"]
    stock_key = (stock["labware"], stock["well"])
    diluent_key = (diluent["labware"], diluent["well"])
    tol = float(dil.get("tolerance_vv", 0.01))
    led = dest_ledger(commands, labware, dil["dest_labware"])

    for target in dil["targets"]:
        well = target["well"]
        want_vv = float(target["vv"])
        sources = led.get(well, {})
        v_stock = sources.get(stock_key, 0.0)
        v_dil = sources.get(diluent_key, 0.0)
        # allow other sources? sum everything as total so an extra source is caught
        total = sum(sources.values())
        if total <= 0:
            rep.checks.append(ConformanceCheck(
                f"dilution[{well}]", False,
                f"no liquid delivered to {well} (expected v/v {want_vv})",
                expected=want_vv, found=None))
            continue
        realized_vv = v_stock / total
        ok = abs(realized_vv - want_vv) <= tol
        detail = (f"well {well}: realized {realized_vv:.3f} v/v "
                  f"(stock {v_stock:g}uL / total {total:g}uL) vs target {want_vv:.3f}")
        if v_dil + v_stock + 1e-6 < total:
            detail += "  [WARN: unexpected extra source into well]"
            ok = False
        rep.checks.append(ConformanceCheck(
            f"dilution[{well}]", ok, detail, expected=want_vv, found=round(realized_vv, 4)))

    # bind concentration to the NAMED stock source (catches 'right volume, wrong stock')
    stock_conc = stock.get("stock_conc")
    if stock_conc:
        for target in dil["targets"]:
            well = target["well"]
            sources = led.get(well, {})
            if sources and stock_key not in sources and float(target["vv"]) > 0:
                rep.checks.append(ConformanceCheck(
                    f"stock_source[{well}]", False,
                    f"well {well} got stock from an unexpected source well, not "
                    f"{stock_key} — final concentration cannot be trusted"))
    return rep


def realized_final_concentration(vv: float, stock_conc: dict) -> dict:
    """Realized final concentration per component: stock_conc * v/v (units preserved)."""
    return {unit: round(val * vv, 4) for unit, val in stock_conc.items()}
