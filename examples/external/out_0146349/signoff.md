# Wet-lab sign-off — Broth Microdilution and Cytotoxicity Assay Serial Dilution

**Paper:** Piper betle Extracts and Multiple Drug Resistant Bacteria
**Status:** BLOCKED (hit iteration cap (5) without converging)

> The automated gates (static + opentrons analyze + conformance) have passed. That means the protocol is API-legal, simulates clean, and realizes the extracted spec. It does **not** mean it is safe to run. A wet-lab-literate reviewer must confirm the items below before the protocol is dispatched to the robot.

## Realized concentrations (from the command ledger)

| well | v/v | mg_per_ml |
|---|---|---|
| A1 | 100% | 100.0 |
| A2 | 50% | 50.0 |
| A3 | 25% | 25.0 |
| A4 | 12% | 12.5 |
| A5 | 6% | 6.25 |
| A6 | 3% | 3.125 |
| A7 | 2% | 1.5625 |
| A8 | 1% | 0.7812 |

## Reviewer checklist (blocking)
- [ ] Dilution series matches the paper's intent (0 / 15 / 25 %).
- [ ] Concentration **basis + units** confirmed (v/v of the 10,000 U/mL stock vs. the abstract's 1500 / 2500 / 10,000 U/mL framing).
- [ ] Assay plate identity confirmed (12-well vs 24-well).
- [ ] Transfer volumes are plausible for the chosen labware.
- [ ] Culture OD normalization is in the linear regime; instrument/pathlength recorded.
- [ ] **Sterility:** OT-2 in an enclosure/HEPA for live-culture steps; sterile single-use labware; reservoirs covered; negative (uninoculated) control well present.
- [ ] External handoffs understood: agar melt/cast, culture add, seal, incubate, imaging are done off the OT-2.

**Reviewer:** ______________________   **Date:** ____________   **Signature:** ____________

_Only after every box is checked should the protocol be dispatched to the robot._
