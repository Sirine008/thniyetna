"""RAG pure parts: chunker, Reciprocal Rank Fusion, grounded prompt.
These modules have no FastAPI / database dependency, so the tests run in any environment."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from rag.chunking import chunk_pages, paragraphs  # noqa: E402
from rag.prompt import REFUSAL, SYSTEM, build_messages  # noqa: E402
from rag.retrieve import query_terms, rrf  # noqa: E402


def _para(i, n=30):
    return " ".join(f"mot{i}x{j}" for j in range(n)) + "."


def test_chunks_respect_size_and_overlap():
    text = "\n\n".join(_para(i) for i in range(40))
    chunks = chunk_pages([(1, text)], size=800, overlap=150)
    assert len(chunks) > 3
    assert all(len(c.text) <= 800 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    for prev, nxt in zip(chunks, chunks[1:]):
        # the next chunk starts with a tail (<= 150 chars, word boundary) of the previous one
        overlap = max(k for k in range(0, 151) if nxt.text.startswith(prev.text[len(prev.text) - k:]))
        assert 100 <= overlap <= 150


def test_chunks_keep_page_and_never_cross_pages():
    pages = [(3, "\n\n".join(_para(i) for i in range(10))), (4, ""), (5, "Court paragraphe.")]
    chunks = chunk_pages(pages)
    assert {c.page for c in chunks} == {3, 5}                     # empty page -> no chunk
    assert chunks[-1].page == 5 and chunks[-1].text == "Court paragraphe."
    assert not any("Court" in c.text for c in chunks if c.page == 3)


def test_long_paragraph_is_split_and_line_wraps_are_joined():
    assert paragraphs("ligne une\ncoupée\n\n\nautre") == ["ligne une coupée", "autre"]
    chunks = chunk_pages([(None, "phrase longue. " * 200)], size=800, overlap=150)
    assert len(chunks) > 1 and all(len(c.text) <= 800 for c in chunks)
    assert all(c.page is None for c in chunks)


def test_rrf_rewards_agreement_between_retrievers():
    fused = rrf([["a", "b", "c"], ["b", "d", "a"]], k=60)
    ids = [i for i, _ in fused]
    assert ids[:2] == ["b", "a"]                                 # in both lists beats first-in-one
    assert set(ids) == {"a", "b", "c", "d"}
    assert dict(fused)["b"] == 1 / 62 + 1 / 61
    assert ids[2:] == ["d", "c"]                                 # d = 1/62 (rank 2) > c = 1/63 (rank 3)


def test_rrf_ties_keep_first_appearance_order():
    fused = rrf([["x"], ["y"]], k=60)
    assert [i for i, _ in fused] == ["x", "y"] and fused[0][1] == fused[1][1]


def test_query_terms_drop_stopwords_but_keep_codes():
    assert query_terms("Quelles sont les limites du modèle M2 ?") == ["limites", "modèle", "m2"]


def test_prompt_has_numbered_sources_and_refusal():
    sources = [{"n": 1, "title": "Guide nids-de-poule", "page": 12, "text": "Enrobé à froid en hiver."},
               {"n": 2, "title": "Model card M2", "page": None, "text": "Limites du modèle."}]
    msgs = build_messages("Comment réparer ?", sources)
    assert msgs[0]["role"] == "system" and REFUSAL in msgs[0]["content"] and msgs[0]["content"] == SYSTEM
    assert REFUSAL == "Je ne trouve pas cette information dans les documents"
    user = msgs[1]["content"]
    assert "[1] Guide nids-de-poule (p. 12)\nEnrobé à froid en hiver." in user
    assert "[2] Model card M2\nLimites du modèle." in user
    assert "[1]" in msgs[0]["content"] and "Comment réparer ?" in user
