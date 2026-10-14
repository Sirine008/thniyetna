#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OSM_DIR="$ROOT/data/osm"
PBF="$OSM_DIR/bizerte.osm.pbf"
IMAGE="${OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend:latest}"

if [[ ! -f "$PBF" ]]; then
  echo "Missing $PBF" >&2
  exit 1
fi

docker run --rm -v "$OSM_DIR:/data" "$IMAGE" osrm-extract -p /opt/car.lua /data/bizerte.osm.pbf
docker run --rm -v "$OSM_DIR:/data" "$IMAGE" osrm-partition /data/bizerte.osrm
docker run --rm -v "$OSM_DIR:/data" "$IMAGE" osrm-customize /data/bizerte.osrm

echo "Bizerte OSRM graph prepared."
