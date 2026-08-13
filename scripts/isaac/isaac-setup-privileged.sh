#!/usr/bin/env bash
# Isaac Sim 6.0.1 privileged setup — run ONCE with sudo. Idempotent + read-only report.
set -uo pipefail
echo "==================== [1/3] add sandesh to docker group ===================="
if id -nG sandesh | tr " " "\n" | grep -qx docker; then
  echo "  already in docker group"
else
  usermod -aG docker sandesh && echo "  added (takes effect on sandesh next login)"
fi

echo "==================== [2/3] create SSD + HDD dirs (owned by sandesh) ========"
install -d -o sandesh -g sandesh \
  /mnt/ssd/isaac-sim \
  /mnt/ssd/isaac-sim/cache/main \
  /mnt/ssd/isaac-sim/cache/computecache \
  /mnt/ssd/isaac-sim/cache/hub \
  /mnt/ssd/isaac-sim/logs \
  /mnt/ssd/isaac-sim/config \
  /mnt/ssd/isaac-sim/data \
  /mnt/ssd/isaac-sim/pkg \
  /mnt/ssd/isaac-sim/documents \
  /mnt/ssd/isaac-sim/outputs \
  /mnt/hdd/isaac-sim-results
echo "  created: /mnt/ssd/isaac-sim/{cache,logs,config,data,pkg,documents,outputs} + /mnt/hdd/isaac-sim-results"

echo "==================== [3/3] docker storage report (no changes) ============="
DR=$(docker info --format "{{.DockerRootDir}}" 2>/dev/null || echo /var/lib/docker)
echo "  data-root: $DR"
echo "  data-root filesystem:"; df -h "$DR" | tail -1
echo -n "  data-root current size: "; du -sh "$DR" 2>/dev/null | awk "{print \$1}"
echo "  existing images:"; docker images --format "    {{.Repository}}:{{.Tag}}  {{.Size}}" 2>/dev/null | sed "s/^/  /" ; [ -z "$(docker images -q 2>/dev/null)" ] && echo "    (none)"
echo "  containers (all, any user):"; docker ps -a --format "    {{.Names}}  [{{.Image}}]  {{.Status}}" 2>/dev/null ; [ -z "$(docker ps -aq 2>/dev/null)" ] && echo "    (none)"
echo "  nvcr.io login cached (root): "; grep -q nvcr.io /root/.docker/config.json 2>/dev/null && echo "    yes" || echo "    no"
echo "==================== DONE ===================="
