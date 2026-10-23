#!/usr/bin/env bash
# Rebuild data/osm/bizerte.osm.pbf for the whole Bizerte governorate (TN-23), then the OSRM graph.
#
# The earlier extract covered only part of the governorate and RN11 was cut, so Menzel Bourguiba,
# Tinja, Mateur and Ras Jebel could not be routed from Bizerte. This clips the Geofabrik Tunisia
# extract (data/external/m2/tunisia-latest.osm.pbf, see data/external/m2/README.md) to the TN-23
# polygon stored in admin_areas, buffered by 2 km so roads crossing the border stay connected
# (osmium "complete_ways" keeps every way that touches the polygon whole).
#
# Needs: the stack's db container (admin_areas loaded by M2 ingest) and Docker.
# Then:  docker compose ... restart osrm
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OSM_DIR="$ROOT/data/osm"
SRC_DIR="$ROOT/data/external/m2"
SRC="tunisia-latest.osm.pbf"
BUFFER_M="${BUFFER_M:-2000}"
DB_CONTAINER="${DB_CONTAINER:-thniyetna-db}"
# Must match the osrm service image in docker-compose.yml (OSRM refuses files from another version).
OSRM_IMAGE="${OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend:v26.9.0-debian}"
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep /data paths as-is

[[ -f "$SRC_DIR/$SRC" ]] || { echo "Missing $SRC_DIR/$SRC" >&2; exit 1; }
win() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else echo "$1"; fi; }

echo "1/3 TN-23 polygon (+${BUFFER_M} m) from admin_areas"
docker exec "$DB_CONTAINER" psql -U thniyetna -d thniyetna -tAc "
  SELECT json_build_object('type','Feature','properties',json_build_object('code','TN-23'),
         'geometry',ST_AsGeoJSON(ST_SimplifyPreserveTopology(
             ST_Buffer(geom::geography, ${BUFFER_M})::geometry, 0.0005))::json)
  FROM admin_areas WHERE code='TN-23'" > "$SRC_DIR/tn23_buffer.geojson"
[[ -s "$SRC_DIR/tn23_buffer.geojson" ]] || { echo "TN-23 polygon not found in admin_areas" >&2; exit 1; }

echo "2/3 osmium extract (Debian osmium-tool)"
docker run --rm -v "$(win "$SRC_DIR"):/src:ro" -v "$(win "$OSM_DIR"):/out" debian:bookworm-slim sh -c "
  apt-get update -qq >/dev/null && apt-get install -y -qq osmium-tool >/dev/null &&
  osmium extract --overwrite -s complete_ways -p /src/tn23_buffer.geojson -o /out/bizerte.osm.pbf /src/$SRC &&
  osmium fileinfo /out/bizerte.osm.pbf | sed -n '1,12p'"

echo "3/3 OSRM graph ($OSRM_IMAGE)"
OSRM_IMAGE="$OSRM_IMAGE" bash "$ROOT/scripts/osrm-setup.sh"
