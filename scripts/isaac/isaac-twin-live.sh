#!/usr/bin/env bash
# Launch the LIVE OT-2 twin. Arg1 = ledger (in-container). Extra args pass through.
set -euo pipefail
IMG=nvcr.io/nvidia/isaac-sim:5.0.0
NAME=isaac-twin
SSD=/mnt/ssd/isaac-sim
LEDGER="${1:-/workspace/ledgers/chemotaxis_prism/analysis.json}"
shift || true
EXTRA=("$@")
docker rm -f isaac-sim isaac-twin >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  --runtime=nvidia --gpus all --network=host --shm-size=2g --restart no \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e OMNI_KIT_ALLOW_ROOT=1 \
  -v "$SSD/cache/main":/isaac-sim/.cache:rw \
  -v "$SSD/cache/computecache":/isaac-sim/.nv/ComputeCache:rw \
  -v "$SSD/cache/hub":/var/cache/hub:rw \
  -v "$SSD/logs":/isaac-sim/.nvidia-omniverse/logs:rw \
  -v "$SSD/config":/isaac-sim/.nvidia-omniverse/config:rw \
  -v "$SSD/data":/isaac-sim/.local/share/ov/data:rw \
  -v "$SSD/workspace":/workspace:rw \
  --entrypoint /isaac-sim/python.sh \
  "$IMG" \
  /workspace/twin/isaac_twin_live.py \
    --ledger "$LEDGER" \
    --twin-root /workspace --assets /workspace/twin/assets/ot2 \
    --labware /workspace/twin/assets/labware --chassis \
    "${EXTRA[@]}" \
    --/rtx/verifyDriverVersion/enabled=false
echo "launched $NAME  ledger=$LEDGER  extra=${EXTRA[*]:-none}"
