"""Final articulation split of the OT-2 reference CAD, using measured component bounds.

    ot2_frame.stl     frame + posts + rails (static)                -> black
    ot2_deck.stl      deck plate (static)                           -> light grey
    ot2_carriage.stl  z-stage plates + Z linear rails, rides beam   -> dark
    ot2_pipette.stl   LEFT-mount pipette (the real CAD pipette)     -> white

The gantry beam is NOT separable in this reference model (verified by z-band scan: every
band spans full width because of the side rails; middle bands hold only corner posts), so
Isaac builds the beam parametrically and drives it in Y.
"""
import os
import json
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "twin/assets/ot2/ot2_upright_nopanels.stl")
OUT = os.path.join(ROOT, "twin/cad/out")
ASSETS = os.path.join(ROOT, "twin/assets/ot2")

m = trimesh.load(SRC)
comps = m.split(only_watertight=False)
W = m.extents[0]
Zmax = m.bounds[1][2]

LEFT_X = (160.0, 197.0)     # measured: left pipette body + internals x[162.8,194.8]
RIGHT_X = (195.0, 232.0)    # measured: right pipette body     x[196.8,228.8]

frame, deck, carriage, left, right = [], [], [], [], []
for c in comps:
    b0, b1 = c.bounds
    xw = b1[0] - b0[0]
    flat_wide_low = (b1[2] - b0[2]) < 20 and xw > 0.6 * W and b0[2] < 30
    in_band = b1[2] > 120 and b0[2] < Zmax - 90 and xw < 0.45 * W
    if flat_wide_low:
        deck.append(c)
    elif in_band and b0[0] >= LEFT_X[0] and b1[0] <= LEFT_X[1]:
        left.append(c)
    elif in_band and b0[0] >= RIGHT_X[0] and b1[0] <= RIGHT_X[1]:
        right.append(c)
    elif in_band:
        carriage.append(c)
    else:
        frame.append(c)


def merge(l):
    return trimesh.util.concatenate(l) if l else None


parts = {"frame": merge(frame), "deck": merge(deck),
         "carriage": merge(carriage), "pipette": merge(left), "pipette_right": merge(right)}

meta = {}
print("parts:")
for k, v in parts.items():
    if v is None:
        print(f"  {k:14s} EMPTY")
        continue
    b = np.round(v.bounds, 1)
    print(f"  {k:14s} faces={len(v.faces):6d} x[{b[0][0]:7.1f},{b[1][0]:7.1f}] "
          f"y[{b[0][1]:7.1f},{b[1][1]:7.1f}] z[{b[0][2]:7.1f},{b[1][2]:7.1f}]")
    v.export(os.path.join(ASSETS, f"ot2_{k}.stl"))
    meta[k] = {"faces": int(len(v.faces)), "bounds": v.bounds.tolist()}

# nozzle = bottom-center of the LEFT pipette (where a tip attaches)
if parts["pipette"] is not None:
    p = parts["pipette"]
    nozzle = [float((p.bounds[0][0] + p.bounds[1][0]) / 2),
              float((p.bounds[0][1] + p.bounds[1][1]) / 2),
              float(p.bounds[0][2])]
    meta["nozzle"] = [round(v, 2) for v in nozzle]
    print("\nLEFT pipette nozzle (tip attach point):", meta["nozzle"])

# carriage top block = where the beam sits (for the parametric beam height)
if parts["carriage"] is not None:
    cb = parts["carriage"].bounds
    meta["beam"] = {"z0": float(cb[1][2] - 100), "z1": float(cb[1][2]),
                    "y0": float(cb[0][1]), "y1": float(cb[1][1]),
                    "carriage_center": [float((cb[0][0] + cb[1][0]) / 2),
                                        float((cb[0][1] + cb[1][1]) / 2)]}
    print("beam band (parametric):", json.dumps(meta["beam"]))

meta["machine_bounds"] = m.bounds.tolist()
json.dump(meta, open(os.path.join(ASSETS, "parts.json"), "w"), indent=2)
print("wrote parts.json")


def to_pv(tm):
    f = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, f)


colors = {"frame": "#17181c", "deck": "#c9ced5", "carriage": "#4a5058",
          "pipette": "#f4f6f9", "pipette_right": "#8f979f"}
for cpos, nm in [("iso", "60_final_iso"), ("xz", "61_final_front")]:
    p = pv.Plotter(off_screen=True, window_size=(1100, 820))
    p.set_background("white")
    for k, v in parts.items():
        if v is not None:
            p.add_mesh(to_pv(v), color=colors[k], smooth_shading=True, specular=0.45)
    p.add_axes(line_width=4)
    p.camera_position = cpos
    p.screenshot(os.path.join(OUT, f"{nm}.png"))
    p.close()
    print("  wrote", nm + ".png")
