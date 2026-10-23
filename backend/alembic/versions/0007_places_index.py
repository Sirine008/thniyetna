"""Place index for the citizen destination search (M3)

Revision ID: 0007_places_index
Revises: 0006_rag_chunk_context
Create Date: 2026-10-23

Additive. Named places (towns, villages, neighbourhoods), named streets and main POIs of the
Bizerte governorate, extracted from data/osm/bizerte.osm.pbf by scripts/build_places_index.py.
`name_norm` is the accent/case-insensitive search key (routing/places_index.normalize, Latin and
Arabic variants), searched with pg_trgm (GET /routing/places). `locality` = nearest town / village
(context for streets and POIs).
"""
from alembic import op

revision = "0007_places_index"
down_revision = "0006_rag_chunk_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
    CREATE TABLE IF NOT EXISTS places (
        id BIGSERIAL PRIMARY KEY,
        osm_type CHAR(1) NOT NULL,
        osm_id BIGINT NOT NULL,
        name TEXT NOT NULL,
        name_ar TEXT,
        name_norm TEXT NOT NULL,
        category TEXT NOT NULL,
        locality TEXT,
        rank SMALLINT NOT NULL DEFAULT 0,
        geom geometry(Point, 4326) NOT NULL,
        UNIQUE (osm_type, osm_id)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS places_name_norm_trgm ON places USING gin (name_norm gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS places_geom_gix ON places USING gist (geom)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS places")
