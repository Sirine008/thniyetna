"""Hybrid retrieval: pgvector cosine top-20 + full-text top-20, fused with Reciprocal Rank Fusion.

RRF (Cormack et al., 2009): score(d) = sum over lists of 1 / (k + rank_d), k = 60. It needs no
score calibration between the two retrievers, only their rankings.
"""
import re
from collections import defaultdict

from . import config

# Small French + English stop-word list: these words would make the OR query match everything.
STOPWORDS = set("""
les des une est sont dans pour par avec sur aux ses ces qui que quoi quel quelle quels quelles
comment pourquoi quand combien elle ils elles nous vous leur leurs mais donc car pas plus moins
tout tous toute toutes cette cet entre sans sous chez être avoir fait faire peut doit the and for
with what how why when which this that are was from est-ce
""".split())
_WORD = re.compile(r"\w+", re.UNICODE)


def query_terms(question: str) -> list[str]:
    """Words for the full-text OR query: >= 3 letters (or any token with a digit, e.g. M2)."""
    seen, out = set(), []
    for w in _WORD.findall(question.lower()):
        if w in seen or w in STOPWORDS or w.replace("_", "") == "":
            continue
        if len(w) >= 3 or any(c.isdigit() for c in w):
            seen.add(w)
            out.append(w)
    return out


def rrf(rank_lists: list[list[str]], k: int = config.RRF_K) -> list[tuple[str, float]]:
    """Fuse ranked id lists. Ties keep the order of first appearance."""
    scores: dict[str, float] = defaultdict(float)
    first_seen: dict[str, int] = {}
    for lst in rank_lists:
        for rank, doc_id in enumerate(lst, start=1):
            scores[doc_id] += 1.0 / (k + rank)
            first_seen.setdefault(doc_id, len(first_seen))
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))


def vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"


def snippet(text: str, n: int = 300) -> str:
    t = " ".join(text.split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def search_queries(question: str, bilingual: bool, model: str | None = None) -> list[str]:
    """The question, plus its translation when bilingual retrieval is on (falls back to the question alone)."""
    if not bilingual:
        return [question]
    from . import ollama
    from .translate import translate
    try:
        other = translate(question, model)
    except ollama.OllamaError:  # a bad translation call must not cost the answer
        other = ""
    return [question] + ([other] if other and other.lower() != question.lower() else [])


def passes_gate(best_similarity: float | None, min_similarity: float = config.RAG_MIN_SIMILARITY) -> bool:
    """Confidence gate (RAG_MIN_SIMILARITY > 0): answer only if the best vector match is close enough."""
    return min_similarity <= 0 or (best_similarity is not None and best_similarity >= min_similarity)


def columns(fts: str, context: bool) -> tuple[str, str, str]:
    """(embedding column, tsvector column, text search config) — whitelisted, never user input."""
    if context:
        return "embedding_ctx", "tsv_fr_ctx", "french"
    if fts == "french":
        return "embedding", "tsv_fr", "french"
    return "embedding", "tsv", "simple"


def retrieve(db, question: str, k: int = config.TOP_K, depth: int = config.CANDIDATES,
             bilingual: bool | None = None, model: str | None = None, fts: str | None = None,
             context: bool | None = None) -> list[dict]:
    """Top-k chunks; see retrieve_scored."""
    return retrieve_scored(db, question, k, depth, bilingual, model, fts, context)[0]


def retrieve_scored(db, question: str, k: int = config.TOP_K, depth: int = config.CANDIDATES,
                    bilingual: bool | None = None, model: str | None = None, fts: str | None = None,
                    context: bool | None = None) -> tuple[list[dict], float | None]:
    """-> (top-k chunks, best vector cosine similarity among the candidates).

    bilingual (RAG_BILINGUAL) also searches the translated question; fts (RAG_FTS_CONFIG) picks the
    'simple' or 'french' full-text column; context (RAG_CHUNK_CONTEXT) searches the columns built
    from title + heading + text. All vector and full-text lists are fused with RRF.
    """
    from sqlalchemy import text

    from . import ollama

    emb_col, tsv_col, ts_cfg = columns(config.RAG_FTS_CONFIG if fts is None else fts,
                                       config.RAG_CHUNK_CONTEXT if context is None else context)
    queries = search_queries(question, config.RAG_BILINGUAL if bilingual is None else bilingual, model)
    lists, best = [], None
    for q, vec in zip(queries, ollama.embed(queries, kind="query")):
        rows = db.execute(text(f"""
            SELECT id::text, 1 - ({emb_col} <=> CAST(:q AS vector)) AS sim FROM rag_chunks
            WHERE {emb_col} IS NOT NULL ORDER BY {emb_col} <=> CAST(:q AS vector) LIMIT :n"""),
            {"q": vector_literal(vec), "n": depth}).all()
        lists.append([r[0] for r in rows])
        if rows:
            best = float(rows[0][1]) if best is None else max(best, float(rows[0][1]))
        terms = query_terms(q)
        if terms:
            lists.append(list(db.execute(text(f"""
                SELECT id::text FROM rag_chunks, to_tsquery(CAST(:cfg AS regconfig), CAST(:tq AS text)) q
                WHERE {tsv_col} @@ q ORDER BY ts_rank_cd({tsv_col}, q) DESC LIMIT :n"""),
                {"cfg": ts_cfg, "tq": " | ".join(terms), "n": depth}).scalars().all()))
    fused = rrf(lists)[:k]
    if not fused:
        return [], best
    rows = {r["id"]: r for r in db.execute(text("""
        SELECT c.id::text id, c.page, c.text, d.title, d.source_path
        FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
        WHERE c.id = ANY(CAST(:ids AS uuid[]))"""), {"ids": [i for i, _ in fused]}).mappings().all()}
    out = []
    for n, (cid, score) in enumerate(fused, start=1):
        r = rows[cid]
        out.append({"n": n, "chunk_id": cid, "title": r["title"], "source_path": r["source_path"],
                    "page": r["page"], "snippet": snippet(r["text"]), "text": r["text"],
                    "score": round(score, 5)})
    return out, (round(best, 4) if best is not None else None)
