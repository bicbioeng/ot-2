"""Generate twin/registry.json — every Opentrons labware, module and pipette,
each marked with how well the Isaac twin can actually render it.

Run this (needs the repo venv, which has opentrons_shared_data) whenever the
Opentrons package is upgraded or a new CAD asset is added:

    .venv/bin/python scripts/build_registry.py

The twin itself only reads the generated JSON, so the Isaac container never
needs the Opentrons package installed.

SUPPORT TIERS
  cad      a real CAD body with boolean-cut cavities, plus matching tube/tip
           geometry where relevant. Renders correctly.
  unsup    we would have to fake it. Rendering a 1.5 mL Eppendorf with the
           15 mL Falcon mesh produces tubes towering over a featureless block --
           it looks authoritative and is wrong, which is worse than refusing.
"""
import json
import os
import sys

import opentrons_shared_data as osd

BASE = os.path.dirname(osd.__file__)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# What the twin can genuinely render. Keyed by Opentrons loadName.
# Adding an entry here is a promise that the geometry is right -- it must be
# backed by a mesh in twin/assets/labware and an entry in lw_meta.json.
# ---------------------------------------------------------------------------
CAD_LABWARE = {
    "corning_96_wellplate_360ul_flat":            "96-well plate, cavities cut",
    "corning_12_wellplate_6.9ml_flat":            "12-well plate, cavities cut",
    "opentrons_96_tiprack_300ul":                 "300 uL tips, individually removable",
    "opentrons_96_tiprack_20ul":                  "20 uL tips, individually removable",
    "opentrons_15_tuberack_falcon_15ml_conical":  "15 mL Falcon rack + conical tube geometry",
    "opentrons_1_trash_1100ml_fixed":             "open trash bin, discarded tips accumulate",
}

# Single-channel only: the twin models ONE nozzle per mount, so an 8-channel
# head would show a single tip doing work eight tips actually do.
CAD_PIPETTES = {
    "p300_single_gen2": "P300 single-channel GEN2",
    "p20_single_gen2":  "P20 single-channel GEN2",
}

REASONS = {
    "tubeRack": "no tube geometry for this rack — only the 15 mL Falcon is modelled",
    "reservoir": "trough wells are not modelled (rectangular, not circular)",
    "wellPlate": "no CAD body for this plate",
    "tipRack": "no CAD body for this tip rack",
    "adapter": "deck adapters are not modelled",
    "aluminumBlock": "aluminium blocks are not modelled",
    "lid": "lids are not modelled",
    "trash": "only the fixed 1100 mL trash is modelled",
    "other": "not modelled",
    "system": "not modelled",
}


def labware():
    root = os.path.join(BASE, "data", "labware", "definitions", "2")
    out = {}
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        ver = sorted(os.listdir(d))[-1]
        j = json.load(open(os.path.join(d, ver)))
        meta = j.get("metadata", {})
        cat = meta.get("displayCategory", "other")
        entry = {
            "category": cat,
            "display": meta.get("displayName", name),
            "wells": len(j.get("wells", {})),
        }
        if name in CAD_LABWARE:
            entry["support"] = "cad"
            entry["note"] = CAD_LABWARE[name]
        else:
            entry["support"] = "unsup"
            entry["note"] = REASONS.get(cat, "not modelled")
        out[name] = entry
    return out


def modules():
    root = os.path.join(BASE, "data", "module", "definitions")
    seen = {}
    for sub in sorted(os.listdir(root)):
        p = os.path.join(root, sub)
        if not os.path.isdir(p):
            continue
        for f in sorted(os.listdir(p)):
            j = json.load(open(os.path.join(p, f)))
            mid = j.get("model") or f.replace(".json", "")
            seen[mid] = {
                "display": j.get("displayName", mid),
                "type": j.get("moduleType", "?"),
                # The twin has no module support at all: no heating, no shaking,
                # no magnet, no lid motion, and no geometry on the deck.
                "support": "unsup",
                "note": "hardware modules are not modelled (no geometry, no thermal/motion state)",
            }
    return seen


def pipettes():
    p = os.path.join(BASE, "data", "pipette", "definitions", "1", "pipetteNameSpecs.json")
    j = json.load(open(p))
    out = {}
    for name, spec in sorted(j.items()):
        e = {
            "display": spec.get("displayName", name),
            "channels": spec.get("channels"),
            "min_ul": spec.get("minVolume"),
            "max_ul": spec.get("maxVolume"),
        }
        if name in CAD_PIPETTES:
            e["support"] = "cad"
            e["note"] = CAD_PIPETTES[name]
        elif "flex" in name or name == "p200_96":
            e["support"] = "unsup"
            e["note"] = "Flex pipette — this twin is an OT-2"
        elif spec.get("channels", 1) != 1:
            e["support"] = "unsup"
            e["note"] = "multi-channel: the twin models one nozzle per mount"
        else:
            e["support"] = "unsup"
            e["note"] = "no CAD for this pipette body"
        out[name] = e
    return out


def main():
    reg = {
        "opentrons_version": getattr(osd, "__version__", "unknown"),
        "labware": labware(),
        "modules": modules(),
        "pipettes": pipettes(),
    }
    dest = os.path.join(REPO, "twin", "registry.json")
    with open(dest, "w") as f:
        json.dump(reg, f, indent=1, sort_keys=True)
    n_ok = sum(1 for v in reg["labware"].values() if v["support"] == "cad")
    print(f"wrote {dest}")
    print(f"  labware  {n_ok} supported / {len(reg['labware'])} known")
    print(f"  pipettes {sum(1 for v in reg['pipettes'].values() if v['support'] == 'cad')} "
          f"supported / {len(reg['pipettes'])} known")
    print(f"  modules  0 supported / {len(reg['modules'])} known")
    return 0


if __name__ == "__main__":
    sys.exit(main())
