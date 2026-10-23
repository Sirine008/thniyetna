# Datasets

## RDD2022
RDD2022 is the initial M1 training/evaluation dataset. Keep downloaded raw data
outside Git (for example `data/external/rdd2022/`) and convert it with
`ml/perception/prepare_rdd2022.py`.

The prepared model uses the four road-damage classes D00, D10, D20 and D40.
Dataset version, split seed, selected countries and local Tunisia pilot data must
be recorded with every benchmark.

## OSM
The routing service uses the prepared Bizerte OSRM graph under `data/osm/`. The citizen destination search uses the `places` table (Alembic 0007), built from the same
`data/osm/bizerte.osm.pbf` by `scripts/build_places_index.py` (see CLAUDE.md).
