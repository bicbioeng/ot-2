"""Measure the OT-2 trash tray from the CAD, bake it into parts.json, and RENDER a
verification image with discarded tips actually lying in it.

The tray is fused into the frame body, so it is found geometrically: the large up-facing
horizontal plane above the deck inside the machine's back-right quadrant.
"""
import os
import json
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, "twin/assets/ot2")
OUT = os.path.join(ROOT, "twin/cad/out")

frame = trimesh.load(os.path.join(ASSETS, "ot2_frame.stl"))
fc, fn, ar = frame.triangles_center, frame.face_normals, frame.area_faces

# largest up-facing plane above the deck plate -> the trash tray surface
cand = (fn[:, 2] > 0.85) & (fc[:, 2] > 18) & (fc[:, 2] < 130)
zs = fc[cand, 2]
# the dominant z among candidates, area-weighted
zbins = {}
for z, a in zip(zs, ar[cand]):
    zbins[round(float(z), 1)] = zbins.get(round(float(z), 1), 0.0) + float(a)
tray_z = max(zbins.items(), key=lambda kv: kv[1])[0]

sel = cand & (np.abs(fc[:, 2] - tray_z) < 1.5)
verts = np.array([v for i in np.where(sel)[0] for v in frame.triangles[i]])
x0, x1 = float(verts[:, 0].min()), float(verts[:, 0].max())
y0, y1 = float(verts[:, 1].min()), float(verts[:, 1].max())
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
print(f"TRASH TRAY: surface z={tray_z:.2f}  center=({cx:.1f},{cy:.1f})  "
      f"size={x1-x0:.1f} x {y1-y0:.1f} mm")

pj = os.path.join(ASSETS, "parts.json")
meta = json.load(open(pj)) if os.path.exists(pj) else {}
meta["trash"] = {"surface_z": tray_z, "center": [cx, cy],
                 "x": [x0, x1], "y": [y0, y1]}
json.dump(meta, open(pj, "w"), indent=2)
print("baked into parts.json")

# ---- verification render: 24 tips LYING on the tray, as they would after a run ----
TIP_LEN, TIP_R = 52.0, 3.2
tips = []
for i in range(24):
    ang = i * 2.399963
    rr = 12 + 5.0 * np.sqrt(i)
    px, py = cx + rr * np.cos(ang), cy + rr * np.sin(ang)
    px = float(np.clip(px, x0 + 12, x1 - 12)); py = float(np.clip(py, y0 + 12, y1 - 12))
    t = trimesh.creation.cone(radius=TIP_R, height=TIP_LEN, sections=16)
    # lay it DOWN: rotate 90 deg about X, then spin about Z — discarded tips lie flat
    t.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    t.apply_transform(trimesh.transformations.rotation_matrix((i * 37) % 360 * np.pi / 180, [0, 0, 1]))
    t.apply_translation([px, py, tray_z + TIP_R + 0.4 + (i % 3) * 1.2])
    tips.append(t)
print(f"placed {len(tips)} tips resting on z={tray_z:.1f} (+{TIP_R:.1f} mm so they lie on the surface)")


def to_pv(tm):
    f = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, f)


for cam, nm in [([(cx + 210, cy - 300, tray_z + 240), (cx, cy, tray_z), (0, 0, 1)], "80_trash_check"),
                ([(cx + 20, cy - 40, tray_z + 150), (cx, cy, tray_z), (0, 0, 1)], "81_trash_close")]:
    p = pv.Plotter(off_screen=True, window_size=(1000, 760))
    p.set_background("white")
    p.add_mesh(to_pv(frame), color="#2a2c30", smooth_shading=True, specular=0.3)
    for t in tips:
        p.add_mesh(to_pv(t), color="#e9ecdf", smooth_shading=True, specular=0.5)
    p.camera_position = cam
    p.screenshot(os.path.join(OUT, f"{nm}.png"))
    p.close()
    print("  wrote", nm + ".png")
