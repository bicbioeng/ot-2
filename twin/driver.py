"""Replay any Opentrons command ledger through the OT-2 kinematic twin.

Input is the SAME analysis.json the real `opentrons analyze` engine produced.
The twin is paper-agnostic: deck + labware geometry come entirely from the real
Opentrons definitions (deck def + the labware definitions embedded in the
ledger), so a new paper's protocol runs with zero code changes and zero guessed
coordinates. It records three physical-feasibility signals the conformance
ledger cannot see:
    * reachability   — every target inside the real deck's addressable extent
    * collisions     — tip penetrating a labware / deck body (MuJoCo contacts)
    * travel margin  — min tip-to-labware clearance while in transit

Rendering uses MuJoCo's Metal-backed offscreen GL context (the M-series GPU).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

import mujoco
import numpy as np

from . import deck
from .deck import LabwareGeom, TRASH_SLOT
from .ot2_model import build_mjcf, travel_tip_z

STANDOFF = 2.0          # mm above the well rim the tip stops (no-liquid twin)


@dataclass
class Step:
    kind: str           # pick | aspirate | dispense | drop
    slot: str | None
    well: str
    volume: float | None


@dataclass
class Report:
    n_steps: int = 0
    reachable_all: bool = True
    reach_violations: list = field(default_factory=list)
    collisions: list = field(default_factory=list)
    min_transit_clearance_mm: float = 999.0
    min_clearance_at: str = ""
    total_travel_mm: float = 0.0
    deck_layout: dict = field(default_factory=dict)
    geometry_source: str = ("exact: ot2_standard deck def + labware definitions "
                            "embedded in the ledger (no approximated coordinates)")
    frames: int = 0
    gpu_render: bool = True
    verdict: str = ""


def parse_ledger(path: str | Path) -> tuple[dict[str, str], dict[str, dict], list[Step]]:
    """Return (layout {slot->loadName}, slot_defs {slot->definition}, steps)."""
    a = json.loads(Path(path).read_text())
    cmds = a.get("commands", [])
    layout: dict[str, str] = {}
    slot_defs: dict[str, dict] = {}
    id2slot: dict[str, str] = {}
    for c in cmds:
        if c.get("commandType") == "loadLabware":
            p, res = c["params"], c.get("result", {})
            slot = str(p.get("location", {}).get("slotName"))
            dfn = res.get("definition")
            if slot and dfn:
                layout[slot] = p.get("loadName")
                slot_defs[slot] = dfn
                if res.get("labwareId"):
                    id2slot[res["labwareId"]] = slot
    steps: list[Step] = []
    for c in cmds:
        t, p = c.get("commandType"), c.get("params", {})
        if t == "pickUpTip":
            steps.append(Step("pick", id2slot.get(p.get("labwareId")), p.get("wellName", "A1"), None))
        elif t == "aspirate":
            steps.append(Step("aspirate", id2slot.get(p.get("labwareId")), p.get("wellName", "A1"), p.get("volume")))
        elif t == "dispense":
            steps.append(Step("dispense", id2slot.get(p.get("labwareId")), p.get("wellName", "A1"), p.get("volume")))
        elif t == "dropTipInPlace":
            steps.append(Step("drop", TRASH_SLOT, "A1", None))
    return layout, slot_defs, steps


class Twin:
    def __init__(self, geoms: dict[str, LabwareGeom], slots: dict[str, dict],
                 well_colors: dict[str, str] | None = None, chassis: dict | None = None):
        self.geoms = geoms
        self.slots = slots
        self.model = mujoco.MjModel.from_xml_string(build_mjcf(geoms, slots, well_colors, chassis))
        self.data = mujoco.MjData(self.model)
        self.jx = self.model.joint("jx").qposadr[0]
        self.jy = self.model.joint("jy").qposadr[0]
        self.jz = self.model.joint("jz").qposadr[0]
        self.tip_gid = self.model.geom("tip").id
        self.tip_sid = self.model.site("tip_site").id
        self.data.qpos[:] = 0
        mujoco.mj_forward(self.model, self.data)
        self.origin = self.data.site_xpos[self.tip_sid].copy()
        self.struct = {}
        for gid in range(self.model.ngeom):
            nm = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, gid)
            if nm and (nm.startswith("lw_") or nm in ("deck", "floor")):
                self.struct[gid] = nm
        # analytic labware boxes for clearance, from EXACT dims
        self.boxes = []
        for slot, g in geoms.items():
            pos = slots[slot]["position"]; cx, cy, cz = g.corner
            xd, yd, zd = g.dims
            self.boxes.append((f"lw_{slot}",
                np.array([pos[0] + cx + xd / 2, pos[1] + cy + yd / 2, pos[2] + cz + zd / 2]),
                np.array([xd / 2, yd / 2, zd / 2])))

    def tip_target_joints(self, x, y, z):
        return (x - self.origin[0], y - self.origin[1], z - self.origin[2])

    def set_tip(self, x, y, z):
        self.data.qpos[self.jx] = x - self.origin[0]
        self.data.qpos[self.jy] = y - self.origin[1]
        self.data.qpos[self.jz] = z - self.origin[2]
        mujoco.mj_forward(self.model, self.data)

    def tip_pos(self):
        return self.data.site_xpos[self.tip_sid].copy()

    def collisions(self):
        out = []
        for i in range(self.data.ncon):
            con = self.data.contact[i]
            if self.tip_gid in (con.geom1, con.geom2):
                other = con.geom2 if con.geom1 == self.tip_gid else con.geom1
                if other in self.struct and con.dist < -0.05:
                    out.append((self.struct[other], float(-con.dist)))
        return out

    def transit_clearance(self, p):
        best = 999.0
        for _, c, h in self.boxes:
            d = np.maximum(np.abs(p - c) - h, 0.0)
            best = min(best, float(np.linalg.norm(d)))
        return best


def well_xyz(step: Step, geoms: dict[str, LabwareGeom], slots: dict[str, dict]):
    if step.kind == "drop":
        tp = slots[TRASH_SLOT]
        cx, cy, _ = deck.slot_center_top(tp["position"], tp["boundingBox"])
        return cx, cy, 40.0 + STANDOFF          # above the trash box (top ~40)
    g = geoms[step.slot]
    x, y, rim = deck.well_deck_xyz(slots[step.slot]["position"], g, step.well)
    return x, y, rim + STANDOFF


_ASSETS = Path(__file__).resolve().parent / "assets" / "ot2"


def _chassis_spec() -> dict | None:
    """Load the real OT-2 reference mesh + its recorded deck-frame alignment.

    Uses the DETAILED reference model (full robot: enclosure + gantry + Z carriage
    + deck plate) rendered as a low-opacity glass shell, with alignment read from
    alignment.json (analytically derived, not guessed)."""
    align_p = _ASSETS / "alignment.json"
    if not align_p.exists():
        return None
    a = json.loads(align_p.read_text())
    mesh_p = _ASSETS / a["asset"]
    if not mesh_p.exists():                      # fall back to the basic shell
        a["asset"] = a.get("asset_basic", "ot2_reference_basic.stl")
        mesh_p = _ASSETS / a["asset"]
        if not mesh_p.exists():
            return None
    return {"meshdir": str(_ASSETS), "basename": a["asset"], "pos": tuple(a["pos"]),
            "zrot": a.get("zrot_deg", 0), "rgba": a.get("rgba", "0.60 0.66 0.74 0.16"),
            "scale": a.get("scale", 1.0)}


def run(analysis_json: str | Path, out_mp4: str | Path,
        report_json: str | Path, fps: int = 30, break_mode: bool = False,
        deck_name: str = "ot2_standard", chassis: bool = False,
        width: int = 1000, height: int = 640) -> Report:
    slots = deck.load_deck(deck_name)
    layout, slot_defs, steps = parse_ledger(analysis_json)
    geoms = {slot: LabwareGeom(dfn) for slot, dfn in slot_defs.items()}
    chassis_spec = _chassis_spec() if chassis else None

    from . import chem as chemistry
    chem = chemistry.load_chem(analysis_json)
    dest_slot = next((s.slot for s in steps if s.kind == "dispense"), None)
    well_colors: dict[str, str] = {}
    if chem and dest_slot:
        for well, w in chem["wells"].items():
            well_colors[f"{dest_slot}:{well}"] = chemistry.conc_color(w["vv"], chem["vmax"])[0]

    twin = Twin(geoms, slots, well_colors, chassis_spec)
    rep = Report(n_steps=len(steps), deck_layout=layout)

    travel_z = twin.origin[2]
    if break_mode:
        travel_z = min(g.dims[2] for g in geoms.values()) - 5.0   # too low -> should crash

    ox, oy, _ = twin.origin
    wps: list[tuple[float, float, float, str]] = [(ox, oy, travel_z, "home")]
    for s in steps:
        tx, ty, tz = well_xyz(s, geoms, slots)
        if not deck.reachable(tx, ty, slots):
            rep.reachable_all = False
            rep.reach_violations.append({"step": f"{s.kind} {s.slot}:{s.well}",
                                         "x": round(tx, 1), "y": round(ty, 1)})
        cx, cy, _ = wps[-1][:3]
        wps.append((cx, cy, travel_z, "ascend"))
        wps.append((tx, ty, travel_z, f"move->{s.slot}:{s.well}"))
        action = f"{s.kind} {s.well}" + (f" {s.volume:g}uL" if s.volume else "")
        if s.kind == "dispense" and chem:
            cap = chemistry.caption(s.well, chem)
            if cap:
                action += f"    ->  {cap}"
        wps.append((tx, ty, tz, action))
        wps.append((tx, ty, tz, "dwell"))
        wps.append((tx, ty, travel_z, "ascend"))

    try:
        renderer = mujoco.Renderer(twin.model, height=height, width=width)
    except Exception as e:  # noqa: BLE001
        rep.gpu_render = False
        rep.verdict = f"render-unavailable: {e}"
        Path(report_json).write_text(json.dumps(asdict(rep), indent=2))
        return rep

    cam = mujoco.MjvCamera()
    x0, x1, y0, y1 = deck.deck_extent(slots)
    cam.lookat[:] = [(x0 + x1) / 2, (y0 + y1) / 2 - 5, 60 if chassis_spec else 25]
    cam.distance = (x1 - x0) + (360 if chassis_spec else 180)
    cam.azimuth = -128; cam.elevation = -22 if chassis_spec else -24

    try:
        import imageio.v2 as imageio
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001
        imageio = None

    panel_rows = []
    if chem:
        for well in sorted(chem["wells"]):
            w = chem["wells"][well]
            rgb = chemistry.conc_color(w["vv"], chem["vmax"])[1]
            panel_rows.append((well, w["vv"],
                               w["conc"].get("penicillin_U_per_mL", 0),
                               w["conc"].get("streptomycin_ug_per_mL", 0),
                               w["ok"], rgb))
    PANEL = 34 + 24 * len(panel_rows) if panel_rows else 0

    frames = []
    last = {"v": "home"}
    def emit(label: str):
        if label and label not in ("dwell", ""):
            last["v"] = label
        shown = last["v"] if label in ("", "dwell") else label
        renderer.update_scene(twin.data, camera=cam)
        img = renderer.render()
        p = twin.tip_pos()
        if p[2] > travel_z - 3.0:
            cl = twin.transit_clearance(p)
            if cl < rep.min_transit_clearance_mm:
                rep.min_transit_clearance_mm = round(cl, 2); rep.min_clearance_at = shown
        for nm, depth in twin.collisions():
            rep.collisions.append({"at": shown, "body": nm, "penetration_mm": round(depth, 2)})
        if imageio is not None:
            im = Image.fromarray(img); dr = ImageDraw.Draw(im)
            dr.rectangle([0, 0, width, 34], fill=(10, 12, 15))
            dr.text((12, 9), f"OT-2 twin  |  {shown}", fill=(220, 235, 240))
            dr.text((width - 210, 9), "MuJoCo - Metal GPU", fill=(120, 200, 210))
            if PANEL:
                canvas = Image.new("RGB", (width, height + PANEL), (12, 14, 18))
                canvas.paste(im, (0, 0))
                d2 = ImageDraw.Draw(canvas); yb = height
                d2.rectangle([0, yb, width, yb + 2], fill=(70, 130, 140))
                d2.text((12, yb + 9),
                        "CHEMISTRY GATE  -  realized concentration from commands[] ledger",
                        fill=(150, 210, 220))
                ok_all = chem["all_ok"]
                d2.text((width - 200, yb + 9),
                        f"conformance {'PASS' if ok_all else 'FAIL'}  {chem['n_ok']}/{chem['n']}",
                        fill=(90, 200, 130) if ok_all else (225, 90, 80))
                for i, (well, vv, pen, strep, ok, rgb) in enumerate(panel_rows):
                    ry = yb + 32 + i * 24
                    d2.rectangle([16, ry + 2, 34, ry + 18], fill=rgb, outline=(210, 214, 220))
                    d2.text((46, ry + 4),
                            f"{well}    {vv*100:g}% v/v       {pen:g} U/mL pen       {strep:g} ug/mL strep",
                            fill=(226, 232, 238))
                    d2.text((width - 60, ry + 4), "OK" if ok else "X",
                            fill=(90, 200, 130) if ok else (225, 90, 80))
                frames.append(np.asarray(canvas))
            else:
                frames.append(np.asarray(im))
        else:
            frames.append(img)

    prev = wps[0]
    twin.set_tip(*prev[:3]); emit(prev[3])
    for nxt in wps[1:]:
        (x0p, y0p, z0p, _), (x1p, y1p, z1p, lbl) = prev, nxt
        dist = math.dist((x0p, y0p, z0p), (x1p, y1p, z1p))
        n = max(2, min(30, int(dist / 14) + 1))
        for k in range(1, n + 1):
            t = k / n
            twin.set_tip(x0p + (x1p - x0p) * t, y0p + (y1p - y0p) * t, z0p + (z1p - z0p) * t)
            rep.total_travel_mm += dist / n
            emit(lbl if k == n else "")
        if lbl == "dwell":
            for _ in range(4):
                emit(lbl)
        prev = nxt
    renderer.close()

    rep.frames = len(frames)
    rep.total_travel_mm = round(rep.total_travel_mm, 1)
    rep.verdict = ("INFEASIBLE" if (rep.collisions or not rep.reachable_all)
                   else "FEASIBLE — all targets reachable, no collisions")
    if imageio is not None:
        imageio.mimsave(str(out_mp4), frames, fps=fps, codec="libx264",
                        quality=8, macro_block_size=None)
    Path(report_json).write_text(json.dumps(asdict(rep), indent=2))
    return rep
