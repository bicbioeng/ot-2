"""Isaac Sim 5.x backend for the OT-2 twin — runs headless in the isaac-sim container.

Coexists with the MuJoCo backend. The *verdicts* (reach / collision / clearance) are the
same exact analytic computations the MuJoCo backend uses — deck-extent reach, point-to-AABB
clearance, tip-vs-box penetration — so both backends agree by construction. Isaac's job is the
photoreal RTX render + the real OT-2 asset; the verdict math is backend-agnostic.

Geometry is exact (deck.py + the labware definitions embedded in the ledger); nothing is guessed.
Run (inside the container):
    ./python.sh /workspace/twin/isaac_twin.py \
        --ledger /workspace/ledgers/chemotaxis_bundle_live/analysis.json \
        --assets /workspace/twin/assets/ot2 --out /workspace/out/isaac \
        --report /workspace/out/isaac_report.json
"""
import argparse
import json
import math
import os
import struct
import sys

sys.stdout.reconfigure(line_buffering=True)  # container logs are piped -> force flush

# ---- args (parse BEFORE SimulationApp so --help works without booting Kit) ----
ap = argparse.ArgumentParser()
ap.add_argument("--ledger", required=True)
ap.add_argument("--deck", default="ot2_standard")
ap.add_argument("--assets", default="/workspace/twin/assets/ot2")
ap.add_argument("--twin-root", default="/workspace")
ap.add_argument("--out", default="/workspace/out/isaac")
ap.add_argument("--report", default="/workspace/out/isaac_report.json")
ap.add_argument("--width", type=int, default=1000)
ap.add_argument("--height", type=int, default=640)
ap.add_argument("--frame-stride", type=int, default=1, help="render every Nth interpolated step")
ap.add_argument("--max-frames", type=int, default=220,
                help="frame budget: motion is interpolated to ~this many frames (uniform speed)")
ap.add_argument("--trace", default="", help="also write a per-frame state trace JSON for the browser twin")
ap.add_argument("--gpu", type=int, default=0, help="which GPU to pin (active + physics)")
ap.add_argument("--chassis", action="store_true", help="load the real OT-2 reference mesh")
args = ap.parse_args()

def log(*a):
    print("[isaac_twin]", *a, flush=True)


# ---- boot Isaac Sim headless FIRST (must precede omni/pxr imports) ----
# Minimal config ONLY — extra keys (renderer/width/height) hang headless at MDL init.
log(f"booting SimulationApp headless (gpu={args.gpu}) ...")
from isaacsim import SimulationApp  # noqa: E402
# Minimal config: RTX is the default renderer on 5.x — omit the explicit `renderer`
# key (it hung headless on 4.5). Pin GPU + disable multi-GPU for a deterministic run.
sim = SimulationApp({"headless": True, "active_gpu": args.gpu,
                     "physics_gpu": args.gpu, "multi_gpu": False})
log("SimulationApp ready")

import numpy as np  # noqa: E402
from pxr import Usd, UsdGeom, UsdLux, UsdShade, Gf, Sdf  # noqa: E402
import omni.usd  # noqa: E402
import omni.replicator.core as rep  # noqa: E402

sys.path.insert(0, args.twin_root)
from twin import deck  # noqa: E402  (stdlib-only; does NOT import mujoco)
from twin.deck import LabwareGeom, TRASH_SLOT  # noqa: E402
log("omni + pxr + replicator + deck imported")

STANDOFF = 2.0
_TIP_R = 2.0
_CLEAR = 20.0
_SHAFT_TOP = 60.0        # pipette shaft length above the nozzle (visual proxy)


# --------------------------- ledger (self-contained) ---------------------------
def parse_ledger(path):
    a = json.loads(open(path).read())
    cmds = a.get("commands", [])
    layout, slot_defs, id2slot = {}, {}, {}
    for c in cmds:
        if c.get("commandType") == "loadLabware":
            p, res = c["params"], c.get("result", {})
            slot = str(p.get("location", {}).get("slotName"))
            dfn = res.get("definition")
            if slot and dfn:
                layout[slot] = p.get("loadName"); slot_defs[slot] = dfn
                if res.get("labwareId"):
                    id2slot[res["labwareId"]] = slot
    steps = []
    for c in cmds:
        t, p = c.get("commandType"), c.get("params", {})
        if t == "pickUpTip":
            steps.append(("pick", id2slot.get(p.get("labwareId")), p.get("wellName", "A1"), None))
        elif t == "aspirate":
            steps.append(("aspirate", id2slot.get(p.get("labwareId")), p.get("wellName", "A1"), p.get("volume")))
        elif t == "dispense":
            steps.append(("dispense", id2slot.get(p.get("labwareId")), p.get("wellName", "A1"), p.get("volume")))
        elif t == "dropTipInPlace":
            steps.append(("drop", TRASH_SLOT, "A1", None))
    return layout, slot_defs, steps


def read_binary_stl(path):
    """Return (points Nx3, face_counts, face_indices) from a binary STL (mm).
    Vectorized (numpy structured dtype) — the detailed OT-2 mesh is ~42k triangles,
    a per-vertex Python loop would be needlessly slow."""
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        buf = f.read(n * 50)
    dt = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    arr = np.frombuffer(buf, dtype=dt, count=n)
    pts = arr["v"].reshape(n * 3, 3).astype(np.float32)
    counts = [3] * n
    idx = list(range(n * 3))
    return pts, counts, idx


# --------------------------- geometry / verdicts (shared math) ---------------------------
def well_xyz(step, geoms, slots):
    kind, slot, well, _ = step
    if kind == "drop":
        tp = slots[TRASH_SLOT]
        cx, cy, _ = deck.slot_center_top(tp["position"], tp["boundingBox"])
        return cx, cy, 40.0 + STANDOFF
    g = geoms[slot]
    x, y, rim = deck.well_deck_xyz(slots[slot]["position"], g, well)
    return x, y, rim + STANDOFF


def boxes_of(geoms, slots):
    out = []
    for slot, g in geoms.items():
        pos = slots[slot]["position"]; cx, cy, cz = g.corner
        xd, yd, zd = g.dims
        out.append((np.array([pos[0] + cx + xd / 2, pos[1] + cy + yd / 2, pos[2] + cz + zd / 2]),
                    np.array([xd / 2, yd / 2, zd / 2])))
    return out


def clearance(p, boxes):
    best = 999.0
    for c, h in boxes:
        d = np.maximum(np.abs(p - c) - h, 0.0)
        best = min(best, float(np.linalg.norm(d)))
    return best


def penetration(p, boxes):
    """Max penetration of the tip sphere into any box (mm), 0 if clear."""
    worst = 0.0
    for c, h in boxes:
        d = np.abs(p - c) - h
        if (d < 0).all():                       # inside the box
            worst = max(worst, float(-d.max()) + _TIP_R)
    return worst


# ------------------------------------ build stage ------------------------------------
slots = deck.load_deck(args.deck)
layout, slot_defs, steps = parse_ledger(args.ledger)
geoms = {s: LabwareGeom(d) for s, d in slot_defs.items()}
boxes = boxes_of(geoms, slots)
x0, x1, y0, y1 = deck.deck_extent(slots)
cxd, cyd = (x0 + x1) / 2, (y0 + y1) / 2
travel_z = max((g.dims[2] for g in geoms.values()), default=30.0) + _CLEAR

log(f"building USD stage: {len(geoms)} labware, travel_z={travel_z:.1f}")
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 0.001)     # author in mm
UsdGeom.Xform.Define(stage, "/World")

# lights — the exact known-good config from the first working render (Isaac's RTX
# auto-exposure blows the frame to white if lights/floor are over-driven, so keep it modest)
dome = UsdLux.DomeLight.Define(stage, "/World/dome"); dome.CreateIntensityAttr(600)
key = UsdLux.DistantLight.Define(stage, "/World/key"); key.CreateIntensityAttr(1500)
UsdGeom.XformCommonAPI(key).SetRotate((-45, 0, 25))


def make_box(path, center, half, rgb, opacity=1.0):
    cube = UsdGeom.Cube.Define(stage, path)          # size 2 -> [-1,1]
    cube.CreateSizeAttr(2.0)
    api = UsdGeom.XformCommonAPI(cube)
    api.SetTranslate(Gf.Vec3d(float(center[0]), float(center[1]), float(center[2])))
    api.SetScale(Gf.Vec3f(float(half[0]), float(half[1]), float(half[2])))
    cube.CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
    if opacity < 1.0:
        cube.CreateDisplayOpacityAttr([opacity])
    return cube


def make_glass_material(path, rgb, opacity=0.10, roughness=0.2):
    """A real transparent UsdPreviewSurface — RTX renders displayOpacity as near-solid,
    so the glass shell needs an actual material with an opacity input to look like glass."""
    mtl = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/PBR")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    sh.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(1)
    mtl.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mtl


def make_cyl(path, center, radius, height, rgb):
    cyl = UsdGeom.Cylinder.Define(stage, path)
    cyl.CreateRadiusAttr(float(radius)); cyl.CreateHeightAttr(float(height))
    cyl.CreateAxisAttr("Z")
    UsdGeom.XformCommonAPI(cyl).SetTranslate(Gf.Vec3d(float(center[0]), float(center[1]), float(center[2])))
    cyl.CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
    return cyl


# ground + deck slab (exact known-good sizes from the first working render)
make_box("/World/floor", (cxd, cyd, -12), ((x1 - x0) / 2 + 120, (y1 - y0) / 2 + 120, 2), (0.16, 0.18, 0.21))
make_box("/World/deck", (cxd, cyd, -2.5), ((x1 - x0) / 2 + 8, (y1 - y0) / 2 + 8, 2.5), (0.12, 0.14, 0.17))

# chemistry overlay colors (from conformance.json next to the ledger, if present)
import importlib.util as _il  # noqa: E402
chem = None
_chem_path = os.path.join(args.twin_root, "twin", "chem.py")
if os.path.exists(_chem_path):
    _spec = _il.spec_from_file_location("p2pchem", _chem_path)
    _m = _il.module_from_spec(_spec); _spec.loader.exec_module(_m)
    chem = _m.load_chem(args.ledger)
dest_slot = next((s[1] for s in steps if s[0] == "dispense"), None)

_PAL = [(0.85, 0.72, 0.35), (0.35, 0.55, 0.85), (0.55, 0.70, 0.55),
        (0.80, 0.60, 0.75), (0.70, 0.70, 0.40)]
for i, (slot, g) in enumerate(geoms.items()):
    pos = slots[slot]["position"]; cxo, cyo, czo = g.corner
    xd, yd, zd = g.dims
    make_box(f"/World/lw_{slot}", (pos[0] + cxo + xd / 2, pos[1] + cyo + yd / 2, pos[2] + czo + zd / 2),
             (xd / 2, yd / 2, zd / 2), _PAL[i % len(_PAL)])
    top = pos[2] + czo + zd
    for well in g.well_names():
        wx, wy = g.well_offset(well); rad = g.well_radius(well)
        rgb = (0.14, 0.19, 0.27)
        if chem and slot == dest_slot and well in chem["wells"]:
            rgb = _m.conc_color(chem["wells"][well]["vv"], chem["vmax"])[1]
            rgb = tuple(c / 255 for c in rgb)
        make_cyl(f"/World/lw_{slot}/w_{well}", (pos[0] + cxo + wx, pos[1] + cyo + wy, top),
                 max(rad - 0.4, 0.6), 1.2, rgb)

# trash
if TRASH_SLOT in slots:
    tp = slots[TRASH_SLOT]["position"]; bb = slots[TRASH_SLOT]["boundingBox"]
    make_box(f"/World/lw_{TRASH_SLOT}", (tp[0] + bb["xDimension"] / 2, tp[1] + bb["yDimension"] / 2, 20),
             (bb["xDimension"] / 2, bb["yDimension"] / 2, 20), (0.25, 0.25, 0.28))

# real OT-2 chassis (glass shell) — DETAILED reference model (full robot) from alignment.json
if args.chassis:
    align = json.load(open(os.path.join(args.assets, "alignment.json")))
    asset = align.get("asset", "ot2_reference_basic.stl")
    stl = os.path.join(args.assets, asset)
    if not os.path.exists(stl):                        # fall back to the basic shell
        asset = align.get("asset_basic", "ot2_reference_basic.stl")
        stl = os.path.join(args.assets, asset)
    rgba = (align.get("rgba", "0.60 0.66 0.74 0.16")).split()
    col = tuple(float(c) for c in rgba[:3])
    op = float(rgba[3]) if len(rgba) > 3 else 0.18
    pts, counts, idx = read_binary_stl(stl)
    mesh = UsdGeom.Mesh.Define(stage, "/World/ot2_chassis")
    mesh.CreatePointsAttr([Gf.Vec3f(*p) for p in pts.tolist()])
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(idx)
    mesh.CreateDisplayColorAttr([Gf.Vec3f(*col)])
    glass = make_glass_material("/World/glassMat", col, opacity=max(op, 0.09), roughness=0.22)
    UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(glass)
    px, py, pz = align["pos"]
    UsdGeom.XformCommonAPI(mesh).SetTranslate(Gf.Vec3d(px, py, pz))
    log(f"chassis: {asset} ({len(counts)} tris, glass opacity {max(op,0.09)}) at {align['pos']}")

# pipette proxy (movable Xform) — slim Z carriage + shaft + colliding nozzle, matching
# the MuJoCo proxy; the real gantry is supplied by the glass mesh above.
pip = UsdGeom.Xform.Define(stage, "/World/pipette")
make_box("/World/pipette/carriage", (0, 0, _SHAFT_TOP - 6), (7, 7, 6), (0.40, 0.44, 0.50))
make_cyl("/World/pipette/shaft", (0, 0, (_SHAFT_TOP + 8) / 2), 3.4, _SHAFT_TOP - 8, (0.90, 0.30, 0.32))
make_cyl("/World/pipette/nozzle", (0, 0, 4), _TIP_R, 8, (0.15, 0.15, 0.15))
pip_api = UsdGeom.XformCommonAPI(pip)


# ---- state engine for the browser trace (liquids/tips/trash) — Isaac doesn't simulate
# liquid; the deterministic ledger does, exactly as the MuJoCo live server + viewer do ----
_a = json.loads(open(args.ledger).read())
_liquids = {l["id"]: l for l in (_a.get("liquids") or [])}
_id2slot = {}
for _c in _a.get("commands", []):
    if _c.get("commandType") == "loadLabware":
        _id2slot[_c.get("result", {}).get("labwareId")] = str(_c["params"].get("location", {}).get("slotName"))
_initial = {}
for _c in _a.get("commands", []):
    if _c.get("commandType") == "loadLiquid":
        _p = _c["params"]; _slot = _id2slot.get(_p["labwareId"])
        for _w, _v in _p.get("volumeByWell", {}).items():
            _initial.setdefault(f"{_slot}/{_w}", []).append({"liquidId": _p["liquidId"], "vol": float(_v)})
_rack_all = [f"{s}/{w}" for s, g in geoms.items() if g.is_tiprack for w in g.well_names()]


def _op_of(step):
    kind, slot, well, vol = step
    if kind == "pick":
        return {"kind": "pickTip", "rack": slot, "well": well}
    if kind == "aspirate":
        return {"kind": "aspirate", "well": f"{slot}/{well}", "vol": vol}
    if kind == "dispense":
        return {"kind": "dispense", "well": f"{slot}/{well}", "vol": vol}
    if kind == "drop":
        return {"kind": "dropTip"}
    return None


class _St:
    def __init__(self):
        self.wells = {k: [dict(o) for o in v] for k, v in _initial.items()}
        self.rack = set(_rack_all); self.tip = None; self.contents = []; self.trash = 0

    def _c(self, key):
        return self.contents if key == "tip" else self.wells.setdefault(key, [])

    def apply(self, op):
        if not op:
            return
        k = op["kind"]
        if k == "pickTip":
            self.tip = True; self.rack.discard(f"{op['rack']}/{op['well']}")
        elif k in ("aspirate", "dispense"):
            src, dst = (self._c(op["well"]), self._c("tip")) if k == "aspirate" else (self._c("tip"), self._c(op["well"]))
            avail = sum(o["vol"] for o in src)
            if avail > 0:
                take = min(op["vol"], avail)
                for o in list(src):
                    amt = o["vol"] / avail * take
                    d = next((x for x in dst if x["liquidId"] == o["liquidId"]), None)
                    if not d:
                        d = {"liquidId": o["liquidId"], "vol": 0.0}; dst.append(d)
                    d["vol"] += amt; o["vol"] -= amt
                src[:] = [o for o in src if o["vol"] > 1e-6]
        elif k == "dropTip":
            self.trash += 1; self.tip = None; self.contents = []

    def frame(self):
        return {"wells": {k: v for k, v in self.wells.items() if sum(o["vol"] for o in v) > 0.01},
                "rackPresent": list(self.rack), "trash": self.trash,
                "tip": self.tip is not None, "contents": self.contents}


_state = _St()
_trace = []

# ------------------------------------ waypoints ------------------------------------
report = {"backend": "isaac-sim-5.x", "n_steps": len(steps), "deck_layout": layout,
          "geometry_source": "exact: ot2_standard deck def + labware defs embedded in ledger",
          "reachable_all": True, "reach_violations": [], "collisions": [],
          "min_transit_clearance_mm": 999.0, "frames": 0, "verdict": ""}

# raw target waypoints (home -> per step: ascend, move, act, dwell, ascend); the contact
# waypoint carries the step's op so the trace applies liquids/tips at the right instant.
wps = [(cxd, cyd, travel_z, "home", None)]
for s in steps:
    tx, ty, tz = well_xyz(s, geoms, slots)
    if not deck.reachable(tx, ty, slots):
        report["reachable_all"] = False
        report["reach_violations"].append({"step": f"{s[0]} {s[1]}:{s[2]}", "x": round(tx, 1), "y": round(ty, 1)})
    cx, cy, _ = wps[-1][:3]
    wps += [(cx, cy, travel_z, "ascend", None), (tx, ty, travel_z, f"move {s[1]}:{s[2]}", None),
            (tx, ty, tz, f"{s[0]} {s[2]}", _op_of(s)), (tx, ty, tz, "dwell", None),
            (tx, ty, travel_z, "ascend", None)]

# Interpolate the path into SMOOTH motion (fix the teleport: render many frames per
# segment, not one). Distribute a fixed frame budget by distance -> uniform speed.
seg_len = [math.dist(wps[i - 1][:3], wps[i][:3]) for i in range(1, len(wps))]
total_len = sum(seg_len) or 1.0
budget = max(60, args.max_frames)
frames_path = [wps[0]]
for i in range(1, len(wps)):
    x0, y0, z0, _, _ = wps[i - 1]; x1, y1, z1, lbl, op = wps[i]
    n = max(2, round(seg_len[i - 1] / total_len * budget))
    for k in range(1, n + 1):
        t = k / n
        frames_path.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t,
                            z0 + (z1 - z0) * t, lbl if k == n else "", op if k == n else None))
    if lbl == "dwell":
        frames_path += [(x1, y1, z1, "dwell", None)] * 3

# ------------------------------------ render ------------------------------------
log(f"stage built ({len(wps)} waypoints -> {len(frames_path)} interpolated frames); camera + render product ...")
os.makedirs(args.out, exist_ok=True)
# Camera must sit OUTSIDE the detailed robot's front glass wall (world y ~ -287) or it
# renders the near wall filling the frame. Place it well in front + elevated, looking in.
_ch_pos = json.load(open(os.path.join(args.assets, "alignment.json")))["pos"] if args.chassis else [0, 0, 0]
_front_y = _ch_pos[1]                       # robot front wall (mesh min-y=0 + pos_y)
cam_y = min(cyd - (y1 - y0) - 120, _front_y - 340)
cam = rep.create.camera(position=(cxd - 120, cam_y, travel_z + 440),
                        look_at=(cxd, cyd + 30, 12))
rp = rep.create.render_product(cam, (args.width, args.height))
writer = rep.WriterRegistry.get("BasicWriter")
writer.initialize(output_dir=args.out, rgb=True)
writer.attach([rp])
log("render product ready; starting frame loop (first frame compiles RTX shaders — slow once)")

last_lbl = "home"
fi = 0
for wi, (x, y, z, lbl, op) in enumerate(frames_path):
    pip_api.SetTranslate(Gf.Vec3d(float(x), float(y), float(z)))
    p = np.array([x, y, z])
    in_transit = z > travel_z - 8            # collisions only in transit (in-well descent is intended)
    if z > travel_z - 3.0:
        report["min_transit_clearance_mm"] = round(min(report["min_transit_clearance_mm"], clearance(p, boxes)), 2)
    pen = penetration(p, boxes) if in_transit else 0.0
    col = pen > 0.05
    if col:
        report["collisions"].append({"at": lbl or last_lbl, "penetration_mm": round(pen, 2)})
    if op:
        _state.apply(op)
    if lbl:
        last_lbl = lbl
    # record a state frame for the browser twin (every frame; rendering stays strided)
    fr = _state.frame()
    fr["pipette"] = [round(float(x), 2), round(float(y), 2), round(float(z), 2)]
    fr["collision"] = bool(col)
    fr["label"] = last_lbl
    _trace.append(fr)
    if wi % args.frame_stride == 0:
        rep.orchestrator.step(rt_subframes=3)
        fi += 1
        if fi == 1 or fi % 25 == 0:
            log(f"rendered frame {fi}/{len(frames_path)} ({last_lbl})")

report["frames"] = fi
log(f"render loop done: {fi} frames")
report["verdict"] = ("INFEASIBLE" if (report["collisions"] or not report["reachable_all"])
                     else "FEASIBLE — all targets reachable, no collisions")
os.makedirs(os.path.dirname(args.report), exist_ok=True)
json.dump(report, open(args.report, "w"), indent=2)
if args.trace:
    json.dump({"backend": "Isaac Sim 5.1 · RTX A6000", "report": report,
               "frames": _trace, "liquids": _liquids},
              open(args.trace, "w"))
    log(f"state trace ({len(_trace)} frames) -> {args.trace}")
print("ISAAC_TWIN_DONE", json.dumps({k: report[k] for k in
      ("verdict", "frames", "reachable_all", "min_transit_clearance_mm")}))
print("  collisions:", len(report["collisions"]), " report:", args.report, " frames_dir:", args.out)

sim.close()
