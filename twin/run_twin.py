"""CLI: replay an Opentrons analysis.json through the OT-2 kinematic twin.

    python -m twin.run_twin <analysis.json> [--out anim.mp4] [--report rep.json]
                            [--break] [--fps 30]

--break lowers the transit height on purpose so the collision detector fires —
a demonstration that the twin catches a physically INFEASIBLE plan, not just
rubber-stamps a good one.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .driver import run


def main() -> None:
    ap = argparse.ArgumentParser(description="OT-2 kinematic digital twin")
    ap.add_argument("analysis", help="Opentrons analysis.json (the commands[] ledger)")
    ap.add_argument("--out", default="twin_run.mp4")
    ap.add_argument("--report", default="twin_report.json")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--break", dest="break_mode", action="store_true",
                    help="force an infeasible (too-low) transit to prove collision detection")
    ap.add_argument("--chassis", action="store_true",
                    help="overlay the real Opentrons OT-2 reference mesh (visual chassis)")
    args = ap.parse_args()

    rep = run(args.analysis, args.out, args.report, fps=args.fps,
              break_mode=args.break_mode, chassis=args.chassis)

    print("=" * 62)
    print(f" OT-2 TWIN  |  {rep.n_steps} ledger steps  |  {rep.frames} frames "
          f"({'Metal GPU' if rep.gpu_render else 'no-GPU'})")
    print("=" * 62)
    print(f" deck: " + ", ".join(f"slot {s}={n}" for s, n in rep.deck_layout.items()))
    print(f" geometry: {rep.geometry_source}")
    print(f" reachable (all targets in envelope) : {rep.reachable_all}")
    print(f" collisions                          : {len(rep.collisions)}")
    if rep.collisions:
        for c in rep.collisions[:5]:
            print(f"     - {c['at']}: hit {c['body']} (pen {c['penetration_mm']} mm)")
    print(f" min transit clearance               : {rep.min_transit_clearance_mm} mm"
          f"  (@ {rep.min_clearance_at})")
    print(f" total gantry travel                 : {rep.total_travel_mm} mm")
    print(f" VERDICT                             : {rep.verdict}")
    print("=" * 62)
    print(f" animation -> {args.out}")
    print(f" report    -> {args.report}")


if __name__ == "__main__":
    main()
