#!/usr/bin/env bash
# One command: run the OT-2 Isaac Sim twin on the gear-triad and get the video on your Mac.
#
#   ./twin/run_isaac_remote.sh [LEDGER] [GPU] [MAX_FRAMES]
#
# It (1) syncs the twin code + the real OT-2 asset to the triad, (2) runs Isaac Sim 5.1
# headless in the container on a chosen GPU, (3) pulls the RGB frames + report back,
# (4) encodes an mp4 locally, and (5) opens it. Isaac has no macOS build, so the render
# must happen on the triad's RTX A6000 — this script hides all of that.
#
# Prereqs (already true on this machine): ssh host alias `gear-triad`, the twin/.venv with
# imageio, and the isaac-sim:5.1.0 image present on the triad. Nothing else to set up.
set -euo pipefail

# ---- args & config ----
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # repo root (…/paper2protocol)
LEDGER="${1:-$HERE/examples/chemotaxis_penstrep/out/bundle_live/analysis.json}"
GPU="${2:-2}"                                                    # host GPU to pin (avoid busy ones)
MAX_FRAMES="${3:-240}"                                           # motion is interpolated to ~this many frames
WIDTH="${WIDTH:-1280}"; HEIGHT="${HEIGHT:-720}"; FPS="${FPS:-30}"
HOST="gear-triad"; REMOTE="p2p-twin"                            # ssh alias + remote workspace dir
IMG="nvcr.io/nvidia/isaac-sim:5.1.0"
SSH=(ssh -o ConnectTimeout=20 -o ServerAliveInterval=8 -o ServerAliveCountMax=6 "$HOST")
PY="$HERE/twin/.venv/bin/python"
OUT_LOCAL="$HERE/twin/out"
STAMP="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo run)"
MP4="$OUT_LOCAL/isaac_ot2_${STAMP}.mp4"

say(){ printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

[ -f "$LEDGER" ] || { echo "ledger not found: $LEDGER"; exit 1; }

# ---- 1. show which GPU is free ----
say "GPU status on $HOST (using GPU $GPU):"
"${SSH[@]}" 'nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader'

# ---- 2. sync code + assets + this run's ledger (tar over ssh; robust on flaky links) ----
say "Syncing twin code + real OT-2 asset to $HOST:~/$REMOTE …"
tar cf - -C "$HERE/twin" isaac_twin.py deck.py chem.py ot2_model.py __init__.py decks assets \
  | "${SSH[@]}" "mkdir -p ~/$REMOTE/twin && tar xf - -C ~/$REMOTE/twin"
tar cf - -C "$(dirname "$LEDGER")" "$(basename "$LEDGER")" \
  | "${SSH[@]}" "mkdir -p ~/$REMOTE/ledgers/run && tar xf - -C ~/$REMOTE/ledgers/run"

# ---- 3. run Isaac in the container on the triad ----
say "Running Isaac Sim twin on $HOST (GPU $GPU, ${WIDTH}x${HEIGHT}, ~${MAX_FRAMES} frames) …"
"${SSH[@]}" bash -s -- "$GPU" "$MAX_FRAMES" "$WIDTH" "$HEIGHT" "$REMOTE" "$IMG" <<'REMOTE_EOF'
set -euo pipefail
GPU="$1"; MAX="$2"; W="$3"; H="$4"; REMOTE="$5"; IMG="$6"
cd "$HOME/$REMOTE"
# Wipe the whole out/ fresh: the container writes as uid 1234 (isaac-sim), so a recursive
# chmod of leftover files fails ("Operation not permitted") and would abort the run. We own
# the out/ directory, so we can delete its uid-1234 contents, then chmod only the fresh dirs.
rm -rf out && mkdir -p out/isaac_frames && chmod 777 out out/isaac_frames
docker rm -f p2p-isaac-run >/dev/null 2>&1 || true   # clear any leftover container (name reuse)
docker run --rm --gpus "device=${GPU}" --shm-size=2g --network=host \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e OMNI_KIT_ACCEPT_EULA=YES \
  -v "$HOME/$REMOTE":/workspace --entrypoint /isaac-sim/python.sh \
  --name p2p-isaac-run "$IMG" \
  /workspace/twin/isaac_twin.py \
    --ledger /workspace/ledgers/run/analysis.json \
    --twin-root /workspace --assets /workspace/twin/assets/ot2 \
    --out /workspace/out/isaac_frames --report /workspace/out/isaac_report.json \
    --gpu 0 --chassis --max-frames "$MAX" --width "$W" --height "$H" \
  > out/isaac_run.log 2>&1 || true
grep -E "chassis:|rendered frame [0-9]+0/|ISAAC_TWIN_DONE|collisions:" out/isaac_run.log || true
[ -f out/isaac_report.json ] || { echo "ERROR: Isaac produced no report — last log lines:"; tail -20 out/isaac_run.log; exit 1; }
REMOTE_EOF

# ---- 4. pull frames + report back ----
say "Pulling frames + report to your Mac …"
rm -rf "$OUT_LOCAL/isaac/isaac_frames"; mkdir -p "$OUT_LOCAL/isaac"
"${SSH[@]}" "cd ~/$REMOTE/out && tar cf - isaac_frames isaac_report.json" | tar xf - -C "$OUT_LOCAL/isaac"
N=$(ls "$OUT_LOCAL/isaac/isaac_frames" | grep -ic '\.png$' || echo 0)
say "Report:"; cat "$OUT_LOCAL/isaac/isaac_report.json"; echo

# ---- 5. encode + open ----
say "Encoding $N frames → $MP4 @ ${FPS}fps …"
"$PY" "$OUT_LOCAL/encode_isaac.py" "$OUT_LOCAL/isaac/isaac_frames" "$MP4" "$FPS"
open "$MP4" 2>/dev/null || true
say "Done → $MP4"
