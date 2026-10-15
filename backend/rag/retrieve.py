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


def retrieve(db, question: str, k: int = config.TOP_K, depth: int = config.CANDIDATES) -> list[dict]:
    from sqlalchemy import text

    from . import ollama

    qvec = vector_literal(ollama.embed([question], kind="query")[0])
    vec_ids = db.execute(text("""
        SELECT id::text FROM rag_chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"""),
        {"q": qvec, "n": depth}).scalars().all()
    terms = query_terms(question)
    fts_ids = []
    if terms:
        fts_ids = db.execute(text("""
            SELECT id::text FROM rag_chunks, to_tsquery('simple', CAST(:tq AS text)) q
            WHERE tsv @@ q ORDER BY ts_rank_cd(tsv, q) DESC LIMIT :n"""),
            {"tq": " | ".join(terms), "n": depth}).scalars().all()
    fused = rrf([list(vec_ids), list(fts_ids)])[:k]
    if not fused:
        return []
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
    return out
