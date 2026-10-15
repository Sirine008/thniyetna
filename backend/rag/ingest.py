"""Index documents for the RAG assistant.

    python -m rag.ingest                       # data/rag/corpus/**/*.{pdf,md,txt}
    python -m rag.ingest --path /data/rag/corpus/guide.pdf
    python -m rag.ingest --contexts                 # rebuild chunk contexts + embedding_ctx only

Audience = field users (equipment / transport supervisors): only the field corpus is indexed
(technical guides, and a future user guide placed in data/rag/corpus/). Developer docs (docs/) are not.
Run inside the api container (`docker compose exec api python -m rag.ingest`): the corpus is mounted
read-only at /data/rag/corpus, and Ollama is reached at OLLAMA_URL.
Unchanged files (same sha256) are skipped; a changed file is deleted and re-indexed.
"""
import argparse
import hashlib
import sys
import time
from pathlib import Path

from sqlalchemy import text

from . import config, ollama
from .chunking import chunk_pages
from .context import build_contexts
from .lang import detect_lang
from .retrieve import vector_literal

EXTENSIONS = {".pdf", ".md", ".txt"}


def discover(paths: list[str] | None) -> list[Path]:
    if paths:
        files = []
        for p in map(Path, paths):
            files.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in EXTENSIONS) if p.is_dir() else [p])
        return files
    return sorted(f for f in config.CORPUS_DIR.rglob("*")
                  if f.is_file() and f.suffix.lower() in EXTENSIONS and f.name.lower() != "readme.md")


def source_path(f: Path) -> str:
    """Stable relative id: corpus/<...>."""
    try:
        return f.resolve().relative_to(config.CORPUS_DIR.parent.resolve()).as_posix()
    except ValueError:
        return f.as_posix()


def read_document(f: Path) -> tuple[str, list[tuple[int | None, str]], int, list[int]]:
    """-> (title, [(page, text)], page count, pages without extractable text)."""
    if f.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(f))
        pages, empty = [], []
        for i, page in enumerate(reader.pages, start=1):
            try:
                t = page.extract_text() or ""
            except Exception:  # a broken page must not stop the document
                t = ""
            (pages.append((i, t)) if t.strip() else empty.append(i))
        meta = (reader.metadata.title if reader.metadata else None) or ""
        title = meta.strip() if len(meta.strip()) > 3 and not meta.lower().startswith("microsoft") else f.stem
        return title, pages, len(reader.pages), empty
    body = f.read_text(encoding="utf-8", errors="replace")
    heading = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), "")
    return heading or f.stem, [(None, body)], 1, []


def _progress(name: str, done: int, total: int) -> None:
    print(f"\r  {name}: {done}/{total} chunks embedded", end="", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Index documents for the RAG assistant")
    ap.add_argument("--path", action="append", help="file or folder (repeatable); default: the corpus")
    ap.add_argument("--batch", type=int, default=16, help="chunks per Ollama /api/embed call")
    ap.add_argument("--contexts", action="store_true",
                    help="only rebuild chunk contexts + embedding_ctx for all indexed chunks (RAG_CHUNK_CONTEXT)")
    args = ap.parse_args(argv)

    from shared.db import engine
    if args.contexts:
        t0 = time.time()
        n = backfill_contexts(engine, args.batch)
        print(f"Contexts rebuilt for {n} chunk(s) in {time.time() - t0:.1f} s")
        return 0
    t0 = time.time()
    files = discover(args.path)
    with engine.connect() as cx:
        known = {r.source_path: r.sha256 for r in cx.execute(text("SELECT source_path, sha256 FROM rag_documents"))}
    known_sha = {sha: path for path, sha in known.items()}
    stats = {"files": len(files), "indexed": 0, "unchanged": 0, "duplicates": 0, "failed": 0, "pages": 0, "chunks": 0}
    empty_report, failures, duplicates = [], [], []
    print(f"RAG ingest: {len(files)} file(s), embeddings {config.RAG_EMBED_MODEL} via {config.OLLAMA_URL}")

    for f in files:
        rel = source_path(f)
        try:
            data = f.read_bytes()
        except OSError as exc:
            stats["failed"] += 1
            failures.append(f"{rel}: {exc}")
            continue
        sha = hashlib.sha256(data).hexdigest()
        if known.get(rel) == sha:
            stats["unchanged"] += 1
            continue
        if sha in known_sha:  # same bytes already indexed under another path (sha256 is unique)
            stats["duplicates"] += 1
            duplicates.append(f"{rel} = {known_sha[sha]}")
            continue
        try:
            title, pages, n_pages, empty = read_document(f)
        except Exception as exc:
            stats["failed"] += 1
            failures.append(f"{rel}: unreadable ({exc})")
            continue
        if empty:
            empty_report.append(f"{rel}: {len(empty)}/{n_pages} page(s) without text: {_ranges(empty)}")
        chunks = chunk_pages(pages, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        if not chunks:
            stats["failed"] += 1
            failures.append(f"{rel}: no extractable text (scanned? needs OCR)")
            continue
        vectors = []
        try:
            for i in range(0, len(chunks), args.batch):
                vectors += ollama.embed([c.text for c in chunks[i:i + args.batch]])
                _progress(f.name, len(vectors), len(chunks))
            print()
        except ollama.OllamaUnavailable as exc:
            print(f"\nOllama unreachable ({exc}); stopping. Already indexed files are kept.", file=sys.stderr)
            return 2
        sample = " ".join(c.text for c in chunks[:5])
        try:
            _store(engine, rel, title, sha, n_pages, detect_lang(sample), chunks, vectors)
        except Exception as exc:  # report and go on with the next file
            stats["failed"] += 1
            failures.append(f"{rel}: not stored ({type(exc).__name__}: {str(exc).splitlines()[0][:200]})")
            continue
        known[rel], known_sha[sha] = sha, rel
        stats["indexed"] += 1
        stats["pages"] += n_pages
        stats["chunks"] += len(chunks)

    print(f"\nSummary: {stats['files']} file(s) · {stats['indexed']} indexed · {stats['unchanged']} unchanged (skipped) · "
          f"{stats['duplicates']} duplicate(s) · {stats['failed']} failed · {stats['pages']} page(s) · "
          f"{stats['chunks']} chunk(s) · {time.time() - t0:.1f} s")
    for line in empty_report:
        print(f"  skipped pages  {line}")
    for line in duplicates:
        print(f"  duplicate      {line}")
    for line in failures:
        print(f"  failed         {line}")
    try:  # new documents get their retrieval context right away
        backfill_contexts(engine, args.batch, only_missing=True)
    except ollama.OllamaUnavailable as exc:
        print(f"Ollama unreachable ({exc}); run `python -m rag.ingest --contexts` later.", file=sys.stderr)
        return 2
    return 1 if stats["failed"] and not stats["indexed"] and not stats["unchanged"] else 0


def backfill_contexts(engine, batch: int = 16, only_missing: bool = False) -> int:
    """Build rag_chunks.context (title — page header — heading, see rag/context.py) and embed
    context + text into embedding_ctx. Chunk ids and texts are not touched. -> chunks updated."""
    with engine.connect() as cx:
        docs = cx.execute(text("""
            SELECT d.id, d.title FROM rag_documents d
            WHERE NOT CAST(:only AS boolean)
               OR EXISTS (SELECT 1 FROM rag_chunks c WHERE c.document_id = d.id AND c.embedding_ctx IS NULL)
            ORDER BY d.source_path"""), {"only": only_missing}).all()
    done = 0
    for doc_id, title in docs:
        with engine.connect() as cx:
            rows = cx.execute(text("SELECT id, page, text FROM rag_chunks WHERE document_id = :d ORDER BY chunk_index"),
                              {"d": doc_id}).all()
        contexts = build_contexts(title, [(r.page, r.text) for r in rows])
        vectors = []
        for i in range(0, len(rows), batch):
            vectors += ollama.embed([f"{c}\n{r.text}" for c, r in zip(contexts[i:i + batch], rows[i:i + batch])])
            _progress(f"context {title[:40]}", len(vectors), len(rows))
        print()
        with engine.begin() as cx:
            cx.execute(text("UPDATE rag_chunks SET context = CAST(:c AS text), embedding_ctx = CAST(:e AS vector) WHERE id = :i"),
                       [{"c": c, "e": vector_literal(v), "i": r.id} for c, v, r in zip(contexts, vectors, rows)])
        done += len(rows)
    return done


def _store(engine, rel, title, sha, n_pages, lang, chunks, vectors) -> None:
    """One transaction per document: an interruption keeps the files already finished."""
    with engine.begin() as cx:
        cx.execute(text("DELETE FROM rag_documents WHERE source_path = CAST(:p AS text)"), {"p": rel})
        doc_id = cx.execute(text("""
            INSERT INTO rag_documents (title, source_path, lang, sha256, pages)
            VALUES (CAST(:t AS text), CAST(:p AS text), CAST(:l AS text), CAST(:s AS text), :n) RETURNING id"""),
            {"t": title, "p": rel, "l": lang, "s": sha, "n": n_pages}).scalar_one()
        cx.execute(text("""
            INSERT INTO rag_chunks (document_id, chunk_index, page, text, embedding)
            VALUES (:d, :i, :pg, CAST(:tx AS text), CAST(:e AS vector))"""),
            [{"d": doc_id, "i": c.index, "pg": c.page, "tx": c.text, "e": vector_literal(v)}
             for c, v in zip(chunks, vectors)])


def _ranges(nums: list[int]) -> str:
    out, start = [], None
    for i, n in enumerate(nums):
        start = n if start is None else start
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f"{start}-{n}")
            start = None
    return ", ".join(out)


if __name__ == "__main__":
    sys.exit(main())
