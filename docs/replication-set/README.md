# Replication set — five papers to reproduce in the Isaac Sim twin

Five open-access papers whose wet-lab liquid handling is specified precisely enough to
regenerate as an Opentrons OT-2 protocol and replay in the twin. Chosen to *escalate* in
liquid-handling difficulty rather than repeat the same shape, so each one stresses something
the last did not.

The chemotaxis paper is deliberately excluded — already replicated and confirmed to behave as
described.

| # | Paper | Assay | What it stresses | PDF |
|---|---|---|---|---|
| 1 | Olive leaf extract MIC vs *L. monocytogenes* <br>`10.1371/journal.pone.0263359` | Broth microdilution MIC | Clean 2-fold series, uniform volumes. **Baseline.** | `plos_0263359.pdf` |
| 2 | *Piper betle* extracts vs MDR bacteria <br>`10.1371/journal.pone.0146349` | MIC + MBC | **Small-volume precision** — 10 µL inoculum into 100 µL. Near the p300's floor. | `plos_0146349.pdf` |
| 3 | Tetrazine–benzothiazoles, antibiofilm + anti-QS <br>`10.1371/journal.pone.0318135` | Microdilution + biofilm + quorum sensing | **Multi-plate, multi-reagent** — 96- *and* 48-well, four reagents, a destain step. | `plos_0318135.pdf` |
| 4 | Colorimetric L-lactate assay <br>`10.1371/journal.pone.0271818` | Enzymatic colorimetric | **Timed three-reagent sequence** with a stop reagent. Order and timing matter. | `plos_0271818.pdf` |
| 5 | Automated enzyme-kinetics assay (pyruvate kinase) <br>`10.1371/journal.pone.0010727` | Kinetic enzyme assay | **Variable-volume matrix** — 7 components, water to a fixed 225 µL, explicit dispense order. Written for a liquid-handling robot. **Hardest.** | `plos_0010727.pdf` |

## Why these five

Every one is open access, aqueous, and uses labware the OT-2 supports. Concretely verified
liquid handling:

1. **0263359** — 8 two-fold dilutions (128 → 1 mg/mL), **50 µL extract + 50 µL culture**,
   8 replicates = 64 wells, BHI broth. The canonical serial dilution.
2. **0146349** — two-fold series from 100 mg/mL in cation-adjusted MHB;
   **10 µL adjusted inoculum into 100 µL extract**. The 10 µL transfer is the interesting part:
   it is where a real robot's accuracy starts to matter.
3. **0318135** — **100 µL** MHB + 2 % glucose into first wells → serial two-fold →
   **100 µL** bacterial suspension to all but sterility controls → **40 µL** INT for MIC
   readout → **50 µL → 150 µL** fresh MHB for MBC → **150 µL** 95 % ethanol destain.
   Separate 48-well leg: **1000 µL** into first well, two-fold series, **500 µL** *C. violaceum*.
4. **0271818** — **50 µL** standard/sample + **50 µL** premixed reaction buffer → 1 h dark
   incubation → **50 µL** 1 M acetic acid stop. Standards 12 → 0.375 mmol/L.
5. **0010727** — per reaction: **62.5 µL** buffer, **0–30 µL** KCl, **0–40 µL** FBP,
   **10 µL** NADH, **0–45 µL** PEP, **10 µL** ADP+MgCl₂, **10 µL** enzyme, water to
   **225 µL**. Stable components first; the reaction is started by adding ADP last.
   NADH standard curve at **150 µL** of 1 / 0.5 / 0.25 / 0.125 mM.

## Steps the robot cannot do

Each paper contains steps outside a liquid handler's scope — incubation at 37 °C, OD/absorbance
reading, centrifugation, overnight growth. These are **not** failures; they are emitted as
labelled handoff gates in the artifact, exactly as the chemotaxis run treats its 15-minute agar
solidification. The twin replays the liquid handling and pauses at each gate.

## Verification chain

"Did it run exactly as the paper describes?" decomposes into five links. Four are machine
-checkable; one is not, and pretending otherwise would be dishonest.

| Link | How it is checked | Automatic? |
|---|---|---|
| Paper → extracted intent (IR) | Generator LLM extracts; **human confirms the methods text before the IR is frozen** | ❌ needs you |
| IR → protocol code | `loop.py` validate/repair against the real engine | ✅ |
| Protocol → ledger | `opentrons analyze` — the same engine that gates a real run | ✅ |
| Ledger → paper's declared numbers | `conformance.py` reconstructs the **actual** volume ledger (aspirate→dispense pairs), derives realized concentrations per well, compares to targets. Derived from behaviour, never by grepping code for the right literal | ✅ |
| Ledger → twin execution | The twin *is* driven by the ledger, deterministically. Verified by rendered checkpoints + state assertions | ✅ |

Because the twin replays the ledger deterministically, "did the GUI show the right run" reduces
to "does the ledger match the paper" (link 4) plus "did the twin execute the ledger faithfully"
(link 5) — and link 5 is provable with pictures.

## Monitoring in the GUI

The twin renders the real Isaac scene at chosen checkpoints from five angles
(`--snapshot DIR --snapshot-ops N`): overview, trash, plate, tubes, tip rack. Checked per run:

- **State** — wells filled, µL transferred, tips consumed from the rack, tips in the trash,
  source-tube levels. Conserved end to end (1 µL = 1 mm³).
- **Feasibility** — reachability, collisions, minimum transit clearance
  (`out/isaac_live_report.json`).
- **Pixels** — rendered images are measured, not eyeballed. Colour saturation is sampled to
  confirm reagents actually render distinctly, after a real bug where liquid rendered as clear
  glass and a state counter still reported success.

This is checkpoint verification with retained evidence, not continuous human watching — which is
the stronger form for a replication claim, because it is repeatable and produces artifacts.
