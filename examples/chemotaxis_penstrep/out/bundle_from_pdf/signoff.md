# Wet-lab sign-off — PenStrep Dilution Series for E. coli Chemotaxis Assay

**Paper:** Agar loaded with chemicals as a drug-releasing mechanism for E. coli negative chemotaxis
**Status:** CONVERGED (all gates passed at iteration 2)

> The automated gates (static + opentrons analyze + conformance) have passed. That means the protocol is API-legal, simulates clean, and realizes the extracted spec. It does **not** mean it is safe to run. A wet-lab-literate reviewer must confirm the items below before the protocol is dispatched to the robot.

## Realized concentrations (from the command ledger)

| well | v/v | penicillin_U_per_mL |
|---|---|---|
| A1 | 0% | 0.0 |
| A2 | 15% | 1500.0 |
| A3 | 25% | 2500.0 |

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
