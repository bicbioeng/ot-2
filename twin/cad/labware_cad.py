"""Generate REAL labware bodies with boolean-cut cavities, from the exact Opentrons
definitions embedded in a run's ledger. Nothing here is hand-typed geometry.

A well plate modelled as an opaque box with cylinders sitting inside it reads as a
featureless slab — the wells are only visible when the renderer highlights them. The fix is
to actually subtract the wells, so the cavities are real geometry that catches light and
shadow like the physical plate.

Outputs (labware LOCAL frame: origin at the labware corner, z=0 at the slot surface):
    lw_<loadname>.stl   (keyed by load name so protocols share the asset dir)
plus lw_meta.json describing what was cut, for the Isaac scene to place liquids correctly.
"""
import os
import sys
import json
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "twin/cad/out")
ASSETS = os.path.join(ROOT, "twin/assets/labware")
os.makedirs(ASSETS, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

LEDGER = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(ROOT, "examples/chemotaxis_prism/out/analysis.json")

# rack block heights (the labware zDimension includes the tubes/tips that stand in them)
TUBERACK_BLOCK_H = 45.0
TIPRACK_TRAY_H = 52.0
SEG = 48


def cyl(radius, height, z0, x, y, sections=SEG):
    c = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    c.apply_translation([x, y, z0 + height / 2])
    return c


a = json.loads(open(LEDGER).read())
_meta_path = os.path.join(ASSETS, "lw_meta.json")
meta = json.load(open(_meta_path)) if os.path.exists(_meta_path) else {}
print(f"existing labware entries: {[k for k in meta if k != 'tube_model']}")
for cmd in a.get("commands", []):
    if cmd.get("commandType") != "loadLabware":
        continue
    d = cmd["result"]["definition"]
    slot = str(cmd["params"]["location"]["slotName"])
    p, dim = d["parameters"], d["dimensions"]
    load = p["loadName"]
    X, Y, Z = dim["xDimension"], dim["yDimension"], dim["zDimension"]
    wells = d["wells"]
    low = load.lower()

    print("=" * 66)
    print(f"slot {slot}: {load}  ({X:.2f} x {Y:.2f} x {Z:.2f} mm, {len(wells)} wells)")

    if "tuberack" in low:
        body_h = min(TUBERACK_BLOCK_H, Z)
        bore_r = max(w["diameter"] for w in wells.values()) / 2 + 1.4      # tube OD clearance
        kind = "tuberack"
    elif p.get("isTiprack") or "tiprack" in low:
        body_h = min(TIPRACK_TRAY_H, Z)
        bore_r = max(w["diameter"] for w in wells.values()) / 2 + 0.5
        kind = "tiprack"
    else:
        body_h = Z
        bore_r = None                                                      # per-well diameter
        kind = "plate"

    body = trimesh.creation.box((X, Y, body_h))
    body.apply_translation([X / 2, Y / 2, body_h / 2])

    cutters = []
    for name, w in wells.items():
        r = (bore_r if bore_r is not None else w["diameter"] / 2)
        if kind == "plate":
            z0 = w["z"]                       # real well bottom above the plate floor
            h = body_h - z0 + 1.0             # cut up through the top face
        else:
            z0 = -1.0
            h = body_h + 2.0                  # through-bore
        cutters.append(cyl(r, h, z0, w["x"], w["y"]))

    print(f"  cutting {len(cutters)} cavities (r={cutters[0].bounding_box.extents[0]/2:.2f} mm) "
          f"from a {body_h:.1f} mm body ...")
    cut = trimesh.boolean.difference([body] + cutters, engine="manifold")
    print(f"  -> faces={len(cut.faces)} watertight={cut.is_watertight} "
          f"volume={cut.volume/1000:.1f} cm^3")

    path = os.path.join(ASSETS, f"lw_{load}.stl")
    cut.export(path)

    meta[load] = {
        "loadName": load, "kind": kind, "mesh": os.path.basename(path),
        "dims": [X, Y, Z], "body_h": body_h,
        "wells": {n: {"x": w["x"], "y": w["y"], "z": w["z"], "depth": w["depth"],
                      "d": w["diameter"], "vmax": w.get("totalLiquidVolume", 0)}
                  for n, w in wells.items()},
    }
    if kind == "tiprack":
        meta[load]["tipLength"] = p.get("tipLength")

json.dump(meta, open(_meta_path, "w"), indent=2)
print("\nwrote lw_meta.json ->", ASSETS)


# ---- render the plate so the cavities can be verified by eye ----
def to_pv(tm):
    f = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, f)


for slot, m in meta.items():
    if not isinstance(m, dict) or "kind" not in m or "mesh" not in m:
        continue
    tm = trimesh.load(os.path.join(ASSETS, m["mesh"]))
    p = pv.Plotter(off_screen=True, window_size=(900, 680))
    p.set_background("white")
    p.add_mesh(to_pv(tm), color="#e8ecf0", smooth_shading=False, show_edges=False, specular=0.4)
    p.add_axes(line_width=3)
    p.camera_position = "iso"
    p.screenshot(os.path.join(OUT, f"70_lw_{m['kind']}_{slot[:22]}.png"))
    p.close()
    print(f"  wrote 70_lw_{m['kind']}_{slot[:22]}.png")
