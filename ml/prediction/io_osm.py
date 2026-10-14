"""OpenStreetMap extraction for M2.

Produces, from the Geofabrik Tunisia PBF:
  * governorate polygons (admin_level=4, "ولاية ...")
  * drivable road ways with length, class and attributes, assigned to a governorate
  * per-governorate road-network statistics (static exposure features)

The road snapshot is current (not historical): it is used as a static
exposure proxy, which is an accepted approximation documented in the model card.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PROCESSED_DIR, RAW_DIR, OSM_FILE, GOV_CODES, gov_code

# OSM highway tag -> road class used in M2 (aligned with the accident place classes)
HIGHWAY_CLASS = {
    "motorway": "motorway", "motorway_link": "motorway",
    "trunk": "national", "trunk_link": "national",
    "primary": "national", "primary_link": "national",
    "secondary": "regional", "secondary_link": "regional",
    "tertiary": "local", "tertiary_link": "local", "unclassified": "local",
    "residential": "urban", "living_street": "urban",
}
ROAD_CLASSES = ["motorway", "national", "regional", "local", "urban"]


def _haversine_m(lon1, lat1, lon2, lat2):
    r = 6371008.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _to_float(v):
    if v is None:
        return math.nan
    try:
        return float(str(v).split()[0].replace(",", "."))
    except (ValueError, IndexError):
        return math.nan


def extract_osm(pbf: str | Path | None = None, out_dir: str | Path | None = None, keep_geometry: bool = True):
    """Run the extraction and write parquet/csv files. Returns (governorates, roads)."""
    import osmium  # heavy optional dependency, imported lazily
    import shapely
    from shapely import wkb as shp_wkb

    pbf = Path(pbf) if pbf else RAW_DIR / OSM_FILE
    out_dir = Path(out_dir) if out_dir else PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    wkbfab = osmium.geom.WKBFactory()

    class Handler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.govs: list[dict] = []
            self.roads: list[dict] = []

        def area(self, a):
            t = a.tags
            if a.from_way() or t.get("boundary") != "administrative" or t.get("admin_level") != "4":
                return
            code = gov_code(t.get("name:fr")) or gov_code(t.get("name:ar")) or gov_code(t.get("name"))
            if code is None:
                return  # neighbouring Algerian / Libyan provinces present in the extract
            try:
                geom = shp_wkb.loads(wkbfab.create_multipolygon(a), hex=True)
            except Exception:  # broken boundary relation
                return
            self.govs.append({"gov_code": code, "name": t.get("name:fr") or t.get("name"), "geometry": geom})

        def way(self, w):
            hw = w.tags.get("highway")
            cls = HIGHWAY_CLASS.get(hw)
            if cls is None:
                return
            try:
                coords = [(n.lon, n.lat) for n in w.nodes]
            except osmium.InvalidLocationError:
                return
            if len(coords) < 2:
                return
            arr = np.asarray(coords)
            length = float(_haversine_m(arr[:-1, 0], arr[:-1, 1], arr[1:, 0], arr[1:, 1]).sum())
            mid = arr[len(arr) // 2]
            t = w.tags
            rec = {
                "osm_id": w.id, "highway": hw, "road_class": cls,
                "name": t.get("name:fr") or t.get("name"), "ref": t.get("ref"),
                "surface": t.get("surface"), "lanes": _to_float(t.get("lanes")),
                "maxspeed": _to_float(t.get("maxspeed")),
                "lit": t.get("lit") == "yes", "bridge": t.get("bridge") not in (None, "no"),
                "tunnel": t.get("tunnel") not in (None, "no"), "oneway": t.get("oneway") == "yes",
                "length_m": length, "mid_lon": float(mid[0]), "mid_lat": float(mid[1]),
            }
            if keep_geometry:
                rec["wkt"] = shapely.LineString(arr).wkt
            self.roads.append(rec)

    h = Handler()
    h.apply_file(str(pbf), locations=True, idx="flex_mem")

    govs = pd.DataFrame(h.govs).drop_duplicates("gov_code")
    if set(govs["gov_code"]) != set(GOV_CODES):
        missing = sorted(set(GOV_CODES) - set(govs["gov_code"]))
        raise RuntimeError(f"Governorate polygons missing from OSM extract: {missing}")
    roads = pd.DataFrame(h.roads)

    # Spatial join: way midpoint -> governorate polygon
    tree = shapely.STRtree(list(govs["geometry"]))
    pts = shapely.points(roads["mid_lon"].to_numpy(), roads["mid_lat"].to_numpy())
    pt_idx, poly_idx = tree.query(pts, predicate="within")
    gov_of = np.full(len(roads), None, dtype=object)
    gov_of[pt_idx] = govs["gov_code"].to_numpy()[poly_idx]
    roads["gov_code"] = gov_of
    roads = roads.dropna(subset=["gov_code"]).reset_index(drop=True)

    govs_out = govs.assign(
        area_km2=[_area_km2(g) for g in govs["geometry"]],
        wkt=[g.wkt for g in govs["geometry"]],
    ).drop(columns="geometry")
    govs_out.to_parquet(out_dir / "governorates.parquet", index=False)
    roads.to_parquet(out_dir / "osm_roads.parquet", index=False)
    stats = governorate_road_stats(roads, govs_out)
    stats.to_csv(out_dir / "governorate_road_stats.csv", index=False)
    return govs_out, roads


def _area_km2(geom) -> float:
    """Equal-area-ish area: scale degrees by cos(latitude) at the centroid."""
    c = geom.centroid
    kx = 111.320 * math.cos(math.radians(c.y))
    ky = 110.574
    return float(geom.area * kx * ky)


def governorate_road_stats(roads: pd.DataFrame, govs: pd.DataFrame) -> pd.DataFrame:
    km = roads.pivot_table(index="gov_code", columns="road_class", values="length_m", aggfunc="sum", fill_value=0) / 1000
    km = km.reindex(columns=ROAD_CLASSES, fill_value=0)
    km.columns = [f"road_km_{c}" for c in km.columns]
    out = km.copy()
    out["road_km_total"] = km.sum(axis=1)
    out = out.join(govs.set_index("gov_code")[["area_km2"]])
    out["road_density_km_per_km2"] = out["road_km_total"] / out["area_km2"]
    for c in ROAD_CLASSES:
        out[f"road_share_{c}"] = out[f"road_km_{c}"] / out["road_km_total"]
    lit = roads.groupby("gov_code").apply(lambda d: (d["length_m"] * d["lit"]).sum() / d["length_m"].sum(), include_groups=False)
    out["road_share_lit"] = lit
    paved = roads.assign(unpaved=roads["surface"].isin(["unpaved", "dirt", "gravel", "ground", "sand", "compacted"]))
    out["road_share_unpaved_tagged"] = paved.groupby("gov_code").apply(
        lambda d: (d["length_m"] * d["unpaved"]).sum() / d["length_m"].sum(), include_groups=False)
    out = out.reindex(GOV_CODES)
    return out.reset_index().rename(columns={"index": "gov_code"})


def load_road_stats(path: str | Path | None = None) -> pd.DataFrame:
    path = Path(path) if path else PROCESSED_DIR / "governorate_road_stats.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `python -m prediction.train extract-osm` first")
    return pd.read_csv(path)
