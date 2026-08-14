# Protocol index

Every OT-2 protocol in this repository, its source paper, and its validation state.
All of these are tracked in git — including the intermediate drafts, because the
validate→repair history is part of the evidence.

## Replicated (paper → protocol → ledger → Isaac Sim twin)

| Protocol | Source paper | `opentrons analyze` | Conformance | Twin |
|---|---|---|---|---|
| [`chemotaxis_prism/protocol.py`](chemotaxis_prism/protocol.py) | PRISM-generated chemotaxis assay (the lab's own live run) | ✅ `ok`, 0 errors, 126 cmds | — | ✅ FEASIBLE, replayed |
| [`mic_ole/protocol.py`](mic_ole/protocol.py) | Liu et al., *PLOS ONE* 17(1):e0263359 — MIC of olive leaf extract vs *L. monocytogenes* | ✅ `ok`, 0 errors, 520 cmds | ✅ **11/11** | ✅ FEASIBLE, 88 wells, 18 tips |

Full write-up: [`docs/replication-set/01-mic-ole.md`](../docs/replication-set/01-mic-ole.md)

## Queued for replication

See [`docs/replication-set/README.md`](../docs/replication-set/README.md). Papers 2–5 are on
disk in `external/`, chosen to escalate in liquid-handling difficulty:
*Piper betle* (10 µL precision) → tetrazines (multi-plate) → L-lactate (timed 3-reagent) →
pyruvate kinase (variable-volume matrix).

## Development history — PenStrep dilution series

`chemotaxis_penstrep/` is the original POC corpus and is kept whole on purpose: it shows the
deterministic validate→repair loop working, including deliberately broken protocols used to
prove the judges catch real faults.

| Path | What it is |
|---|---|
| `iterations/draft1–4.py` | successive generator drafts, incl. `draft3.py` "doctored dilution" |
| `out/live_drafts/llm_draft_1–5.py` | raw LLM output before repair |
| `out/virtual_ot2/proto-*.py` | every protocol dispatched to the simulated robot; the `M1 bad overaspirate` ones are **intentionally faulty** and must fail |
| `out/bundle/`, `out/bundle_live/`, `out/bundle_from_pdf/` | signed-off artifacts: `protocol.py` + `analysis.json` + `conformance.json` + `signoff.md` |

## Running any of them

```bash
# validate and produce the ledger
.venv/bin/python -m opentrons.cli analyze \
  --json-output examples/<name>/out/analysis.json examples/<name>/protocol.py

# check it against the paper's claims (needs a claims.json — see mic_ole)
.venv/bin/python scripts/replication_check.py \
  examples/<name>/out/analysis.json examples/<name>/claims.json

# replay it in the Isaac Sim twin
rsync -a examples/<name>/out/analysis.json \
  gear-workstation:/mnt/ssd/isaac-sim/workspace/ledgers/<name>/
ssh gear-workstation '~/isaac-twin-live.sh /workspace/ledgers/<name>/analysis.json --speed 0.6 --ui'
```

## Labware note

Protocols use standard Opentrons load names from `opentrons_shared_data` — the same library
`opentrons analyze` and the Opentrons App resolve against. For example
`corning_96_wellplate_360ul_flat` is *"Corning 96 Well Plate 360 µL Flat"* (namespace
`opentrons`, definition v5; Corning catalog 3650/3916/3915/3361/3590/9018/3596 and others;
96 wells, 6.86 mm diameter, 10.67 mm deep, 360 µL).

If your bench plate differs, swap the load name — Opentrons also ships
`corning_96_wellplate_330ul`, `nest_96_wellplate_200ul_flat`, `costar_96_wellplate_2.2ml`,
`armadillo_96_wellplate_200ul_pcr_full_skirt` and more. Changing it re-runs cleanly through
`analyze` and the twin picks up the new geometry automatically.
