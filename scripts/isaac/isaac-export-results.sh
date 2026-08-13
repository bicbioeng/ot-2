#!/usr/bin/env bash
# Export a finished Isaac Sim run off the SSD scratch onto the spinning-disk archive.
#   ~/isaac-export-results.sh [run-name]
# SSD (/mnt/ssd) is fast scratch; /mnt/hdd is the 25.5 TB archive. Copy-then-verify,
# never move: nothing is deleted from the SSD by this script.
set -euo pipefail
SSD=/mnt/ssd/isaac-sim
HDD=/mnt/hdd/isaac-sim-results
RUN="${1:-run-$(date +%Y%m%d-%H%M%S)}"
DEST="$HDD/$RUN"

echo "== exporting Isaac run -> $DEST =="
mkdir -p "$DEST"

# what a run produces that is worth keeping
for src in "$SSD/workspace/out" "$SSD/workspace/ledgers" "$SSD/workspace/twin" "$SSD/logs"; do
  [ -d "$src" ] || continue
  name=$(basename "$src")
  echo "  copying $name ..."
  rsync -a --info=stats1 "$src/" "$DEST/$name/" 2>/dev/null || rsync -a "$src/" "$DEST/$name/"
done

# provenance: what produced this run
{
  echo "run:        $RUN"
  echo "exported:   $(date -Is)"
  echo "host:       $(hostname)"
  echo "gpu:        $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null)"
  echo "image:      $(docker inspect isaac-twin --format "{{.Config.Image}}" 2>/dev/null || echo n/a)"
  echo "cmd:        $(docker inspect isaac-twin --format "{{join .Config.Cmd \" \"}}" 2>/dev/null || echo n/a)"
} > "$DEST/RUN_INFO.txt"

echo "== verify =="
S=$(du -sb "$DEST" 2>/dev/null | cut -f1)
echo "  archived bytes: $S"
find "$DEST" -maxdepth 2 -type d | head -12
echo "  report:"; cat "$DEST/out/isaac_live_report.json" 2>/dev/null | head -12 || echo "  (no report yet)"
echo "== DONE -> $DEST (SSD copy left intact) =="
