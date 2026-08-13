#!/usr/bin/env bash
# Live digital twin: run the MuJoCo (Metal) sim and watch it drive the browser scene in real time.
# Starts (1) the static page server and (2) the MuJoCo WebSocket stream, then opens the browser.
# Click the red "● LIVE" button in the page to connect to the running sim.
#
#   ./twin/viewer/live.sh [LEDGER] [STATIC_PORT] [WS_PORT]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LEDGER="${1:-$ROOT/examples/chemotaxis_penstrep/out/bundle_live/analysis.json}"
SPORT="${2:-8777}"; WPORT="${3:-8781}"
PY="$ROOT/twin/.venv/bin/python"

# free the ports if a previous run left something behind
for p in "$SPORT" "$WPORT"; do lsof -ti tcp:"$p" 2>/dev/null | xargs kill 2>/dev/null || true; done
sleep 1

echo "▶ static page  → http://localhost:${SPORT}/ot2_digital_twin.html"
( cd "$HERE" && python3 -m http.server "$SPORT" >/tmp/ot2_static.log 2>&1 ) &
STATIC=$!
echo "▶ MuJoCo·Metal live stream → ws://localhost:${WPORT}"
( cd "$ROOT" && "$PY" -m twin.viewer.live_server "$LEDGER" --port "$WPORT" >/tmp/ot2_live.log 2>&1 ) &
LIVE=$!

cleanup(){ echo; echo "stopping…"; kill "$STATIC" "$LIVE" 2>/dev/null || true; exit 0; }
trap cleanup INT TERM
sleep 2
open "http://localhost:${SPORT}/ot2_digital_twin.html"
echo
echo "  In the page, click the red ●LIVE button (bottom bar) to stream the running MuJoCo sim."
echo "  Ctrl-C here stops both servers.   logs: /tmp/ot2_live.log  /tmp/ot2_static.log"
wait
