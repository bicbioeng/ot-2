"""Generate a REAL thin-walled Falcon conical tube (and verify it with a render).

A tube drawn as a solid cylinder with opacity<1 renders as a glass ROD: a path tracer sends
every ray through the whole solid volume, so it comes out dark, mirror-like and hides the
liquid inside. A real 15 mL Falcon is a ~1 mm shell. Building it as outer-minus-inner makes
the reagent column inside plainly visible, which is the point.

Dimensions come from the Opentrons definition (interior d=14.9, depth=117.5).
"""
import os
import json
import numpy as np
import trimesh
import pyvista as pv

pv.OFF_SCREEN = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LW = os.path.join(ROOT, "twin/assets/labware")
OUT = os.path.join(ROOT, "twin/cad/out")

meta = json.load(open(os.path.join(LW, "lw_meta.json")))
tube_slot = next((s for s, m in meta.items() if m["kind"] == "tuberack"), None)
w = list(meta[tube_slot]["wells"].values())[0]
R_IN = w["d"] / 2.0                 # interior radius (liquid fits this)
DEPTH = w["depth"]
WALL = 1.05                         # real Falcon wall
R_OUT = R_IN + WALL
CONE_H = 20.0
SEG = 64
print(f"Falcon 15 mL from the definition: interior d={w['d']:.2f} depth={DEPTH:.1f} "
      f"-> r_in={R_IN:.2f} r_out={R_OUT:.2f} wall={WALL}")


def tube_solid(r, cone_h, total_h, z0=0.0):
    """cone bottom (apex down) + cylinder body, as one solid."""
    cone = trimesh.creation.cone(radius=r, height=cone_h, sections=SEG)
    cone.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    cone.apply_translation([0, 0, z0 + cone_h / 2.0])
    body_h = total_h - cone_h
    body = trimesh.creation.cylinder(radius=r, height=body_h, sections=SEG)
    body.apply_translation([0, 0, z0 + cone_h + body_h / 2.0])
    return trimesh.boolean.union([cone, body], engine="manifold")


outer = tube_solid(R_OUT, CONE_H, DEPTH + WALL, z0=-WALL)
inner = tube_solid(R_IN, CONE_H - WALL * 0.5, DEPTH + 6.0, z0=0.0)   # +6 opens the top
tube = trimesh.boolean.difference([outer, inner], engine="manifold")
print(f"tube shell: faces={len(tube.faces)} watertight={tube.is_watertight} "
      f"extents={np.round(tube.extents,2)}")
tube.export(os.path.join(LW, "tube_falcon15.stl"))

# matching liquid solid (full tube) — Isaac scales/cuts it by volume
liq = tube_solid(R_IN * 0.985, CONE_H, DEPTH, z0=0.0)
liq.export(os.path.join(LW, "tube_falcon15_liquid.stl"))
meta["tube_model"] = {"mesh": "tube_falcon15.stl", "liquid_mesh": "tube_falcon15_liquid.stl",
                      "r_in": R_IN, "r_out": R_OUT, "cone_h": CONE_H, "depth": DEPTH, "wall": WALL}
json.dump(meta, open(os.path.join(LW, "lw_meta.json"), "w"), indent=2)
print("exported tube_falcon15.stl + tube_falcon15_liquid.stl, updated lw_meta.json")


def to_pv(tm):
    f = np.hstack([np.full((len(tm.faces), 1), 3), tm.faces]).astype(np.int64)
    return pv.PolyData(tm.vertices, f)


# verification: thin-wall tube with an amber column at 8000 uL, next to the OLD solid rod
def liquid_at(vol):
    cone_v = np.pi * R_IN ** 2 * CONE_H / 3.0
    h = CONE_H + (vol - cone_v) / (np.pi * R_IN ** 2) if vol > cone_v else \
        (3 * vol * CONE_H ** 2 / (np.pi * R_IN ** 2)) ** (1 / 3)
    return tube_solid(R_IN * 0.985, min(CONE_H, h), h, z0=0.0)


p = pv.Plotter(off_screen=True, window_size=(900, 900))
p.set_background("white")
p.add_mesh(to_pv(tube), color="#eaf0f4", opacity=0.30, smooth_shading=True, specular=0.5)
p.add_mesh(to_pv(liquid_at(8000)), color="#dc9e33", smooth_shading=True, specular=0.3)
solid = trimesh.creation.cylinder(radius=R_OUT, height=DEPTH, sections=SEG)
solid.apply_translation([34, 0, DEPTH / 2])
p.add_mesh(to_pv(solid), color="#eaf0f4", opacity=0.30, smooth_shading=True, specular=0.5)
lq2 = liquid_at(8000); lq2.apply_translation([34, 0, 0])
p.add_mesh(to_pv(lq2), color="#dc9e33", smooth_shading=True)
p.camera_position = [(120, -150, 95), (17, 0, 55), (0, 0, 1)]
p.screenshot(os.path.join(OUT, "90_tube_shell_vs_rod.png"))
p.close()
print("wrote 90_tube_shell_vs_rod.png  (LEFT = new thin shell, RIGHT = old solid rod)")
