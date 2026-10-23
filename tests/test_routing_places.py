"""M3 destination search: place index (routing/places_index.py, scripts/build_places_index.py),
GET /routing/places, GET /routing/places/nearest and the out-of-zone message of POST /routing/route.

The pure parts run anywhere; the endpoint tests need fastapi (skipped in ml/.venv, run them in the api image).
"""
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from routing import places_index as P  # noqa: E402
import build_places_index as B  # noqa: E402


# ------------------------------------------------------------------ normalisation / classification
def test_search_key_is_accent_case_and_punctuation_insensitive():
    assert P.normalize("menzel bourguiba") == P.normalize("Menzel Bourguiba") == "menzel bourguiba"
    assert P.normalize("MENZEL-BOURGUIBA") == P.normalize("  Ménzel   Bourguïba ") == "menzel bourguiba"
    assert P.normalize("Hôpital Régional") == "hopital regional"
    assert P.normalize("L'École des Sœurs") == "l ecole des soeurs"
    assert P.normalize(None) == P.normalize("") == ""


def test_arabic_names_ignore_diacritics_and_letter_variants():
    assert P.normalize("منزل بورقيبة") == P.normalize("مَنْزِل بورقيبه")
    assert P.normalize("رأس الجبل") == P.normalize("راس الجبل")


def test_classify_places_streets_and_main_pois():
    assert P.classify({"place": "town"}) == "town"
    assert P.classify({"place": "quarter"}) == "neighbourhood"
    assert P.classify({"highway": "residential", "name": "Rue X"}) == "street"
    assert P.classify({"amenity": "hospital"}) == "hospital"
    assert P.classify({"amenity": "school"}) == "school"
    assert P.classify({"office": "government"}) == "administration"
    assert P.classify({"railway": "station"}) == "station"
    assert P.classify({"leisure": "marina"}) == "port"
    assert P.classify({"amenity": "cafe"}) is None
    assert P.classify({"highway": "footway"}) is None
    assert set(P.CATEGORY_RANK) == set(P.CATEGORY_FR)


def test_names_prefer_french_for_display_and_keep_the_arabic_name():
    name, name_ar, variants = P.names({"name": "منزل بورقيبة", "name:fr": "Menzel Bourguiba"})
    assert (name, name_ar) == ("Menzel Bourguiba", "منزل بورقيبة")
    key = P.search_key(variants)
    assert "menzel bourguiba" in key and P.normalize("منزل بورقيبة") in key
    assert P.names({"highway": "residential"}) is None
    assert P.names({"name": "بنزرت"})[0] == "بنزرت"


def test_place_row_gives_the_category_in_french():
    row = {"name": "Hôpital Régional de Menzel Bourguiba", "name_ar": None, "category": "hospital",
           "locality": "Menzel Bourguiba", "lat": 37.15, "lon": 9.79}
    assert P.place_row(row) == {"name": row["name"], "category": "Hôpital", "category_key": "hospital",
                                "lat": 37.15, "lon": 9.79, "locality": "Menzel Bourguiba"}
    town = P.place_row({**row, "name": "Mateur", "category": "town", "locality": "Mateur"})
    assert town["category"] == "Ville" and "locality" not in town


def test_osrm_coverage_error_messages():
    assert P.osrm_coverage_error({"code": "NoSegment"}) == P.OUT_OF_ZONE_DESTINATION
    assert P.osrm_coverage_error({"code": "NoRoute"}) == P.OUT_OF_ZONE_DESTINATION
    assert P.OUT_OF_ZONE_DESTINATION == "Destination hors de la zone couverte (gouvernorat de Bizerte)"
    near = {"distance": 12.0}
    far = {"distance": P.MAX_SNAP_M + 1}
    assert P.osrm_coverage_error({"code": "Ok", "waypoints": [near, near]}) is None
    assert P.osrm_coverage_error({"code": "Ok", "waypoints": [near, far]}) == P.OUT_OF_ZONE_DESTINATION
    assert P.osrm_coverage_error({"code": "Ok", "waypoints": [far, near]}) == P.OUT_OF_ZONE_START
    assert P.osrm_coverage_error({"code": "InvalidQuery"}) is None  # a real error stays an error


def test_search_sql_is_index_friendly_and_ranked():
    sql = P.SEARCH_SQL
    assert "ILIKE '%' || :q || '%'" in sql and "word_similarity(:q, name_norm)" in sql
    assert sql.index("CASE WHEN") < sql.index("word_similarity(:q, name_norm) DESC") < sql.index("rank DESC")
    migration = (ROOT / "backend/alembic/versions/0007_places_index.py").read_text(encoding="utf-8")
    assert "pg_trgm" in migration and "gin_trgm_ops" in migration and 'down_revision = "0006_rag_chunk_context"' in migration


# ------------------------------------------------------------------ builder script
def way(name, lat, lon, length, osm_id, ends=None):
    e = B.entry("w", osm_id, {"name": name, "highway": "residential"}, "street", lat, lon)
    return {**e, "length_m": length, "ends": ends or ((lat, lon), (lat, lon))}


def test_street_ways_are_merged_per_town_but_not_across_towns():
    ways = [way("Avenue Habib Bourguiba", 37.2740, 9.8700, 300, 1),
            way("Avenue Habib Bourguiba", 37.2760, 9.8720, 800, 2),       # same street, 280 m away
            way("Avenue Habib Bourguiba", 37.1530, 9.7850, 500, 3),       # Menzel Bourguiba, 15 km away
            way("Rue de Rome", 37.2750, 9.8710, 200, 4)]
    streets = B.merge_streets(ways)
    assert sorted((s["name"], s["osm_id"]) for s in streets) == [
        ("Avenue Habib Bourguiba", 2), ("Avenue Habib Bourguiba", 3), ("Rue de Rome", 4)]
    assert all("length_m" not in s and "ends" not in s for s in streets)


def test_dedup_keeps_one_entry_per_poi_and_per_town():
    hosp = B.entry("n", 1, {"name": "Hôpital X", "amenity": "hospital"}, "hospital", 37.27, 9.87)
    hosp_area = {**hosp, "osm_type": "w", "osm_id": 2, "lat": 37.2705}       # ~55 m away
    town = B.entry("n", 3, {"name": "Mateur", "place": "town"}, "town", 37.04, 9.665)
    town_area = {**town, "osm_type": "r", "osm_id": 4, "lat": 37.05}         # ~1.1 km away
    kept = B.dedup([hosp, hosp_area, town, town_area])
    assert sorted((k["osm_type"], k["osm_id"]) for k in kept) == [("n", 3), ("w", 2)]


def test_line_middle():
    (lat, lon), length = B._line_middle([(37.0, 9.0), (37.0, 9.01), (37.0, 9.03)])
    assert abs(lon - 9.015) < 1e-9 and lat == 37.0 and 2600 < length < 2700


# ------------------------------------------------------------------ API (needs fastapi)
class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDB:
    """Answers the place / coverage queries; covered=False puts every point outside TN-23."""

    def __init__(self, places=(), covered=True):
        self.places, self.covered, self.calls = list(places), covered, []

    def execute(self, stmt, params):
        sql = str(stmt)
        self.calls.append((sql, params))
        if "FROM admin_areas" in sql:
            return FakeResult([] if self.covered is None else [{"covered": self.covered}])
        if "FROM places" in sql:
            return FakeResult(self.places[:params.get("limit", 1)])
        raise NotImplementedError(sql[:40])

    def rollback(self):
        pass


@pytest.fixture
def R():
    pytest.importorskip("fastapi")
    from routing import router
    return router


ROW = {"name": "Menzel Bourguiba", "name_ar": "منزل بورقيبة", "category": "town", "locality": None,
       "lat": 37.1537, "lon": 9.7856}


def test_places_endpoint_normalises_the_query_and_returns_french_categories(R):
    db = FakeDB([ROW])
    rows = R.search_places(q="  MÉNZEL-bourguiba ", limit=8, db=db)
    assert db.calls[0][1] == {"q": "menzel bourguiba", "limit": 8}
    assert rows == [{"name": "Menzel Bourguiba", "name_ar": "منزل بورقيبة", "category": "Ville",
                     "category_key": "town", "lat": 37.1537, "lon": 9.7856}]
    assert R.search_places(q="-", limit=8, db=db) == []  # nothing left to search


def test_places_endpoint_without_index_is_a_503(R):
    class Broken(FakeDB):
        def execute(self, stmt, params):
            raise RuntimeError('relation "places" does not exist')
    with pytest.raises(R.HTTPException) as err:
        R.search_places(q="mateur", limit=8, db=Broken())
    assert err.value.status_code == 503


def test_nearest_place_and_coverage(R):
    near = R.nearest_place(lat=37.15, lon=9.79, db=FakeDB([{**ROW, "distance_m": 412.4}]))
    assert near["covered"] is True and near["message"] is None
    assert near["place"]["name"] == "Menzel Bourguiba" and near["place"]["distance_m"] == 412
    out = R.nearest_place(lat=36.80, lon=10.18, db=FakeDB([], covered=False))
    assert out == {"place": None, "covered": False, "message": P.OUT_OF_ZONE_DESTINATION}


def test_route_outside_tn23_is_a_clear_french_422_before_osrm(R, monkeypatch):
    monkeypatch.setattr(R, "_fetch_osrm", lambda *a, **k: pytest.fail("OSRM must not be called"))
    req = R.RouteRequest(current_lat=37.27, current_lon=9.87, destination_lat=36.80, destination_lon=10.18)

    class OnlyDestinationOut(FakeDB):
        def execute(self, stmt, params):
            self.covered = params["lat"] > 37
            return super().execute(stmt, params)
    with pytest.raises(R.HTTPException) as err:
        R.get_route(req, OnlyDestinationOut())
    assert (err.value.status_code, err.value.detail) == (422, P.OUT_OF_ZONE_DESTINATION)
    with pytest.raises(R.HTTPException) as err:
        R.get_route(req, FakeDB(covered=False))
    assert err.value.detail == P.OUT_OF_ZONE_START


@pytest.mark.parametrize("body,detail", [
    ({"code": "NoSegment", "message": "Could not find a matching segment"}, P.OUT_OF_ZONE_DESTINATION),
    ({"code": "Ok", "routes": [], "waypoints": [{"distance": 3.0}, {"distance": 9000.0}]}, P.OUT_OF_ZONE_DESTINATION),
])
def test_osrm_unroutable_point_is_a_clear_french_422(R, monkeypatch, body, detail):
    monkeypatch.setattr(R.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(body).encode()))
    req = R.RouteRequest(current_lat=37.27, current_lon=9.87, destination_lat=37.20, destination_lon=9.60)
    with pytest.raises(R.HTTPException) as err:
        R.get_route(req, FakeDB(covered=None))  # coverage unknown: OSRM decides
    assert (err.value.status_code, err.value.detail) == (422, detail)


def test_other_osrm_errors_are_unchanged(R, monkeypatch):
    body = {"code": "InvalidQuery", "message": "Query string malformed"}
    monkeypatch.setattr(R.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(body).encode()))
    with pytest.raises(R.HTTPException) as err:
        R._fetch_osrm([(37.27, 9.87), (37.2, 9.6)])
    assert err.value.status_code == 502
