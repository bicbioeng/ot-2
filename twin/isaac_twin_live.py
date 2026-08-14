"""Live-streaming Isaac Sim OT-2 twin — articulated machine, real CAD, real liquid handling.

Machine (twin/cad/split_final.py, from the Opentrons reference CAD):
    frame     static   black frame + posts + rails + trash bin
    deck      static   deck plate with the slot grid
    beam      Y        gantry beam spanning the machine (parametric: fused in the CAD)
    carriage  X        z-stage plates + Z linear rails, rides the beam
    pipette   Z        the real LEFT-mount pipette CAD, hangs off the carriage

Labware (twin/cad/labware_cad.py) is CAD with boolean-cut cavities, generated from the exact
Opentrons definitions in the run's ledger — the wells are real holes, not cylinders hidden
inside an opaque slab.

Liquid handling is volumetric and conserved: 1 uL = 1 mm^3. Source tubes are UNCAPPED (a
capped tube cannot be aspirated from), their level falls as liquid is drawn; the drawn volume
appears inside the tip; dispensing raises the destination well and empties the tip. Tips are
removed from the rack when picked, carried on the nozzle, and dropped into the trash where
they accumulate. Aspiration descends to just below the liquid surface, dispensing to the
protocol's own well_bottom_clearance.

Because 200 uL in a 6.9 mL Corning well is a TRUE height of 0.49 mm (invisible on screen),
liquid is drawn with a visualisation gain (--liquid-gain, default 3x). True volumes and
heights are logged; --liquid-gain 1 renders at exact physical scale.

Run inside the isaac-sim container:
    /isaac-sim/python.sh /workspace/twin/isaac_twin_live.py \
        --ledger /workspace/ledgers/chemotaxis_prism/analysis.json \
        --twin-root /workspace --assets /workspace/twin/assets/ot2 --chassis \
        --/rtx/verifyDriverVersion/enabled=false
"""
import argparse
import json
import math
import os
import struct
import sys
import time

sys.stdout.reconfigure(line_buffering=True)

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", required=True)
ap.add_argument("--deck", default="ot2_standard")
ap.add_argument("--assets", default="/workspace/twin/assets/ot2")
ap.add_argument("--labware", default="/workspace/twin/assets/labware")
ap.add_argument("--twin-root", default="/workspace")
ap.add_argument("--gpu", type=int, default=0)
ap.add_argument("--chassis", action="store_true")
ap.add_argument("--fps", type=float, default=60.0)
ap.add_argument("--max-frames", type=int, default=1100)
ap.add_argument("--speed", type=float, default=1.0,
                help="playback rate; 0.25 = quarter speed. Live-adjustable via out/speed.json")
ap.add_argument("--liquid-gain", default="auto",
                help="visual exaggeration of liquid height: a number, or 'auto' (default) to "
                     "scale PER LABWARE so the run's largest fill reads ~55%% of well depth. "
                     "A fixed gain cannot serve both a 12-well plate (200 uL = 0.53 mm) and a "
                     "96-well plate (200 uL = 5.81 mm) — one is invisible, the other saturates.")
ap.add_argument("--tube-start", type=float, default=8000.0, help="uL preloaded in each source tube")
ap.add_argument("--once", action="store_true")
ap.add_argument("--validate", action="store_true")
ap.add_argument("--edit", action="store_true")
ap.add_argument("--ui", action="store_true",
                help="run the protocol WITH the Isaac Sim editor UI (stage tree, property panel, toolbar) instead of the full-screen kiosk view")
ap.add_argument("--snapshot", default="",
                help="render the scene to PNGs after fast-forwarding the run, then exit "
                     "(self-check: proves what is ACTUALLY visible, not what a counter says)")
ap.add_argument("--snapshot-ops", type=int, default=0,
                help="how many protocol ops to apply before the snapshot (0 = all)")
args, _kit_argv = ap.parse_known_args()


def log(*a):
    print("[isaac_twin_live]", *a, flush=True)


# ------------------------------- boot -------------------------------
STREAMING_KIT = "/isaac-sim/apps/isaacsim.exp.full.streaming.kit"
log(f"booting SimulationApp (gpu={args.gpu}); kit args: {_kit_argv}")
from isaacsim import SimulationApp  # noqa: E402
_cfg = {"headless": True, "active_gpu": args.gpu, "physics_gpu": args.gpu, "multi_gpu": False}
if args.validate:
    # minimal boot: fast. NOTE: it does not load the RTX material pipeline, so it must
    # never be used for snapshots — everything renders untextured grey.
    sim = SimulationApp(_cfg); _experience = False
elif os.path.exists(STREAMING_KIT):
    sim = SimulationApp(_cfg, experience=STREAMING_KIT); _experience = True
else:
    sim = SimulationApp(_cfg); _experience = False
log(f"SimulationApp ready (experience={_experience}, validate={args.validate})")

import carb  # noqa: E402
_settings = carb.settings.get_settings()
_settings.set("/app/window/drawMouse", True)
_settings.set("/app/livestream/allowResize", True)
if not _experience and not args.validate:
    try:
        from isaacsim.core.utils.extensions import enable_extension
    except Exception:
        from omni.isaac.core.utils.extensions import enable_extension
    for _ext in ("omni.kit.livestream.webrtc", "omni.services.streamclient.webrtc"):
        try:
            enable_extension(_ext); break
        except Exception:
            pass
for _ in range(6):
    sim.update()
log("livestream ready; WebRTC signaling on host :49100")

import numpy as np  # noqa: E402
from pxr import UsdGeom, UsdLux, UsdShade, Gf, Sdf  # noqa: E402
import omni.usd  # noqa: E402

sys.path.insert(0, args.twin_root)
from twin import deck  # noqa: E402
from twin.deck import LabwareGeom, TRASH_SLOT  # noqa: E402
log("omni + pxr + deck imported")

_TIP_R = 2.0
_CLEAR = 20.0
TIP_LEN = 52.0             # p300 tip
BOTTOM_CLEARANCE = 1.0     # the protocol's own well_bottom_clearance (aspirate & dispense)
IMMERSION = 3.0            # how far below the liquid surface the tip dips to aspirate
CONE_H = 20.0              # conical bottom of a 15 mL Falcon
AUTO_GAIN = str(args.liquid_gain).strip().lower() == "auto"
GAIN = 1.0 if AUTO_GAIN else max(0.05, float(args.liquid_gain))


# --------------------------- ledger ---------------------------
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
        elif t == "blowout":
            # the protocol blows out at the well TOP (wellLocation.origin == "top")
            steps.append(("blowout", id2slot.get(p.get("labwareId")), p.get("wellName", "A1"), None))
        elif t in ("dropTip", "dropTipInPlace"):
            steps.append(("drop", TRASH_SLOT, "A1", None))
        elif t == "custom" and "DELAY" in str(p.get("legacyCommandType", "")):
            # protocol.delay(...) — e.g. the 15 min room-temp agar solidification
            steps.append(("delay", None, p.get("legacyCommandText", "delay"), None))
    return layout, slot_defs, steps


def read_binary_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        buf = f.read(n * 50)
    dt = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    arr = np.frombuffer(buf, dtype=dt, count=n)
    return arr["v"].reshape(n * 3, 3).astype(np.float32), [3] * n, list(range(n * 3))


# --------------------------- liquid physics (1 uL == 1 mm^3) ---------------------------
def h_flat(vol, r):
    """Height of `vol` uL standing in a flat-bottomed cylinder of radius r."""
    return max(0.0, vol) / (math.pi * r * r)


def h_conical(vol, r, cone_h=CONE_H):
    """Height above the tube's bottom tip for a conical-bottomed tube (Falcon)."""
    cone_v = math.pi * r * r * cone_h / 3.0
    if vol <= 0:
        return 0.0
    if vol <= cone_v:
        return (3.0 * vol * cone_h * cone_h / (math.pi * r * r)) ** (1.0 / 3.0)
    return cone_h + (vol - cone_v) / (math.pi * r * r)


# ------------------------------------ stage ------------------------------------
slots = deck.load_deck(args.deck)
layout, slot_defs, steps = parse_ledger(args.ledger)
geoms = {s: LabwareGeom(d) for s, d in slot_defs.items()}
x0, x1, y0, y1 = deck.deck_extent(slots)
cxd, cyd = (x0 + x1) / 2, (y0 + y1) / 2
travel_z = max((g.dims[2] for g in geoms.values()), default=30.0) + _CLEAR

LW = {}
_lwm = os.path.join(args.labware, "lw_meta.json")
if os.path.exists(_lwm):
    LW = json.load(open(_lwm))

_kinds = {}
for s in steps:
    _kinds[s[0]] = _kinds.get(s[0], 0) + 1
log(f"stage: {len(geoms)} labware, {len(steps)} steps {_kinds}, travel_z={travel_z:.1f}, "
    f"liquid gain={GAIN}x, speed={args.speed}x")

stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 0.001)
UsdGeom.Xform.Define(stage, "/World")


# ---------------- prim + material helpers ----------------
def make_box(path, center, half, rgb=(0.8, 0.8, 0.8)):
    c = UsdGeom.Cube.Define(stage, path); c.CreateSizeAttr(2.0)
    api = UsdGeom.XformCommonAPI(c)
    api.SetTranslate(Gf.Vec3d(*[float(v) for v in center]))
    api.SetScale(Gf.Vec3f(*[float(v) for v in half]))
    c.CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
    return c


def make_cyl(path, center, radius, height, rgb=(0.8, 0.8, 0.8)):
    c = UsdGeom.Cylinder.Define(stage, path)
    c.CreateRadiusAttr(float(radius)); c.CreateHeightAttr(float(height)); c.CreateAxisAttr("Z")
    UsdGeom.XformCommonAPI(c).SetTranslate(Gf.Vec3d(*[float(v) for v in center]))
    c.CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
    return c


def make_cone(path, center, radius, height, rgb=(0.8, 0.8, 0.8), flip=False):
    c = UsdGeom.Cone.Define(stage, path)
    c.CreateRadiusAttr(float(radius)); c.CreateHeightAttr(float(height)); c.CreateAxisAttr("Z")
    api = UsdGeom.XformCommonAPI(c)
    api.SetTranslate(Gf.Vec3d(*[float(v) for v in center]))
    if flip:
        api.SetRotate(Gf.Vec3f(180.0, 0.0, 0.0))
    c.CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
    return c


def make_pbr(path, rgb, roughness=0.5, metallic=0.0, opacity=1.0, ior=None):
    """Every visible prim gets a real material — RTX shades unbound prims with a flat default,
    which is why displayColor-only liquids rendered black."""
    mtl = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/S")
    sh.CreateIdAttr("UsdPreviewSurface")
    din = sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f); din.Set(Gf.Vec3f(*rgb))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(metallic))
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opacity))
    if ior is not None:
        sh.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(float(ior))
    mtl.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mtl, din


def M(path, *a, **k):
    return make_pbr(path, *a, **k)[0]


def bind(geom, mtl):
    UsdShade.MaterialBindingAPI(geom.GetPrim()).Bind(mtl)


def show(g, v):
    im = UsdGeom.Imageable(g.GetPrim())
    im.MakeVisible() if v else im.MakeInvisible()


def add_mesh(path, stl, rgb):
    pts, counts, idx = read_binary_stl(stl)
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr([Gf.Vec3f(*p) for p in pts.tolist()])
    m.CreateFaceVertexCountsAttr(counts); m.CreateFaceVertexIndicesAttr(idx)
    m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    m.CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
    return m, len(counts)


# ---------------- lighting ----------------
UsdLux.DomeLight.Define(stage, "/World/dome").CreateIntensityAttr(850)
_k = UsdLux.DistantLight.Define(stage, "/World/key"); _k.CreateIntensityAttr(2600)
UsdGeom.XformCommonAPI(_k).SetRotate((-42, 0, 20))
_f = UsdLux.DistantLight.Define(stage, "/World/fill"); _f.CreateIntensityAttr(1000)
UsdGeom.XformCommonAPI(_f).SetRotate((-20, 0, -130))
for _gk in ("/app/viewport/grid/enabled", "/persistent/app/viewport/grid/enabled"):
    try:
        _settings.set(_gk, False)
    except Exception:
        pass

MAT = {
    "frame": M("/World/mat/frame", (0.055, 0.058, 0.065), roughness=0.42),
    "deck":  M("/World/mat/deck", (0.78, 0.80, 0.83), roughness=0.35, metallic=0.35),
    "beam":  M("/World/mat/beam", (0.20, 0.21, 0.24), roughness=0.38, metallic=0.35),
    "carr":  M("/World/mat/carr", (0.28, 0.30, 0.34), roughness=0.40),
    "pip":   M("/World/mat/pip", (0.94, 0.95, 0.96), roughness=0.32),
    "table": M("/World/mat/table", (0.17, 0.18, 0.21), roughness=0.75),
    "rack":  M("/World/mat/rack", (0.13, 0.14, 0.17), roughness=0.55),
    # Clear lab PLASTIC, not glass: low roughness + low opacity renders as chrome under a dome
    # light and mirrors away the liquid inside. Frosted polypropylene reads as see-through.
    "plate": M("/World/mat/plate", (0.90, 0.93, 0.96), roughness=0.30, opacity=0.40, ior=1.46),
    "glass": M("/World/mat/glass", (0.95, 0.97, 0.99), roughness=0.22, opacity=0.13, ior=1.46),
    "tip":   M("/World/mat/tip", (0.88, 0.90, 0.86), roughness=0.32, opacity=0.60, ior=1.49),
}
_tw = max(x1 - x0, y1 - y0) / 2 + 300
bind(make_box("/World/table", (cxd, cyd, -70), (_tw, _tw, 4), (0.17, 0.18, 0.21)), MAT["table"])

# ---------------- reagents ----------------
_PALETTE = [(0.86, 0.62, 0.20), (0.62, 0.40, 0.10), (0.91, 0.88, 0.71),
            (0.66, 0.78, 0.38), (0.87, 0.63, 0.36),
            (0.45, 0.65, 0.88), (0.80, 0.55, 0.75), (0.70, 0.70, 0.42)]
_src = []
for _s in steps:
    if _s[0] == "aspirate" and (_s[1], _s[2]) not in _src:
        _src.append((_s[1], _s[2]))
REAGENT = {k: _PALETTE[i % len(_PALETTE)] for i, k in enumerate(_src)}
src_wells = set(_src)
log(f"reagents: {[f'{s}/{w}' for s, w in _src]}")

# ---------------- labware ----------------
well_liq, tube_liq, rack_tips = {}, {}, {}
WELLGEO = {}


def wdef(slot, well):
    return geoms[slot].definition["wells"][well]


def labware_origin(slot):
    pos = slots[slot]["position"]; c = geoms[slot].corner
    return pos[0] + c[0], pos[1] + c[1], pos[2] + c[2]


for slot, g in geoms.items():
    ox, oy, oz = labware_origin(slot)
    low = g.load_name.lower()
    meta = LW.get(g.load_name, {})   # keyed by loadName: protocols share assets
    mesh_file = os.path.join(args.labware, meta.get("mesh", "")) if meta.get("mesh") else ""
    kind = meta.get("kind") or ("tuberack" if "tuberack" in low
                                else "tiprack" if (g.is_tiprack or "tiprack" in low) else "plate")
    # CAD body with real cut cavities
    if mesh_file and os.path.exists(mesh_file):
        bodym, nt = add_mesh(f"/World/lw_{slot}/body", mesh_file,
                             (0.90, 0.93, 0.96) if kind == "plate" else (0.13, 0.14, 0.17))
        UsdGeom.XformCommonAPI(bodym).SetTranslate(Gf.Vec3d(ox, oy, oz))
        bind(bodym, MAT["plate"] if kind == "plate" else MAT["rack"])
        log(f"  slot {slot} {g.load_name}: CAD body {nt} tris ({kind}, cavities cut)")
    else:
        xd, yd, zd = g.dims
        bh = zd if kind == "plate" else (45.0 if kind == "tuberack" else 52.0)
        bind(make_box(f"/World/lw_{slot}/body", (ox + xd / 2, oy + yd / 2, oz + bh / 2),
                      (xd / 2, yd / 2, bh / 2)), MAT["rack"])
        log(f"  slot {slot}: no CAD body, using block fallback")

    for well in g.well_names():
        w = wdef(slot, well)
        wx, wy, wz, wd_, dia = w["x"], w["y"], w["z"], w["depth"], w["diameter"]
        r = dia / 2
        px, py = ox + wx, oy + wy
        if kind == "tuberack":
            if (slot, well) not in src_wells:
                continue                                   # only the tubes the run actually uses
            # UNCAPPED Falcon, THIN-WALLED. A solid cylinder with opacity<1 path-traces as a
            # glass ROD — dark, mirror-like, and it hides the liquid. A ~1 mm shell does not.
            tube_bot = oz + wz
            _tm = LW.get("tube_model") or {}
            _tmesh = os.path.join(args.labware, _tm.get("mesh", "")) if _tm else ""
            if _tmesh and os.path.exists(_tmesh):
                _tg, _tn = add_mesh(f"/World/lw_{slot}/tube_{well}", _tmesh, (0.93, 0.95, 0.97))
                UsdGeom.XformCommonAPI(_tg).SetTranslate(Gf.Vec3d(px, py, tube_bot))
                bind(_tg, MAT["glass"])
            else:
                bind(make_cone(f"/World/lw_{slot}/tube_{well}_c", (px, py, tube_bot + CONE_H / 2),
                               r + 0.9, CONE_H, flip=True), MAT["glass"])
                body_h = wd_ - CONE_H
                bind(make_cyl(f"/World/lw_{slot}/tube_{well}_b",
                              (px, py, tube_bot + CONE_H + body_h / 2), r + 0.9, body_h), MAT["glass"])
            rgb = REAGENT[(slot, well)]
            lc = make_cone(f"/World/lw_{slot}/liq_{well}_c", (px, py, tube_bot + CONE_H / 2),
                           r * 0.99, CONE_H, rgb, flip=True)
            lb = make_cyl(f"/World/lw_{slot}/liq_{well}_b", (px, py, tube_bot + CONE_H), r * 0.99, 1.0, rgb)
            # opaque: a reagent column seen THROUGH a tube wall must not also be see-through
            mtl, din = make_pbr(f"/World/mat/liq_{slot}_{well}", rgb, roughness=0.28, opacity=1.0)
            bind(lc, mtl); bind(lb, mtl)
            tube_liq[f"{slot}/{well}"] = {"cone": lc, "body": lb, "din": din, "r": r,
                                          "bot": tube_bot, "rgb": rgb, "rim": oz + wz + wd_,
                                          "x": px, "y": py}
        elif kind == "tiprack":
            tl = meta.get("tipLength") or wd_
            top = oz + wz + wd_
            t = make_cone(f"/World/lw_{slot}/tip_{well}", (px, py, top - tl / 2), r * 1.02, tl, flip=True)
            bind(t, MAT["tip"]); rack_tips[f"{slot}/{well}"] = t
        else:                                              # plate well: liquid disc in a real cavity
            base = oz + wz
            rgb0 = (0.35, 0.38, 0.44)
            lq = make_cyl(f"/World/lw_{slot}/liq_{well}", (px, py, base + 0.25), r * 0.965, 0.5, rgb0)
            mtl, din = make_pbr(f"/World/mat/liq_{slot}_{well}", rgb0, roughness=0.28, opacity=1.0)
            bind(lq, mtl)
            show(lq, False)
            well_liq[f"{slot}/{well}"] = {"prim": lq, "din": din, "r": r * 0.965,
                                          "base": base, "depth": wd_, "x": px, "y": py}
            WELLGEO[f"{slot}/{well}"] = (px, py, base, wd_)

# --- per-labware liquid gain -------------------------------------------------
# Work out the largest volume this protocol puts in any single plate well, then scale so it
# renders at ~55% of the well depth. Keeps a 0.5 mm film visible without saturating a well
# that is already legibly full.
_max_vol = {}
for _s in steps:
    if _s[0] == "dispense":
        _k = f"{_s[1]}/{_s[2]}"
        if _k in well_liq:
            _max_vol[_k] = _max_vol.get(_k, 0.0) + float(_s[3] or 0)
for _k, _w in well_liq.items():
    if not AUTO_GAIN:
        _w["gain"] = GAIN; continue
    _v = _max_vol.get(_k, 0.0)
    _ht = h_flat(_v, _w["r"]) if _v > 0 else 0.0
    _w["gain"] = 1.0 if _ht <= 0 else max(1.0, min(25.0, 0.55 * _w["depth"] / _ht))
_g = sorted({round(w.get("gain", GAIN), 2) for w in well_liq.values()})
log(f"labware built: {len(well_liq)} plate wells, {len(tube_liq)} source tubes (UNCAPPED), "
    f"{len(rack_tips)} tips in rack; liquid gain {'auto' if AUTO_GAIN else 'fixed'} -> {_g}")

# ---------------- machine ----------------
NOZZLE = [179.85, 112.17, 225.27]
pmeta = {}
_pj = os.path.join(args.assets, "parts.json")
if os.path.exists(_pj):
    pmeta = json.load(open(_pj)); NOZZLE = pmeta.get("nozzle", NOZZLE)

gantry = UsdGeom.Xform.Define(stage, "/World/gantry")
carriage = UsdGeom.Xform.Define(stage, "/World/gantry/carriage")
pipette = UsdGeom.Xform.Define(stage, "/World/gantry/carriage/pipette")
gantry_api = UsdGeom.XformCommonAPI(gantry)
carriage_api = UsdGeom.XformCommonAPI(carriage)
pipette_api = UsdGeom.XformCommonAPI(pipette)

have_cad = False
if args.chassis:
    fp, dp, cp, pp = (os.path.join(args.assets, f"ot2_{n}.stl")
                      for n in ("frame", "deck", "carriage", "pipette"))
    if all(os.path.exists(p) for p in (fp, dp, cp, pp)):
        have_cad = True
        mf, nf = add_mesh("/World/machine_frame", fp, (0.055, 0.058, 0.065)); bind(mf, MAT["frame"])
        md, nd = add_mesh("/World/machine_deck", dp, (0.78, 0.80, 0.83)); bind(md, MAT["deck"])
        mc, nc = add_mesh("/World/gantry/carriage/mesh", cp, (0.28, 0.30, 0.34)); bind(mc, MAT["carr"])
        mp, np_ = add_mesh("/World/gantry/carriage/pipette/mesh", pp, (0.94, 0.95, 0.96)); bind(mp, MAT["pip"])
        log(f"CAD machine: frame={nf} deck={nd} carriage={nc} pipette={np_} tris; nozzle={NOZZLE}")
        bm = pmeta.get("beam", {}); mb = pmeta.get("machine_bounds", [[-116, -93, -63], [508, 475, 599]])
        bz1 = bm.get("z1", 580.0); bz0 = max(bm.get("z0", 480.0), bz1 - 95)
        bind(make_box("/World/gantry/beam",
                      ((mb[0][0] + 55 + mb[1][0] - 55) / 2, 192.0, (bz0 + bz1) / 2),
                      ((mb[1][0] - mb[0][0] - 110) / 2, 34.0, (bz1 - bz0) / 2),
                      (0.20, 0.21, 0.24)), MAT["beam"])

# carried tip: a real p300 profile (collar + long taper), + the liquid column inside it
tip_grp = UsdGeom.Xform.Define(stage, "/World/gantry/carriage/pipette/tipgrp")
_collar = make_cyl("/World/gantry/carriage/pipette/tipgrp/collar",
                   (NOZZLE[0], NOZZLE[1], NOZZLE[2] - 6), 3.6, 12.0)
_taper = make_cone("/World/gantry/carriage/pipette/tipgrp/taper",
                   (NOZZLE[0], NOZZLE[1], NOZZLE[2] - 12 - (TIP_LEN - 12) / 2), 3.4, TIP_LEN - 12, flip=True)
bind(_collar, MAT["tip"]); bind(_taper, MAT["tip"])
TIPLIQ_R, TIPLIQ_BASE = 2.6, NOZZLE[2] - TIP_LEN + 6
tipliq = make_cyl("/World/gantry/carriage/pipette/tipgrp/liq",
                  (NOZZLE[0], NOZZLE[1], TIPLIQ_BASE), TIPLIQ_R, 1.0, (0.8, 0.6, 0.2))
_tlm, tipliq_din = make_pbr("/World/mat/tipliq", (0.8, 0.6, 0.2), roughness=0.28, opacity=1.0)
bind(tipliq, _tlm)
show(tip_grp, False); show(tipliq, False)

# ---- trash: a REAL open bin ----
# The reference CAD models the trash as a solid block, so tips could only ever sit on its lid
# (and the earlier build buried them ~50 mm inside the mesh). twin/cad/trash_open.py removes
# the lid and records the cavity; here we line it and pile used tips on its actual floor.
import random as _rnd  # noqa: E402
_rng = _rnd.Random(7)
TR = pmeta.get("trash") or {}
if TR.get("floor_z") is not None:
    ix0, ix1 = TR["inner_x"]; iy0, iy1 = TR["inner_y"]
    tr_floor, tr_rim = TR["floor_z"], TR["rim_z"]
    tcx, tcy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
    _d = tr_rim - tr_floor
    bind(make_box("/World/trash/floor", (tcx, tcy, tr_floor + 1.5),
                  ((ix1 - ix0) / 2, (iy1 - iy0) / 2, 1.5), (0.10, 0.11, 0.13)), MAT["rack"])
    for _n, _c, _h in (("wl", (ix0, tcy, tr_floor + _d / 2), (1.0, (iy1 - iy0) / 2, _d / 2)),
                       ("wr", (ix1, tcy, tr_floor + _d / 2), (1.0, (iy1 - iy0) / 2, _d / 2)),
                       ("wf", (tcx, iy0, tr_floor + _d / 2), ((ix1 - ix0) / 2, 1.0, _d / 2)),
                       ("wb", (tcx, iy1, tr_floor + _d / 2), ((ix1 - ix0) / 2, 1.0, _d / 2))):
        bind(make_box(f"/World/trash/{_n}", _c, _h, (0.10, 0.11, 0.13)), MAT["rack"])
    log(f"trash: OPEN bin, floor z={tr_floor:.1f} rim z={tr_rim:.1f}, "
        f"inner {ix1-ix0:.0f}x{iy1-iy0:.0f} mm, centre ({tcx:.0f},{tcy:.0f})")
else:
    _tp = deck.slot_center_top(slots[TRASH_SLOT]["position"], slots[TRASH_SLOT]["boundingBox"]) \
        if TRASH_SLOT in slots else (cxd, cyd, 0)
    ix0, ix1, iy0, iy1 = _tp[0] - 60, _tp[0] + 60, _tp[1] - 60, _tp[1] + 60
    tr_floor, tr_rim, tcx, tcy = 30.0, 90.0, _tp[0], _tp[1]
    log("trash: no CAD measurement in parts.json — using deck slot 12 fallback")

trash_pos = (tcx, tcy, tr_rim)
n_drop = max(1, sum(1 for s in steps if s[0] == "drop"))
trash_tips = []
for i in range(n_drop):
    px = _rng.uniform(ix0 + 16, ix1 - 16)
    py = _rng.uniform(iy0 + 16, iy1 - 16)
    pz = tr_floor + 3 + 3.3 + (i // 8) * 5.5 + _rng.uniform(0, 1.6)   # they stack in layers
    t = make_cone(f"/World/trash/tip_{i}", (px, py, pz), 3.3, TIP_LEN * 0.92)
    # a discarded tip lands on its SIDE at a random angle — not standing in a pattern
    UsdGeom.XformCommonAPI(t).SetRotate(
        Gf.Vec3f(90.0 + _rng.uniform(-18, 18), _rng.uniform(-12, 12), _rng.uniform(0, 360)))
    bind(t, MAT["tip"]); show(t, False)
    trash_tips.append(t)

try:
    try:
        from isaacsim.core.utils.viewports import set_camera_view
    except Exception:
        from omni.isaac.core.utils.viewports import set_camera_view
    set_camera_view(eye=[cxd + 200, cyd - (y1 - y0) - 290, travel_z + 350], target=[cxd, cyd + 40, 55])
except Exception as e:  # noqa: BLE001
    log(f"camera framing skipped: {e}")

# ------------------------------------ motion planning ------------------------------------
# Pre-simulate the liquid so each aspirate targets the CURRENT surface (real robots aspirate
# relative to the liquid, and a falling level means a lower target each time).
_vol = {k: args.tube_start for k in tube_liq}


def tube_surface_abs(key, vol):
    t = tube_liq[key]
    return t["bot"] + h_conical(vol, t["r"])


def work_xyz(i, step):
    kind, slot, well, vol = step
    if kind == "drop":
        # hold the tip over the OPEN bin, above its rim, and release
        return trash_pos[0], trash_pos[1], trash_pos[2] + 32.0
    if kind == "delay":
        return cxd, cyd, travel_z            # park clear of the deck while the agar sets
    ox, oy, oz = labware_origin(slot)
    w = wdef(slot, well)
    x, y = ox + w["x"], oy + w["y"]
    rim = oz + w["z"] + w["depth"]
    if kind == "pick":
        return x, y, rim - 7.47                       # tipOverlap: nozzle seats into the tip
    if kind == "blowout":
        return x, y, rim + 1.0                        # blow out at the well top, per the ledger
    if kind == "aspirate":
        key = f"{slot}/{well}"
        if key in tube_liq:
            surf = tube_surface_abs(key, _vol[key])
            z = max(oz + w["z"] + BOTTOM_CLEARANCE, surf - IMMERSION)
            _vol[key] = max(0.0, _vol[key] - float(vol or 0))
            return x, y, z
        return x, y, oz + w["z"] + BOTTOM_CLEARANCE
    return x, y, oz + w["z"] + BOTTOM_CLEARANCE       # dispense: protocol's bottom clearance


targets = [work_xyz(i, s) for i, s in enumerate(steps)]

report = {"backend": "isaac-sim-5.x live", "n_steps": len(steps), "deck_layout": layout,
          "reachable_all": True, "reach_violations": [], "collisions": [],
          "min_transit_clearance_mm": 999.0, "verdict": ""}
boxes = []
for slot, g in geoms.items():
    pos = slots[slot]["position"]; c = g.corner; d = g.dims
    boxes.append((np.array([pos[0] + c[0] + d[0] / 2, pos[1] + c[1] + d[1] / 2, pos[2] + c[2] + d[2] / 2]),
                  np.array([d[0] / 2, d[1] / 2, d[2] / 2])))

wps = [(cxd, cyd, travel_z, "home", None)]
for i, s in enumerate(steps):
    tx, ty, tz = targets[i]
    if not deck.reachable(tx, ty, slots):
        report["reachable_all"] = False
        report["reach_violations"].append({"step": f"{s[0]} {s[1]}:{s[2]}"})
    cx, cy, _ = wps[-1][:3]
    wps += [(cx, cy, travel_z, "ascend", None), (tx, ty, travel_z, "move", None),
            (tx, ty, tz, f"{s[0]} {s[2]}", s), (tx, ty, tz, "dwell", None),
            (tx, ty, travel_z, "ascend", None)]

seg = [math.dist(wps[i - 1][:3], wps[i][:3]) for i in range(1, len(wps))]
tot = sum(seg) or 1.0
path = [wps[0]]
for i in range(1, len(wps)):
    ax, ay, az, _, _ = wps[i - 1]; bx, by, bz, lbl, op = wps[i]
    n = max(2, round(seg[i - 1] / tot * max(150, args.max_frames)))
    for k in range(1, n + 1):
        t = k / n
        path.append((ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t,
                     lbl if k == n else "", op if k == n else None))
    if op is not None and op[0] == "delay":   # the agar solidification hold, made visible
        path += [(bx, by, bz, "", None)] * 150
    elif lbl == "dwell":                      # hold at the action so it is watchable
        path += [(bx, by, bz, "", None)] * 12

for (x, y, z, lbl, op) in path:
    p = np.array([x, y, z])
    if z > travel_z - 3.0:                       # transit height: nothing may be in the way
        best = 999.0
        for c, h in boxes:
            d = np.maximum(np.abs(p - c) - h, 0.0)
            best = min(best, float(np.linalg.norm(d)))
        report["min_transit_clearance_mm"] = round(min(report["min_transit_clearance_mm"], best), 2)
    if z > travel_z - 8.0:                       # a real strike: tip inside labware while traversing
        worst = 0.0
        for c, h in boxes:
            d = np.abs(p - c) - h
            if (d < 0).all():
                worst = max(worst, float(-d.max()) + _TIP_R)
        if worst > 0.05:
            report["collisions"].append({"at": lbl, "penetration_mm": round(worst, 2)})
report["verdict"] = ("INFEASIBLE" if (report["collisions"] or not report["reachable_all"])
                     else "FEASIBLE — all targets reachable, no collisions")
log(f"VERDICT: {report['verdict']} | min_clearance={report['min_transit_clearance_mm']}mm")
try:
    os.makedirs(os.path.join(args.twin_root, "out"), exist_ok=True)
    json.dump(report, open(os.path.join(args.twin_root, "out", "isaac_live_report.json"), "w"), indent=2)
except Exception:
    pass

if args.edit:
    try:
        _settings.set("/app/window/hideUi", False)
    except Exception:
        pass
    log("EDIT MODE — static scene, full UI.")
    while sim.is_running():
        sim.update(); time.sleep(1.0 / args.fps)
    sim.close(); sys.exit(0)


# ------------------------------------ liquid state ------------------------------------
def set_tube(key, vol):
    """Source level from conserved volume. The conical bottom is scaled about its apex so the
    liquid stays seated in the tip of the cone, not floating in it."""
    t = tube_liq[key]
    hh = h_conical(vol, t["r"])
    if hh <= CONE_H:                                  # only the conical bottom holds liquid
        show(t["body"], False)
        s = max(0.02, hh / CONE_H)
        UsdGeom.XformCommonAPI(t["cone"]).SetScale(Gf.Vec3f(s, s, s))
        UsdGeom.XformCommonAPI(t["cone"]).SetTranslate(
            Gf.Vec3d(t["x"], t["y"], float(t["bot"] + s * CONE_H / 2)))
        show(t["cone"], vol > 1)
    else:
        UsdGeom.XformCommonAPI(t["cone"]).SetScale(Gf.Vec3f(1, 1, 1))
        UsdGeom.XformCommonAPI(t["cone"]).SetTranslate(
            Gf.Vec3d(t["x"], t["y"], float(t["bot"] + CONE_H / 2)))
        show(t["cone"], True)
        bh = hh - CONE_H
        t["body"].GetHeightAttr().Set(float(bh))
        UsdGeom.XformCommonAPI(t["body"]).SetTranslate(
            Gf.Vec3d(t["x"], t["y"], float(t["bot"] + CONE_H + bh / 2)))
        show(t["body"], True)


def set_well(key, vol, rgb):
    w = well_liq[key]
    h_true = h_flat(vol, w["r"])
    h = min(w["depth"] - 0.4, h_true * w.get("gain", GAIN))
    if vol <= 0.01:
        show(w["prim"], False); return
    w["prim"].GetHeightAttr().Set(float(max(0.2, h)))
    UsdGeom.XformCommonAPI(w["prim"]).SetTranslate(
        Gf.Vec3d(w["x"], w["y"], float(w["base"] + h / 2)))
    w["din"].Set(Gf.Vec3f(*rgb))
    show(w["prim"], True)


def set_tipliq(vol, rgb):
    if vol <= 0.01:
        show(tipliq, False); return
    h = min(TIP_LEN * 0.62, (vol / 300.0) * TIP_LEN * 0.62 * max(1.0, GAIN * 0.5))
    tipliq.GetHeightAttr().Set(float(max(0.4, h)))
    UsdGeom.XformCommonAPI(tipliq).SetTranslate(Gf.Vec3d(NOZZLE[0], NOZZLE[1], TIPLIQ_BASE + h / 2))
    tipliq_din.Set(Gf.Vec3f(*rgb))
    show(tipliq, True)


class State:
    def __init__(self):
        self.reset(first=True)

    def reset(self, first=False):
        self.tip = False; self.tip_vol = 0.0; self.tip_rgb = (0.8, 0.6, 0.2); self.agar_set = False
        self.wells = {k: 0.0 for k in well_liq}
        self.wrgb = {k: (0.35, 0.38, 0.44) for k in well_liq}
        self.tubes = {k: args.tube_start for k in tube_liq}
        self.trash = 0
        show(tip_grp, False); show(tipliq, False)
        for k in well_liq:
            set_well(k, 0.0, (0.35, 0.38, 0.44))
        for k in tube_liq:
            set_tube(k, args.tube_start)
        for t in rack_tips.values():
            show(t, True)
        for t in trash_tips:
            show(t, False)

    def apply(self, op):
        if not op:
            return
        kind, slot, well, vol = op
        key = f"{slot}/{well}"
        v = float(vol or 0)
        if kind == "pick":
            self.tip = True; self.tip_vol = 0.0
            if key in rack_tips:
                show(rack_tips[key], False)      # the tip LEAVES the rack
            show(tip_grp, True)
        elif kind == "aspirate":
            if key in tube_liq:
                self.tip_rgb = tube_liq[key]["rgb"]
                self.tubes[key] = max(0.0, self.tubes[key] - v)
                set_tube(key, self.tubes[key])   # source level falls by exactly what was drawn
            self.tip_vol += v
            set_tipliq(self.tip_vol, self.tip_rgb)
        elif kind == "dispense":
            if key in well_liq:
                self.wells[key] += v
                self.wrgb[key] = self.tip_rgb
                set_well(key, self.wells[key], self.tip_rgb)
            self.tip_vol = max(0.0, self.tip_vol - v)
            set_tipliq(self.tip_vol, self.tip_rgb)
        elif kind == "blowout":
            # the last of the liquid is expelled — the tip ends up truly empty
            self.tip_vol = 0.0
            set_tipliq(0.0, self.tip_rgb)
        elif kind == "delay":
            # protocol.delay(): the agar sets. Solidified agar is duller and more opaque than
            # the molten mix that was dispensed, so darken every well that holds some.
            self.agar_set = True
            for k, v in self.wells.items():
                if v > 0:
                    r, g, b = self.wrgb[k]
                    self.wrgb[k] = (r * 0.80, g * 0.82, b * 0.78)
                    set_well(k, v, self.wrgb[k])
            log(f"  [protocol] {well}")            # the ledger's own delay text
        elif kind == "drop":
            self.tip = False; self.tip_vol = 0.0
            show(tip_grp, False); show(tipliq, False)
            if self.trash < len(trash_tips):
                show(trash_tips[self.trash], True)   # and lands in the trash
            self.trash += 1


state = State()
_r0 = list(well_liq.values())[0]["r"] if well_liq else 11.4
_w0 = list(well_liq.values())[0] if well_liq else None
_g0 = _w0.get("gain", GAIN) if _w0 else GAIN
_vmax0 = max(_max_vol.values()) if _max_vol else 200.0
log(f"liquid model: 1 uL = 1 mm^3. Largest well fill {_vmax0:.0f} uL = {h_flat(_vmax0, _r0):.2f} mm true, "
    f"shown {h_flat(_vmax0, _r0)*_g0:.2f} mm at {_g0:.2f}x in a {_w0['depth'] if _w0 else 0:.1f} mm well. "
    f"Tubes start at {args.tube_start:.0f} uL (surface {h_conical(args.tube_start, 7.45):.1f} mm).")

if args.validate:
    # exercise the liquid system for real before declaring the scene good: every op kind,
    # against real prims, so a bad transform/attr fails here and not 3 minutes into a boot.
    _probe = [s for s in steps[:8]]
    for _op in _probe:
        state.apply(_op)
    log(f"VALIDATE OK — machine + CAD labware + liquid system built and exercised "
        f"({len(_probe)} ops: tip on={state.tip}, tip_vol={state.tip_vol:.0f}uL, "
        f"trash={state.trash})")
    sim.close(); sys.exit(0)

if args.snapshot:
    # Fast-forward the protocol, park the pipette mid-action, and RENDER. This is the honest
    # check: a state counter proves the code ran, a picture proves it is visible.
    import omni.replicator.core as rep  # noqa: E402
    n_ops = args.snapshot_ops or len(steps)
    last = None
    for i, s in enumerate(steps[:n_ops]):
        state.apply(s)
        last = (i, s)
    if last is not None:
        _i, _s = last
        tx, ty, tz = targets[_i]
        zb = tz + (TIP_LEN if state.tip else 0.0)
        gantry_api.SetTranslate(Gf.Vec3d(0.0, float(ty - NOZZLE[1]), 0.0))
        carriage_api.SetTranslate(Gf.Vec3d(float(tx - NOZZLE[0]), 0.0, 0.0))
        pipette_api.SetTranslate(Gf.Vec3d(0.0, 0.0, float(zb - NOZZLE[2])))
    log(f"snapshot: applied {n_ops} ops -> {sum(1 for v in state.wells.values() if v > 0)} wells "
        f"filled, {state.trash} tips in trash, tip_on={state.tip}")
    os.makedirs(args.snapshot, exist_ok=True)
    _tp = trash_pos
    VIEWS = [("overview", (cxd + 210, cyd - (y1 - y0) - 300, travel_z + 330), (cxd, cyd + 30, 45)),
             ("trash",    (_tp[0] + 130, _tp[1] - 190, _tp[2] + 165), (_tp[0], _tp[1], tr_floor + 12))]
    # aim each labware view at the REAL labware, computed from its slot + dimensions —
    # hardcoded offsets from the deck centre pointed the last run at bare deck.
    for _slot, _g in geoms.items():
        _ox, _oy, _oz = labware_origin(_slot)
        _xd, _yd, _zd = _g.dims
        _lcx, _lcy = _ox + _xd / 2, _oy + _yd / 2
        _top = _oz + _zd
        _nm = ("plate" if not (_g.is_tiprack or "rack" in _g.load_name.lower())
               else "tiprack" if _g.is_tiprack else "tubes")
        _d = max(_xd, _yd)
        VIEWS.append((_nm, (_lcx + _d * 0.55, _lcy - _d * 0.95, _top + _d * 0.75),
                      (_lcx, _lcy, _oz + _zd * 0.45)))
    for nm, eye, tgt in VIEWS:
        c = rep.create.camera(position=eye, look_at=tgt)
        rp = rep.create.render_product(c, (1280, 800))
        w = rep.WriterRegistry.get("BasicWriter")
        d = os.path.join(args.snapshot, nm)
        w.initialize(output_dir=d, rgb=True)
        w.attach([rp])
        rep.orchestrator.step(rt_subframes=12)
        w.detach()
        log(f"  rendered {nm} -> {d}")
    log("SNAPSHOT DONE")
    sim.close(); sys.exit(0)

# ------------------------------------ live loop ------------------------------------
if args.ui:
    # editor mode: keep the Kit UI (stage tree / property panel / toolbar) visible while the
    # protocol plays, so the scene can be inspected and prims selected during the run.
    for _k in ("/app/window/hideUi", "/app/window/hideStatusBar"):
        try:
            _settings.set(_k, False)
        except Exception:
            pass
    log("EDITOR UI enabled — stage tree + property panel visible during the run")

speed = max(0.05, args.speed)
speed_file = os.path.join(args.twin_root, "out", "speed.json")
try:
    json.dump({"speed": speed}, open(speed_file, "w"))
except Exception:
    pass
log(f"streaming {len(path)} frames/pass @ {args.fps:.0f}fps, speed {speed}x. "
    f"Change speed live by editing {speed_file} (no restart).")

pass_no = 0
fi = 0
while True:
    pass_no += 1
    for (x, y, z, lbl, op) in path:
        t0 = time.time()
        fi += 1
        if fi % 30 == 0:                      # live speed control
            try:
                sp = float(json.load(open(speed_file)).get("speed", speed))
                if sp > 0 and abs(sp - speed) > 1e-6:
                    speed = max(0.02, min(8.0, sp)); log(f"speed -> {speed}x")
            except Exception:
                pass
        z_body = z + (TIP_LEN if state.tip else 0.0)
        if have_cad:
            gantry_api.SetTranslate(Gf.Vec3d(0.0, float(y - NOZZLE[1]), 0.0))
            carriage_api.SetTranslate(Gf.Vec3d(float(x - NOZZLE[0]), 0.0, 0.0))
            pipette_api.SetTranslate(Gf.Vec3d(0.0, 0.0, float(z_body - NOZZLE[2])))
        else:
            pipette_api.SetTranslate(Gf.Vec3d(float(x - NOZZLE[0]), float(y - NOZZLE[1]),
                                              float(z_body - NOZZLE[2])))
        if op:
            state.apply(op)
        sim.update()
        s = (1.0 / args.fps) / speed - (time.time() - t0)
        if s > 0:
            time.sleep(s)
    filled = sum(1 for v in state.wells.values() if v > 0)
    drawn = sum(args.tube_start - v for v in state.tubes.values())
    log(f"pass {pass_no}: {filled}/{len(well_liq)} wells filled, {state.trash} tips in trash, "
        f"{drawn:.0f} uL transferred")
    if args.once:
        break
    state.reset()

while sim.is_running():
    sim.update(); time.sleep(1.0 / args.fps / speed)
sim.close()
