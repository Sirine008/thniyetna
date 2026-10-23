"""Place index for the destination search (table `places`, Alembic 0007).

Pure Python (no FastAPI / DB import): shared by the API (routing/router.py) and the builder script
(scripts/build_places_index.py), so the query and the stored `name_norm` are normalised the same way.
"""
from __future__ import annotations

import re
import unicodedata

# Arabic letter variants folded to one form, so "مدينة" / "مدينه" and "أ" / "ا" match (+ French ligatures).
_AR_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي", "ـ": None,
                         "œ": "oe", "æ": "ae"})
_SEPARATORS = re.compile(r"[^\w]+", re.UNICODE)


def normalize(text: str | None) -> str:
    """Accent-, case- and punctuation-insensitive search key: "Menzel-Bourguiba" -> "menzel bourguiba",
    "Bénzart" -> "benzart"; Arabic loses its diacritics (harakat) and letter variants are folded."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(_SEPARATORS.sub(" ", stripped.translate(_AR_FOLD)).replace("_", " ").split())


# category key -> label shown to users (French)
CATEGORY_FR = {
    "city": "Ville",
    "town": "Ville",
    "village": "Village",
    "hamlet": "Hameau",
    "suburb": "Quartier",
    "neighbourhood": "Quartier",
    "locality": "Lieu-dit",
    "street": "Rue",
    "hospital": "Hôpital",
    "clinic": "Centre de santé",
    "school": "École",
    "university": "Université",
    "townhall": "Mairie",
    "administration": "Administration",
    "police": "Police",
    "post_office": "Poste",
    "station": "Gare",
    "bus_station": "Gare routière",
    "port": "Port",
}
# higher first when two results match equally well (a town before a street of the same name)
CATEGORY_RANK = {"city": 100, "town": 90, "village": 70, "suburb": 60, "port": 55, "hospital": 50,
                 "station": 50, "bus_station": 45, "townhall": 45, "university": 40, "neighbourhood": 40,
                 "administration": 35, "police": 30, "post_office": 30, "clinic": 30, "school": 25,
                 "hamlet": 20, "locality": 15, "street": 10}

PLACE_TYPES = {"city": "city", "town": "town", "village": "village", "hamlet": "hamlet", "suburb": "suburb",
               "quarter": "neighbourhood", "neighbourhood": "neighbourhood", "locality": "locality",
               "isolated_dwelling": "locality"}
AMENITY_TYPES = {"hospital": "hospital", "clinic": "clinic", "doctors": "clinic", "school": "school",
                 "college": "school", "university": "university", "townhall": "townhall",
                 "courthouse": "administration", "police": "police", "post_office": "post_office",
                 "bus_station": "bus_station", "ferry_terminal": "port"}
STREET_HIGHWAYS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
                   "living_street", "pedestrian", "service"}


def classify(tags) -> str | None:
    """Category key for an OSM object's tags (dict-like with .get), or None if it is not indexed.
    Streets are the named highway ways; everything else is a place or a main POI."""
    if tags.get("place") in PLACE_TYPES:
        return PLACE_TYPES[tags.get("place")]
    if tags.get("amenity") in AMENITY_TYPES:
        return AMENITY_TYPES[tags.get("amenity")]
    if tags.get("healthcare") == "hospital":
        return "hospital"
    if tags.get("office") == "government" or tags.get("government"):
        return "administration"
    if tags.get("railway") in ("station", "halt") or tags.get("public_transport") == "station":
        return "station"
    if (tags.get("harbour") == "yes" or tags.get("landuse") == "port" or tags.get("industrial") == "port"
            or tags.get("leisure") == "marina"):
        return "port"
    if tags.get("highway") in STREET_HIGHWAYS:
        return "street"
    return None


def _is_arabic(text: str) -> bool:
    return any("؀" <= c <= "ۿ" for c in text)


def names(tags) -> tuple[str, str | None, list[str]] | None:
    """(display name, Arabic name, all variants) from OSM name tags; French preferred for display.
    Tunisian OSM often has `name` in Arabic and `name:fr` in French."""
    variants = [v for v in (tags.get("name:fr"), tags.get("name"), tags.get("name:en"), tags.get("name:ar"),
                            tags.get("alt_name"), tags.get("old_name"), tags.get("official_name")) if v]
    if not variants:
        return None
    latin = [v for v in variants if not _is_arabic(v)]
    arabic = [v for v in variants if _is_arabic(v)]
    display = latin[0] if latin else arabic[0]
    name_ar = arabic[0] if arabic and arabic[0] != display else None
    unique = list(dict.fromkeys(variants))
    return display, name_ar, unique


def search_key(variants) -> str:
    """name_norm stored in the table: every normalised variant, deduplicated, separated by ' | '."""
    return " | ".join(dict.fromkeys(n for n in (normalize(v) for v in variants) if n))


# Search: name start first, then word start, then trigram word similarity (typos), then importance.
# ILIKE uses the GIN trigram index. MIN_WORD_SIMILARITY is below pg_trgm's `<%` default (0.6) so that
# one-letter typos match ("bourgiba", "mnzel"); the table holds ~700 rows, a scan is cheap.
# :q is normalize()d, so it holds only letters, digits and spaces (no LIKE wildcard).
MIN_WORD_SIMILARITY = 0.5
SEARCH_SQL = f"""
  SELECT name, name_ar, category, locality, ST_Y(geom) AS lat, ST_X(geom) AS lon
  FROM places
  WHERE name_norm ILIKE '%' || :q || '%' OR word_similarity(:q, name_norm) >= {MIN_WORD_SIMILARITY}
  ORDER BY CASE WHEN name_norm ILIKE :q || '%' OR name_norm ILIKE '%| ' || :q || '%' THEN 0
                WHEN name_norm ILIKE '% ' || :q || '%' THEN 1 ELSE 2 END,
           word_similarity(:q, name_norm) DESC, rank DESC, length(name)
  LIMIT :limit
"""

NEAREST_RADIUS_M = 3000
NEAREST_SQL = """
  SELECT name, name_ar, category, locality, ST_Y(geom) AS lat, ST_X(geom) AS lon,
         ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography) AS distance_m
  FROM places
  WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :radius)
  ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon,:lat),4326)
  LIMIT 1
"""

# Same zone as the OSRM extract (scripts/osm-clip-bizerte.sh: TN-23 buffered by 2 km).
COVERAGE_BUFFER_M = 2000
COVERAGE_SQL = """
  SELECT ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :buffer) AS covered
  FROM admin_areas WHERE code = 'TN-23'
"""

OUT_OF_ZONE_DESTINATION = "Destination hors de la zone couverte (gouvernorat de Bizerte)"
OUT_OF_ZONE_START = "Point de départ hors de la zone couverte (gouvernorat de Bizerte)"
# OSRM snaps any point to the nearest road of its graph: further than this, the point is outside the graph.
MAX_SNAP_M = 1500


def place_row(row) -> dict:
    """API shape of a `places` row."""
    out = {"name": row["name"], "category": CATEGORY_FR.get(row["category"], row["category"]),
           "category_key": row["category"], "lat": round(float(row["lat"]), 6), "lon": round(float(row["lon"]), 6)}
    for key in ("name_ar", "locality"):
        if row.get(key) and row[key] != row["name"]:
            out[key] = row[key]
    if row.get("distance_m") is not None:
        out["distance_m"] = round(float(row["distance_m"]))
    return out


def osrm_coverage_error(body: dict) -> str | None:
    """French message when OSRM could not route because a point is outside its graph, else None.
    `NoSegment` / `NoRoute` mean the point cannot be matched / reached; a snap distance above MAX_SNAP_M
    means OSRM matched it to a road far away (a point outside the governorate)."""
    code = body.get("code")
    if code in ("NoSegment", "NoRoute"):
        return OUT_OF_ZONE_DESTINATION
    if code != "Ok":
        return None
    waypoints = body.get("waypoints") or []
    if waypoints and float(waypoints[0].get("distance") or 0) > MAX_SNAP_M:
        return OUT_OF_ZONE_START
    if len(waypoints) > 1 and float(waypoints[-1].get("distance") or 0) > MAX_SNAP_M:
        return OUT_OF_ZONE_DESTINATION
    return None
