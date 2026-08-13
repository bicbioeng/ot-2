#!/usr/bin/env bash
# Migrate docker data-root from nvme (/var/lib/docker) to SSD (/mnt/ssd/docker).
# Run ONCE with sudo. Nothing is running (only exited containers) -> safe window.
# Non-destructive: old /var/lib/docker is LEFT IN PLACE until we verify, then you rm it.
set -euo pipefail
OLD=/var/lib/docker
NEW=/mnt/ssd/docker
TS=$(date +%Y%m%d-%H%M%S)

echo "== pre-flight =="
echo -n "  images now: "; docker images -q | wc -l
echo -n "  containers (all): "; docker ps -aq | wc -l
echo "  SSD free:"; df -h /mnt/ssd | tail -1
echo "  old store size:"; du -sh "$OLD" 2>/dev/null | awk "{print \$1}"

echo "== stop docker =="
systemctl stop docker docker.socket
sleep 2
if pgrep -x dockerd >/dev/null; then echo "  ERROR: dockerd still running, aborting"; exit 1; fi
echo "  stopped."

echo "== rsync $OLD -> $NEW (preserving hardlinks/ACLs/xattrs) =="
mkdir -p "$NEW"
rsync -aHAX --numeric-ids --info=progress2 "$OLD"/ "$NEW"/
echo "  rsync complete."

echo "== repoint daemon.json (preserving nvidia runtime) =="
cp -a /etc/docker/daemon.json "/etc/docker/daemon.json.bak-$TS"
python3 - << PY
import json
p="/etc/docker/daemon.json"
d=json.load(open(p))
d["data-root"]="$NEW"
json.dump(d, open(p,"w"), indent=4)
print(open(p).read())
PY
echo "  backup saved: /etc/docker/daemon.json.bak-$TS"

echo "== start docker =="
systemctl start docker
sleep 3

echo "== VERIFY =="
echo -n "  data-root now: "; docker info --format "{{.DockerRootDir}}"
echo -n "  images visible: "; docker images -q | wc -l
echo "  nvidia runtime present: "; docker info --format "{{.Runtimes}}" | grep -o nvidia || echo "    MISSING!"
echo "  nvme free now:"; df -h / | tail -1
echo "  ssd free now:"; df -h /mnt/ssd | tail -1
echo
echo "== NEXT: if data-root=/mnt/ssd/docker and images count looks right (~37),"
echo "   reclaim the nvme later with:  sudo rm -rf /var/lib/docker  (kept for now)"
echo "== DONE =="
