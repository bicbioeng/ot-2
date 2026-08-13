"""Integration check (local, fast): place the ledger's labware onto the upright,
panels-off OT-2 mesh's REAL deck slots and render, so alignment is verified before
pushing to Isaac. Prints the exact chassis placement to bake into the Isaac twin.
"""
import os
import sys
import json
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from twin import deck                                   # noqa: E402
from twin.deck import LabwareGeom, TRASH_SLOT           # noqa: E402

STL = os.path.join(ROOT, "twin/assets/ot2/ot2_reference_detailed.stl")
LEDGER = os.path.join(ROOT, "examples/chemotaxis_penstrep/out/bundle_live/analysis.json")
OUT = os.path.join(ROOT, "twin/cad/out")

# ---- upright + panels-off mesh, and track the deck-plate center through the transform ----
m = trimesh.load(STL)
C = m.centroid
R = trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0], C)
m.apply_transform(R)
tmin = m.bounds[0].copy()
m.apply_translation(-tmin)
Zt = m.extents[2]
# DETECT the deck plane: large upward-facing (normal +Z) region in the lower half of the machine
fn = m.face_normals
fc = m.triangles_center
areas = m.area_faces
sel = (fn[:, 2] > 0.80) & (fc[:, 2] < 0.45 * Zt) & (fc[:, 2] > 0.02 * Zt)   # exclude the very floor/feet
if not sel.any():
    sel = (fn[:, 2] > 0.7) & (fc[:, 2] < 0.5 * Zt)
deck_z = float(np.average(fc[sel, 2], weights=areas[sel]))
# deck footprint center from the selected up-faces (robust: 5-95 percentile bbox)
dx = (np.percentile(fc[sel, 0], 5) + np.percentile(fc[sel, 0], 95)) / 2
dy = (np.percentile(fc[sel, 1], 5) + np.percentile(fc[sel, 1], 95)) / 2
deck_pt = np.array([dx, dy, deck_z])
print("DETECTED deck plane: z=%.1f center=(%.1f,%.1f) [upright frame, height=%.1f]" % (deck_z, dx, dy, Zt))

comps = m.split(only_watertight=False)
Z = m.extents[2]
keep = []
for c in comps:
    ex, ey, ez = c.extents
    cz = c.centroid[2]
    if ((min(ex, ey) < 14 and max(ex, ey) > 150 and ez > 150) or
            (ez < 18 and ex > 150 and ey > 150 and cz > 0.55 * Z)):
        continue
    keep.append(c)
mesh = trimesh.util.concatenate(keep)

# ---- functional deck + labware from the ledger ----
slots = deck.load_deck("ot2_standard")
a = json.loads(open(LEDGER).read())
slot_defs = {}
for c in a.get("commands", []):
    if c.get("commandType") == "loadLabware":
        s = str(c["params"].get("location", {}).get("slotName"))
        d = c.get("result", {}).get("definition")
        if s and d:
            slot_defs[s] = d
geoms = {s: LabwareGeom(d) for s, d in slot_defs.items()}
x0, x1, y0, y1 = deck.deck_extent(slots)
func_cx, func_cy = (x0 + x1) / 2, (y0 + y1) / 2
print("functional deck center:", round(func_cx, 1), round(func_cy, 1), "extent x", round(x0, 1), round(x1, 1))

# ---- align mesh deck -> functional deck (this is the chassis placement for Isaac) ----
CHASSIS_OFFSET = np.array([func_cx - deck_pt[0], func_cy - deck_pt[1], 0.0 - deck_pt[2]])
print("CHASSIS_OFFSET (bake into Isaac, mesh already rotX+90):", np.round(CHASSIS_OFFSET, 1))
mesh.apply_translation(CHASSIS_OFFSET)
mesh.export(os.path.join(OUT, "ot2_upright_nopanels.stl"))

# ---- render mesh + labware boxes together ----
def to_pv(tm):
    f = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, f)

p = pv.Plotter(off_screen=True, window_size=(1100, 820))
p.set_background("white")
p.add_mesh(to_pv(mesh), color="lightsteelblue", smooth_shading=True, specular=0.4, opacity=1.0)
pal = ["goldenrod", "royalblue", "seagreen", "orchid"]
for i, (s, g) in enumerate(geoms.items()):
    pos = slots[s]["position"]; cxo, cyo, czo = g.corner
    xd, yd, zd = g.dims
    cx, cy, cz = pos[0] + cxo + xd / 2, pos[1] + cyo + yd / 2, pos[2] + czo + zd / 2
    box = pv.Cube(center=(cx, cy, cz), x_length=xd, y_length=yd, z_length=zd)
    p.add_mesh(box, color=pal[i % len(pal)])
if TRASH_SLOT in slots:
    tp = slots[TRASH_SLOT]["position"]; bb = slots[TRASH_SLOT]["boundingBox"]
    p.add_mesh(pv.Cube(center=(tp[0] + bb["xDimension"] / 2, tp[1] + bb["yDimension"] / 2, 20),
                       x_length=bb["xDimension"], y_length=bb["yDimension"], z_length=40), color="dimgray")
p.add_axes(line_width=4)
p.camera_position = "iso"
p.screenshot(os.path.join(OUT, "30_assembled_iso.png")); p.close()

for cpos, nm in [("xz", "31_assembled_front"), ("yz", "32_assembled_side")]:
    p = pv.Plotter(off_screen=True, window_size=(1100, 820)); p.set_background("white")
    p.add_mesh(to_pv(mesh), color="lightsteelblue", smooth_shading=True, specular=0.4)
    for i, (s, g) in enumerate(geoms.items()):
        pos = slots[s]["position"]; cxo, cyo, czo = g.corner; xd, yd, zd = g.dims
        p.add_mesh(pv.Cube(center=(pos[0]+cxo+xd/2, pos[1]+cyo+yd/2, pos[2]+czo+zd/2),
                           x_length=xd, y_length=yd, z_length=zd), color=pal[i % len(pal)])
    p.camera_position = cpos; p.add_axes(line_width=4)
    p.screenshot(os.path.join(OUT, f"{nm}.png")); p.close()
print("wrote 30_assembled_iso / 31_front / 32_side ; exported ot2_upright_nopanels.stl")
