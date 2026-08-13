"""Find the X-gantry beam inside the fused frame body, and split the carriage into
z-stage / left pipette / right pipette. Produces the articulated part set for Isaac:

    ot2_frame.stl     static frame + posts + top rails          (black)
    ot2_deck.stl      deck plate                                (light grey)
    ot2_beam.stl      X-beam, travels in Y                      (dark)
    ot2_zstage.stl    Z carriage block, travels in X (+Z)       (dark)
    ot2_pipette.stl   LEFT-mount pipette, travels in Z          (white)

Also reports the pipette NOZZLE tip position so tips/liquid attach at the real point.
"""
import os
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
comps = sorted(comps, key=lambda c: -len(c.faces))
frame_body = comps[0]                      # biggest = frame + beam fused
print("frame body faces:", len(frame_body.faces),
      "bounds", np.round(frame_body.bounds, 1).tolist())

# ---- histogram the frame body by z to locate the beam band ----
fc = frame_body.triangles_center
Xlo, Xhi = frame_body.bounds[0][0], frame_body.bounds[1][0]
W = Xhi - Xlo
print("\nz-band scan of the frame body (looking for a full-width band that is NOT the top rails):")
bands = []
for z0 in range(int(frame_body.bounds[0][2]), int(frame_body.bounds[1][2]), 25):
    sel = (fc[:, 2] >= z0) & (fc[:, 2] < z0 + 25)
    if sel.sum() < 40:
        continue
    xs, ys = fc[sel, 0], fc[sel, 1]
    span = (xs.max() - xs.min()) / W
    bands.append((z0, sel.sum(), span, ys.min(), ys.max()))
    print(f"  z[{z0:4d},{z0+25:4d}) faces={sel.sum():5d} x-span={span:4.2f} "
          f"y[{ys.min():7.1f},{ys.max():7.1f}]")

# The beam: full-width, sits in the upper-middle (below the very top rails), and is
# localized in Y (it is a beam, not the whole top frame).
CARRIAGE_TOP_Z = 418.5      # measured: carriage upper block z-range starts here
BEAM_Z0, BEAM_Z1 = CARRIAGE_TOP_Z - 30, frame_body.bounds[1][2] - 60
sel_faces = ((fc[:, 2] >= BEAM_Z0) & (fc[:, 2] <= BEAM_Z1) &
             (fc[:, 1] > 100) & (fc[:, 1] < 260))
print(f"\nbeam selection z[{BEAM_Z0:.0f},{BEAM_Z1:.0f}] y[100,260] -> faces {sel_faces.sum()}")

beam = None
if sel_faces.sum() > 200:
    beam = frame_body.submesh([np.where(sel_faces)[0]], append=True)
    rest = frame_body.submesh([np.where(~sel_faces)[0]], append=True)
    print("  beam bounds:", np.round(beam.bounds, 1).tolist())
    print("  beam x-span fraction:", round((beam.bounds[1][0] - beam.bounds[0][0]) / W, 2))
else:
    rest = frame_body
    print("  !! no beam band found; frame stays fused")

# ---- deck plate + remaining static ----
deck_body = None
static_rest = []
for c in comps[1:]:
    b0, b1 = c.bounds
    if (b1[2] - b0[2]) < 20 and (b1[0] - b0[0]) > 0.6 * W and b0[2] < 30:
        deck_body = c if deck_body is None else trimesh.util.concatenate([deck_body, c])
    else:
        static_rest.append(c)

# ---- carriage assembly (everything in the gantry band, from decompose.py rules) ----
Zmax = m.bounds[1][2]
carr = []
leftover = []
for c in static_rest:
    b0, b1 = c.bounds
    if b1[2] > 120 and b0[2] < Zmax - 90 and (b1[0] - b0[0]) < 0.45 * W:
        carr.append(c)
    else:
        leftover.append(c)

# split carriage by x into left pipette / right pipette / shared z-stage
LEFT_X = (150.0, 196.0)      # measured pipette body ranges (+ ejector arms)
RIGHT_X = (196.0, 250.0)
left, right, zstage = [], [], []
for c in carr:
    cx = c.centroid[0]
    b0, b1 = c.bounds
    tall = (b1[2] - b0[2]) > 120
    if tall and LEFT_X[0] <= cx < LEFT_X[1]:
        left.append(c)
    elif tall and RIGHT_X[0] <= cx < RIGHT_X[1]:
        right.append(c)
    else:
        zstage.append(c)


def merge(lst):
    return trimesh.util.concatenate(lst) if lst else None


parts = {
    "frame": merge([rest] + leftover),
    "deck": deck_body,
    "beam": beam,
    "zstage": merge(zstage),
    "pipette": merge(left),
    "pipette_right": merge(right),
}

print("\nparts:")
for k, v in parts.items():
    if v is None:
        print(f"  {k:14s} EMPTY")
        continue
    b = np.round(v.bounds, 1)
    print(f"  {k:14s} faces={len(v.faces):6d} x[{b[0][0]:7.1f},{b[1][0]:7.1f}] "
          f"y[{b[0][1]:7.1f},{b[1][1]:7.1f}] z[{b[0][2]:7.1f},{b[1][2]:7.1f}]")
    v.export(os.path.join(ASSETS, f"ot2_{k}.stl"))

if parts["pipette"] is not None:
    p = parts["pipette"]
    nozzle = [round(float(p.centroid[0]), 1), round(float(p.centroid[1]), 1), round(float(p.bounds[0][2]), 1)]
    print("\nLEFT pipette nozzle tip (attach tips/liquid here):", nozzle)


def to_pv(tm):
    f = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, f)


colors = {"frame": "#1a1a1e", "deck": "#c8ccd2", "beam": "#3a3f47",
          "zstage": "#5a6068", "pipette": "#f2f4f7", "pipette_right": "#9aa2ab"}
for cpos, nm in [("iso", "50_parts_iso"), ("xz", "51_parts_front")]:
    p = pv.Plotter(off_screen=True, window_size=(1100, 820))
    p.set_background("white")
    for k, v in parts.items():
        if v is not None:
            p.add_mesh(to_pv(v), color=colors[k], smooth_shading=True, specular=0.4)
    p.add_axes(line_width=4)
    p.camera_position = cpos
    p.screenshot(os.path.join(OUT, f"{nm}.png"))
    p.close()
    print("  wrote", nm + ".png")
