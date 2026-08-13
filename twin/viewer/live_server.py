"""Live sim bridge — stream the running MuJoCo (Metal) OT-2 twin to the browser over WebSocket.

The browser page (ot2_digital_twin.html) renders; THIS process is the sim. It steps the real
MuJoCo kinematic twin through the protocol — MuJoCo computes the pipette pose + contact/collision
against the exact labware geometry — while the deterministic state engine tracks liquids, tips, and
the trash. Each ~1/30 s it emits a state frame the page applies via window.twin.pushFrame().

    python -m twin.viewer.live_server <analysis.json> [--port 8781] [--fps 30] [--loop]

Metal now; the identical frame schema will later be emitted by the Isaac run on the triad, so the
same page can watch either backend live.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

import websockets

from twin import deck as deckmod
from twin.driver import Twin
from twin.deck import LabwareGeom
from twin.viewer.build_twin_scene import parse as parse_scene


# ---------------- state engine (mirrors the JS applyOp exactly) ----------------
def total(lst):
    return sum(o["vol"] for o in lst)


def move_liquid(src, dst, vol):
    avail = total(src)
    if avail <= 0:
        return
    take = min(vol, avail)
    for o in list(src):
        amt = (o["vol"] / avail) * take
        d = next((x for x in dst if x["liquidId"] == o["liquidId"]), None)
        if not d:
            d = {"liquidId": o["liquidId"], "vol": 0.0}
            dst.append(d)
        d["vol"] += amt
        o["vol"] -= amt
    src[:] = [o for o in src if o["vol"] > 1e-6]


class SimState:
    def __init__(self, scene):
        self.scene = scene
        self.reset()

    def reset(self):
        self.wells = {k: [dict(o) for o in v] for k, v in self.scene["initial"].items()}
        self.rack = set(f"{lw['slot']}/{w['name']}"
                        for lw in self.scene["labware"] if lw["kind"] == "tiprack"
                        for w in lw["wells"])
        self.tip = None
        self.contents = []
        self.trash = 0

    def container(self, key):
        if key == "tip":
            return self.contents
        return self.wells.setdefault(key, [])

    def apply(self, op):
        if not op:
            return
        k = op["kind"]
        if k == "pickTip":
            self.tip = {"rack": op["rack"], "well": op["well"]}
            self.rack.discard(f"{op['rack']}/{op['well']}")
        elif k == "aspirate":
            move_liquid(self.container(op["well"]), self.container("tip"), op["vol"])
        elif k == "dispense":
            move_liquid(self.container("tip"), self.container(op["well"]), op["vol"])
        elif k == "dropTip":
            self.trash += 1
            self.tip = None
            self.contents = []

    def frame(self):
        return {"wells": {k: v for k, v in self.wells.items() if total(v) > 0.01},
                "rackPresent": list(self.rack), "trash": self.trash,
                "tip": self.tip is not None, "contents": self.contents}


# ---------------- MuJoCo twin for real pose + collision ----------------
def build_twin(analysis_path):
    slots = deckmod.load_deck("ot2_standard")
    import json as _j
    a = _j.loads(Path(analysis_path).read_text())
    slot_defs = {}
    for c in a.get("commands", []):
        if c.get("commandType") == "loadLabware":
            p, r = c["params"], c.get("result", {})
            slot = str(p.get("location", {}).get("slotName"))
            if r.get("definition"):
                slot_defs[slot] = r["definition"]
    geoms = {s: LabwareGeom(d) for s, d in slot_defs.items()}
    return Twin(geoms, slots), geoms, slots


def interpolate(steps, home, budget=240):
    """Same distance-budgeted interpolation the render uses -> smooth motion."""
    wps = [tuple(home) + ("home",)]
    for s in steps:
        wps.append(tuple(s["approach"]) + (f'{s["type"]} approach',))
        wps.append(tuple(s["contact"]) + (f'{s["type"]} {s.get("well","")}', s["i"]))
        wps.append(tuple(s["approach"]) + ("ascend",))
    # build frames with op-index carried on the contact waypoint
    frames = []
    seg_len = [math.dist(wps[i - 1][:3], wps[i][:3]) for i in range(1, len(wps))]
    tot = sum(seg_len) or 1.0
    for i in range(1, len(wps)):
        a, b = wps[i - 1], wps[i]
        n = max(2, round(seg_len[i - 1] / tot * budget))
        opi = b[4] if len(b) > 4 else None
        for k in range(1, n + 1):
            t = k / n
            pos = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
            frames.append((pos, b[3], opi if k == n else None))
    return frames


async def run(ws, scene, twin, path, fps, loop):
    steps = scene["steps"]
    home = scene["deck"]["home"]
    travel_z = scene["deck"]["travelZ"]
    frames = interpolate(steps, home)
    st = SimState(scene)
    dt = 1.0 / fps
    while True:
        st.reset()
        for pos, label, opi in frames:
            # MuJoCo: set pose, read real site position + any contact
            twin.set_tip(*pos)
            tp = twin.tip_pos()
            # Collisions only count in TRANSIT — descending into the target well is intended
            # (MuJoCo models labware as a solid box, so an in-well tip is a false positive).
            in_transit = pos[2] > travel_z - 8
            cols = twin.collisions() if in_transit else []
            if opi is not None:
                st.apply(steps[opi]["op"])
            fr = st.frame()
            fr["pipette"] = [round(float(tp[0]), 2), round(float(tp[1]), 2), round(float(tp[2]), 2)]
            fr["collision"] = bool(cols)
            fr["label"] = f"{label}" + (f"  ⚠ collision:{cols[0][0]}" if cols else "")
            fr["backend"] = "MuJoCo · Metal"
            await ws.send(json.dumps(fr))
            await asyncio.sleep(dt)
        if not loop:
            await ws.send(json.dumps({"done": True}))
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--port", type=int, default=8781)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--loop", action="store_true", default=True)
    ap.add_argument("--once", dest="loop", action="store_false")
    args = ap.parse_args()

    scene = parse_scene(args.analysis)
    twin, geoms, slots = build_twin(args.analysis)
    print(f"[live] MuJoCo twin ready · {len(scene['steps'])} steps · "
          f"streaming on ws://localhost:{args.port}  (open the page + click ● LIVE)")

    async def handler(ws):
        peer = getattr(ws, "remote_address", "?")
        print(f"[live] client connected {peer}")
        try:
            await run(ws, scene, twin, args.analysis, args.fps, args.loop)
        except websockets.ConnectionClosed:
            print("[live] client disconnected")

    async def serve():
        async with websockets.serve(handler, "localhost", args.port, max_size=2 ** 20):
            await asyncio.Future()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
