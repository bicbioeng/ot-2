"""Stand the OT-2 STL upright (+90 X), split into components, and drop the flat
enclosure wall/window panels — keep the frame, gantry, carriage, deck, trash.
Renders the result so we can verify 'panels off' before pushing to Isaac.
"""
import os
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STL = os.path.join(ROOT, "twin/assets/ot2/ot2_reference_detailed.stl")
OUT = os.path.join(ROOT, "twin/cad/out")
os.makedirs(OUT, exist_ok=True)

m = trimesh.load(STL)
# stand upright: +90 about X, then drop to z-min = 0
m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0], m.centroid))
m.apply_translation(-m.bounds[0])
Z = m.extents[2]
print("upright extents (x,y,z):", np.round(m.extents, 1))

comps = m.split(only_watertight=False)
print("connected components:", len(comps))


def to_pv(tm):
    faces = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, faces)


keep, dropped = [], []
for i, c in enumerate(comps):
    ex, ey, ez = c.extents
    cz = c.centroid[2]
    thin_flat_vertical = (min(ex, ey) < 14) and (max(ex, ey) > 150) and (ez > 150)   # side/front/back wall
    thin_flat_top = (ez < 18) and (ex > 150) and (ey > 150) and (cz > 0.55 * Z)       # top panel
    is_panel = thin_flat_vertical or thin_flat_top
    (dropped if is_panel else keep).append(c)
    if len(comps) <= 40:
        print(f"  comp {i:2d} ext=({ex:6.1f},{ey:6.1f},{ez:6.1f}) faces={len(c.faces):5d} "
              f"cz={cz:6.1f} -> {'DROP panel' if is_panel else 'keep'}")

print(f"kept {len(keep)} comps, dropped {len(dropped)} panels")


def render(comp_list, name, cpos, color="lightsteelblue", opacity=1.0):
    p = pv.Plotter(off_screen=True, window_size=(1000, 780))
    p.set_background("white")
    for c in comp_list:
        p.add_mesh(to_pv(c), color=color, smooth_shading=True, specular=0.35, opacity=opacity)
    p.add_axes(line_width=4)
    p.show_grid(color="gray")
    p.camera_position = cpos
    p.screenshot(os.path.join(OUT, f"{name}.png"))
    p.close()
    print("  wrote", name + ".png")


if keep:
    render(keep, "20_nopanels_iso", "iso")
    render(keep, "21_nopanels_front", "xz")
    # export the panels-off, upright mesh for Isaac
    if len(keep) > 0:
        merged = trimesh.util.concatenate(keep)
        merged.export(os.path.join(OUT, "ot2_upright_nopanels.stl"))
        print("  exported ot2_upright_nopanels.stl", np.round(merged.extents, 1))
else:
    print("!! nothing kept — panels classifier too aggressive or single fused mesh")
    render(comps, "20_all_iso", "iso", opacity=0.35)
