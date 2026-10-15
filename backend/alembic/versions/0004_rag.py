"""RAG assistant: pgvector, documents, chunks (vector + full text), query log

Revision ID: 0004_rag
Revises: 0003_m2_risk_model
Create Date: 2026-10-15

Additive only. Embeddings come from Ollama `nomic-embed-text` (768 dims); the
`tsv` column is generated with the 'simple' configuration (no stemming, works for
French, English and Arabic text alike). `rag_queries` keeps every question with the
retrieved chunk ids so retrieval and answers can be evaluated later.
"""
from alembic import op

revision = "0004_rag"
down_revision = "0003_m2_risk_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
    CREATE TABLE IF NOT EXISTS rag_documents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title TEXT NOT NULL,
        source_path TEXT NOT NULL UNIQUE,
        lang TEXT,
        sha256 TEXT NOT NULL UNIQUE,
        pages INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS rag_chunks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id UUID NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        page INTEGER,
        text TEXT NOT NULL,
        embedding vector(768) NOT NULL,
        tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
        UNIQUE (document_id, chunk_index)
    );
    CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding ON rag_chunks USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_rag_chunks_tsv ON rag_chunks USING gin (tsv);

    CREATE TABLE IF NOT EXISTS rag_queries (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        asked_by TEXT,
        question TEXT NOT NULL,
        retrieved_chunk_ids UUID[] NOT NULL DEFAULT '{}',
        model TEXT,
        latency_ms INTEGER,
        answer TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_rag_queries_created ON rag_queries(created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rag_queries; DROP TABLE IF EXISTS rag_chunks; DROP TABLE IF EXISTS rag_documents;")
