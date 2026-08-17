#!/usr/bin/env bash
# Run ANY Opentrons OT-2 protocol.py in Isaac Sim and stream it over WebRTC.
#
#   scripts/isaac/sim-protocol.sh <protocol.py> [speed]
#
# Does everything: validates the protocol, builds the ledger, ships it to the
# workstation, points the always-on service at it, and blocks until there is a
# real picture to connect to.
#
# The twin is driven by the protocol's ANALYSIS LEDGER, not by the .py itself --
# deck, labware, volumes and motion are all read from what the robot would
# actually do. That analyze step is the same engine that gates a real OT-2 run,
# so a protocol the robot would reject never reaches the sim.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${ISAAC_HOST:-gear-workstation}"
IP="${ISAAC_IP:-172.22.56.137}"

PY="${1:?usage: sim-protocol.sh <protocol.py> [speed]   (speed default 0.5)}"
SPEED="${2:-0.5}"
[ -f "$PY" ] || { echo "no such file: $PY" >&2; exit 1; }

# Name the run after the file, or after its folder when the file is generically
# named (protocol.py) so two papers do not collide on one ledger directory.
# printf, not echo: `basename x | tr -c ...` turns the trailing newline into a
# stray '_' and every ledger dir ends up misnamed.
_base="$(basename "$PY" .py)"
if [ "$_base" = "protocol" ] || [ "$_base" = "main" ]; then
    _base="$(basename "$(cd "$(dirname "$PY")" && pwd)")"
fi
NAME="$(printf '%s' "$_base" | tr -c 'A-Za-z0-9_-' '_')"
OUT="$(mktemp -d)/${NAME}"
mkdir -p "$OUT"

echo "==> 1/4  validating $(basename "$PY") with the Opentrons engine"
if ! "$REPO/.venv/bin/python" -m opentrons.cli analyze \
        --json-output "$OUT/analysis.json" "$PY" >"$OUT/analyze.log" 2>&1; then
    echo "ANALYZE FAILED -- the robot itself would reject this protocol:" >&2
    tail -30 "$OUT/analyze.log" >&2
    exit 1
fi

# analyze exits 0 even when the protocol errors; the verdict is inside the JSON.
"$REPO/.venv/bin/python" - "$OUT/analysis.json" <<'PY' || exit 1
import json, sys
j = json.load(open(sys.argv[1]))
errs = j.get("errors") or []
if j.get("result") != "ok" or errs:
    print(f"PROTOCOL NOT RUNNABLE (result={j.get('result')}, {len(errs)} error(s)):", file=sys.stderr)
    for e in errs[:5]:
        print("   -", e.get("detail") or e, file=sys.stderr)
    sys.exit(1)
cmds = j.get("commands", [])
lab = [(l.get("location", {}).get("slotName"), l.get("loadName")) for l in j.get("labware", [])]
pip = [(p.get("mount"), p.get("pipetteName")) for p in j.get("pipettes", [])]
print(f"    ok -- {len(cmds)} commands")
for m, n in pip:
    print(f"    pipette  {m:<5} {n}")
for s, n in sorted(lab, key=lambda x: str(x[0])):
    print(f"    slot {str(s):<3} {n}")
PY

echo "==> 2/4  shipping the ledger to $HOST"
ssh "$HOST" "mkdir -p /mnt/ssd/isaac-sim/workspace/ledgers/$NAME"
rsync -a "$OUT/analysis.json" "$HOST:/mnt/ssd/isaac-sim/workspace/ledgers/$NAME/"

echo "==> 3/4  pointing the sim at it (speed ${SPEED}x)"
ssh "$HOST" "~/isaac-service.sh run /workspace/ledgers/$NAME/analysis.json $SPEED" >/dev/null

echo "==> 4/4  waiting for the first rendered frame (~3 min; connecting early is the black screen)"
ssh "$HOST" '~/isaac-ready.sh'

echo
echo "  READY -- open the Isaac Sim WebRTC Streaming Client and connect to:  $IP"
echo "  it loops forever and resets between passes; cue a clean start with:"
echo "      ssh $HOST '~/isaac-record-cue.sh'"
echo "  change speed live, no restart:"
echo "      ssh $HOST '~/isaac-speed.sh 0.25'"
