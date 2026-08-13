# OT-2 kinematic digital twin (MuJoCo)

The physics-twin half of Paper2Protocol, on the **lighter simulator path** (MuJoCo/MJX, not
Omniverse — see `../examples/external/prism_review.html` for why). It replays the *same*
`analysis.json` command ledger the real `opentrons analyze` engine produces and verifies that the
gantry can **physically execute** the run.

It is built for the real research goal: a validation corpus of *many* papers, and eventually an
actual OT-2 in a physical lab. So two properties are non-negotiable and enforced by construction:

1. **Paper-agnostic.** Nothing is hardcoded to any experiment. Deck + labware come entirely from
   the run's ledger, so a new paper's protocol runs with **zero code changes**.
2. **No guessed geometry.** Every coordinate is sourced from a real Opentrons definition. The twin
   *refuses* (raises) rather than approximating a missing well or slot.

## Geometry provenance — exact, nothing assumed

| Geometry | Source | Notes |
|---|---|---|
| Labware wells (x, y, z, depth, shape, diameter/dims) | the labware **definition embedded in each `loadLabware` result** inside `analysis.json` | the ledger is self-describing; wells looked up by name, never by pitch math |
| Deck slot offsets + bounding boxes | the real `ot2_standard` deck definition → `twin/decks/ot2_standard.json` | exported once from `opentrons_shared_data`; regen below |
| Reach envelope | computed from the **actual deck slot extent** (+ a documented pipette over-travel margin) | not an invented number |

The **only** abstraction is the pipette: a rigid Cartesian arm (gantry + nozzle stub). Labware and
deck geometry are exact; the arm is the proxy whose deck-frame motion / collision / reach the twin
validates. Full pipette-and-tip CAD is a documented next step, not a hidden assumption. Labware on a
**module** (which adds a z offset) currently **raises** rather than being silently placed — no guessing.

Regenerate the deck table (needs the opentrons env):
```bash
.venv/bin/python -c "import json; from opentrons_shared_data.deck import load; \
d=load('ot2_standard',3); \
json.dump({'deck':'ot2_standard','slots':{s['id']:{'position':s['position'],'boundingBox':s['boundingBox']} \
for s in d['locations']['orderedSlots']}}, open('twin/decks/ot2_standard.json','w'), indent=2)"
```

## Honest scope — the twin vs the ledger

| Layer | Proves | Here |
|---|---|---|
| **This twin** | motion / collision / reachability | MuJoCo replay of the gantry |
| **Conformance ledger** (`src/paper2protocol/conformance.py`) | dosing / concentrations / units | reconstructed from `commands[]` |

The twin **does not simulate liquid** — every engine, Isaac Sim's PBF fluids included, yields
visually-plausible not metrology-grade liquid; sub-µL dosing accuracy stays with the conformance
ledger. This mirrors PRISM's own admission ("we do not simulate liquid physics").

## What it checks
- **Reachability** — every well target inside the real deck's addressable extent.
- **Collisions** — the pipette nozzle penetrating a labware/deck body (MuJoCo's contact solver).
- **Travel clearance** — min nozzle-to-labware distance while flying between wells (safety margin).

## Run it
```bash
python -m twin.run_twin <analysis.json> [--out anim.mp4] [--report rep.json] [--break]
```

## Validation across papers (abstraction proven)

Same code, different protocols, driven only by each ledger's embedded geometry:

| Run | Deck (from the ledger) | Steps | Verdict |
|---|---|---|---|
| chemotaxis `bundle_live` | slot1 tiprack · slot2 reservoir · slot3 **corning_24**_wellplate | 32 | **FEASIBLE**, 0 collisions, 20.0 mm clearance |
| chemotaxis `bundle_from_pdf` | slot1 **reservoir** · slot2 **tiprack** (swapped) · slot3 **corning_12**_wellplate | 48 | **FEASIBLE**, 0 collisions |

The second run uses a labware (`corning_12_wellplate_6.9ml_flat`) and slot arrangement the twin had
never seen — it built the exact deck from the definitions with no code change. This is the property
the multi-paper replication study depends on.

`--break` (transit height forced below the labware) → **INFEASIBLE, hundreds of nozzle-vs-labware
collisions**: the twin catches a physically impossible plan rather than rubber-stamping it.

## Unified view — physics twin + chemistry gate in one frame

When the ledger sits in a bundle next to `conformance.json` + `ir.json`, the render also loads the
**realized concentrations** (reconstructed from the `commands[]` ledger by `conformance.py`):
- each destination well is tinted by realized concentration (cool → warm);
- a **CHEMISTRY GATE** panel lists per-well v/v, U/mL penicillin, µg/mL streptomycin, and the
  conformance verdict (`PASS 3/3`);
- each dispense caption names the concentration it creates.

The `--break` run makes the thesis concrete: **physics INFEASIBLE while the CHEMISTRY GATE still
reads PASS** — the two gates are independent. A plan can be chemically correct yet physically
impossible, which is exactly why the twin (motion) and the conformance ledger (chemistry) are
complementary, not redundant.

## Result on the chemotaxis run
Deck: slot 1 `opentrons_96_tiprack_300ul` · slot 2 `nest_12_reservoir_15ml` (A1 PenStrep stock,
A2 LB) · slot 3 `corning_24_wellplate_3.4ml_flat`. 32 ledger steps building the 0 / 15 / 25 % v/v
series, fresh tip per transfer → **FEASIBLE**, realized 0 / 1500 / 2500 U/mL PenStrep, conformance
PASS 3/3. Artifacts in `out/`.

## GPU status (Apple M-series, Metal)
- **Rendering — GPU (Metal).** MuJoCo's offscreen renderer uses the Metal-backed GL context.
- **Physics — CPU.** MuJoCo's C solver; for a single OT-2 scene it is effectively instant.
- **MJX on Metal (GPU physics)** — available in principle (`jax-metal`; MJX runs on any XLA target
  incl. Apple Silicon) but experimental/heavy to install and only pays off for *thousands of
  parallel* rollouts (RL / trajectory optimization). Deferred to the parallel-rollout milestone.

## Real OT-2 3D asset (MuJoCo)

The MuJoCo twin can overlay the **official Opentrons OT-2 reference mesh** as a visual chassis:
```bash
python -m twin.run_twin <analysis.json> --chassis --out twin/out/run.mp4
```
- **Asset:** `twin/assets/ot2/ot2_reference_basic.stl` — the official OT-2 Reference Model (Basic)
  from the `Opentrons/ot2` hardware repo (real mm; 1,650 verts). Provenance + sha256 in
  `twin/assets/PROVENANCE.md`; deck-frame alignment in `twin/assets/ot2/alignment.json`.
- **Honest note:** the mesh is a **non-colliding visual chassis** — it never changes a coordinate.
  All functional geometry (slots, wells, collisions) stays exact from the Opentrons definitions. The
  Basic envelope is coarse and true-scale (671 mm tall), so it renders as a subtle context around the
  compact functional gantry frame. A "Detailed" mesh + STEP/DXF exist in the same repo for higher
  fidelity, and extension meshes (tube/tip racks, pipette clamps) are catalogued in `PROVENANCE.md`.

## Isaac Sim backend (WORKING — coexists with MuJoCo)

The photoreal RTX backend is **live on the lab gear-triad** (3× RTX **A6000**, which have RT Cores).
It **cannot run on this Mac** (no macOS/Apple-Silicon Isaac build), so it runs headless in the
`nvcr.io/nvidia/isaac-sim:5.1.0` container on the A6000 box and the frames are pulled back here.

**Cross-validation result (chemotaxis `bundle_live`):** Isaac Sim 5.1 returns the **identical verdict**
to MuJoCo — **FEASIBLE, 0 collisions, 20.0 mm min transit clearance** — because both backends call the
*same* backend-agnostic analytic checks (deck-extent reach, point-to-AABB clearance, tip-vs-box
penetration) over the *same* exact geometry (`deck.py` + the labware defs embedded in the ledger). Two
independent physics engines agreeing by construction is the point: Isaac adds photoreal RTX rendering
of the real OT-2 asset, it does **not** add a second, disagreeing verdict. Output: `out/isaac_report.json`
+ 22 RTX frames → `out/isaac_ot2_chemotaxis.mp4`.

### How to run it on the gear-triad (Isaac has no macOS build)

Isaac Sim runs headless in the `isaac-sim:5.1.0` container on the triad's RTX A6000. The twin code
and the real OT-2 asset are already staged on the triad at **`~/p2p-twin`**, so running is just:

```bash
ssh gear-triad                                    # (1) get on the box
export PATH=$HOME/.local/bin:$PATH                # (2) so the mp4 encoder is found
bash ~/p2p-twin/run_isaac.sh                      # (3) run — defaults: GPU 2, 240 frames, 1280x720
#   ./run_isaac.sh [GPU] [MAX_FRAMES] [WIDTH] [HEIGHT] [FPS]
#   bash ~/p2p-twin/run_isaac.sh 1 400            # GPU 1, extra-smooth motion
```

It prints the GPU load (pick a free one — GPU 0 is often busy), renders, prints the
FEASIBLE/INFEASIBLE report, **encodes the mp4 on the triad** (`~/p2p-twin/out/isaac_ot2.mp4`), and
prints the exact one-line `scp` to pull that single file to your Mac, e.g.:

```bash
# run this on your Mac afterwards:
scp gear-triad:~/p2p-twin/out/isaac_ot2.mp4 ~/Downloads/ && open ~/Downloads/isaac_ot2.mp4
```

Run a **different protocol**: `LEDGER=/workspace/ledgers/<name>/analysis.json bash ~/p2p-twin/run_isaac.sh`
(the path is inside the container; put the ledger under `~/p2p-twin/ledgers/<name>/` first).

**Gotchas the script already handles:** the `runheadless.sh` entrypoint trap, `--ipc/--network=host`,
the EULA prompt, the uid-1234 output-permission issue (wipes `out/` fresh each run), and clearing a
leftover `p2p-isaac-run` container so a re-run never fails on a name collision.

### One command from your Mac (does the sync + run + pull + open for you)

If you'd rather not ssh in — this syncs the latest code, runs on the triad, pulls the video, and
opens it locally:

```bash
./twin/run_isaac_remote.sh                        # defaults: chemotaxis, GPU 2, 240 frames
./twin/run_isaac_remote.sh <analysis.json> <gpu> <max_frames>
```
`isaac_twin.py` builds a USD stage from the exact geometry (deck slab, labware boxes, well cylinders
tinted by realized concentration, the real OT-2 chassis mesh, a movable pipette Xform), renders every
6th waypoint with `omni.replicator` + `BasicWriter`, and runs the shared reach/collision/clearance
checks — writing the report to disk **before** `SimulationApp.close()` (which can hang headless).

**Container gotchas (all solved, recorded):**
- Image ENTRYPOINT is `runheadless.sh` (a streaming server) → override with `--entrypoint /isaac-sim/python.sh`.
- Needs a big `/dev/shm`: use **`--shm-size=2g --network=host`** (else libomniclient SIGABRTs on
  the 64 MB default). Do **not** use `--ipc=host` on the shared box — it collides on carb's named
  shared memory with other users' Isaac runs (`Failed to create shared memory carb-RStringInternals`).
- **Isaac 5.x runs as `uid=1234(isaac-sim)`, not root** → host mounts it writes to (the output dir)
  must be world-writable (`chmod 777`). This is the #1 5.x-vs-4.5 behavior change.
- **Do NOT bind-mount host cache dirs** onto `/isaac-sim/kit/cache` — the uid-1234 process can't write
  them and it silently breaks `rtx::shaderdb` (render hangs). Let Isaac use its in-container cache.
- **Version matters:** Isaac **4.5** segfaults on this box (driver 580 / CUDA 13, built for the ~570 era);
  Isaac **5.1**'s validated Linux driver is 580.65.06 — the 580 branch is exactly right. It was a
  version mismatch, not a hardware/driver fault.

## Files
- `deck.py` — real deck loader + exact `LabwareGeom` view over an Opentrons definition.
- `ot2_model.py` — builds the MJCF from exact geometry (labware boxes, wells, gantry, nozzle).
- `driver.py` — parses any ledger, replays it, runs the checks, renders the overlay.
- `chem.py` — loads the conformance-ledger chemistry for the unified overlay.
- `decks/ot2_standard.json` — the real OT-2 deck slot table.
- `run_twin.py` — CLI.

## Next
- Fold the engine into the `dts-twin` pillar (this contributes the OT-2 asset + conformance gate).
- Grow the multi-paper replication corpus (each paper → full pipeline → twin) as the paper's evidence.
- Model modules (temp/thermocycler/heater-shaker) so module-based protocols run without raising.
- Genesis prototype for a co-simulated liquid leg (rigid + SPH) — watch-item.
