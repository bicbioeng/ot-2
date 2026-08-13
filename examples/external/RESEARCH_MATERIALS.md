# Paper2Protocol — Research Materials Dossier

*The complete corpus reviewed for the PRISM comparison + literature review. This is the working
source-of-record; the polished advisor deliverable is `prism_review.html`. Compiled 2026-08-05.*

Everything here was either (a) read directly from a primary source on disk, or (b) produced by a
literature sweep whose every citation was then re-resolved by an independent adversarial reference
checker via live web search. **37 external citations, 0 fabricated; 4 factual corrections applied.**

---

## 0 · Manifest — source files on disk

| File | What it is |
|---|---|
| `PRISM_2601.05356.pdf` (9.9 MB) | The PRISM paper — "Protocol Refinement through Intelligent Simulation Modeling," Argonne / MADSci group. |
| `PRISM_text.txt` (142,557 chars, 43 pp) | Full extracted text of PRISM, used for the verbatim quotes below. |
| `literature_verified.json` (88 KB) | **Raw** output of the verified-literature workflow — all 4 legs, every entry with verdict + verify_note. Durable copy of the run. |
| `literature_workflow_journal.jsonl` (138 KB) | Per-agent journal for the same workflow (8 agents: 4 find → 4 verify). |
| `plos_0146349.pdf`, `plos_0263359.pdf`, `plos_0318135.pdf` | External test papers (Piper betle / olive-leaf MIC assays) run through the pipeline for generality. |
| `out_0146349/` | Ingest-run artifact bundle from `plos_0146349.pdf`. |
| `prism_review.html` | The polished, advisor-facing distillation of this dossier. |
| `../../captured/analyze_contract.{json,md}` | M1 empirical `opentrons analyze` contract (pinned to opentrons 8.8.2). |
| `~/.claude/plans/sorted-floating-engelbart.md` | The approved, adversarially-hardened build plan. |

---

## 1 · PRISM teardown (verbatim-grounded)

PRISM = target experiment → **multi-agent chain** → **MADSci YAML** (declarative atomic robot actions)
→ MADSci capability/inventory validation → **NVIDIA Omniverse physics digital twin** (collision +
object-presence + reach checks) → LLM repair loop until physically clean → **human** scientific review.
Benchmarks: **PCR amplification** and **Cell Painting**. Instrument cell: OT-2 **+ PF400 arm + Azenta
sealer/peeler + Hidex reader**.

### 1.1 The 4-agent prompt chain (PRISM appendix A, quoted)

**WebSurfer** (source-of-truth extractor):
> "get the … protocol and extract: reagent list and volumes; step-by-step liquid handling
> instructions; thermocycling conditions; … Make every numeric value explicit (µL, °C, s). **No
> ranges.** If the vendor omits a fact, say **'Not specified by vendor.'** Do not include melt-curve
> analysis unless explicitly stated." → emits a `CONSTANTS (SOURCE-OF-TRUTH)` block.

**Protocol Planner** (CONSTANTS → enumerated OT-2 steps). Hard rules:
> "Treat WebSurfer's CONSTANTS as the source-of-truth. **Minimum accurate transfer = 5 µL** … Scale
> all components proportionally while maintaining valid concentrations (preserve the master-mix factor)
> … Prepare each source with **≥10% overage and SHOW THE MATH** … 96-well PCR plate can hold 100 µl …
> if you require ≥100 µl of any reagent you should have 2 wells … **use fresh tips for every transfer**
> … select the smallest suitable pipette (P20 vs P300) … Keep the wells apart on the final plate to
> avoid contamination … Exactly 2 Test wells (include Template DNA) and 2 Control wells (exclude it)."
> Strict per-step line format: `X.) Transfer [volume] of [reagent] from [Well] … with 3 mix cycles.
> [Tip action - eject tip]`.

**Critique** (concrete numbered fixes): verify per-reaction volumes match/scale with concentrations
preserved; total per-well volume equals declared total; reagent plate lists all sources with ≥10%
overage + arithmetic; well-capacity split if ≥100 µl; 2 Test / 2 Control non-adjacent; no transfer
<5 µL; every step fully enumerated (no "repeat for wells"); strict line-format compliance; deck
declarations explicit.

**Validator**: confirm all Critique feedback incorporated, all volumes/wells match constants, format
exact; "Return only the final corrected and validated protocol."

> **Read on our design:** all four are LLMs. This is a *generation-side refinement panel* that sharpens
> the draft **before** any engine sees it — it is **not** a deterministic acceptance gate. That is the
> seam we hardened with a non-LLM `loop.py` gate.

### 1.2 Inventory / capability validation — MADSci (§2.2, L436–462)
> "MADSci examines the YAML file to ensure that all required fields are present, that the **robots
> referenced in the protocol exist in the laboratory configuration**, that the requested actions are
> **within each robot's capabilities**. … MADSci also checks whether the **arguments provided for each
> action match the expected inputs**."

Robot capabilities/actions/arguments are "defined once and packaged together," so a lab is composed by
declaring which robots are present + lab-specific constraints. **Static/schema-level only** — no reagent
quantity or tip-count tracking. Plate *presence* is checked later in the twin by ray-casting.

### 1.3 Digital twin (§2.3, L465–521)
Vendor/repository **CAD** → add **collision geometries + joints measured off the real robots** → sim
drivers translate MADSci commands to joint motions, communicated over **ZeroMQ** ("same MADSci software
… only the robot interface modules changed"). Functional-accuracy placement, not sub-mm.

### 1.4 Error detection (§2.3.2, L522–554)
Physics collision detection (ignoring intended gripper-plate contact); **ray-cast object-presence**
(is the plate where the robot expects?); **reach / joint-limit** validation. Every error → an
English-language description the LLM repairs against, iteratively, until clean.

### 1.5 The honesty boundary (§2.3.3, L555–583, quoted)
> "**Simulation success does not guarantee scientific accuracy.** The simulation confirms physical
> executability but cannot verify that the protocol will achieve the intended scientific outcome, **as
> we do not simulate liquid physics, chemical reactions, or biological processes.** After a protocol
> passes simulation validation, it undergoes **human review** to verify scientific accuracy."

**→ The orthogonality thesis:** PRISM proves *physics, not chemistry*; Paper2Protocol proves *chemistry
(via the command-ledger conformance gate), not physics*. Complementary. Ideal = PRISM's physics twin +
our conformance ledger, both behind one deterministic non-LLM gate (which PRISM lacks — its Validator
is an LLM).

---

## 2 · LIT-1 — Automated / LLM-based protocol review & validation
*9 sources · 0 fabricated. Positioning a deterministic validate→repair loop with a command-ledger gate.*

1. **Boiko et al.** Autonomous chemical research with LLMs (**Coscientist**). *Nature* 624:570–578, 2023. `10.1038/s41586-023-06792-0` — ✔ verified.
   GPT-4 agent autonomously designs/plans/executes experiments (incl. Pd cross-coupling opt) on real hardware. *No deterministic pre-execution gate* between generated code and instrument.
2. **M. Bran et al.** Augmenting LLMs with chemistry tools (**ChemCrow**). *Nat. Machine Intelligence* 6:525–535, 2024. `10.1038/s42256-024-00832-8` — ✔.
   18-tool GPT-4 agent; tool-mediated "safety" step, but correctness judged by the same LLM loop — no external sound checker.
3. **O'Donoghue et al.** **BioPlanner**: Automatic Evaluation of LLMs on Protocol Planning in Biology. *EMNLP* 2023, 2676–2694. `10.18653/v1/2023.emnlp-main.162` — ✔.
   Constrains steps to admissible "pseudofunctions" and scores conformance — but a *soft similarity metric*, evaluating plans, not repairing them. Closest conceptual cousin to our ledger.
4. **Jiang et al.** **ProtoCode**: LLMs for machine-readable PCR protocols from publications. *SLAS Technology* 29(3):100134, 2024. `10.1016/j.slast.2024.100134` — ✔ (DOI 302-redirects to Elsevier PII S2472630324000165).
   Paper→machine-readable→cycler-file; 69–100% field accuracy. Our exact space; residual 0–31% extraction error is what a conformance ledger catches before hardware.
5. **Opentrons Labworks.** **OpentronsAI** — NL→Opentrons Python + in-chat simulation. Vendor. `opentrons.com/ai` — ✔ **[correction: dating softened]** — the dynamic-sim launch was announced **March 2026** (not "2024–2025"); docs sub-path unconfirmed.
   Closest deployed analog: pairs LLM generation with a deterministic simulator gate — but that gate checks *API-level executability, not semantic intent conformance*.
6. **Darvish et al.** **ORGANA**: robotic assistant for automated chemistry. *Matter* 8(2):101897, 2025. `10.1016/j.matt.2024.10.015` — ✔.
   Perception-based *run-time* error detection — catches physical failures *after* commands issue; our gate rejects *before* dispatch.
7. **Bartley, Beal, Rogers, Bryce, et al.** Building an Open Representation for Biological Protocols (**LabOP**). *ACM JETC* 19(3):1–21, 2023. `10.1145/3604568` — ✔ **[correction: author fix]** — draft's "Karr, Strychalski" attribution was wrong; corrected to the real front-listed authors.
   OWL/RDF representation on UML/Autoprotocol/Aquarium/SBOL/PROV with export to Opentrons/Echo/SiLA. Ships *no* correctness validator — schema-valid ≠ procedurally correct. PROV = ledger substrate.
8. **Madaan et al.** **Self-Refine**: Iterative Refinement with Self-Feedback. *NeurIPS* 2023. `arXiv:2303.17651` — ✔.
   Single LLM generates→critiques→refines, ~20% gains. The template for our "repair" half; we swap its LLM critic for a sound external gate.
9. **Stechly, Valmeekam & Kambhampati.** On the Self-Verification Limitations of LLMs on Reasoning and Planning Tasks. *ICLR* 2025, 8097–8150. `arXiv:2402.08115` — ✔. (Companion: **Huang et al.**, "LLMs Cannot Self-Correct Reasoning Yet," ICLR 2024, `arXiv:2310.01798`.)
   On planning-shaped tasks, LLM self-critique **collapses** performance while a **sound external verifier** yields large gains. **The theoretical justification for a deterministic conformance gate over an LLM critic.**

**LIT-1 synthesis — where existing protocol-review methods are WEAK (the gap our ledger fills):**
- **(1) No sound external gate** — Coscientist/ChemCrow/ORGANA/Self-Refine self-adjudicate; Stechly + Huang show this collapses on planning tasks. None inserts a deterministic model-external verifier between generated commands and the instrument.
- **(2) Schema-valid ≠ procedurally correct** — Autoprotocol/Aquarium/LabOP-SBOL validate representation (JSON schema, OWL/RDF, PROV) but ship no checker that a protocol uses only allowed ops in a legal order with satisfied preconditions.
- **(3) Simulators check syntax, not intent** — OpentronsAI's simulator catches API/labware/tip errors but happily simulates a valid-but-semantically-wrong procedure.
- **(4) Eval metrics are soft & non-repairing** — BioPlanner/ProtoCode score per-step/field similarity (69–100%) but neither hard-rejects nor repairs a nonconforming sequence.
- **(5) Monitoring is post-dispatch** — ORGANA detects failures via perception *after* commands issue.
- **(6) Verifier quality is itself unvalidated** — Ma et al., "Rethinking Verification for LLM Code Generation" (`arXiv:2507.06920`, TCGBench/SAGA, NeurIPS 2025): test suites are homogeneous and miss subtle faults — the analog of an incomplete command ledger.

**→ Proposed: a Command-Ledger Conformance Rate** — fraction of emitted commands that (a) draw from the
allowed-op set, (b) satisfy declared preconditions/resource state, (c) preserve the reference step-DAG
order — computed by a deterministic LLM-external checker gating dispatch, driving a bounded repair loop
whose *proposer* is the LLM but whose *accept/reject is never* an LLM. Report **ledger coverage**
alongside conformance to avoid the TCGBench "homogeneous suite inflates pass rate" failure.

---

## 3 · LIT-2 — Reproducibility metrics → a "replication percent"
*8 sources · 0 fabricated.*

1. **Baker, M.** 1,500 scientists lift the lid on reproducibility. *Nature* 533:452–454, 2016. `10.1038/533452a` — ✔.
   ~90% affirm a crisis; ranks **poor method/protocol description** among the top *fixable* causes → aim the metric at under-specified steps; weight assertion-realization heavily.
2. **Open Science Collaboration (Nosek et al.).** Estimating the reproducibility of psychological science. *Science* 349:aac4716, 2015. `10.1126/science.aac4716` — ✔.
   Reproducibility depends *entirely* on the metric: 36% by significance, 47% effect-size-in-CI. A lone success rate is meaningless without a stated rule → **declared multi-criterion, tolerance-band rule; report a vector.**
3. **Errington et al.** Investigating the replicability of preclinical cancer biology. *eLife* 10:e71601, 2021. `10.7554/eLife.71601` (+ companion `10.7554/eLife.67995`) — ✔.
   Intended 193 experiments, completed only 50 — protocol incompleteness & reagent unavailability blocked the rest. **Separates "could-not-attempt" from "attempted-and-failed"** → the source for honest-BLOCKED accounting.
4. **King et al.** The Automation of Science (Robot Scientist **"Adam"**). *Science* 324:85–89, 2009. `10.1126/science.1165620` — ✔ **[correction: pages added]**.
   Autonomous hypothesis→experiment; every step in a formal logical ontology linked to 6.6M measurements — the experiment *is* its own replayable record → an assertion-level ledger makes replication computable.
5. **Arias, D.S. & Taylor, R.E.** Scientific Discovery at the Press of a Button: Navigating Emerging Cloud Laboratory Technology. *Adv. Materials Technologies*, 2024. `10.1002/admt.202400084` — ✔ **[correction: author fix]** — draft's first-author initials "J.J.R." were **wrong**; actual authors D. Sebastian Arias & Rebecca E. Taylor. Throughput/founding-year figures unconfirmed → provisional.
   Cloud labs (Emerald Cloud Lab, Strateos) codify every step → remove operator drift; reproducibility gains from unit-/parameter-complete encoding + standardized execution.
6. **Schuster, Kamuju, Zhou & Mathaes.** Piston-driven automated liquid handlers. *SLAS Technology* 29(2):**100128**, 2024. `10.1016/j.slast.2024.100128` — ✔ **[correction: DOI + authors fixed]** — draft's DOI (…100134) was **wrong** and authorless.
   Automation CV ≈ **0.15–1.50%** larger volumes, rising to **2–8% near 1 µL** → gives tolerance `τ` a **measured, volume-dependent** value (not a flat constant).
7. **Wilkinson et al.** The FAIR Guiding Principles. *Scientific Data* 3:160018, 2016. `10.1038/sdata.2016.18` — ✔.
   15 machine-actionability principles; spawned quantitative FAIR-maturity scoring as a satisfied-fraction → template for the gate/handoff completeness term.
8. **Pineau et al.** Improving Reproducibility in ML Research (NeurIPS 2019 Reproducibility Program). *JMLR* 22(164):1–20, 2021. `arXiv:2003.12206` — ✔.
   Operationalizes reproducibility as a satisfied-fraction over a fixed machine-checkable checklist → direct precedent for RP% as a rubric fraction (each assertion realized / BLOCKED / dropped).

**Follow-up (unverified — do not cite until checked):** (a) an inter-lab ring-trial / proficiency-test
dataset with published between-lab CV to calibrate `τ` per assay class empirically; (b) a stats source
on prediction-interval coverage for replication (Patil/Peng/Leek or Mathur & VanderWeele) to formalize
the `r_c` concordance criterion beyond the OSC CI rule.

### 3.1 The proposed metric (full spec)

**Design principle** (OSC 2015 + Errington 2021): meaningless without (i) a declared multi-criterion
success rule and (ii) strict separation of could-not-attempt / attempted-and-failed / silently-dropped.
So **RP% is a vector: (RP%, BLOCKED%, SILENT-DROP%).**

**Inputs** (all from the analyze pass):
- `A` = IR assertions (each a discrete checkable claim: step, concentration target, gate, handoff).
- `L` = `commands[]` ledger; each command carries postconditions + provenance to assertions.
- Partition `A` → **R** (realized: a ledger command satisfies the postcondition), **B** (honest-BLOCKED: flagged unrealizable — missing reagent, ambiguous spec, unsupported op), **D** (silent-drop: in A but neither realized nor BLOCKED — the dishonest bucket, target 0). Attemptable scope `A* = A \ B`.

**Four terms** (each ∈ [0,1]):
```
r_a = |R| / |A*|                    assertion realization (attemptable scope)
r_c = |{p ∈ P* : dim_ok(p) AND |ĉ(p) − c_target(p)| / c_target(p) ≤ τ(class, vol)}| / |P*|
r_g = |{i ∈ I(class) : satisfied(i)}| / |I(class)|   gate/handoff completeness
h   = 1 − |D| / |A|                 honesty factor (penalizes silent loss)
```
- `dim_ok` = **hard gate**: a dimensional/unit mismatch fails the step regardless of numeric closeness (catches the unit-error class).
- `τ` = assay-class tolerance, defaulted to the **measured, volume-dependent** liquid-handling CV (SLAS 2024): ≈0.15–1.5% larger volumes, widening to 2–8% sub-µL. CI-style concordance (OSC 2015), not exact equality.
- `I(class)` = assay-class invariant set (e.g., qPCR requires a no-template-control gate; a transfer requires a volume/units-conserved handoff). FAIR-maturity-style satisfied-fraction.

**Composite:**
```
RP% = 100 · h · ( w_a·r_a + w_c·r_c + w_g·r_g ),   w_a + w_c + w_g = 1
default  w_a=0.40, w_c=0.30, w_g=0.30   (assay-class configurable; Baker 2016 → realization weighted highest)

HARD VETO: any dim_ok failure or unsatisfied SAFETY-critical invariant caps RP% (e.g. → 0).
CO-REPORT (non-negotiable):  BLOCKED% = 100·|B|/|A|   SILENT-DROP% = 100·|D|/|A|
RP% is NEVER shown without BLOCKED%.
```
**Worked shape:** |A|=100, B=15, D=0, A*=85. R=76 → r_a=0.894. P*=30, 27 within τ & dim_ok → r_c=0.900.
I=12, 11 satisfied → r_g=0.917. h=1. **RP% = 100·(0.40·0.894 + 0.30·0.900 + 0.30·0.917) = 90.3%.**
Report **(RP 90.3, BLOCKED 15, SILENT-DROP 0)**. A protocol that honestly BLOCKS 60% and perfectly
realizes the rest → (RP 100 over attemptable, BLOCKED 60, SILENT-DROP 0): transparent, not inflated.

---

## 4 · LIT-3 — Equipment / bill of materials
*11 sources · 0 fabricated. All specs fetched from live vendor docs.*

### 4.1 Layer A — wet automation (Opentrons OT-2), one physical build
- **OT-2 robot** — 11-slot deck + trash, 2 pipette mounts. Robot ≈ **$6,500**; full setup "from $10,000." `docs → opentrons.com/robots/ot-2`
- **GEN2 pipettes** — P20 Single (1–20 µL; **±15% at 1 µL**, ±1.5% at 20 µL), P300 Single (20–300), P1000 Single (100–1000; ±0.7% at 1000). 8-channel only P20/P300 (**no P1000 multi**). `docs.opentrons.com/ot-2/pipettes/` — the **1 µL floor** and range-overlap the translator must respect.
- **Temperature Module GEN2** — 4–95 °C; interchangeable aluminum blocks (96-PCR / 2 mL / 1.5 mL, sold separately); 1 slot; ~65 °C in ~6 min. `opentrons.com/products/temperature-module-gen2`
- **Thermocycler Module GEN2** — block 4–99 °C, heated lid → 110 °C, holds indefinitely; occupies **slots 7/8/10/11** (double footprint — reserve first). `docs.opentrons.com/v2/modules/thermocycler.html`
- **Heater-Shaker** (GEN1; no GEN2 exists) — 37–95 °C ±0.5; 200–3000 rpm, 2.0 mm orbital. `docs.opentrons.com/ot-2/modules/heater-shaker/` — <37 °C or >3000 rpm is out-of-spec → flag.
- **Consumables** — 20/300/1000 µL tip racks; 12-column reservoirs; SBS 96/384 plates; tube racks (allowlist-checked).

### 4.2 Layer B — digital-twin compute (lighter path; NOT Omniverse)
**Decisive verified fact** (NVIDIA Isaac Sim requirements, `docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html`, quoted): **"GPUs without RT Cores (A100, H100) are not supported."** If only datacenter GPUs are available, the twin **must** use MJX / Genesis / SAPIEN / PyBullet.

| Tier | Engine | GPU / compute | Use |
|---|---|---|---|
| **Minimum** (prototype) | PyBullet (CPU) or MJX single-scene CPU | **No GPU**; 4-core, 16–32 GB RAM; any OS | Deck layout, reachability, step ordering, CI smoke test |
| **Recommended** (workstation) | MuJoCo **MJX** (JAX+CUDA 12) · Genesis · SAPIEN/ManiSkill | Consumer **RTX 4070Ti–4080 / 5070–5080, 12–16 GB VRAM** (*no RT-Cores needed*; SAPIEN needs Vulkan driver >470; MJX needs CUDA 12+JAX); 8-core, 32–64 GB, Ubuntu 22.04, NVMe | Batched contact-rich sim; thousands of parallel liquid-handling rollouts |
| **Research-grade** (photoreal / scale) | **A:** Isaac Sim/Lab · **B:** MJX-Warp / Genesis @ datacenter | **A** needs RTX 4080→5080→PRO 6000 (48 GB); **A100/H100 unsupported**. **B** exploits A100/H100/L40S (40–80 GB) headless — the *only* way to use datacenter cards | **A** = photoreal perception twin; **B** = pure physics/RL throughput |

**Asset-prep note (MJX):** simplify collision meshes to ≤~200 verts (general convex) and <~32 verts
(convex-convex); URDF importable to MJCF. Isaac path needs URDF/MJCF → **USD** conversion.

---

## 5 · LIT-4 — GPU-accelerated physics simulation (Isaac / MuJoCo / lighter)
*13 sources · 0 fabricated.*

**Simulators / benchmarks:**
1. **Makoviychuk et al.** Isaac Gym: High-Performance GPU-Based Physics Sim for Robot Learning. *NeurIPS* D&B 2021. `arXiv:2108.10470` — ✔. End-to-end GPU (PhysX + PyTorch, no CPU round-trip); 2–3 orders-of-magnitude RL speedup; founded the massively-parallel-envs paradigm. *Preview deprecated → use Isaac Lab.*
2. **Mittal et al.** **ORBIT** → **Isaac Lab**. *IEEE RA-L* 8(6):3740–3747, 2023. `10.1109/LRA.2023.3270034` — ✔. The open, lighter app layer on Isaac Sim (the intended "not-full-Omniverse" entry point); inherits PhysX GPU particle fluids + RTX rendering — **the only candidate that can render believable liquid in wells.**
3. **Todorov, Erez & Tassa.** **MuJoCo**. *IROS* 2012, 5026–5033. `10.1109/IROS.2012.6386109`; **MJX** (MuJoCo 3.0, 2023) — ✔. Gold-standard contact-rich control; MJX → thousands of differentiable envs on NVIDIA/AMD/Apple/TPU. **Weakness: no native liquid** — aqueous handling must be an analytical layer.
4. **Genesis Embodied AI.** Genesis: Generative & Universal Physics Engine. Open-source, Dec 2024. `github.com/Genesis-Embodied-AI/Genesis` — ✔ (**project, no peer-reviewed paper**; ~43M FPS/RTX 4090 self-reported). Unified rigid + MPM + **SPH-fluid** + PBD in one Python API → the single-engine answer to "contact-rich robot + liquid." **High-upside watch-item, not yet load-bearing.**
5. **Xiang et al.** **SAPIEN**. *CVPR* 2020. `arXiv:2003.08515`; **ManiSkill3** `arXiv:2410.00425` (ICLR 2025, 30k+ FPS) — ✔. Articulated-object sim + ray-traced render; ManiSkill adds GPU-parallel manipulation. Rigid/articulated only — no native fluid. Lower barrier than Isaac (Vulkan+driver>470 vs RT-Cores), headless render.
6. **Freeman et al.** **Brax**. *NeurIPS* D&B 2021. `arXiv:2106.13281` — ✔. JAX-native differentiable rigid-body; speed/differentiability over contact fidelity. *MJX is the stronger JAX choice today.*
7. **Zhu et al.** **robosuite**. 2020 (rev. 2025). `arXiv:2009.12293` — ✔. MuJoCo-powered modular robot/gripper/controller/task scaffolding — a ready pattern to stand up an OT-2 env with tested controllers.

**Sim-to-real transfer:**
8. **Tobin et al.** Domain Randomization for Transferring DNNs Sim→Real. *IROS* 2017. `arXiv:1703.06907` — ✔. Randomize textures/lighting/pose → real localization ~1.5 cm, zero real images. The transfer backbone (randomize deck lighting, labware appearance, tip-fit force, liquid viscosity/surface tension).
9. **OpenAI: Andrychowicz et al.** Learning Dexterous In-Hand Manipulation. *IJRR* 39(1), 2020 (+ **ADR**, 2019). `arXiv:1808.00177` — ✔. Zero-shot sim→real via extensive randomization + calibration; actuator/latency modeling (not photorealism) drives transfer. Cautionary on brute-force-randomization compute cost.
10. **Zhao, Queralta & Westerlund.** Sim-to-Real Transfer in Deep RL: a Survey. *IEEE SSCI* 2020, 737–744. `arXiv:2009.13303` — ✔. Maps the reality-gap closers (randomization, adaptation, imitation, meta-learning, system-ID) → structures the twin's validation plan.

**GPU fluid (relevant to pipetting):**
11. **Macklin & Müller.** **Position Based Fluids**. *ACM TOG (SIGGRAPH)* 32(4):104, 2013. `10.1145/2461912.2461984` — ✔. Stable large-timestep real-time fluid + surface tension — the algorithmic core of GPU particle fluids in FleX/PhysX/Isaac Sim. **Visually plausible, not metrologically exact.**
12. **Macklin, Müller, Chentanez & Kim.** Unified Particle Physics for Real-Time Applications. *ACM TOG (SIGGRAPH)* 33(4), 2014 (basis of NVIDIA FleX; **2025 SIGGRAPH Test-of-Time**). `10.1145/2601097.2601152` — ✔. One particle representation unifying rigid+granular+cloth+fluid with two-way coupling → why Isaac Sim can co-simulate labware + aqueous liquid in one scene. FleX itself legacy; consumed via PhysX particles.
13. *(Isaac Gym / PhysX lineage — cross-referenced with #1–2.)*

**The domain-gap caveat every leg agreed on:** every engine here — including Isaac Sim PBF fluids —
yields **visually/behaviorally plausible liquid, NOT metrology-grade volumetric accuracy**. None
certifies sub-µL OT-2 dosing without real-hardware calibration. OT-2 specifics (tip press-fit forces,
aspiration air-gap dynamics, capillary/meniscus) are out-of-the-box in *no* engine. **→ Dosing accuracy
stays with the conformance ledger; physics sim is scoped to motion / collision / reachability.**

### 5.1 Head-to-head + roadmap recommendation

| Engine | Native liquid | GPU need | Render | Dev speed | Verdict for our twin |
|---|---|---|---|---|---|
| **MuJoCo / MJX** | none (analytical) | any / CPU / Apple | basic | high | **Start here** — kinematics + collision + reachability |
| **Genesis** | rigid+SPH+MPM in one solver | any CUDA/ROCm/Metal | good | medium | Watch-item — the liquid-leg prototype |
| **SAPIEN / ManiSkill** | none | Vulkan, driver >470 | strong, headless | high | CI validation of pick/place + tip handling |
| **Isaac Sim / Lab** | PhysX PBF/FleX fluids | RT-Core RTX only; **no A100/H100** | photoreal | low | Later — photoreal perception twin, if arm added |
| **PyBullet** | none | none | software | high | Zero-GPU baseline / laptop prototype |

**Recommendation.** Start with **MuJoCo/MJX** for a lightweight kinematic + collision + deck-reachability
twin of the OT-2 gantry (Cartesian, simple). The scientifically load-bearing part — volumes/concentrations
— is *already* validated by our conformance ledger, and physics sim can't deliver metrology-grade dosing
anyway. Honest partition: **physics twin = motion/collision/reachability; conformance ledger =
dosing/chemistry.** Add **Genesis** as a watch-item for the co-simulated liquid leg; reserve **Isaac Lab**
for a later photoreal perception twin *if a manipulator is added*. Because the lab's gear-triad GPUs are
datacenter-class, the Isaac path is off the table there by NVIDIA's own requirement — MJX/Genesis isn't
just lighter, it's the *only* path that runs on the hardware we already schedule. **Where it lives:** fold
the physics-twin engine into the existing `dts-twin` pillar (Paper2Protocol contributes the OT-2 asset +
conformance-ledger gate; `dts-twin` provides sim substrate + GPU scheduling) rather than a separate stack.

---

## 6 · Provenance & methodology

- **PRISM quotes** — read directly from `PRISM_text.txt` (§2.2–2.3 and appendix A).
- **Literature** — 4 parallel "find" sweeps (WebSearch/WebFetch, `effort:high`) → 4 independent
  adversarial "verify" agents that re-resolved every DOI/arXiv id via live web search on 2026-08-05.
  **37 citations, 0 fabricated.** Corrections applied: SLAS DOI (…100134 → …100128) + missing authors;
  cloud-lab first-author (J.J.R. → Arias & Taylor); LabOP author attribution (Karr/Strychalski removed);
  OpentronsAI dating softened (→ March 2026); King pages added (324:85–89).
- **Raw data** — `literature_verified.json` (full entries + verify_notes) and
  `literature_workflow_journal.jsonl` (per-agent).
- **Constraint honored throughout** — no tests added to this project; digital-twin path targets
  Isaac-Sim / MuJoCo / lighter (not Omniverse).
