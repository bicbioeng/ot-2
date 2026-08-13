#!/usr/bin/env bash
# Change the running sim speed WITHOUT restarting.  ~/isaac-speed.sh 0.25
set -euo pipefail
S="${1:?usage: isaac-speed.sh <multiplier>  e.g. 0.25 = quarter speed, 2 = double}"
F=/mnt/ssd/isaac-sim/workspace/out/speed.json
mkdir -p "$(dirname "$F")"
printf "{\"speed\": %s}\n" "$S" > "$F"
chmod 666 "$F" 2>/dev/null || true
echo "speed -> ${S}x (picked up within ~half a second)"
