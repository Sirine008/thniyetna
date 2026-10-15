"""RAG: French full-text column (stemming) next to the 'simple' one

Revision ID: 0005_rag_fts_french
Revises: 0004_rag
Create Date: 2026-10-15

Additive. `tsv_fr` uses the 'french' configuration (stemming: enrobé/enrobés,
chaud/chauds, French stop words). The 'simple' `tsv` column stays, so the part A
retrieval is unchanged; `RAG_FTS_CONFIG=french` switches the query to `tsv_fr`.
Generated column: existing chunks are indexed when the migration runs.
"""
from alembic import op

revision = "0005_rag_fts_french"
down_revision = "0004_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE rag_chunks
        ADD COLUMN IF NOT EXISTS tsv_fr tsvector GENERATED ALWAYS AS (to_tsvector('french', text)) STORED;
    CREATE INDEX IF NOT EXISTS idx_rag_chunks_tsv_fr ON rag_chunks USING gin (tsv_fr);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_rag_chunks_tsv_fr; ALTER TABLE rag_chunks DROP COLUMN IF EXISTS tsv_fr;")
