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

# Every OT-2 pipette, single and 8-channel. A multi is modelled as 8 nozzles on
# 9 mm centres: it takes a whole tip-rack column, and one aspirate moves liquid
# in eight wells at once. Flex pipettes and the 96-channel head are refused —
# this is an OT-2 twin and their geometry is not the same machine.
CAD_PIPETTES = {
    "p20_single_gen2":   "P20 single-channel GEN2",
    "p300_single_gen2":  "P300 single-channel GEN2",
    "p1000_single_gen2": "P1000 single-channel GEN2",
    "p20_multi_gen2":    "P20 8-channel GEN2",
    "p300_multi_gen2":   "P300 8-channel GEN2",
    "p10_single":        "P10 single-channel GEN1",
    "p50_single":        "P50 single-channel GEN1",
    "p300_single":       "P300 single-channel GEN1",
    "p1000_single":      "P1000 single-channel GEN1",
    "p10_multi":         "P10 8-channel GEN1",
    "p50_multi":         "P50 8-channel GEN1",
    "p300_multi":        "P300 8-channel GEN1",
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


# Modules the lab actually owns and the twin models: a body on the deck at the
# right footprint and height, and labware raised onto it by the module's own
# labwareOffset. Anything else is still refused.
CAD_MODULES = {
    "temperatureModuleV1": "Temperature Module GEN1",
    "temperatureModuleV2": "Temperature Module GEN2",
    "magneticModuleV1":    "Magnetic Module GEN1",
    "magneticModuleV2":    "Magnetic Module GEN2",
    "thermocyclerModuleV1": "Thermocycler GEN1 (lid rendered, opens/closes)",
}


def modules():
    """Emit module geometry too, not just support flags.

    The Isaac container has no Opentrons package, so the twin cannot read module
    definitions at run time. The numbers it needs to place a module and the
    labware on top of it are baked in here.
    """
    root = os.path.join(BASE, "data", "module", "definitions")
    seen = {}
    for sub in sorted(os.listdir(root)):
        p = os.path.join(root, sub)
        if not os.path.isdir(p):
            continue
        for f in sorted(os.listdir(p)):
            j = json.load(open(os.path.join(p, f)))
            mid = j.get("model") or f.replace(".json", "")
            dims = j.get("dimensions", {})
            entry = {
                "display": j.get("displayName", mid),
                "type": j.get("moduleType", "?"),
                # geometry: footprint, height, where the body sits vs the slot,
                # and where labware sits on top of the body
                "x_dim": dims.get("xDimension"),
                "y_dim": dims.get("yDimension"),
                "height": dims.get("bareOverallHeight"),
                "lid_height": dims.get("lidHeight"),
                "labware_iface_x": dims.get("labwareInterfaceXDimension"),
                "labware_iface_y": dims.get("labwareInterfaceYDimension"),
                "corner_offset": j.get("cornerOffsetFromSlot", {}),
                "labware_offset": j.get("labwareOffset", {}),
            }
            if mid in CAD_MODULES:
                entry["support"] = "cad"
                entry["note"] = CAD_MODULES[mid]
            else:
                entry["support"] = "unsup"
                entry["note"] = "not modelled (no geometry for this module)"
            seen[mid] = entry
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
            e["note"] = "Flex / 96-channel — this twin is an OT-2"
        else:
            e["support"] = "unsup"
            e["note"] = "not an OT-2 pipette"
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
    print(f"  modules  {sum(1 for v in reg['modules'].values() if v['support'] == 'cad')} "
          f"supported / {len(reg['modules'])} known")
    return 0


if __name__ == "__main__":
    sys.exit(main())
