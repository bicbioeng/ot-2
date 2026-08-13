"""Decompose the upright, panels-off OT-2 into the assemblies the real machine moves as:

    static   : frame posts + extrusion rails + deck plate + trash bin   (never moves)
    gantry   : the X-beam spanning left-right, which travels in Y (front-back)
    carriage : the Z-stage / pipette mount hanging off the beam, travels in X along it

The reference STL is one fused body, so nothing can animate until it is split. We classify
by real spatial rules in the deck frame (deck surface z=0), render each group in a distinct
color to verify by eye, then export three STLs for Isaac to drive as separate Xforms.
"""
import os
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "twin/assets/ot2/ot2_upright_nopanels.stl")   # already deck-aligned
OUT = os.path.join(ROOT, "twin/cad/out")
ASSETS = os.path.join(ROOT, "twin/assets/ot2")
os.makedirs(OUT, exist_ok=True)

m = trimesh.load(SRC)
print("source:", os.path.basename(SRC), "faces", len(m.faces))
print("bounds min", np.round(m.bounds[0], 1), "max", np.round(m.bounds[1], 1))

comps = m.split(only_watertight=False)
print("components:", len(comps))

# ---- inspect the biggest bodies so classification is grounded, not guessed ----
info = []
for i, c in enumerate(comps):
    b0, b1 = c.bounds
    info.append((len(c.faces), i, b0, b1, c.extents))
info.sort(reverse=True, key=lambda t: t[0])
print("\ntop bodies by face count (deck frame, z=0 is deck surface):")
for nf, i, b0, b1, ex in info[:18]:
    print(f"  #{i:4d} faces={nf:6d}  x[{b0[0]:7.1f},{b1[0]:7.1f}] "
          f"y[{b0[1]:7.1f},{b1[1]:7.1f}] z[{b0[2]:7.1f},{b1[2]:7.1f}]")

# ---- classify ----
# The gantry assembly lives ABOVE the deck and its labware (nothing static is up there
# except the top frame rails, which sit at the very top and span the full footprint).
Zmax = m.bounds[1][2]
Xmin, Xmax = m.bounds[0][0], m.bounds[1][0]
TOP_FRAME_Z = Zmax - 90.0        # top frame rails band
GANTRY_Z_LO = 120.0              # above labware height

static, gantry, carriage = [], [], []
for c in comps:
    b0, b1 = c.bounds
    ex = c.extents
    cz_lo, cz_hi = b0[2], b1[2]
    spans_x = (b1[0] - b0[0]) > 0.72 * (Xmax - Xmin)
    in_gantry_band = cz_hi > GANTRY_Z_LO and cz_lo < TOP_FRAME_Z
    if not in_gantry_band:
        static.append(c)
        continue
    # within the gantry band: the beam spans X; the carriage is a compact body that hangs low
    if spans_x and ex[2] < 200:
        gantry.append(c)
    elif (b1[0] - b0[0]) < 0.45 * (Xmax - Xmin) and cz_lo < 420:
        carriage.append(c)
    else:
        static.append(c)

print(f"\nclassified: static={len(static)}  gantry={len(gantry)}  carriage={len(carriage)}")


def merge(lst):
    return trimesh.util.concatenate(lst) if lst else None


def to_pv(tm):
    f = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, f)


groups = [("static", merge(static), "lightslategray"),
          ("gantry", merge(gantry), "red"),
          ("carriage", merge(carriage), "limegreen")]

for cpos, nm in [("iso", "40_groups_iso"), ("xz", "41_groups_front"), ("yz", "42_groups_side")]:
    p = pv.Plotter(off_screen=True, window_size=(1100, 820))
    p.set_background("white")
    for name, g, col in groups:
        if g is not None:
            p.add_mesh(to_pv(g), color=col, smooth_shading=True, specular=0.3)
    p.add_axes(line_width=4)
    p.camera_position = cpos
    p.screenshot(os.path.join(OUT, f"{nm}.png"))
    p.close()
    print("  wrote", nm + ".png")

for name, g, _ in groups:
    if g is None:
        print(f"  !! {name}: EMPTY")
        continue
    path = os.path.join(ASSETS, f"ot2_{name}.stl")
    g.export(path)
    print(f"  exported ot2_{name}.stl  faces={len(g.faces):6d} "
          f"bounds x[{g.bounds[0][0]:.0f},{g.bounds[1][0]:.0f}] "
          f"y[{g.bounds[0][1]:.0f},{g.bounds[1][1]:.0f}] z[{g.bounds[0][2]:.0f},{g.bounds[1][2]:.0f}]")
