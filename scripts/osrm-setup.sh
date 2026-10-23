#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OSM_DIR="$ROOT/data/osm"
PBF="$OSM_DIR/bizerte.osm.pbf"
IMAGE="${OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend:v26.9.0-debian}"  # keep in sync with docker-compose.yml

# Git Bash on Windows: give Docker a Windows path and stop MSYS rewriting /data.
if command -v cygpath >/dev/null; then OSM_MOUNT="$(cygpath -w "$OSM_DIR")"; export MSYS_NO_PATHCONV=1; else OSM_MOUNT="$OSM_DIR"; fi

if [[ ! -f "$PBF" ]]; then
  echo "Missing $PBF" >&2
  exit 1
fi

docker run --rm -v "$OSM_MOUNT:/data" "$IMAGE" osrm-extract -p /opt/car.lua /data/bizerte.osm.pbf
docker run --rm -v "$OSM_MOUNT:/data" "$IMAGE" osrm-partition /data/bizerte.osrm
docker run --rm -v "$OSM_MOUNT:/data" "$IMAGE" osrm-customize /data/bizerte.osrm

echo "Bizerte OSRM graph prepared."
