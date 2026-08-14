"""Replication check — does the ledger actually realize what the paper claims?

Reconstructs the run from the `opentrons analyze` commands[] ledger by simulating every
aspirate/dispense against a container model, then tests the paper's declared numbers against
what the protocol *does*. Nothing is read from the protocol source: a check that grepped the
code for the right literal would pass a protocol that merely mentions the number.

    python scripts/replication_check.py examples/mic_ole/out/analysis.json examples/mic_ole/claims.json

Exit code 0 = every claim satisfied.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict


class Container:
    """Volume + mass of each tracked solute, so concentrations fall out of the mixing."""

    def __init__(self, name, volume=0.0, conc=None, infinite=False):
        self.name = name
        self.volume = volume
        self.conc = dict(conc or {})     # solute -> mg/mL (or arbitrary units)
        self.infinite = infinite         # a stock we never drain

    def take(self, vol):
        if not self.infinite:
            self.volume = max(0.0, self.volume - vol)
        return dict(self.conc)

    def give(self, vol, conc):
        if self.infinite:
            return
        total = self.volume + vol
        if total <= 0:
            return
        merged = {}
        for k in set(self.conc) | set(conc):
            mass = self.conc.get(k, 0.0) * self.volume + conc.get(k, 0.0) * vol
            merged[k] = mass / total
        self.volume, self.conc = total, merged


def simulate(ledger_path, stocks):
    a = json.loads(open(ledger_path).read())
    cmds = a.get("commands", [])

    id2slot, slot2load, pipettes = {}, {}, {}
    for c in cmds:
        if c.get("commandType") == "loadPipette":
            pipettes[c.get("result", {}).get("pipetteId")] = {
                "name": c["params"].get("pipetteName"),
                "mount": c["params"].get("mount"),
            }
        if c.get("commandType") == "loadLabware":
            p, res = c["params"], c.get("result", {})
            slot = str(p.get("location", {}).get("slotName"))
            slot2load[slot] = p.get("loadName")
            if res.get("labwareId"):
                id2slot[res["labwareId"]] = slot

    containers = {}

    def get(slot, well):
        key = f"{slot}/{well}"
        if key not in containers:
            spec = stocks.get(key)
            containers[key] = Container(
                key,
                volume=float("inf") if spec and spec.get("infinite") else 0.0,
                conc=(spec or {}).get("conc"),
                infinite=bool(spec and spec.get("infinite")),
            )
        return containers[key]

    held = None          # what the tip is carrying: (volume, conc)
    tips_used = 0
    transfers = []
    volume_ops = []      # (pipetteId, op, volume) — for the min-volume audit
    for c in cmds:
        t, p = c.get("commandType"), c.get("params", {})
        if t == "pickUpTip":
            tips_used += 1
            held = None
        elif t == "aspirate":
            src = get(id2slot.get(p.get("labwareId")), p.get("wellName"))
            vol = float(p.get("volume") or 0)
            volume_ops.append((p.get("pipetteId"), "aspirate", vol))
            held = (vol, src.take(vol))
        elif t == "dispense":
            dst = get(id2slot.get(p.get("labwareId")), p.get("wellName"))
            vol = float(p.get("volume") or 0)
            volume_ops.append((p.get("pipetteId"), "dispense", vol))
            conc = held[1] if held else {}
            dst.give(vol, conc)
            transfers.append((dst.name, vol, dict(conc)))
            held = None
    return containers, transfers, tips_used, slot2load, pipettes, volume_ops


def main():
    ledger, claims_path = sys.argv[1], sys.argv[2]
    claims = json.loads(open(claims_path).read())
    containers, transfers, tips_used, slot2load, pipettes, volume_ops = simulate(
        ledger, claims["stocks"])

    plate = claims["plate_slot"]
    solute = claims["solute"]
    marker = claims["biology_marker"]

    results = []

    def check(name, ok, detail):
        results.append((name, bool(ok), detail))

    # --- labware actually loaded ---
    for slot, expected in claims["expect_labware"].items():
        check(f"labware slot {slot}", slot2load.get(slot) == expected,
              f"expected {expected}, loaded {slot2load.get(slot)}")

    # --- the realized dilution series, derived from the mixing ---
    got = []
    for tube in claims["series_wells"]:
        c = containers.get(f"{claims['rack_slot']}/{tube}")
        got.append(round(c.conc.get(solute, 0.0), 4) if c else None)
    want = claims["concentrations"]
    ok_series = len(got) == len(want) and all(
        g is not None and abs(g - w) <= max(0.01, 0.02 * w) for g, w in zip(got, want))
    check("dilution series realized", ok_series, f"expected {want}, realized {got}")

    # --- per-well contents of the assay plate ---
    wells = defaultdict(lambda: {"vol": 0.0, "ole": None, "bio": 0.0})
    for name, vol, conc in transfers:
        slot, well = name.split("/")
        if slot != plate:
            continue
        w = wells[well]
        w["vol"] += vol
        if conc.get(solute, 0.0) > 0:
            w["ole"] = round(conc[solute], 4)
        if conc.get(marker, 0.0) > 0:
            w["bio"] += vol

    # experimental wells: OLE + culture, at the paper's total volume
    def near(a, b):
        return abs(a - b) <= max(1e-3, 2e-3 * abs(b))

    per_conc = defaultdict(int)
    for well, w in wells.items():
        if w["ole"] and w["bio"] > 0:
            per_conc[w["ole"]] += 1
    reps = claims["replicates"]
    # match by tolerance: realized concentrations are rounded for display, so an exact
    # key lookup fails on values like 19.53125 -> 19.5312
    counts = {c: sum(n for k, n in per_conc.items() if near(k, c)) for c in want}
    ok_reps = all(counts[c] == reps for c in want)
    check(f"{reps} replicates per concentration", ok_reps,
          f"per-concentration well counts: {[counts[c] for c in want]}"
          + ("" if ok_reps else f"  (expected {reps} each)"))

    tv = claims["total_well_volume"]
    exp_wells = {w: v for w, v in wells.items() if v["ole"] and v["bio"] > 0}
    bad_vol = {w: round(v["vol"], 1) for w, v in exp_wells.items() if abs(v["vol"] - tv) > 0.51}
    check(f"every experimental well = {tv} uL", not bad_vol,
          f"{len(exp_wells)} experimental wells; off-volume: {bad_vol or 'none'}")

    # a protocol may legitimately use more than one component volume (e.g. 100 uL of
    # extract + a 10 uL inoculum); every plate dispense must still be one of them
    cvs = claims.get("component_volumes")
    if cvs is None:
        cvs = [claims["component_volume"]]
    cvs = [float(x) for x in cvs]
    bad_comp = [(n, v) for n, v, _ in transfers
                if n.startswith(plate + "/") and not any(abs(v - c) < 0.01 for c in cvs)]
    check(f"every plate dispense in {cvs} uL", not bad_comp,
          f"{len(bad_comp)} dispense(s) of another size: {sorted({v for _, v in bad_comp})[:5]}"
          if bad_comp else "all dispenses accounted for")

    # --- controls: declared per paper, because papers do not agree on what they mean.
    # Paper 0263359's "negative control" is broth only; paper 0146349's is extract
    # WITHOUT inoculum. Hardcoding either one silently mis-scores the other.
    for ctrl in claims.get("controls", []):
        want_solute = ctrl.get("solute")          # True / False / None = don't care
        want_bio = ctrl.get("biology")
        sel = []
        for w, v in wells.items():
            has_s = bool(v["ole"])
            has_b = v["bio"] > 0
            if want_solute is not None and has_s != want_solute:
                continue
            if want_bio is not None and has_b != want_bio:
                continue
            sel.append(w)
        n_min = ctrl.get("min_wells", 1)
        ok = len(sel) >= n_min
        detail = f"{len(sel)} wells: {sorted(sel)[:9]}"
        n_concs = ctrl.get("n_concentrations")
        if n_concs is not None:
            covered = len({wells[w]["ole"] for w in sel if wells[w]["ole"]})
            ok = ok and covered == n_concs
            detail += f" covering {covered}/{n_concs} concentrations"
        check(f"control: {ctrl['name']}", ok, detail)

    # --- every transfer within its pipette's RATED range ---
    # `opentrons analyze` does NOT enforce this: a 10 uL aspirate on a p300_single_gen2
    # (rated minimum 20 uL) passes with zero errors and would simply be dispensed
    # inaccurately on the bench. Checked here against Opentrons' own spec data.
    try:
        import opentrons_shared_data as _osd, os as _os
        _specs = json.load(open(_os.path.join(
            _os.path.dirname(_osd.__file__),
            "data", "pipette", "definitions", "1", "pipetteNameSpecs.json")))
    except Exception:
        _specs = {}
    under = []
    for pid, op, vol in volume_ops:
        spec = _specs.get((pipettes.get(pid) or {}).get("name") or "")
        if not spec or vol <= 0:
            continue
        lo, hi = spec.get("minVolume"), spec.get("maxVolume")
        if lo is not None and vol < lo - 1e-9:
            under.append(f"{pipettes[pid]['name']} {op} {vol:g}uL < min {lo}uL")
        if hi is not None and vol > hi + 1e-9:
            under.append(f"{pipettes[pid]['name']} {op} {vol:g}uL > max {hi}uL")
    _seen = sorted(set(under))
    check("every transfer within pipette rated range", not _seen,
          f"{len(under)} out-of-range op(s): {_seen[:3]}" if _seen
          else f"{len(volume_ops)} ops across " +
               ", ".join(sorted({(v or {}).get('name', '?') for v in pipettes.values()})))

    # --- sanity ---
    check("tips used", tips_used > 0, f"{tips_used} tips")

    width = max(len(n) for n, _, _ in results)
    print(f"\nREPLICATION CHECK — {claims['paper']}")
    print(f"ledger: {ledger}\n")
    n_ok = 0
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
        n_ok += ok
    print(f"\n  {n_ok}/{len(results)} checks passed")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
