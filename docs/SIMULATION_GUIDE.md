# Paper2Protocol — Simulation & Twin Guide

*How the system simulates and verifies a protocol: the three simulation layers, how each works, how
Isaac Sim differs from MuJoCo and the lighter engines, the exact run commands, and the iteration
loops. Companion to `SYSTEM_DESIGN.md` (the formal math/methods) and `../twin/README.md`.*

---

## 0. Three simulation layers — what each one proves

Paper2Protocol does **not** rely on a single simulator. It stacks three, each sound for a different
question. This separation is the whole design: no one layer is asked to prove something it can't.

| # | Layer | Question it answers | Engine | Where it runs |
|---|---|---|---|---|
| **1** | **`opentrons analyze`** (software sim / acceptance oracle) | Is the protocol API-legal, and does the realized **chemistry** match the paper? | Opentrons 8.8.2 analysis engine (deterministic) | pipeline venv (any host) |
| **2** | **MuJoCo twin** (kinematic physics) | Can the gantry **physically** run it? reach / collision / clearance | MuJoCo 3.11 (CPU physics + Metal/GL render) | anywhere — incl. this Mac |
| **3** | **Isaac Sim twin** (photoreal physics) | Same physical question, at **photoreal RTX fidelity** with the real OT-2 asset | Isaac Sim 4.5 (USD + PhysX + RTX) | gear-triad A6000 (Linux) |

**Orthogonality (the load-bearing idea).** Layer 1 proves *chemistry, not physics*. Layers 2 and 3
prove *physics, not chemistry*. A plan can pass one and fail another — our `--break` run is physically
**INFEASIBLE** while the chemistry gate still reads **PASS**. That is why they are complementary, not
redundant, and why the **acceptance gate is deterministic Python over Layer 1**, never an LLM (PRISM's
Validator is an LLM; ours is not — see the ICLR 2025 self-verification result in `SYSTEM_DESIGN.md`).

**Layers 2 and 3 are two *backends* of the same twin.** They share the exact same verdict math
(reach = deck-extent; clearance = point-to-AABB; collision = tip-vs-box penetration), so **they agree
by construction**. The difference is only the renderer and asset fidelity. MuJoCo is the fast,
runs-everywhere backend; Isaac is the photoreal, sim-to-real-capable backend.

---

## 1. How each layer works

### 1.1 `opentrons analyze` — the acceptance oracle (Layer 1)
The same engine the physical robot runs, on virtual hardware. It ingests `protocol.py` and emits
`analysis.json` with a `commands[]` stream (every `pickUpTip / aspirate / dispense / dropTip` with
labware, well, volume) **and the full labware definitions inline**. Two checks ride on it:
- **Static + API-legality** — labware allow-list, pipette min/max per step, tip-rack presence, etc.
- **Command-ledger conformance** (`conformance.py`) — reconstruct realized v/v and concentrations
  from `commands[]` (`c_u(w) = C_uˢᵗᵒᶜᵏ · Vstock/Vtotal`) and check against the IR within tolerance.
It is fully deterministic — the acceptance authority. It does **not** model liquid physics or motion.

### 1.2 MuJoCo twin — kinematic physics, portable (Layer 2)
- **Model:** a procedurally-built MJCF — a 3-axis Cartesian gantry (Y bridge → X carriage → Z pipette)
  over a deck of labware boxes. Geometry is **exact**: deck slots from the real `ot2_standard` deck
  def, every well from the labware definition embedded in the ledger. Nothing hand-typed.
- **Physics:** MuJoCo's soft-convex contact solver (Todorov 2012/2014), used in a **restricted
  kinematic mode** — gravity off, position playback (`set qpos`; `mj_forward`), reading collision
  detection. We don't integrate dynamics; we sample kinematic waypoints.
- **Render:** offscreen via the Metal-backed GL context (the Apple M-series GPU). ~17 s for the whole
  chemotaxis run, 887 frames.
- **Real asset:** the official Opentrons OT-2 reference mesh can be overlaid as a non-colliding
  visual chassis (`--chassis`).

### 1.3 Isaac Sim twin — photoreal physics on the A6000 (Layer 3)
- **Stack:** NVIDIA **Omniverse Kit** → a **USD** scene graph → **PhysX 5** physics → the **RTX**
  renderer (hardware ray tracing). Runs headless inside the `nvcr.io/nvidia/isaac-sim:4.5.0`
  container on a gear-triad **RTX A6000** (RT Cores required — this is why A100/H100 can't run it).
- **Our backend (`twin/isaac_twin.py`):** builds the *same* exact deck + labware geometry as a USD
  stage (mm units), tints destination wells by the conformance-ledger concentration, loads the real
  OT-2 STL as a USD mesh, and replays the ledger waypoints — computing the **same analytic
  reach/collision/clearance verdicts** as MuJoCo, and rendering photoreal RTX frames via Replicator.
- **Why it's heavier:** photoreal ray tracing + USD + a 15 GB container + a ~4-min cold start (shader
  compile + extension sync, then cached). The payoff is photoreal frames, physically-based sensors,
  and a genuine sim-to-real / RL path (Isaac Lab) that the lighter engines don't offer out of the box.

---

## 2. Isaac Sim vs MuJoCo vs the lighter engines

The comparison that drove our engine choice (grounded in the verified literature — `RESEARCH_MATERIALS.md`, LIT-4):

| Engine | Physics | Native liquid | Render | GPU needed | Cold start | Best for |
|---|---|---|---|---|---|---|
| **Isaac Sim / Lab** | PhysX 5 | PhysX PBF/FleX fluids | **Photoreal RTX** | **RT-Core RTX only** (A6000 ✓, A100/H100 ✗) | ~4 min (cached after) | photoreal twin, sensor sim, sim-to-real, RL |
| **MuJoCo / MJX** | soft-convex, best-in-class contact | none (analytical layer) | basic (GL) | any / CPU / Apple Metal | instant | fast contact-rich validation, portability, RL (MJX) |
| **Genesis** | unified multi-physics | **rigid + SPH in one solver** | good | any CUDA/ROCm/Metal | medium | co-simulating robot **+ liquid** (watch-item) |
| **SAPIEN / ManiSkill** | PhysX | none | strong, headless | Vulkan, driver >470 | medium | GPU-parallel manipulation, CI |
| **PyBullet** | Bullet | none | software | none | instant | zero-GPU baseline / laptop |

**How Isaac Sim differs fundamentally.** MuJoCo is a *physics library* you drive from Python — one
process, one scene, deterministic, no external services. Isaac Sim is an *application platform*
(Omniverse Kit): a USD stage graph, a plugin/extension system (it syncs extension registries on first
run), PhysX 5, and a real-time **RTX ray-traced** renderer with physically-based materials and
sensors. That buys photorealism and a sim-to-real ecosystem (Isaac Lab: thousands of GPU-parallel RL
envs, domain randomization) — at the cost of heavyweight setup (RT-Core GPU, Linux, big container,
shader compile, `--ipc=host --network=host`). For **our** job — verifying an aqueous-handling gantry —
the *verdict* is identical across backends (the geometry math is exact and engine-independent); Isaac
earns its place as the **photoreal, presentation-and-sim-to-real** backend, MuJoCo as the **fast,
everywhere** one.

**Why not just Isaac for everything?** Because Isaac can't run on the dev Mac (no Apple-Silicon build)
and its cold start is minutes; MuJoCo gives an instant local loop. And critically — **no engine, Isaac
included, gives metrology-grade liquid** (Isaac's PBF fluids are visually plausible, not sub-µL
accurate). So dosing accuracy stays with Layer 1's conformance ledger regardless of engine.

---

## 3. The runs — exact commands

### 3.1 Layer 1 — pipeline (ingest → validated protocol)
```bash
cd paper2protocol
uv run paper2protocol run "<paper.pdf>"          # → IR → codegen → loop → bundle (analysis.json)
uv run paper2protocol run "<paper.pdf>" --live   # live LLM
```

### 3.2 Layer 2 — MuJoCo twin (this Mac)
```bash
twin/.venv/bin/python -m twin.run_twin <analysis.json> \
    --out twin/out/run.mp4 --report twin/out/report.json
twin/.venv/bin/python -m twin.run_twin <analysis.json> --chassis   # + real OT-2 mesh
twin/.venv/bin/python -m twin.run_twin <analysis.json> --break     # prove collision detection
```

### 3.3 Layer 3 — Isaac Sim twin (gear-triad A6000, via SSH)
Known-good container invocation (see the gotchas in §4.3):
```bash
ssh gear-triad
C=~/docker/isaac-sim
docker run --rm --runtime nvidia --gpus '"device=1"' \
  --ipc=host --network=host \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y \
  -v $C/cache/kit:/isaac-sim/kit/cache -v $C/cache/ov:/root/.cache/ov \
  -v $C/cache/glcache:/root/.cache/nvidia/GLCache -v $C/cache/computecache:/root/.nv/ComputeCache \
  -v /home/sandesh/p2p-twin:/workspace -w /isaac-sim \
  nvcr.io/nvidia/isaac-sim:4.5.0 \
  ./python.sh /workspace/twin/isaac_twin.py \
     --ledger /workspace/ledgers/chemotaxis_bundle_live/analysis.json \
     --chassis --out /workspace/out/isaac --report /workspace/out/isaac_report.json
```
Outputs land in `~/p2p-twin/out/` (report JSON + RGB frames) — check those, not the exit code (§4.3).

---

## 4. The iteration loops

### 4.1 The protocol validate→repair loop (Layer 1) — the science loop
`loop.py` is the deterministic gate. Per iteration: run static checks → `opentrons analyze` →
conformance. **CONVERGED** iff static = 0 faults AND analyze `ok`/`errors:[]` AND all IR assertions
realized. Anti-oscillation tracks an *error signature* and reseeds on recurrence; **hard cap = 5**.
Outcomes: CONVERGED (bundle), **BLOCKED** (cap hit → honest partial artifact, e.g. the Piper betle
paper), **REFUSED** (`dilution=null` when no automatable aqueous step). The LLM proposes/repairs; it
never declares convergence.

### 4.2 The twin verify loop (Layers 2 & 3) — the physics loop
Replay the ledger → per waypoint compute reach (deck extent), collision (tip-vs-box penetration),
clearance (point-to-AABB) → **FEASIBLE** (all reachable, no collisions) or **INFEASIBLE**. Same math
in both backends, so MuJoCo and Isaac must agree — that agreement is itself a cross-check.

### 4.3 The Isaac dev-iteration loop (how we build Layer 3 on gear-triad)
Because Isaac can't run on the Mac, the loop is: **author locally → `scp` to `~/p2p-twin` → run in the
container over SSH → inspect the output files → fix → rerun.** Hard-won gotchas, all recorded:
- **Must** pass `--ipc=host --network=host`, or it SIGABRTs at ~1.4 s in `libomniclient` (shared-mem
  + localhost resolution).
- **Mount the 8 cache volumes** under `~/docker/isaac-sim` so the ~4-min first-run shader compile +
  extension sync (≈800 files) is one-time.
- **stdout is block-buffered** in the container → `sys.stdout.reconfigure(line_buffering=True)`.
- **`SimulationApp.close()` can hang headless** → write the report + frames to disk **before** close,
  run with a timeout, and **verify by the output files**, not the exit code.
- Use **GPU 1 or 2** (`--gpus '"device=1"'`) — GPU 0 carries a ~37 GB workload.
- Verification target: `isaac_report.json` must match MuJoCo's verdict (FEASIBLE, 0 collisions) on the
  chemotaxis ledger, and the RGB frames must show the deck/labware/pipette correctly.

---

## 5. Cheat-sheet

| Goal | Command |
|---|---|
| Validate a paper → protocol | `uv run paper2protocol run <pdf>` |
| Fast physics twin (local) | `twin/.venv/bin/python -m twin.run_twin <ledger>` |
| + real OT-2 chassis | `... --chassis` |
| Prove it catches bad plans | `... --break` |
| Photoreal Isaac twin | SSH gear-triad → the `docker run … isaac_twin.py` in §3.3 |
| Deck geometry (exact) | `twin/decks/ot2_standard.json` + labware defs in each ledger |
| Asset provenance | `twin/assets/PROVENANCE.md` |

**Environments:** pipeline = Python 3.10.20 (`.venv`, opentrons 8.8.2); MuJoCo twin = Python 3.11.15
(`twin/.venv`, mujoco 3.11); Isaac = `nvcr.io/nvidia/isaac-sim:4.5.0` on gear-triad (Ubuntu 22.04,
driver 580.159, 3× RTX A6000).
