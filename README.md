# Paper2Protocol

Ingest a scientific paper (PDF) → a generator LLM writes an Opentrons protocol → **Claude Code drives a deterministic validate→repair loop whose sole acceptance authority is the real `opentrons analyze` engine (never an LLM)** → a validated artifact staged for human wet-lab sign-off.

Part of **LABA** (the Lab Automation pillar of Lab AI-OS). Design & adversarial review: `~/.claude/plans/sorted-floating-engelbart.md`.

## Locked scope (v1 POC)
- **Robot job = aqueous only**: PenStrep dilution series + OD-based culture normalization. Everything touching agar/the plate is external (human or other robot), emitted as labeled handoff gates.
- **Generator** = configurable, default non-Claude (Gemini 3 Pro / GPT codex). Claude Code = validator/corrector. **`loop.py`** = deterministic accept/block gate.
- **Input** = PDF, with an extracted-methods-text human confirm before the IR is frozen.
- Demo n=1 = the E. coli negative-chemotaxis / PenStrep paper.

## Layout
```
schemas/        IR + critic JSON schemas
src/paper2protocol/
  extract.py triage.py ir.py codegen.py
  static_checks.py simulate.py conformance.py critic.py loop.py
  providers/ record_replay.py artifact.py cli.py
data/allowlists/  verified labware load-names + admissible Opentrons API
captured/         golden analysis.json + the empirically-verified analyze contract (M1)
examples/chemotaxis_penstrep/  the demo paper + golden IR + fixtures
tests/            unit tests + injected-bug corpus + prompt-injection test
```

## Judges-first build (M0→M8)
The deterministic judges (simulate / static / conformance) are built and proven **before** any LLM is trusted. See the plan.

## Quickstart (deterministic core; no LLM keys needed)
```bash
uv sync                                   # installs opentrons + core (python 3.10 via uv)
uv run python scripts/capture_contract.py # M1: dump the real analyze contract + golden JSON
uv run pytest                             # the deterministic judges
```

## OT-2 Digital Twin (NVIDIA Isaac Sim)

A live 3D twin that replays any validated protocol on the real Opentrons OT-2 CAD and reports
whether the run is physically executable (reachability, collisions, clearance) before anyone
touches the robot. Liquid handling is volumetric and conserved.

**→ [docs/isaac-twin/README.md](docs/isaac-twin/README.md)** — install, run, run your own
protocol, regenerate the CAD assets, troubleshooting.

```bash
# reference example: the PRISM chemotaxis run
ssh gear-workstation '~/isaac-twin-live.sh /workspace/ledgers/chemotaxis_prism/analysis.json --speed 0.6 --ui'
# then point the Isaac Sim WebRTC client at 172.22.56.137
```
