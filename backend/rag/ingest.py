"""Index documents for the RAG assistant.

    python -m rag.ingest                       # data/rag/corpus/**/*.{pdf,md,txt} + docs/**/*.md
    python -m rag.ingest --path /data/rag/corpus/guide.pdf

Run inside the api container (`docker compose exec api python -m rag.ingest`): the corpus and
docs are mounted read-only at /data/rag/corpus and /data/docs, and Ollama is reached at OLLAMA_URL.
Unchanged files (same sha256) are skipped; a changed file is deleted and re-indexed.
"""
import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

from sqlalchemy import text

from . import config, ollama
from .chunking import chunk_pages
from .retrieve import vector_literal

EXTENSIONS = {".pdf", ".md", ".txt"}
_FR = set("le la les des du une est et pour dans sur par au aux que qui".split())
_EN = set("the and of to is in for on with that by are be this".split())


def discover(paths: list[str] | None) -> list[Path]:
    if paths:
        files = []
        for p in map(Path, paths):
            files.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in EXTENSIONS) if p.is_dir() else [p])
        return files
    corpus = sorted(f for f in config.CORPUS_DIR.rglob("*")
                    if f.is_file() and f.suffix.lower() in EXTENSIONS and f.name.lower() != "readme.md")
    return corpus + sorted(config.DOCS_DIR.rglob("*.md"))


def source_path(f: Path) -> str:
    """Stable relative id: corpus/<...> or docs/<...>."""
    for root in (config.CORPUS_DIR.parent, config.DOCS_DIR.parent):
        try:
            return f.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    return f.as_posix()


def detect_lang(sample: str) -> str:
    letters = [c for c in sample if c.isalpha()]
    if letters and sum("؀" <= c <= "ۿ" for c in letters) / len(letters) > 0.3:
        return "ar"
    words = re.findall(r"[a-zà-ÿ]+", sample.lower())
    fr, en = sum(w in _FR for w in words), sum(w in _EN for w in words)
    return "fr" if fr >= en else "en"


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
    ap.add_argument("--path", action="append", help="file or folder (repeatable); default: corpus + docs")
    ap.add_argument("--batch", type=int, default=16, help="chunks per Ollama /api/embed call")
    args = ap.parse_args(argv)

    from shared.db import engine
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
    return 1 if stats["failed"] and not stats["indexed"] and not stats["unchanged"] else 0


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
