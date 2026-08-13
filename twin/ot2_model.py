"""Procedurally build an MJCF OT-2 twin from EXACT, per-run geometry.

Nothing here is labware-specific or paper-specific: every box, well marker, and
gantry range is derived from the real Opentrons deck definition + the labware
definitions embedded in the run's ledger (see deck.py). Feed it any protocol's
geometry and it builds that protocol's exact deck.

The pipette is an abstracted rigid arm (a Cartesian gantry + a shaft). Labware
and deck geometry are exact; the arm is the proxy whose deck-frame motion,
collision, and reach the twin validates. Full pipette/tip CAD is a documented
next step, not a hidden assumption.
"""
from __future__ import annotations

from .deck import LabwareGeom, TRASH_SLOT

_SHAFT = 60.0          # proxy pipette length above the tip (mm)
_TIP_R = 2.0           # tip radius (the colliding part of the arm)
_CLEARANCE = 20.0      # travel height above the tallest labware

_PALETTE = [
    "0.85 0.72 0.35 1", "0.35 0.55 0.85 1", "0.55 0.70 0.55 1",
    "0.80 0.60 0.75 1", "0.70 0.70 0.40 1", "0.50 0.75 0.80 1",
]


def travel_tip_z(geoms: dict[str, LabwareGeom]) -> float:
    tallest = max((g.dims[2] for g in geoms.values()), default=30.0)
    return tallest + _CLEARANCE


def _labware_body(slot: str, geom: LabwareGeom, slot_pos, color: str,
                  well_colors: dict[str, str]) -> str:
    cx, cy, cz = geom.corner
    xdim, ydim, zdim = geom.dims
    bx = slot_pos[0] + cx + xdim / 2
    by = slot_pos[1] + cy + ydim / 2
    parts = [
        f'<geom name="lw_{slot}" type="box" '
        f'pos="{bx:.3f} {by:.3f} {slot_pos[2] + cz + zdim/2:.3f}" '
        f'size="{xdim/2:.3f} {ydim/2:.3f} {zdim/2:.3f}" rgba="{color}"/>'
    ]
    top_z = slot_pos[2] + cz + zdim
    for well in geom.well_names():
        wx, wy = geom.well_offset(well)
        rad = geom.well_radius(well)
        key = f"{slot}:{well}"
        if key in well_colors:
            rgba, r, zt = well_colors[key], rad + 0.3, 1.2
        else:
            rgba, r, zt = "0.14 0.19 0.27 0.9", max(rad - 0.4, 0.6), 0.4
        parts.append(
            f'<geom type="cylinder" contype="0" conaffinity="0" '
            f'pos="{slot_pos[0]+cx+wx:.3f} {slot_pos[1]+cy+wy:.3f} {top_z:.3f}" '
            f'size="{r:.3f} {zt}" rgba="{rgba}"/>')
    return "\n      ".join(parts)


def build_mjcf(geoms: dict[str, LabwareGeom], slots: dict[str, dict],
               well_colors: dict[str, str] | None = None,
               chassis: dict | None = None) -> str:
    """chassis (optional): {'meshdir','basename','pos':(x,y,z),'zrot':deg,'rgba','scale'}
    adds the real OT-2 reference mesh as a NON-colliding visual chassis."""
    well_colors = well_colors or {}
    tz = travel_tip_z(geoms)

    compiler_xml = mesh_asset = chassis_body = ""
    if chassis:
        s = chassis.get("scale", 1.0)
        px, py, pz = chassis["pos"]
        compiler_xml = f'<compiler meshdir="{chassis["meshdir"]}"/>'
        mesh_asset = (f'<mesh name="ot2chassis" file="{chassis["basename"]}" '
                      f'scale="{s} {s} {s}"/>')
        chassis_body = (f'<geom type="mesh" mesh="ot2chassis" '
                        f'pos="{px:.2f} {py:.2f} {pz:.2f}" euler="0 0 {chassis.get("zrot",0)}" '
                        f'rgba="{chassis.get("rgba","0.62 0.66 0.70 0.32")}" '
                        f'contype="0" conaffinity="0"/>')

    lw_xml = []
    for i, (slot, g) in enumerate(geoms.items()):
        lw_xml.append(_labware_body(slot, g, slots[slot]["position"],
                                    _PALETTE[i % len(_PALETTE)], well_colors))

    # deck extent -> base slab + gantry travel ranges (all from real slot boxes)
    xs0 = [s["position"][0] for s in slots.values()]
    ys0 = [s["position"][1] for s in slots.values()]
    xs1 = [s["position"][0] + s["boundingBox"]["xDimension"] for s in slots.values()]
    ys1 = [s["position"][1] + s["boundingBox"]["yDimension"] for s in slots.values()]
    xmin, xmax, ymin, ymax = min(xs0), max(xs1), min(ys0), max(ys1)
    cxd, cyd = (xmin + xmax) / 2, (ymin + ymax) / 2
    hxd, hyd = (xmax - xmin) / 2 + 8, (ymax - ymin) / 2 + 8

    # trash (fixed slot) from the real deck slot box
    trash = ""
    if TRASH_SLOT in slots:
        tp = slots[TRASH_SLOT]["position"]; bb = slots[TRASH_SLOT]["boundingBox"]
        trash = (f'<geom name="lw_{TRASH_SLOT}" type="box" '
                 f'pos="{tp[0]+bb["xDimension"]/2:.2f} {tp[1]+bb["yDimension"]/2:.2f} 20" '
                 f'size="{bb["xDimension"]/2:.2f} {bb["yDimension"]/2:.2f} 20" '
                 f'rgba="0.25 0.25 0.28 1"/>')

    return f"""
<mujoco model="ot2_twin">
  {compiler_xml}
  <option timestep="0.002" gravity="0 0 0"/>
  <visual>
    <global offwidth="1280" offheight="800"/>
    <headlight diffuse="0.5 0.5 0.5" ambient="0.35 0.35 0.35"/>
    <quality shadowsize="4096"/>
  </visual>
  <asset>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.16 0.18 0.21"
             rgb2="0.20 0.23 0.27" width="512" height="512"/>
    <material name="grid" texture="grid" texrepeat="8 8" reflectance="0.05"/>
    {mesh_asset}
  </asset>
  <worldbody>
    <light pos="{cxd:.0f} {ymin-60:.0f} 500" dir="0 0.2 -1" diffuse="0.8 0.8 0.8"/>
    <light pos="{cxd:.0f} {ymax+60:.0f} 450" dir="0 -0.3 -1" diffuse="0.5 0.5 0.55"/>
    <geom name="floor" type="plane" pos="{cxd:.1f} {cyd:.1f} -8" size="400 400 1" material="grid"/>
    <geom name="deck" type="box" pos="{cxd:.2f} {cyd:.2f} -2.5" size="{hxd:.2f} {hyd:.2f} 2.5"
          rgba="0.12 0.14 0.17 1"/>
    {chassis_body}
    {trash}

    <body name="labware">
      {"".join(chr(10)+"      "+x for x in lw_xml)}
    </body>

    <!-- Moving pipette proxy. The real gantry/carriage geometry is supplied by the
         detailed OT-2 mesh (static visual context); this proxy is the MOVING element
         whose deck-frame motion / collision / reach the twin actually validates, so it
         is kept slim (a thin Z carriage bar + the pipette shaft + the colliding tip)
         rather than a big block that would fight the real mesh. -->
    <body name="gantry_y" pos="0 0 0">
      <joint name="jy" type="slide" axis="0 1 0" range="{ymin-15:.1f} {ymax+15:.1f}"/>
      <!-- slim gantry rail: spans X, rides front-back in Y (matches the real OT-2 gantry) -->
      <geom type="box" pos="{cxd:.1f} 0 {tz+_SHAFT-4:.1f}" size="{hxd:.1f} 3.5 3.5"
            rgba="0.34 0.37 0.42 1" contype="0" conaffinity="0"/>
      <body name="gantry_x" pos="0 0 0">
        <joint name="jx" type="slide" axis="1 0 0" range="{xmin-15:.1f} {xmax+15:.1f}"/>
        <!-- X carriage block: rides along the gantry rail in X, stays at travel height -->
        <geom type="box" pos="0 0 {tz+_SHAFT-4:.1f}" size="7 8 7"
              rgba="0.42 0.46 0.52 1" contype="0" conaffinity="0"/>
        <body name="pipette" pos="0 0 0">
          <joint name="jz" type="slide" axis="0 0 1" range="{-(tz+10):.1f} 45"/>
          <!-- shaft: visual only (non-colliding), rises UP from the nozzle -->
          <geom type="capsule" fromto="0 0 {tz+8:.1f} 0 0 {tz+_SHAFT:.1f}"
                size="3.4" rgba="0.90 0.30 0.32 1" contype="0" conaffinity="0"/>
          <!-- nozzle tip: the only colliding part, a short stub at the bottom -->
          <geom name="tip" type="capsule"
                fromto="0 0 {tz:.1f} 0 0 {tz+8:.1f}" size="{_TIP_R}"
                rgba="0.15 0.15 0.15 1"/>
          <site name="tip_site" pos="0 0 {tz:.1f}" size="1.5" rgba="1 0.9 0.2 1"/>
        </body>
      </body>
    </body>
  </worldbody>
</mujoco>
"""
