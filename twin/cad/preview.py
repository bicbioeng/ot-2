"""Multi-view offscreen preview of the OT-2 assets (the 'shared visual language').
Loads a mesh, reports its axes, and renders candidate orientations so we can pick the
one that stands the robot on its feet (Z-up) before baking the rotation in.
"""
import os
import sys
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # paper2protocol
STL = os.path.join(ROOT, "twin/assets/ot2/ot2_reference_detailed.stl")
OUT = os.path.join(ROOT, "twin/cad/out")
os.makedirs(OUT, exist_ok=True)


def to_pv(tm):
    faces = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, faces)


def render(tm, name, cpos="iso", color="lightsteelblue", opacity=1.0, edges=False):
    mesh = to_pv(tm)
    p = pv.Plotter(off_screen=True, window_size=(960, 720))
    p.set_background("white")
    p.add_mesh(mesh, color=color, smooth_shading=True, show_edges=edges,
               edge_color="steelblue", opacity=opacity, specular=0.3)
    p.add_axes(line_width=4)      # RGB = XYZ so we can read orientation
    p.show_grid(color="gray")
    p.camera_position = cpos
    p.screenshot(os.path.join(OUT, f"{name}.png"))
    p.close()
    print(f"  wrote {name}.png")


def rot(tm, ang_deg, axis):
    t = tm.copy()
    ax = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[axis]
    t.apply_transform(trimesh.transformations.rotation_matrix(np.radians(ang_deg), ax, tm.centroid))
    return t


m = trimesh.load(STL)
print("STL:", STL)
print("  vertices:", len(m.vertices), "faces:", len(m.faces))
print("  extents (x,y,z) mm:", np.round(m.extents, 1))
print("  bounds min:", np.round(m.bounds[0], 1), "max:", np.round(m.bounds[1], 1))
print("  tallest axis (likely current 'up'):", "xyz"[int(np.argmax(m.extents))])

print("rendering standing candidates, transparent, to see the interior deck/gantry ...")
sneg = rot(m, -90, "x")
spos = rot(m, 90, "x")
# iso + front (xz) + a low front-3/4 to spot deck-at-bottom vs top
render(sneg, "10_Xneg90_iso_xray", "iso", color="lightsteelblue", opacity=0.30, edges=True)
render(sneg, "11_Xneg90_front_xray", "xz", color="lightsteelblue", opacity=0.30, edges=True)
render(spos, "12_Xpos90_iso_xray", "iso", color="lightsteelblue", opacity=0.30, edges=True)
render(spos, "13_Xpos90_front_xray", "xz", color="lightsteelblue", opacity=0.30, edges=True)
print("done ->", OUT)
