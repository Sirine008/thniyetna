# M2 raw inputs (not versioned)

Place these files here (names can be overridden with env vars):

| File | Env var | Source | Used for |
|---|---|---|---|
| `accidents_tn.json` | `M2_ACCIDENTS_FILE` | Tunisian road-accident open-data export (JSON, Arabic keys, `{"data": [...]}`), 2015 → 2026 | targets + accident history |
| `weather_reference.xlsx` | `M2_WEATHER_FILE` | Meteostat daily export of one reference station (date, tavg, tmin, tmax, prcp, wspd, pres) — or `weather_governorates.csv` built by `python -m prediction.fetch_weather` | weather features |
| `tunisia-latest.osm.pbf` | `M2_OSM_FILE` | Geofabrik Tunisia extract | governorate polygons, road network, segments |

The training run of 2026-10-11 used the export `28-09-2026-18-00-55.json`
(69 394 accidents, last day 2026-09-27), the Meteostat export `export.xlsx`
(2022-04-01 → 2026-10-08) and `tunisia-latest.osm.pbf`. SHA-256 prefixes are
recorded in `reports/m2/training_report.json`.
