# Autonomous-Lab Ecosystem, Prior Art & Hardware Due-Diligence

**Purpose.** Before committing ~$50K to lab hardware beside the OT-2, map the field we are
entering: the orchestration frameworks, the hardware-abstraction layers, the LLM/AI
protocol-generation peers, the reference autonomous labs and *how they learn*, and the real
equipment economics. This is the "know what everyone else built and learned first" document —
so Paper2Protocol / Lab AI-OS is positioned deliberately, not reinvented, and so the capital
spend is de-risked by simulation and standards before a purchase order.

Scope note: this is a **living dossier**. Every claim is sourced. Items marked ⚠ are from
secondary sources (primary PDF paywalled) and should be confirmed against the primary before
being quoted in the paper. Last swept: 2026-08-06.

---

## 0. Where Paper2Protocol sits (one diagram in words)

A self-driving lab is three layers. Knowing which layer each project occupies tells us who is a
competitor, who is a dependency, and who is a peer.

```
  ┌─────────────────────────────────────────────────────────────────┐
  │ (C) DECISION / LEARNING LAYER   — what to run next               │
  │     Bayesian optimization, active learning, LLM planners         │
  │     e.g. Coscientist, ChemCrow, Gryffin/Phoenics, A-Lab's AL     │
  ├─────────────────────────────────────────────────────────────────┤
  │ (B) ORCHESTRATION / LAB-OS      — schedule & run a workflow      │
  │     MADSci, WEI, ChemOS 2.0, AlabOS, HELAO, Bluesky, UniLabOS    │
  │     IvoryOS, Aquarium   ← LABA / Lab AI-OS lives here            │
  ├─────────────────────────────────────────────────────────────────┤
  │ (A) INSTRUMENT / PROTOCOL LAYER — actuate one device             │
  │     Opentrons API, PyLabRobot, Autoprotocol, SiLA 2, XDL, LabOP  │
  │     ← Paper2Protocol emits into here; the twin validates here    │
  └─────────────────────────────────────────────────────────────────┘
```

**Paper2Protocol** is a *compiler into layer (A)* with a deterministic validation gate — it turns
a paper into a validated Opentrons protocol. **The digital twin** validates layer (A) physics
before hardware exists. **LABA / Lab AI-OS** is a layer (B) orchestrator that will *consume*
Paper2Protocol's `run(pdf, config) -> ArtifactBundle` seam. This dossier is mostly about (B) and
(C), because that is the field we must not be naïve about, plus the layer-(A) standards we should
emit toward instead of locking to one vendor.

---

## 1. Orchestration / Lab-OS frameworks (layer B) — the field LABA competes/coexists with

| Framework | Origin | Lang | Device comms / standard | Dashboard / UI | License | Relevance to us |
|---|---|---|---|---|---|---|
| **MADSci** | Argonne **AD-SDL** (Self-Driving Lab div.) | Python | **MADSci Node** standard over REST/HTTP; OpenTelemetry tracing | **Web dashboard @ `:8000`** (`ghcr.io/ad-sdl/madsci_dashboard`) + `madsci tui` | open (repo has LICENSE; beta) | **Closest peer to LABA.** Modular manager services; the "Node" idea is exactly our thin instrument seam. Study its schemas. |
| **WEI** (Workflow Execution Interface) | Argonne AD-SDL (MADSci's **predecessor**) | Python | REST modules + workflow YAML | web UI | open | The prior generation → shows the migration path & what they dropped. |
| **ChemOS / ChemOS 2.0** | Aspuru-Guzik group (Toronto/Vector) | Python | **SiLA 2**, with a **simulation mode** | orchestration UI | open | Chemistry SDL orchestration; SiLA2 + sim-mode mirror our simulate-first stance. |
| **AlabOS** | Berkeley **A-Lab** (Ceder group) | Python | task graph + **resource reservation** | web | open (SSC) | Powers a *real* 17-day autonomous campaign. Reservation model avoids deadlocks — directly relevant if LABA schedules shared hardware. |
| **HELAO / HELAO-async** | Caltech / HTE community | Python | each component = its own web server | per-server | open | Extreme modularity (server-per-instrument) — a design point to weigh vs MADSci's managers. |
| **Bluesky / Ophyd** | NSLS-II / DOE light sources | Python | EPICS / device abstraction | web + notebooks | BSD | Battle-tested at synchrotrons; strong on *data acquisition*, weak on synthesis. Mature RunEngine worth studying. |
| **IvoryOS** | (Nature Comms 2025) | Python | wraps any Python-driven SDL | **interoperable web interface** | open | "Put a web UI on your existing Python SDL" — a fast path to a dashboard over our own stack. |
| **UniLabOS** | deepmodeling (arXiv 2512.21766, Dec 2025) | Python + **ROS 2 / DDS** | A/R/A&R model, transactional **CRUTD**, edge-cloud | governance UI | open (`deepmodeling/Uni-Lab-OS`) | Newest, most ambitious "**AI-native OS**." ROS2/DDS decentralized discovery + human-in-the-loop governance = the architecture Lab AI-OS is reaching for. **Read this one closely.** |
| **Aquarium** | UW **BIOFAB** | Ruby/Rails | LIMS + protocol execution | web | open | Biology-first (not materials); protocol + inventory + technician workflow. |

**Takeaways for LABA:** (1) the "**Node / device-server behind a common REST interface**" pattern is
universal (MADSci, WEI, HELAO) — our thin seam is the right shape. (2) A **resource-reservation
scheduler** (AlabOS) is the non-obvious hard part everyone eventually builds. (3) **UniLabOS** and
**MADSci** are the two to benchmark against; don't design LABA in a vacuum.

---

## 2. Instrument / protocol layer (layer A) — emit toward standards, not one vendor

| Thing | What it is | Why it matters to Paper2Protocol |
|---|---|---|
| **Opentrons Python API** (≤2.27) | our current codegen target; validated by `opentrons analyze` | the deterministic oracle we already lean on |
| **PyLabRobot** | hardware-**agnostic** Python SDK; **one interface** for OT-2, Hamilton STAR/Vantage, Tecan EVO, plus plate readers, pumps, scales, heater-shakers; interactive (Jupyter/REPL); peer-reviewed in *Device* (Cell Press) | **The escape hatch from OT-2 lock-in.** If codegen targets PyLabRobot, the *same* paper→protocol pipeline drives a Hamilton/Tecan later — huge for the $50K decision (buy the machine, keep the software). Repo: `PyLabRobot/pylabrobot`. |
| **Autoprotocol** | JSON protocol description language (Strateos/Transcriptic) | a vendor-neutral IR our IR could export to |
| **SiLA 2** | industry standard for lab device interfaces (like OPC-UA for labs) | if we buy instruments, prefer SiLA2-speaking ones; ChemOS2 already uses it |
| **XDL** (Chemical Description Language) | Cronin group (Glasgow) hardware-independent synthesis language | the chemistry-synthesis analog of our IR |
| **LabOP / PAML** | Laboratory Open Protocol language (Bioprotocols WG) | emerging protocol standard for biology; watch-item for IR interop |

**Decision implication:** before buying anything beside the OT-2, prefer instruments that speak
**SiLA 2** and/or are supported by **PyLabRobot**, so the software investment survives the hardware
choice. Retargeting codegen to PyLabRobot is the highest-leverage way to make Paper2Protocol
hardware-portable.

---

## 3. LLM / AI protocol-generation peers (positions our contribution)

| System | Group | What it does | How we differ |
|---|---|---|---|
| **Coscientist** | CMU (Gomes/Boiko et al., *Nature* 2023) | GPT-4 plans + writes + executes experiments, **drove a real Opentrons** | We add a **deterministic, non-LLM acceptance gate** (`opentrons analyze` + conformance ledger). Coscientist trusts the LLM to be right; we refuse to. |
| **ChemCrow** | EPFL (*Nat. Mach. Intell.* 2024) | LLM + 18 expert chem tools for synthesis planning | Tool-augmented reasoning, not a *validated compiler*; no simulate→repair convergence gate. |
| **OpentronsAI** | Opentrons | NL → Opentrons protocol (commercial) | Generation only; **no independent validation loop, no conformance recompute, no honest automation-partition**. This is exactly the gap Paper2Protocol fills. |

**Our defensible novelty (restated):** the *closed, deterministically-gated generate→validate→repair
loop with honest automation partitioning* — not "an LLM wrote Opentrons code," which is already
commodity. Everyone above generates; almost nobody **verifies against the real engine and refuses
to fake a green run.**

---

## 4. Reference autonomous labs — and *how they learn* (the training/decision loop)

The user's ask: "others' experiments and their **learning & training process**." The layer-(C)
engine is almost never a trained neural net — it is **sequential optimization / active learning**:

- **Berkeley A-Lab** (*Nature* 2023, Ceder group). Robotic arms + furnaces + XRD, driven by
  **active learning** over DFT-predicted targets; ML analyzes XRD to decide next synthesis.
  Reported **~36 of 57 target compounds over 17 days** of continuous operation ⚠ (news release
  figure; confirm exact count against the primary Nature paper). *Lesson they published:* the hard
  part was **hardware/software glue and recovery from failed syntheses**, not the AI — they built
  some rigs (e.g. the sample-recovery shaker) from scratch. Software = **AlabOS** (§1).
- **Coscientist** (*Nature* 2023). LLM as the planner; the "training" is **in-context + tool use**,
  not fine-tuning. Demonstrated closed-loop optimization of a Pd-catalyzed reaction on real hardware.
- **Self-driving polymer lab** (arXiv 2509.05351, 2025) — **Bayesian optimization** of LCST of
  thermoresponsive polymers; canonical small-SDL loop (propose → run → measure → update surrogate).
- **Optimization engines in common use:** **Bayesian optimization** (Gryffin / Phoenics from the
  Aspuru-Guzik group; Ax/BoTorch; scikit-optimize) and **active learning** dominate the decision
  layer. LLM planners (Coscientist/ChemCrow) are the newer entrant. Takeaway: our layer-(C), when
  we add one, should likely be **BO/active-learning first**, with an LLM planner as an option — not
  an LLM by default.
- **Cloud labs** (Emerald Cloud Lab, Strateos) — remote, fully-scheduled labs; the "buy access,
  not hardware" alternative worth pricing against a $50K in-house build. ⚠ pricing model
  (per-experiment/subscription) to confirm.

---

## 5. Hardware & cost reality for the $50K decision (beside OT-2)

Ballpark capital costs (2026, secondary sources ⚠ — get quotes before committing):

| Tier / item | Indicative cost | Notes |
|---|---|---|
| **OT-2** (have/target) | **< ~$10k** | entry-tier; the reason this project is affordable at all |
| Mid-range liquid handler (Tecan EVO, Hamilton STARlet, Agilent Bravo) | **~$100k–$200k** | out of a $50K budget on its own |
| High-end (Hamilton Vantage, Tecan Fluent) | **$200k–$500k+** | not in scope |
| **Plate reader** (abs/fluor/lum; e.g. Tecan Infinite M-series — the paper already uses an M200) | ~$15k–$40k+ | the readout instrument for the chemotaxis assay's OD/optical reads |
| CO₂ **incubator** | ~$5k–$15k | live-culture steps |
| Automated **plate sealer / peeler** | ~$5k–$20k | the "seal" gate our IR already emits |
| Benchtop **centrifuge** | ~$3k–$10k | |
| Small **robotic arm** (Meca500 / UR-class) for plate transport | ~$10k–$30k | turns islands into a workcell; A-Lab-style glue |
| **Temperature Module GEN2** (OT-2) | ~$1k–$2k | already demoed in-sim on virtual hardware |

**What a $50K budget beside an OT-2 realistically buys:** *not* a second big liquid handler, but a
**workcell around the OT-2** — plate reader + incubator + sealer + small arm + modules + consumables
— i.e. the pieces that turn the OT-2 into a closed loop for *this* assay. **This is the single most
important reason the digital twin exists:** it lets us prove the workcell layout, reach, collisions,
and protocol feasibility *in simulation* before any of these are purchased.

---

## 6. Standards to design toward (so the spend survives)

- **Prefer SiLA 2 / PyLabRobot-supported instruments** → software portability across vendors.
- **Adopt a MADSci-style Node seam** for LABA → interoperable with the leading open orchestrators.
- **Keep the IR exportable** toward Autoprotocol / LabOP → not locked to Opentrons' dialect.
- **Simulate before you buy** (this repo's twin) → the cheapest possible way to catch a wrong
  hardware choice is a render, not a return-merchandise-authorization.

---

## 7. Open questions to close before a purchase order

1. Exact A-Lab result count + BOM from the primary *Nature* paper (paywalled here). ⚠
2. Emerald Cloud Lab / Strateos current pricing vs a $50K in-house workcell. ⚠
3. Which target instruments (plate reader, sealer, arm) are **PyLabRobot- or SiLA2-supported** today.
4. Does retargeting codegen to **PyLabRobot** (vs Opentrons-only) pay for itself in hardware freedom?
5. Benchmark LABA's design against **MADSci** and **UniLabOS** schemas before finalizing its Node API.

---

## 8. Sources

- MADSci — repo `github.com/AD-SDL/MADSci`; docs `ad-sdl.github.io/MADSci`; JOSS paper
  `joss.theoj.org/papers/10.21105/joss.09416.pdf`; org `github.com/AD-SDL`.
- PyLabRobot — repo `github.com/PyLabRobot/pylabrobot`; paper *Device* (Cell Press)
  `cell.com/device/fulltext/S2666-9986(23)00170-9`; preprint `biorxiv.org/content/10.1101/2023.07.10.547733v2`.
- ChemOS 2.0 — `sciencedirect.com/science/article/pii/S2590238524001954`; ChemOS (orig.)
  `ncbi.nlm.nih.gov/pmc/articles/PMC7161969/`.
- AlabOS — `sciencedirect.com/org/science/article/pii/S2635098X24001839`.
- IvoryOS — *Nat. Commun.* 2025 `nature.com/articles/s41467-025-60514-w`.
- UniLabOS — arXiv `arxiv.org/abs/2512.21766`; repo `github.com/deepmodeling/Uni-Lab-OS`.
- SDL review — *Chem. Rev.* 2024 `pubs.acs.org/doi/10.1021/acs.chemrev.4c00055` (paywalled).
- A-Lab — *Nature* 2023 `nature.com/articles/s41586-023-06734-w` (paywalled); Berkeley Lab news
  `newscenter.lbl.gov/2023/04/17/meet-the-autonomous-lab-of-the-future/`.
- Self-driving polymer LCST — arXiv `arxiv.org/html/2509.05351v1`.
- Liquid-handler cost — `excedr.com/blog/how-much-does-a-liquid-handler-cost`;
  `assay.dev/2023/10/27/on-lab-automation/`.
- Grassroots autonomous-lab network roadmap — arXiv `arxiv.org/html/2506.17510v1`.

_Cross-refs: `docs/SYSTEM_DESIGN.md` (our system + 37-source literature), `docs/SIMULATION_GUIDE.md`
(the three simulation layers), `twin/README.md` (the MuJoCo twin)._
