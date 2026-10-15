# PostGIS 16 + pgvector for the RAG assistant (rag_chunks.embedding).
# Same PostgreSQL major (16) as before, so the existing postgres_data volume is reused as is.
# The base image is Debian 11 (bullseye): apt.postgresql.org no longer serves bullseye-pgdg,
# so the package comes from the frozen PGDG archive.
FROM postgis/postgis:16-3.4
RUN echo "deb [ signed-by=/usr/local/share/keyrings/postgres.gpg.asc ] http://apt-archive.postgresql.org/pub/repos/apt bullseye-pgdg-archive main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
