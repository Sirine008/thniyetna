"""RAG: chunk context (document title + section heading) for embedding and search

Revision ID: 0006_rag_chunk_context
Revises: 0005_rag_fts_french
Create Date: 2026-10-15

Additive. `context` holds "<title> — <page header> — <nearest heading>" (built by
`python -m rag.ingest --contexts`, see rag/context.py). It is used for retrieval only:
`embedding_ctx` embeds context + text and `tsv_fr_ctx` indexes context + text ('french').
The displayed / prompted text stays `text`. `RAG_CHUNK_CONTEXT=true` switches retrieval
to these columns; `embedding_ctx` is NULL until the backfill has run.
"""
from alembic import op

revision = "0006_rag_chunk_context"
down_revision = "0005_rag_fts_french"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE rag_chunks
        ADD COLUMN IF NOT EXISTS context TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS embedding_ctx vector(768);
    ALTER TABLE rag_chunks
        ADD COLUMN IF NOT EXISTS tsv_fr_ctx tsvector
            GENERATED ALWAYS AS (to_tsvector('french', context || ' ' || text)) STORED;
    CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_ctx ON rag_chunks USING hnsw (embedding_ctx vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_rag_chunks_tsv_fr_ctx ON rag_chunks USING gin (tsv_fr_ctx);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX IF EXISTS idx_rag_chunks_tsv_fr_ctx;
    DROP INDEX IF EXISTS idx_rag_chunks_embedding_ctx;
    ALTER TABLE rag_chunks DROP COLUMN IF EXISTS tsv_fr_ctx, DROP COLUMN IF EXISTS embedding_ctx,
        DROP COLUMN IF EXISTS context;
    """)
