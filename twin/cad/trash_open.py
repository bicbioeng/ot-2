"""The Opentrons reference CAD simplifies the trash to a SOLID block, so discarded tips could
only ever sit on its lid. The real OT-2 trash is an open container that tips fall into.

The frame mesh is a component selection (not a closed volume) so a boolean fails. Instead we
delete the block's LID faces — the large up-facing plane at the tray surface — and record the
cavity so the scene can line it with a floor + 4 inner walls and pile the used tips inside.
"""
import os
import json
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
rng = np.random.default_rng(7)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, "twin/assets/ot2")
OUT = os.path.join(ROOT, "twin/cad/out")

meta = json.load(open(os.path.join(ASSETS, "parts.json")))
tr = meta["trash"]
x0, x1 = tr["x"]; y0, y1 = tr["y"]; top = tr["surface_z"]
WALL, DEPTH = 9.0, 58.0

src = os.path.join(ASSETS, "ot2_frame.stl.bak")
if not os.path.exists(src):
    src = os.path.join(ASSETS, "ot2_frame.stl")
with open(src, "rb") as _fh:                      # .bak has no recognised extension
    frame = trimesh.load(_fh, file_type="stl")
print(f"frame in: {len(frame.faces)} faces (from {os.path.basename(src)})")

fc, fn = frame.triangles_center, frame.face_normals
lid = ((fn[:, 2] > 0.85) & (np.abs(fc[:, 2] - top) < 2.0) &
       (fc[:, 0] > x0 - 2) & (fc[:, 0] < x1 + 2) &
       (fc[:, 1] > y0 - 2) & (fc[:, 1] < y1 + 2))
print(f"lid faces to remove: {lid.sum()}")
kept = frame.submesh([np.where(~lid)[0]], append=True)
kept.export(os.path.join(ASSETS, "ot2_frame.stl"))
print(f"frame out: {len(kept.faces)} faces -> ot2_frame.stl (lid removed, bin is now open)")

meta["trash"].update({
    "rim_z": top, "floor_z": top - DEPTH, "wall": WALL,
    "inner_x": [x0 + WALL, x1 - WALL], "inner_y": [y0 + WALL, y1 - WALL],
})
json.dump(meta, open(os.path.join(ASSETS, "parts.json"), "w"), indent=2)
print(f"parts.json trash: rim={top:.1f} floor={top-DEPTH:.1f} "
      f"inner x{meta['trash']['inner_x']} y{meta['trash']['inner_y']}")

# ---- verification render: liner + a jumbled pile of used tips INSIDE the bin ----
ix0, ix1 = meta["trash"]["inner_x"]
iy0, iy1 = meta["trash"]["inner_y"]
floor = meta["trash"]["floor_z"]
liner = []
fl = trimesh.creation.box((ix1 - ix0, iy1 - iy0, 3.0))
fl.apply_translation([(ix0 + ix1) / 2, (iy0 + iy1) / 2, floor + 1.5])
liner.append(fl)
for (ax, ay, sx, sy) in ((ix0, None, 2.0, iy1 - iy0), (ix1, None, 2.0, iy1 - iy0),
                         (None, iy0, ix1 - ix0, 2.0), (None, iy1, ix1 - ix0, 2.0)):
    w = trimesh.creation.box((sx, sy, DEPTH))
    w.apply_translation([ax if ax is not None else (ix0 + ix1) / 2,
                         ay if ay is not None else (iy0 + iy1) / 2, floor + DEPTH / 2])
    liner.append(w)

TIP_LEN, TIP_R = 52.0, 3.3
tips = []
for i in range(24):
    t = trimesh.creation.cone(radius=TIP_R, height=TIP_LEN, sections=14)
    t.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2 + rng.normal(0, 0.30), [1, 0, 0]))
    t.apply_transform(trimesh.transformations.rotation_matrix(rng.uniform(0, 2 * np.pi), [0, 0, 1]))
    t.apply_translation([rng.uniform(ix0 + 16, ix1 - 16), rng.uniform(iy0 + 16, iy1 - 16),
                         floor + 3 + TIP_R + (i // 8) * 5.5 + rng.uniform(0, 1.6)])
    tips.append(t)
print(f"piled {len(tips)} tips on the bin floor z={floor:.1f} (rim {top:.1f})")


def to_pv(tm):
    f = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, f)


cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
for cam, nm in [([(cx + 200, cy - 260, top + 200), (cx, cy, floor + 20), (0, 0, 1)], "82_trash_open"),
                ([(cx + 40, cy - 120, top + 110), (cx, cy, floor + 15), (0, 0, 1)], "83_trash_open_close")]:
    p = pv.Plotter(off_screen=True, window_size=(1000, 760))
    p.set_background("white")
    p.add_mesh(to_pv(kept), color="#26282c", smooth_shading=True, specular=0.3)
    for w in liner:
        p.add_mesh(to_pv(w), color="#1b1d20", smooth_shading=True)
    for t in tips:
        p.add_mesh(to_pv(t), color="#eceee2", smooth_shading=True, specular=0.5)
    p.camera_position = cam
    p.screenshot(os.path.join(OUT, f"{nm}.png"))
    p.close()
    print("  wrote", nm + ".png")
