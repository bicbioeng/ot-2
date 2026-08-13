# Paper2Protocol — System Design, Methods, Mathematics & Materials

*A scientist's master documentation of the system: the closed-loop design, the mathematics and
physics behind each gate, the paper corpus tested, the equipment and software, the literature the
design stands on, and how to reproduce everything. Compiled 2026-08-05.*

**Companion documents** (this file is the master; these hold the detail):
- `examples/external/RESEARCH_MATERIALS.md` — the full annotated bibliography (37 sources) + PRISM teardown.
- `examples/external/literature_verified.json` — raw verified literature (per-entry web-check notes).
- `examples/external/prism_review.html` — advisor-facing PRISM vs Paper2Protocol review.
- `twin/README.md` — the digital-twin engine, geometry provenance, and run instructions.

Every version, spec, and coordinate in this document is sourced from the real environment or a real
definition — nothing is assumed or approximated. Where a value is a design choice (e.g. a tolerance),
it is labelled as such.

---

## 1. Abstract

Paper2Protocol ingests a scientific-paper PDF and produces a **validated, dry-runnable Opentrons OT-2
protocol** for the aqueous liquid-handling slice of the paper's method (a dilution / concentration
series). A generator LLM writes the protocol; a **deterministic, non-LLM gate** (`loop.py`) drives a
validate→repair loop whose sole acceptance authority is the real `opentrons analyze` engine plus
static analysis plus a command-ledger conformance check. The system emits one of three **honest
outcomes**: CONVERGED (a verified protocol + artifact bundle), BLOCKED (non-convergence within a hard
cap), or REFUSED (no automatable aqueous step — `dilution=null`). A separate **kinematic digital twin**
(MuJoCo) replays the resulting command ledger to verify the gantry can *physically* execute it
(reach / collision / clearance). The two validation layers are **orthogonal**: the conformance ledger
proves chemistry (realized concentrations, units) but not physics; the twin proves physics but not
chemistry. Neither is an LLM.

---

## 2. Problem statement & thesis

Turning a paper's methods into a runnable protocol is an LLM-generation problem (OpentronsAI,
Coscientist, ProtoCode already do generation), but generation alone is unsound: LLM self-verification
collapses on planning-shaped tasks (Stechly & Kambhampati, ICLR 2025; Huang et al., ICLR 2024). The
contribution here is the **closed, deterministically-gated loop with honest automation partitioning**,
and a **twin** that adds physical-executability checking the chemistry gate cannot do.

> **Thesis.** A generator LLM compiles a schema-validated Intermediate Representation into an
> Opentrons `.py`; a deterministic gate accepts it *only* when the real analyze engine returns
> `ok`, static rules pass, and a command-ledger conformance check reproduces the intended chemistry;
> a physics twin then proves the gantry can execute it. The LLM proposes and repairs; it never
> adjudicates correctness.

**Orthogonal validation (the central design principle).**

| | proves | cannot prove |
|---|---|---|
| Conformance ledger (`conformance.py`) | chemistry: realized v/v, concentrations, units | physical executability |
| Digital twin (`twin/`) | physics: reach, collision, clearance | dosing accuracy / chemistry |

PRISM (arXiv:2601.05356) validates the physics half via an Omniverse twin but "does not simulate
liquid physics, chemical reactions, or biological processes" and defers science to human review;
Paper2Protocol mechanizes the chemistry half and adds a lighter physics twin. The ideal system is
both, behind a single non-LLM gate.

---

## 3. System architecture & pipeline

```
PDF ──▶ (1) extract methods text (PyMuPDF → pdfplumber fallback)
     ──▶ (2) LLM extraction → typed IR (dilution targets, stock_conc+units,
             labware-from-allowlist, gates, off_deck, open_clarifications)
     ──▶ (3) automation triage: ROBOT / GATE / OFF_DECK
     ──▶ (4) codegen: IR → protocol.py (generator LLM, grounded on an allowlist)
     ──▶ (5) VALIDATE→REPAIR LOOP  — loop.py is the deterministic acceptance authority
             ├ static_checks.py   (AST + allowlist rules; no sim spent on obvious faults)
             ├ opentrons analyze   (the real engine, on virtual hardware)
             └ conformance.py      (reconstruct realized chemistry from commands[])
     ──▶ (6) artifact bundle (protocol.py, ir.json, analysis.json, conformance.json,
             run_log.json, signoff.md, MANIFEST.json)
     ──▶ (7) digital twin (twin/): replay commands[] → reach/collision/clearance + render
     ──▶ (8) dispatch: OT2Client (Runs API) / VirtualOT2
```

**The deterministic gate.** `loop.py` declares CONVERGED iff: static findings = 0 AND
`analyze.result == ok` with `errors == []` under `--check` AND every IR assertion is realized by
conformance. Anti-oscillation tracks an *error signature* (errorType + normalized line + code) and
reseeds on recurrence; the hard cap is **5 iterations**. Non-convergence → a BLOCKED artifact
(last `.py`, full iteration log, residual errors). No LLM can declare CONVERGED.

**Three honest outcomes** (all designed; §6 shows which are demonstrated on the corpus):
- **CONVERGED** — verified protocol + bundle.
- **BLOCKED** — did not reach a clean pass within the cap; the partial ledger is emitted, not faked.
- **REFUSED** — extraction found no automatable aqueous step → `dilution=null` (never invented).

---

## 4. Mathematical formalism

### 4.1 Intermediate Representation (IR)
The IR is a typed spec: `dilution.targets = [(well, vv)]` (vv = volume fraction of stock in the well),
`stock_source.stock_conc = {unit: value}` (units explicit and preserved), `dest_labware`,
`total_vol_ul`, `tolerance_vv`, plus `gates`, `off_deck`, and `open_clarifications`. Concentrations
carry **units as first-class keys** (e.g. `penicillin_U_per_mL`, `streptomycin_ug_per_mL`) so a
dimensionless percent can never silently stand in for a concentration.

### 4.2 Command-ledger conformance
Operate on the analyze `commands[]` stream, never on the source text (which is trivially
reward-hackable). For each destination well *w*, partition the dispensed volume by source:

$$V_{\text{stock}}(w)=\!\!\sum_{\text{disp}\to w \text{ from stock}}\!\!v,\qquad
  V_{\text{dil}}(w)=\!\!\sum_{\text{disp}\to w \text{ from diluent}}\!\!v,\qquad
  V_{\text{tot}}(w)=V_{\text{stock}}(w)+V_{\text{dil}}(w).$$

**Realized volume fraction** and **realized final concentration** (unit-preserving) are

$$r(w)=\frac{V_{\text{stock}}(w)}{V_{\text{tot}}(w)},\qquad
  c_u(w)=C^{\text{stock}}_u\cdot r(w)\ \ \forall u\in\text{stock\_conc}.$$

**Conformance gate:** well *w* passes iff units match (dimensional check) **and**
$|r(w)-\text{target}(w)|\le \tau$, with default $\tau=0.01$ (`tolerance_vv`, a design choice).

*Worked example — chemotaxis (`bundle_live`), verified from the ledger:*
stock $C_{\text{pen}}=10000$ U/mL, $C_{\text{strep}}=10000$ µg/mL, $V_{\text{tot}}=200$ µL.

| well | $V_{\text{stock}}$ | $r(w)$ | target | pen (U/mL) | strep (µg/mL) | pass |
|---|---|---|---|---|---|---|
| A1 | 0 µL | 0.000 | 0.00 | 0 | 0 | ✓ |
| A2 | 30 µL | 0.150 | 0.15 | 1500 | 1500 | ✓ |
| A3 | 50 µL | 0.250 | 0.25 | 2500 | 2500 | ✓ |

→ conformance PASS 3/3, `|r−target| = 0 ≤ 0.01`.

### 4.3 Replication-percent metric (RP%)
For the multi-paper validation study we report a **vector**, never a lone number, following OSC 2015
(a success rule must be declared) and Errington 2021 (could-not-attempt must be separated from
attempted-and-failed). Let the IR assertions *A* partition into **R** (realized), **B**
(honest-BLOCKED — flagged unrealizable) and **D** (silently dropped; target = 0), with attemptable
scope $A^\*=A\setminus B$.

$$
r_a=\frac{|R|}{|A^\*|},\quad
r_c=\frac{|\{p\in P^\*: \text{dim\_ok}(p)\wedge \tfrac{|\hat c(p)-c_{\text{tgt}}(p)|}{c_{\text{tgt}}(p)}\le\tau(\text{class},\text{vol})\}|}{|P^\*|},\quad
r_g=\frac{|\{i\in I(\text{class}):\text{satisfied}(i)\}|}{|I(\text{class})|},\quad
h=1-\frac{|D|}{|A|}.
$$

$$\boxed{\ \text{RP\%}=100\cdot h\cdot(w_a r_a+w_c r_c+w_g r_g),\quad w_a{+}w_c{+}w_g=1\ }$$

Defaults $w_a{=}0.40, w_c{=}0.30, w_g{=}0.30$ (Baker 2016: under-specified method is the dominant
fixable cause, so realization is weighted highest). `dim_ok` is a **hard veto** — any unit/dimensional
mismatch, or any unsatisfied safety-critical invariant in $I(\text{class})$, caps RP% (→ 0 for the
affected leg). $\tau$ is the **measured, volume-dependent** liquid-handling CV (§5.4): ≈0.15–1.5% for
larger volumes, widening to 2–8% sub-µL (Schuster et al. 2024). **Mandatory co-report:**
$\text{BLOCKED\%}=100|B|/|A|$, $\text{SILENT\text{-}DROP\%}=100|D|/|A|$. RP% is never shown without
BLOCKED%. *Worked:* |A|=100, B=15, D=0 ⇒ RP% = 100·(0.40·0.894+0.30·0.900+0.30·0.917) = **90.3%**,
report (RP 90.3, BLOCKED 15, SILENT-DROP 0).

### 4.4 Command-Ledger Conformance Rate (the review metric)
The fraction of emitted commands that (a) draw from the allowed-operation set, (b) satisfy declared
preconditions / resource state, and (c) preserve the reference step-DAG ordering — computed by a
deterministic, LLM-external checker that gates dispatch. Reported alongside **ledger coverage**
(comprehensiveness of the allowed-op set) to avoid the "homogeneous test suite inflates the pass
rate" failure (Ma et al., NeurIPS 2025).

---

## 5. The digital twin — physics & geometry

### 5.1 Geometry model (exact; nothing approximated)
Deck frame: $x$ left→right, $y$ front→back, $z$ up, in mm. Sources of truth:
- **Labware** — the definition embedded in each `analysis.json` `loadLabware` **result.definition**
  (exact per-well `x,y,z,depth,shape,diameter|xDimension/yDimension`). Wells are looked up by name.
- **Deck slots** — the real `ot2_standard` deck definition (`twin/decks/ot2_standard.json`,
  exported from `opentrons_shared_data`): slot position + bounding box.

Well center and rim height in deck frame (slot origin $s$, labware corner offset $c$):

$$p_{xy}(w)=s_{xy}+c_{xy}+\text{well}_{xy}(w),\qquad
  z_{\text{rim}}(w)=s_z+c_z+\text{well}.z(w)+\text{well}.depth(w).$$

(Verified: Corning 24-well A1 `z`=2.87 + `depth`=17.4 = 20.27 = `zDimension` — the rim equals the
labware top.) The no-liquid twin descends to $z_{\text{rim}}+\delta$, $\delta=2$ mm standoff.

### 5.2 Gantry forward kinematics & calibration
The OT-2 gantry is three orthogonal prismatic joints $(q_x,q_y,q_z)$ (Y bridge → X carriage →
Z pipette). Because the slides are axis-aligned, the nozzle-tip world position is the exact linear map

$$\mathbf{p}_{\text{tip}}(q)=\mathbf{p}_0+(q_x,q_y,q_z),$$

where $\mathbf{p}_0$ is **calibrated** as the tip-site world position at $q=0$ (read from MuJoCo after
`mj_forward`). To place the tip at target $\mathbf{t}$: $q=\mathbf{t}-\mathbf{p}_0$. Travel height is
auto-derived per protocol: $z_{\text{travel}}=\max_i(\text{zDimension}_i)+20$ mm, guaranteeing the
nozzle clears the tallest labware during lateral moves for *any* deck.

### 5.3 Contact model, reach, clearance
The twin uses **MuJoCo 3.11.0** in a restricted kinematic mode: gravity disabled, position playback
(`set qpos`; `mj_forward`), reading MuJoCo's collision detection (`mj_collision` within
`mj_fwdPosition`). We do **not** integrate dynamics — trajectories are sampled kinematic waypoints.
MuJoCo's contact solver is the soft, convex, analytically-invertible model (Todorov et al. 2012;
Todorov 2014). Signals:
- **Collision** — a contact pair involving the nozzle geom and a structural geom (`lw_*`, `deck`,
  `floor`) with signed distance $d<-0.05$ mm (penetration). Only the nozzle stub collides; the shaft
  and gantry are visual (non-colliding).
- **Reach** — target $(x,y)$ must lie within the real deck extent $\pm 15$ mm pipette over-travel:
  $x\in[x_{\min}-15,\,x_{\max}+15]$, likewise $y$; $x_{\min\dots}$ from the actual slot boxes.
- **Travel clearance** — minimum nozzle-to-labware distance while at travel height, using the
  point-to-AABB Euclidean distance $d(\mathbf p,\text{box})=\lVert\max(|\mathbf p-\mathbf c|-\mathbf h,\,0)\rVert_2$
  minimized over labware boxes $(\mathbf c,\mathbf h)$ (center, half-extent from exact dims).

Verdict: **INFEASIBLE** if any collision or any unreachable target; else **FEASIBLE**. The
`--break` mode forces $z_{\text{travel}}$ below the labware to confirm the detector fires (it does:
hundreds of nozzle-vs-tiprack collisions), proving the twin catches impossible plans.

### 5.4 Scope boundary — why no liquid physics
Every GPU physics engine, including Isaac Sim's position-based fluids (Macklin & Müller 2013;
Macklin et al. 2014 / FleX), yields **visually-plausible, not metrology-grade** liquid; none certifies
sub-µL dosing without real-hardware calibration, and OT-2 specifics (tip press-fit, aspiration
air-gap, capillary/meniscus) are out-of-the-box in no engine. Empirically, automated liquid-handling
CV is ≈0.15–1.5% for larger volumes rising to 2–8% near 1 µL (Schuster et al., SLAS Technology 2024).
**Therefore dosing accuracy stays with the conformance ledger; the twin is scoped to
motion / collision / reachability.** This is the same boundary PRISM draws for its twin.

### 5.5 Rendering
Offscreen rendering via MuJoCo's Metal-backed GL context (the Apple M-series GPU). A per-frame PIL
overlay draws the action caption and the **CHEMISTRY GATE** panel (realized concentrations from
`conformance.py`), tinting each destination well by concentration — unifying physics and chemistry in
one frame. Physics runs on CPU (instant for one scene); GPU-parallel physics (MJX on Metal) is a
future milestone for thousands of parallel rollouts, not single-run replay.

---

## 6. Materials — paper corpus tested

| Paper (assay) | Ingest → outcome | Notes |
|---|---|---|
| *E. coli* negative chemotaxis, PenStrep repellent (`chemotaxis_penstrep`) | **CONVERGED** (manual IR + PDF-ingested variant) | 0/15/25 % v/v series; conformance PASS 3/3; realized 0/1500/2500 U/mL |
| Piper betle extract, broth microdilution + MTT (`plos_0146349`) | **BLOCKED** | valid 8-step 2-fold serial dilution (100 mg/mL) extracted; loop did not reach a clean pass within cap 5 → honest BLOCKED artifact with partial ledger |
| `plos_0263359`, `plos_0318135` (MIC assays) | in corpus, not yet run | reserved for the replication study |

**REFUSAL** (`dilution=null`) is a designed outcome (extraction refuses to invent a series when the
paper has no automatable aqueous step); CONVERGED and BLOCKED are demonstrated empirically above.

**Twin validation across decks (abstraction proven, zero code changes):**

| Run | deck (from the ledger) | steps | twin verdict |
|---|---|---|---|
| chemotaxis `bundle_live` | tiprack · reservoir · **corning_24**_wellplate | 32 | **FEASIBLE**, 0 collisions, 20.0 mm clearance |
| chemotaxis `bundle_from_pdf` | reservoir · tiprack (swapped) · **corning_12**_wellplate | 48 | **FEASIBLE**, 0 collisions |

Artifacts: `twin/out/*.mp4` (+ `_BROKEN`), per-run reports, stills.

---

## 7. Equipment / Bill of materials

### 7.1 Wet-lab (Opentrons OT-2) — specs from official vendor docs
- **OT-2 robot** — 11-slot deck + trash, 2 pipette mounts (robot ≈ $6,500; full setup "from $10,000").
- **GEN2 pipettes** — P20 Single (1–20 µL; ±15% at 1 µL), P300 Single (20–300 µL), P1000 Single
  (100–1000 µL; ±0.7% at 1000). 8-channel only in P20/P300 (no P1000 multi). → **1 µL floor**.
- **Temperature Module GEN2** (4–95 °C, interchangeable Al blocks), **Thermocycler GEN2** (block
  4–99 °C, lid → 110 °C; occupies slots 7/8/10/11), **Heater-Shaker** (37–95 °C, 200–3000 rpm).
- **Consumables** — 20/300/1000 µL tip racks, 12-column reservoirs, SBS 96/384 plates, tube racks.

### 7.2 Digital-twin compute (lighter path; **not** Omniverse)
Decisive verified constraint (NVIDIA Isaac Sim requirements, verbatim): *"GPUs without RT Cores
(A100, H100) are not supported."* If only datacenter GPUs are available, the twin **must** use
MJX / Genesis / SAPIEN / PyBullet.

| Tier | Engine | GPU / compute |
|---|---|---|
| Minimum | PyBullet / MJX-CPU | none; 4-core, 16–32 GB RAM |
| Recommended | MuJoCo **MJX** / Genesis / SAPIEN | consumer RTX 4070Ti–5080, 12–16 GB VRAM (no RT-Cores) |
| Research-grade | Isaac Sim/Lab **or** MJX-Warp/Genesis @ datacenter | RTX 4080→PRO 6000 (Isaac) *or* A100/H100/L40S (MJX only) |

### 7.3 Development / validation machine (this build)
**Apple M1 Pro, Metal 4, macOS 27.0 (arm64)** — used for all twin renders (Metal GPU) reported here.

---

## 8. Software dependencies (exact, from the live environments)

**Pipeline environment** — Python 3.10.20 (pinned to the OT-2 robot's CPython 3.10):

| package | version | role |
|---|---|---|
| opentrons / opentrons-shared-data | **8.8.2** | analyze engine (the acceptance oracle) + labware/deck defs |
| google-genai | 2.16.0 | generator/extractor (Gemini) |
| openai | 2.53.0 | generator/extractor (GPT) |
| anthropic | 0.120.2 | generator/extractor (Claude) |
| PyMuPDF (fitz) | 1.28.0 | primary PDF text extraction |
| pdfplumber | 0.11.10 | fallback PDF extraction |
| fastapi / uvicorn | 0.141.1 / 0.52.1 | web GUI |
| click | 8.4.2 | CLI |
| jsonschema | 4.17.3 | IR schema validation |
| pydantic | 2.13.4 | typed models |
| numpy | 1.26.4 | numerics |
| python-dotenv | 1.2.2 | API-key loading |

**Analyze-engine contract (verified empirically at build):** opentrons **8.8.2**; Protocol API
version range **2.0 → 2.27** (`MAX_SUPPORTED_VERSION = 2.27`); protocols authored at apiLevel 2.20.
Invocation `python -m opentrons.cli analyze --json-output - [--check]`; the parser is pinned to this
captured contract (`captured/analyze_contract.{json,md}`).

**Twin environment** — Python 3.11.15 (isolated venv, kept separate from the OT-2-pinned pipeline env):

| package | version | role |
|---|---|---|
| mujoco | **3.11.0** | rigid-body sim + collision + Metal render |
| numpy | 2.4.6 | kinematics |
| imageio / imageio-ffmpeg | 2.37.4 / 0.6.0 | mp4 encoding |
| pillow | 12.3.0 | overlay rendering |
| pyopengl | 3.1.10 | GL context |

---

## 9. Related & prior systems

Closest prior art is **PRISM** (arXiv:2601.05356): WebSurfer→Planner→Critique→Validator multi-agent
chain → MADSci YAML → NVIDIA Omniverse digital twin (collision + ray-cast object-presence + reach).
It validates physical executability but explicitly not science, and its Validator is an LLM.
Divergence from Paper2Protocol: (a) our acceptance gate is deterministic Python, not an LLM; (b) we
mechanize chemistry via the command-ledger; (c) we have no robotic arm → transitions are human-gated
`pause` handoffs, not arm moves; (d) our twin is the lighter MuJoCo path. Full teardown +
side-by-side: `examples/external/prism_review.html`.

Broader cluster (all in §10): Coscientist, ChemCrow, ORGANA (LLM lab agents); OpentronsAI, ProtoCode,
BioPlanner (paper/NL → protocol); LabOP / Autoprotocol (protocol description languages); Self-Refine
(iterative repair); Stechly/Kambhampati, Huang (self-verification limits — the theoretical basis for
our external gate).

---

## 10. Literature reviewed (37 sources, adversarially verified)

Four sweeps, each citation independently web-resolved by an adversarial reference-checker (0
fabrications; 4 factual corrections applied). Full annotations + verify-notes:
`RESEARCH_MATERIALS.md` and `literature_verified.json`. Consolidated references below (§13).

- **Protocol review / LLM-for-protocol (9):** Coscientist, ChemCrow, BioPlanner, ProtoCode,
  OpentronsAI, ORGANA, LabOP, Self-Refine, Stechly & Kambhampati (+ Huang; + Ma et al. on verifier
  quality). *Gap our ledger fills:* no sound external gate; schema-valid ≠ procedurally correct;
  simulators check syntax not intent; eval metrics soft & non-repairing.
- **Reproducibility metrics (8):** Baker 2016, Open Science Collaboration 2015, Errington 2021,
  King 2009 (Robot Scientist), Arias & Taylor 2024 (cloud labs), Schuster et al. 2024 (liquid-handler
  CV), Wilkinson 2016 (FAIR), Pineau 2021 (NeurIPS reproducibility checklist). → the RP% metric (§4.3).
- **Equipment / BOM (11 vendor docs):** Opentrons OT-2, GEN2 pipettes, Temperature/Thermocycler/
  Heater-Shaker modules; NVIDIA Isaac Sim & Isaac Lab requirements; MuJoCo MJX; Genesis; SAPIEN;
  PyBullet. → §7.
- **GPU physics simulation (13):** Isaac Gym (Makoviychuk 2021), ORBIT/Isaac Lab (Mittal 2023),
  MuJoCo (Todorov 2012), Genesis 2024, SAPIEN (Xiang 2020) / ManiSkill3, Brax, robosuite, domain
  randomization (Tobin 2017), OpenAI dexterous (Andrychowicz 2020) + ADR, sim-to-real survey (Zhao
  2020), Position-Based Fluids (Macklin & Müller 2013), Unified Particle Physics / FleX (Macklin 2014).
  → the twin's engine choice (§5, §7.2).

---

## 11. Reproducibility

**Pipeline (OT-2 env):**
```bash
cd paper2protocol
uv run paper2protocol run "<paper.pdf>"          # ingest → IR → codegen → loop → bundle
uv run paper2protocol run "<paper.pdf>" --live   # live LLM calls
uv run python -m opentrons.cli analyze --version # engine contract check
```
**Digital twin (twin env):**
```bash
python -m twin.run_twin examples/chemotaxis_penstrep/out/bundle_live/analysis.json \
    --out twin/out/chemotaxis_twin.mp4 --report twin/out/chemotaxis_twin_report.json
python -m twin.run_twin <analysis.json> --break   # prove collision detection fires
```
**Data availability.** Ledgers + bundles under `examples/chemotaxis_penstrep/out/`; external test PDFs
+ PLOS ingest under `examples/external/`; verified literature `literature_verified.json`; deck def
`twin/decks/ot2_standard.json`. Environments: pipeline Python 3.10.20 (`.venv`), twin Python 3.11.15
(`twin/.venv`); versions in §8.

---

## 12. Provenance, verification methodology & limitations

**How the facts were verified.** (1) The analyze CLI contract was captured empirically at build (real
exit codes, `--check` behaviour, one golden `analysis.json`) and the parser pinned to it — an early
research brief that mis-stated the opentrons version/entrypoint was corrected against the installed
8.8.2. (2) Labware/deck geometry is read from real Opentrons definitions, never hand-typed. (3) The
literature was gathered by four parallel sweeps, then each citation re-resolved by an independent
adversarial checker (0 fabricated; corrected: a wrong SLAS DOI …100134→…100128, two author
attributions, one date). (4) Dependency versions in §8 are read from the live environments.

**Limitations / threats to validity.**
- **n small.** The converged corpus is one paper (two protocol variants); Piper betle BLOCKED; two
  PLOS papers not yet run. The multi-paper replication study is the next milestone (§6).
- **Twin scope.** Kinematic, single-arm-free OT-2; the pipette is an abstracted rigid nozzle (labware
  and deck geometry are exact). No liquid physics (by design; §5.4). Modules add a z-offset and
  currently **raise** rather than being placed — no silent guessing.
- **Chemistry ≠ physics.** Each gate is sound only for its half; a plan can pass one and fail the
  other (demonstrated: `--break` is INFEASIBLE while conformance still PASSes).
- **LLM extraction error** flows into the IR; the dual-family cross-check + `open_clarifications`
  surface ambiguity but do not eliminate it — the deterministic gates catch downstream inconsistency,
  not a plausibly-wrong-but-self-consistent extraction, which is why human wet-lab sign-off remains.

---

## 13. References (consolidated)

**Prior systems & protocol review.**
Boiko et al., *Nature* 624:570 (2023), doi:10.1038/s41586-023-06792-0 · Bran et al., *Nat. Mach.
Intell.* 6:525 (2024), doi:10.1038/s42256-024-00832-8 · O'Donoghue et al., *EMNLP* 2023,
doi:10.18653/v1/2023.emnlp-main.162 · Jiang et al., *SLAS Technology* 29(3):100134 (2024),
doi:10.1016/j.slast.2024.100134 · Opentrons Labworks, OpentronsAI (opentrons.com/ai) · Darvish et al.,
*Matter* 8(2):101897 (2025), doi:10.1016/j.matt.2024.10.015 · Bartley, Beal, Rogers, Bryce et al.
(LabOP), *ACM JETC* 19(3) (2023), doi:10.1145/3604568 · Madaan et al. (Self-Refine), *NeurIPS* 2023,
arXiv:2303.17651 · Stechly, Valmeekam & Kambhampati, *ICLR* 2025, arXiv:2402.08115 · Huang et al.,
*ICLR* 2024, arXiv:2310.01798 · Ma et al., *NeurIPS* 2025, arXiv:2507.06920 · **PRISM**, arXiv:2601.05356.

**Reproducibility metrics.**
Baker, *Nature* 533:452 (2016), doi:10.1038/533452a · Open Science Collaboration, *Science*
349:aac4716 (2015), doi:10.1126/science.aac4716 · Errington et al., *eLife* 10:e71601 (2021),
doi:10.7554/eLife.71601 · King et al., *Science* 324:85 (2009), doi:10.1126/science.1165620 ·
Arias & Taylor, *Adv. Mater. Technol.* (2024), doi:10.1002/admt.202400084 · Schuster, Kamuju, Zhou &
Mathaes, *SLAS Technology* 29(2):100128 (2024), doi:10.1016/j.slast.2024.100128 · Wilkinson et al.
(FAIR), *Sci. Data* 3:160018 (2016), doi:10.1038/sdata.2016.18 · Pineau et al., *JMLR* 22(164) (2021),
arXiv:2003.12206.

**GPU physics simulation & sim-to-real.**
Makoviychuk et al. (Isaac Gym), *NeurIPS* D&B 2021, arXiv:2108.10470 · Mittal et al. (ORBIT/Isaac Lab),
*IEEE RA-L* 8(6):3740 (2023), doi:10.1109/LRA.2023.3270034 · Todorov, Erez & Tassa (MuJoCo), *IROS*
2012, doi:10.1109/IROS.2012.6386109 · Genesis (github.com/Genesis-Embodied-AI/Genesis, 2024) ·
Xiang et al. (SAPIEN), *CVPR* 2020, arXiv:2003.08515; ManiSkill3, arXiv:2410.00425 (ICLR 2025) ·
Freeman et al. (Brax), *NeurIPS* D&B 2021, arXiv:2106.13281 · Zhu et al. (robosuite), arXiv:2009.12293 ·
Tobin et al. (domain randomization), *IROS* 2017, arXiv:1703.06907 · Andrychowicz et al. (OpenAI
dexterous), *IJRR* 39(1) (2020), arXiv:1808.00177 · Zhao, Queralta & Westerlund (survey), *IEEE SSCI*
2020, arXiv:2009.13303 · Macklin & Müller (Position Based Fluids), *ACM TOG* 32(4):104 (2013),
doi:10.1145/2461912.2461984 · Macklin et al. (Unified Particle Physics / FleX), *ACM TOG* 33(4) (2014),
doi:10.1145/2601097.2601152.

**Equipment (vendor documentation).** Opentrons OT-2, GEN2 pipettes, Temperature Module GEN2,
Thermocycler Module GEN2, Heater-Shaker (docs.opentrons.com) · NVIDIA Isaac Sim & Isaac Lab
requirements (docs.isaacsim.omniverse.nvidia.com) · MuJoCo MJX (mujoco.readthedocs.io) · Genesis,
SAPIEN, PyBullet official docs. Full URLs + fetch notes in `literature_verified.json`.
