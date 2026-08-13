"""Build the interactive digital-twin scene from a real Opentrons analysis.json.

This is the deterministic *twin state engine*: it replays the command ledger and emits a
self-describing scene (exact geometry + the full step-by-step state timeline) that the
Three.js viewer animates. Nothing is guessed — geometry comes from the labware definitions
embedded in the ledger + the real ot2_standard deck; liquids and volumes come from the
loadLiquid commands and the aspirate/dispense stream.

Output: twin/viewer/ot2_digital_twin.html  (single self-contained file; opens in any browser)

    python -m twin.viewer.build_twin_scene <analysis.json> [--out out.html]
"""
from __future__ import annotations

import argparse
import base64
import json
import math
from pathlib import Path

from twin import deck as deckmod

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "ot2"
TEMPLATE = Path(__file__).resolve().parent / "ot2_twin_template.html"
TRASH_SLOT = "12"


def kind_of(load_name: str) -> str:
    n = load_name.lower()
    if "tiprack" in n:
        return "tiprack"
    if "reservoir" in n:
        return "reservoir"
    return "plate"


def parse(analysis_path: str):
    a = json.loads(Path(analysis_path).read_text())
    cmds = a.get("commands", [])
    liquids = {l["id"]: l for l in (a.get("liquids") or [])}

    # ---- labware + pipette ----
    id2slot, id2load, id2def = {}, {}, {}
    pipette = {"model": "unknown", "channels": 1, "minVol": 0, "maxVol": 0,
               "tipLength": 0.0, "mount": "left"}
    for c in cmds:
        t = c.get("commandType")
        if t == "loadLabware":
            p, r = c["params"], c.get("result", {})
            lid = r.get("labwareId")
            id2slot[lid] = str(p.get("location", {}).get("slotName"))
            id2load[lid] = p.get("loadName")
            id2def[lid] = r.get("definition", {})
        elif t == "loadPipette":
            p = c["params"]
            name = p.get("pipetteName", "unknown")
            pipette["model"] = name
            pipette["mount"] = p.get("mount", "left")
            pipette["channels"] = 8 if "multi" in name else 1
    # pipette volume envelope from the name
    vol_map = {"p20": (1, 20), "p50": (5, 50), "p300": (20, 300), "p1000": (100, 1000)}
    for k, (lo, hi) in vol_map.items():
        if k in pipette["model"]:
            pipette["minVol"], pipette["maxVol"] = lo, hi

    slots = deckmod.load_deck("ot2_standard")

    # ---- build labware geometry (exact) ----
    labware = []
    key_of = {}  # labwareId -> slot key
    for lid, dfn in id2def.items():
        slot = id2slot[lid]
        key_of[lid] = slot
        pos = slots[slot]["position"]
        corner = dfn.get("cornerOffsetFromSlot", {"x": 0, "y": 0, "z": 0})
        dims = dfn.get("dimensions", {})
        cz = corner.get("z", 0)
        wells = []
        tiplen = (dfn.get("parameters", {}) or {}).get("tipLength")
        for wname, w in dfn.get("wells", {}).items():
            wells.append({
                "name": wname,
                "x": pos[0] + corner.get("x", 0) + w["x"],
                "y": pos[1] + corner.get("y", 0) + w["y"],
                "bottomZ": pos[2] + cz + w["z"],
                "depth": w.get("depth", 10),
                "diameter": w.get("diameter", w.get("xDimension", 6)),
                "yDim": w.get("yDimension", w.get("diameter", 6)),
                "shape": w.get("shape", "circular"),
                "capacity": w.get("totalLiquidVolume", 0),
            })
        labware.append({
            "id": lid, "slot": slot, "loadName": id2load[lid],
            "kind": kind_of(id2load[lid]),
            "displayName": (dfn.get("metadata", {}) or {}).get("displayName", id2load[lid]),
            "cornerX": pos[0] + corner.get("x", 0),
            "cornerY": pos[1] + corner.get("y", 0),
            "cornerZ": pos[2] + cz,
            "dimX": dims.get("xDimension", 127.76),
            "dimY": dims.get("yDimension", 85.47),
            "dimZ": dims.get("zDimension", 15),
            "tipLength": tiplen,
            "wells": wells,
        })
        if tiplen:
            pipette["tipLength"] = tiplen

    travel_z = max((lw["cornerZ"] + lw["dimZ"] for lw in labware), default=40) + 20

    # Deck layout to match THIS machine: slots 1-8 are labware placeholders, slot 9 is the
    # (larger) trash area at the back-right. Positions use the real Opentrons slot pitch, so
    # the loaded labware (slots 1/2/3) sits exactly where the ledger puts it.
    occupied = {lw["slot"] for lw in labware}
    slot_list = []
    for sid in [str(i) for i in range(1, 9)]:          # 1..8 placeholders
        if sid not in slots:
            continue
        p = slots[sid]["position"]; bb = slots[sid]["boundingBox"]
        slot_list.append({"id": sid, "x": p[0], "y": p[1],
                          "dx": bb["xDimension"], "dy": bb["yDimension"],
                          "isTrash": False, "occupied": sid in occupied})

    # slot 9 = trash, LARGER than a placeholder, at the back-right corner
    anc = slots["9"]["position"]; bb9 = slots["9"]["boundingBox"]
    t_dx, t_dy = bb9["xDimension"] * 1.15, bb9["yDimension"] * 1.35
    tcx = anc[0] + bb9["xDimension"] / 2 + (t_dx - bb9["xDimension"]) / 2
    tcy = anc[1] + bb9["yDimension"] / 2 + (t_dy - bb9["yDimension"]) / 2
    trash = {"x": tcx, "y": tcy, "z": anc[2], "dx": t_dx, "dy": t_dy, "dz": 55, "id": "9"}
    slot_list.append({"id": "9", "x": tcx - t_dx / 2, "y": tcy - t_dy / 2,
                      "dx": t_dx, "dy": t_dy, "isTrash": True, "occupied": False})

    # deck extent over the 1-9 grid (drives the platform + camera framing)
    x0 = min(s["x"] for s in slot_list); x1 = max(s["x"] + s["dx"] for s in slot_list)
    y0 = min(s["y"] for s in slot_list); y1 = max(s["y"] + s["dy"] for s in slot_list)

    # pipette home / park position: directly above the trash (matches the real robot at rest)
    home = [trash["x"], trash["y"], travel_z]

    def well_of(lid, wname):
        for lw in labware:
            if lw["id"] == lid:
                for w in lw["wells"]:
                    if w["name"] == wname:
                        return lw, w
        return None, None

    # ---- initial liquids (loadLiquid) ----
    initial = {}  # "slot/well" -> [{liquidId, vol}]
    for c in cmds:
        if c.get("commandType") == "loadLiquid":
            p = c["params"]; lid = p["labwareId"]; slot = id2slot.get(lid)
            for wname, vol in p.get("volumeByWell", {}).items():
                initial.setdefault(f"{slot}/{wname}", []).append(
                    {"liquidId": p["liquidId"], "vol": float(vol)})

    # ---- replay the ledger into ordered steps ----
    steps = []
    prev = list(home)   # robot starts parked above the trash

    def push(stype, x, y, z_action, **extra):
        nonlocal prev
        s = {"i": len(steps), "type": stype,
             "travel": [round(prev[0], 2), round(prev[1], 2), round(travel_z, 2)],
             "approach": [round(x, 2), round(y, 2), round(travel_z, 2)],
             "contact": [round(x, 2), round(y, 2), round(z_action, 2)]}
        s.update(extra)
        steps.append(s)
        prev = [x, y, travel_z]

    # Detect mixing: an aspirate immediately followed by a dispense in the SAME well is a
    # mix cycle (Opentrons mix / mix_after) — homogenizing a just-added reagent, NOT a
    # transfer. Label them "mix N/M" so the twin reads correctly.
    ad = [i for i, c in enumerate(cmds) if c.get("commandType") in ("aspirate", "dispense")]
    mix_of = {}
    j = 0
    while j < len(ad) - 1:
        a, d = cmds[ad[j]], cmds[ad[j + 1]]
        same = (a["commandType"] == "aspirate" and d["commandType"] == "dispense"
                and a["params"].get("labwareId") == d["params"].get("labwareId")
                and a["params"].get("wellName") == d["params"].get("wellName"))
        if same:
            run, k = [], j
            while k < len(ad) - 1:
                aa, dd = cmds[ad[k]], cmds[ad[k + 1]]
                if (aa["commandType"] == "aspirate" and dd["commandType"] == "dispense"
                        and aa["params"].get("wellName") == a["params"].get("wellName")
                        and dd["params"].get("wellName") == a["params"].get("wellName")):
                    run += [(ad[k], ad[k + 1])]; k += 2
                else:
                    break
            for n, (ia, idd) in enumerate(run, 1):
                mix_of[ia] = mix_of[idd] = (n, len(run))
            j = k
        else:
            j += 1

    for ci, c in enumerate(cmds):
        t = c.get("commandType"); p = c.get("params", {})
        if t == "pickUpTip":
            lid = p["labwareId"]; wname = p.get("wellName", "A1")
            lw, w = well_of(lid, wname)
            top = lw["cornerZ"] + lw["dimZ"]
            push("pickUpTip", w["x"], w["y"], top,
                 slot=lw["slot"], well=wname,
                 op={"kind": "pickTip", "rack": lw["slot"], "well": wname})
        elif t in ("aspirate", "dispense"):
            lid = p["labwareId"]; wname = p.get("wellName", "A1"); vol = float(p.get("volume", 0))
            lw, w = well_of(lid, wname)
            zc = w["bottomZ"] + 2.0
            push(t, w["x"], w["y"], zc, slot=lw["slot"], well=wname, volume=vol,
                 mix=mix_of.get(ci),
                 op={"kind": t, "well": f"{lw['slot']}/{wname}", "vol": vol})
        elif t in ("dropTipInPlace", "moveToAddressableAreaForDropTip"):
            if t == "dropTipInPlace" and trash:
                push("dropTip", trash["x"], trash["y"], trash["z"] + trash["dz"],
                     slot=TRASH_SLOT, op={"kind": "dropTip"})

    meta = {}
    irp = Path(analysis_path).parent / "ir.json"
    if irp.exists():
        ir = json.loads(irp.read_text())
        meta = {"protocol_name": ir.get("protocol_name"),
                "paper": ir.get("paper", {}),
                "api_level": ir.get("api_level"),
                "partition": ir.get("automation_partition", {}),
                "dilution": ir.get("dilution", {})}
    conf = None
    cp = Path(analysis_path).parent / "conformance.json"
    if cp.exists():
        conf = json.loads(cp.read_text())

    return {
        "meta": meta, "conformance": conf, "pipette": pipette,
        "deck": {"x0": x0, "x1": x1, "y0": y0, "y1": y1,
                 "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "travelZ": travel_z,
                 "slots": slot_list, "home": home},
        "trash": trash, "labware": labware, "liquids": liquids,
        "initial": initial, "steps": steps,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "ot2_digital_twin.html"))
    ap.add_argument("--no-chassis", action="store_true", help="omit the embedded OT-2 mesh (smaller file)")
    args = ap.parse_args()

    scene = parse(args.analysis)

    # embed the real OT-2 glass shell (detailed STL) as base64 + its alignment
    stl_b64 = ""
    align = {}
    if not args.no_chassis:
        stl = ASSETS / "ot2_reference_detailed.stl"
        ap_ = ASSETS / "alignment.json"
        if stl.exists() and ap_.exists():
            stl_b64 = base64.b64encode(stl.read_bytes()).decode()
            align = json.loads(ap_.read_text())

    html = TEMPLATE.read_text()
    html = html.replace("/*__SCENE_JSON__*/", json.dumps(scene))
    html = html.replace("/*__CHASSIS_JSON__*/",
                        json.dumps({"pos": align.get("pos", [0, 0, 0]),
                                    "opacity": 0.12}))
    html = html.replace("__STL_B64__", stl_b64)
    Path(args.out).write_text(html)
    kb = len(html) / 1024
    print(f"scene: {len(scene['steps'])} steps, {len(scene['labware'])} labware, "
          f"{sum(len(l['wells']) for l in scene['labware'])} wells, chassis={'yes' if stl_b64 else 'no'}")
    print(f"wrote {args.out} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
