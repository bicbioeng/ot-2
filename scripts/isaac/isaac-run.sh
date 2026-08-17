#!/usr/bin/env bash
# Run ANY Opentrons OT-2 protocol.py in Isaac Sim and stream it over WebRTC.
# Lives on gear-workstation as ~/isaac-run.sh
#
#   ~/isaac-run.sh <protocol.py> [speed]
#
# Nothing needs to be installed locally: the protocol is analysed inside the
# ot-analyze container (the workstation's own Python is 3.8, too old for the
# Opentrons package). The twin is driven by the protocol's ANALYSIS LEDGER, not
# by the .py — that analyze step is the same engine that gates a real OT-2 run,
# so a protocol the robot would reject never reaches the sim.
set -euo pipefail
IP=172.22.56.137

PY="${1:?usage: isaac-run.sh <protocol.py> [speed]   (speed default 0.5)}"
SPEED="${2:-0.5}"
[ -f "$PY" ] || { echo "no such file: $PY" >&2; exit 1; }
PYDIR="$(cd "$(dirname "$PY")" && pwd)"
PYFILE="$(basename "$PY")"

# Name the run after the file, or its folder when generically named, so two
# papers cannot collide on one ledger directory.
BASE="$(basename "$PYFILE" .py)"
case "$BASE" in protocol|main) BASE="$(basename "$PYDIR")";; esac
NAME="$(printf '%s' "$BASE" | tr -c 'A-Za-z0-9_-' '_')"
DEST="/mnt/ssd/isaac-sim/workspace/ledgers/$NAME"

echo "==> 1/4  validating $PYFILE with the Opentrons engine"
mkdir -p "$DEST"
if ! docker run --rm -v "$PYDIR":/work:ro -v "$DEST":/out ot-analyze:latest \
        analyze --json-output /out/analysis.json "/work/$PYFILE" \
        >"/tmp/analyze.$$.log" 2>&1; then
    echo "ANALYZE FAILED -- the robot itself would reject this protocol:" >&2
    tail -25 "/tmp/analyze.$$.log" >&2
    exit 1
fi

# analyze exits 0 even when the protocol errors; the verdict is inside the JSON.
python3 "$(dirname "$0")/.isaac-run-check.py" "$DEST/analysis.json" || exit 1

chmod -R 777 "$DEST" 2>/dev/null || true
echo "==> 2/4  ledger stored at $DEST"
echo "==> 3/4  pointing the sim at it (speed ${SPEED}x)"
"$HOME/isaac-service.sh" run "/workspace/ledgers/$NAME/analysis.json" "$SPEED" >/dev/null
echo "==> 4/4  waiting for the first rendered frame (~3 min; connecting early is the black screen)"
"$HOME/isaac-ready.sh"
echo
echo "  READY -- open the Isaac Sim WebRTC Streaming Client and connect to:  $IP"
echo "  clean start for recording:  ~/isaac-record-cue.sh"
echo "  change speed live:          ~/isaac-speed.sh 0.25"
