#!/usr/bin/env bash
# Open the OT-2 interactive digital twin in your browser.
# Three.js is self-hosted (twin/viewer/lib) so this needs NO internet — but browsers block
# ES-module loading over file://, so we serve the folder over a tiny local http server.
#
#   ./twin/viewer/serve.sh [PORT]
set -euo pipefail
PORT="${1:-8777}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
# stop a previous server on this port, if any
lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill 2>/dev/null || true
echo "▶ serving the digital twin at http://localhost:${PORT}/ot2_digital_twin.html"
python3 -m http.server "$PORT" >/tmp/ot2_twin_http.log 2>&1 &
SRV=$!
sleep 1
open "http://localhost:${PORT}/ot2_digital_twin.html"
echo "  (server pid $SRV — press Ctrl-C to stop, or: kill $SRV)"
wait $SRV
