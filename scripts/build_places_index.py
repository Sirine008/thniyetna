"""Build the destination search index (table `places`, Alembic 0007) from the clipped TN-23 extract.

    ml/.venv/Scripts/python.exe -X utf8 scripts/build_places_index.py              # rebuild the table
    ml/.venv/Scripts/python.exe -X utf8 scripts/build_places_index.py --dry-run    # counts only, no DB

Reads data/osm/bizerte.osm.pbf (scripts/osm-clip-bizerte.sh) with pyosmium and keeps:
  * named places: city / town / village / hamlet / suburb / quarter / neighbourhood / locality
  * named streets: highway ways with a name; the ways of one street (same name, < 1 km apart) are
    merged into one entry, located at the middle of its longest way
  * main POIs: hospitals / clinics, schools / universities, town halls / administrations / police /
    post offices, railway and bus stations, ports / marinas
Each entry gets its display name (name:fr preferred), Arabic name, the normalised search key of every
name variant (routing/places_index.py, same function as the API), a category and a point.
Only points inside TN-23 (admin_areas, 300 m tolerance for the coast) are kept; `locality` is then
the nearest town / village. The table is replaced in one transaction (idempotent).
Needs DATABASE_URL (host DB: postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5433/thniyetna).
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from routing.places_index import CATEGORY_FR, CATEGORY_RANK, PLACE_TYPES, classify, names, search_key  # noqa: E402

PBF = ROOT / "data" / "osm" / "bizerte.osm.pbf"
STREET_MERGE_M = 1000   # ways of the same street name closer than this are one street
POI_DEDUP_M = 300       # same name + category (node and building of one hospital) -> one entry
PLACE_DEDUP_M = 3000    # a town mapped as a node and as a polygon -> one entry
TN23_TOLERANCE_M = 300
LOCALITY_CATEGORIES = ("city", "town", "village", "suburb")
PLACE_CATEGORIES = set(PLACE_TYPES.values())


def _dist_m(a, b):
    k = 111320.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[0] - b[0]) * 110540.0, (a[1] - b[1]) * k)


def _line_middle(points):
    """(point at half the length of the polyline, length in m)."""
    seg = [_dist_m(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(seg)
    half, run = total / 2, 0.0
    for i, d in enumerate(seg):
        if run + d >= half and d > 0:
            t = (half - run) / d
            return (points[i][0] + t * (points[i + 1][0] - points[i][0]),
                    points[i][1] + t * (points[i + 1][1] - points[i][1])), total
        run += d
    return points[len(points) // 2], total


def entry(osm_type, osm_id, tags, category, lat, lon):
    found = names(tags)
    if not found:
        return None
    name, name_ar, variants = found
    return {"osm_type": osm_type, "osm_id": osm_id, "name": name, "name_ar": name_ar,
            "name_norm": search_key(variants), "category": category,
            "rank": CATEGORY_RANK.get(category, 0), "lat": lat, "lon": lon}


def merge_streets(ways):
    """One entry per street: ways with the same search key are merged when < STREET_MERGE_M apart
    (single linkage, longest first); the entry is the middle of the longest way of the group."""
    by_name = defaultdict(list)
    for w in ways:
        by_name[w["name_norm"]].append(w)
    out = []
    for group in by_name.values():
        clusters = []
        for w in sorted(group, key=lambda x: -x["length_m"]):
            home = next((c for c in clusters if any(_dist_m((w["lat"], w["lon"]), (m["lat"], m["lon"])) < STREET_MERGE_M
                                                     or _ends_touch(w, m) for m in c)), None)
            if home is None:
                clusters.append([w])
            else:
                home.append(w)
        out += [{k: v for k, v in c[0].items() if k not in ("length_m", "ends")} for c in clusters]
    return out


def _ends_touch(a, b):
    return any(_dist_m(p, q) < 50 for p in a["ends"] for q in b["ends"])


def dedup(points):
    """Drop a point with the same search key and category as a kept one within POI_DEDUP_M (PLACE_DEDUP_M
    for towns, villages...). Place nodes first (the usual centre point), polygons first for POIs."""
    kept = defaultdict(list)
    out = []
    for p in sorted(points, key=lambda x: (x["osm_type"] == "n") != (x["category"] in PLACE_CATEGORIES)):
        key = (p["name_norm"], p["category"])
        radius = PLACE_DEDUP_M if p["category"] in PLACE_CATEGORIES else POI_DEDUP_M
        if any(_dist_m((p["lat"], p["lon"]), (k["lat"], k["lon"])) < radius for k in kept[key]):
            continue
        kept[key].append(p)
        out.append(p)
    return out


def extract(pbf: Path):
    import osmium
    from shapely import wkb as shp_wkb

    wkbfab = osmium.geom.WKBFactory()

    class Handler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.points, self.ways = [], []

        def node(self, n):
            category = classify(n.tags)
            if category and category != "street" and n.location.valid():
                e = entry("n", n.id, n.tags, category, n.location.lat, n.location.lon)
                if e:
                    self.points.append(e)

        def way(self, w):
            category = classify(w.tags)
            if not category or (category != "street" and w.is_closed()):
                return  # closed POI / place polygons come through area()
            pts = [(nd.lat, nd.lon) for nd in w.nodes if nd.location.valid()]
            if len(pts) < 2:
                return
            (lat, lon), length = _line_middle(pts)
            e = entry("w", w.id, w.tags, category, lat, lon)
            if e and category == "street":
                self.ways.append({**e, "length_m": length, "ends": (pts[0], pts[-1])})
            elif e:
                self.points.append(e)

        def area(self, a):
            category = classify(a.tags)
            if not category or category == "street":
                return
            try:
                c = shp_wkb.loads(wkbfab.create_multipolygon(a), hex=True).representative_point()
            except Exception:  # broken polygon
                return
            e = entry("w" if a.from_way() else "r", a.orig_id(), a.tags, category, c.y, c.x)
            if e:
                self.points.append(e)

    h = Handler()
    h.apply_file(str(pbf), locations=True)
    return dedup(h.points) + merge_streets(h.ways)


LOAD_SQL = """
  INSERT INTO places (osm_type, osm_id, name, name_ar, name_norm, category, rank, geom)
  SELECT t.osm_type, t.osm_id, t.name, t.name_ar, t.name_norm, t.category, t.rank, t.geom
  FROM places_load t
  WHERE NOT EXISTS (SELECT 1 FROM admin_areas WHERE code = 'TN-23')
     OR EXISTS (SELECT 1 FROM admin_areas a WHERE a.code = 'TN-23'
                AND ST_DWithin(a.geom::geography, t.geom::geography, %(tol)s))
  ON CONFLICT (osm_type, osm_id) DO NOTHING
"""
LOCALITY_SQL = """
  UPDATE places p SET locality = (
    SELECT t.name FROM places t WHERE t.category = ANY(%(cats)s) AND t.id <> p.id
    ORDER BY t.geom <-> p.geom LIMIT 1)
  WHERE p.category NOT IN ('city', 'town')
"""


def load(rows, database_url: str):
    import psycopg

    url = database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        has_tn23 = cur.execute("SELECT count(*) FROM admin_areas WHERE code = 'TN-23'").fetchone()[0]
        cur.execute("""CREATE TEMP TABLE places_load (osm_type char(1), osm_id bigint, name text, name_ar text,
                       name_norm text, category text, rank smallint, geom geometry(Point,4326)) ON COMMIT DROP""")
        with cur.copy("COPY places_load FROM STDIN") as copy:
            for r in rows:
                copy.write_row((r["osm_type"], r["osm_id"], r["name"], r["name_ar"], r["name_norm"], r["category"],
                                r["rank"], f"SRID=4326;POINT({r['lon']} {r['lat']})"))
        cur.execute("TRUNCATE places RESTART IDENTITY")
        cur.execute(LOAD_SQL, {"tol": TN23_TOLERANCE_M})
        cur.execute(LOCALITY_SQL, {"cats": list(LOCALITY_CATEGORIES)})
        counts = cur.execute("SELECT category, count(*) FROM places GROUP BY category ORDER BY 2 DESC").fetchall()
        conn.commit()
    if not has_tn23:
        print("WARNING: no TN-23 polygon in admin_areas (run the M2 ingest): nothing was filtered out.")
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pbf", type=Path, default=PBF)
    ap.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    ap.add_argument("--dry-run", action="store_true", help="extract and print counts, no database write")
    args = ap.parse_args(argv)
    if not args.pbf.exists():
        sys.exit(f"Missing {args.pbf} (scripts/osm-clip-bizerte.sh)")
    rows = extract(args.pbf)
    print(f"extracted {len(rows)} entries from {args.pbf.name} (before the TN-23 filter):")
    for cat, n in Counter(r["category"] for r in rows).most_common():
        print(f"  {CATEGORY_FR[cat]:<16} {cat:<14} {n}")
    print(f"  with an Arabic name: {sum(1 for r in rows if r['name_ar'])}")
    if args.dry_run:
        return
    if not args.database_url:
        sys.exit("Set DATABASE_URL (host DB, see CLAUDE.md) or use --dry-run")
    counts = load(rows, args.database_url)
    print(f"places table: {sum(n for _, n in counts)} rows inside TN-23")
    for cat, n in counts:
        print(f"  {CATEGORY_FR[cat]:<16} {n}")


if __name__ == "__main__":
    main()
