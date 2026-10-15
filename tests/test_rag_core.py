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
    msgs = build_messages("Comment réparer ?", sources, "v1", numbers_rule=False)   # part A prompt, unchanged
    assert msgs[0]["role"] == "system" and REFUSAL in msgs[0]["content"] and msgs[0]["content"] == SYSTEM
    assert REFUSAL == "Je ne trouve pas cette information dans les documents"
    user = msgs[1]["content"]
    assert "[1] Guide nids-de-poule (p. 12)\nEnrobé à froid en hiver." in user
    assert "[2] Model card M2\nLimites du modèle." in user
    assert "[1]" in msgs[0]["content"] and "Comment réparer ?" in user


def test_prompt_defaults_are_v2_with_numbers_rule():
    from rag import config
    sources = [{"n": 1, "title": "Guide", "page": 3, "text": "Texte."}]
    assert (config.RAG_PROMPT_VERSION, config.RAG_NUMBERS_RULE, config.RAG_BILINGUAL) == ("v2", True, False)
    assert (config.RAG_MIN_SIMILARITY, config.RAG_FTS_CONFIG, config.RAG_CHUNK_CONTEXT) == (0, "simple", False)
    assert build_messages("Q ?", sources) == build_messages("Q ?", sources, "v2", numbers_rule=True)
    assert build_messages("Q ?", sources, "v1", False)[1]["content"].endswith("Réponse (en citant les sources) :")


def test_prompt_v2_few_shot_refusal_and_question_last():
    from rag.prompt import FEW_SHOT_ANSWER, SYSTEM_V2
    sources = [{"n": 1, "title": "Guide", "page": 3, "text": "Texte."}]
    msgs = build_messages("Comment réparer ?", sources, "v2", numbers_rule=False)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[0]["content"] == SYSTEM_V2 and REFUSAL in SYSTEM_V2 and "[1]" in SYSTEM_V2
    assert "[1]" in msgs[2]["content"] and msgs[2]["content"] == FEW_SHOT_ANSWER
    user = msgs[3]["content"]
    assert user.startswith("Sources :") and "[1] Guide (p. 3)\nTexte." in user
    assert user.splitlines()[-1] == "Question : Comment réparer ?"


def test_translation_targets_other_language_cleans_and_caches(monkeypatch):
    from rag import ollama, translate as T
    calls = []

    def fake_chat(messages, model=None, options=None):
        calls.append((messages[0]["content"], model))
        return 'Translation: "What are the limits of the M2 model?"\n\nNote: literal.'
    monkeypatch.setattr(ollama, "chat", fake_chat)
    T.translate.cache_clear()
    q = "Quelles sont les limites du modèle M2 ?"
    assert T.translate(q, "m") == "What are the limits of the M2 model?"
    assert T.translate(q, "m") == "What are the limits of the M2 model?"
    assert len(calls) == 1 and "into English" in calls[0][0]
    assert T.target_lang("What is raveling and how is it measured?") == "fr"
    T.translate.cache_clear()


def test_search_queries_fall_back_to_the_question(monkeypatch):
    from rag import ollama, translate as T
    from rag.retrieve import search_queries
    assert search_queries("Bonjour ?", bilingual=False) == ["Bonjour ?"]

    def broken(*a, **k):
        raise ollama.OllamaError("HTTP 500")
    monkeypatch.setattr(ollama, "chat", broken)
    T.translate.cache_clear()
    assert search_queries("Quelles sont les limites ?", bilingual=True) == ["Quelles sont les limites ?"]
    monkeypatch.setattr(ollama, "chat", lambda *a, **k: "What are the limits?")
    T.translate.cache_clear()
    assert search_queries("Quelles sont les limites ?", bilingual=True) == ["Quelles sont les limites ?",
                                                                             "What are the limits?"]
    T.translate.cache_clear()


def test_numbers_rule_only_extends_the_system_prompt():
    from rag.prompt import NUMBERS_RULE, SYSTEM_V2
    sources = [{"n": 1, "title": "Guide", "page": 3, "text": "Texte."}]
    off, on = build_messages("Q ?", sources, "v2", False), build_messages("Q ?", sources, "v2", True)
    assert on[0]["content"] == f"{SYSTEM_V2} {NUMBERS_RULE}" and "≤" in NUMBERS_RULE
    assert off[0]["content"] == SYSTEM_V2 and off[1:] == on[1:]
    assert build_messages("Q ?", sources, "v1", True)[0]["content"] == f"{SYSTEM} {NUMBERS_RULE}"


def test_confidence_gate_and_whitelisted_columns():
    from rag.retrieve import columns, passes_gate
    assert passes_gate(0.3, 0) and passes_gate(None, 0)
    assert passes_gate(0.71, 0.7) and not passes_gate(0.69, 0.7) and not passes_gate(None, 0.7)
    assert columns("simple", False) == ("embedding", "tsv", "simple")
    assert columns("french", False) == ("embedding", "tsv_fr", "french")
    assert columns("simple", True) == ("embedding_ctx", "tsv_fr_ctx", "french")


def test_chunk_context_headers_headings_and_footers():
    from rag.context import build_contexts, heading_candidates, page_header
    t1 = ("27 réparation de nids-de-poule avec un enrobé Chaud 5.2 NIVEAU DE QUALITÉ SOUHAITÉ / Continuité du "
          "profil (±5 mm). 6. DURABILITÉ DE LA RÉPARATION La longévité ... CONSEIL PERMANENT chaussées")
    assert page_header(t1) == "réparation de nids-de-poule avec un enrobé Chaud"
    assert [h for _, h in heading_candidates(t1)][:2] == ["5.2 NIVEAU DE QUALITÉ SOUHAITÉ", "6 DURABILITÉ DE LA RÉPARATION"]
    assert heading_candidates("Une largeur ≤ 6 mm. EC-10 PG 58-28 MTQ 6325 LOW A crack") == []
    ctx = build_contexts("Guide", [(27, t1), (27, "suite du texte"), (28, "x CONSEIL PERMANENT y"),
                                   (29, "CONSEIL PERMANENT z"), (30, "texte simple")])
    assert ctx[0] == ("Guide — réparation de nids-de-poule avec un enrobé Chaud — "
                      "5.2 NIVEAU DE QUALITÉ SOUHAITÉ; 6 DURABILITÉ DE LA RÉPARATION")
    assert ctx[1] == "Guide — réparation de nids-de-poule avec un enrobé Chaud — 6 DURABILITÉ DE LA RÉPARATION"
    assert ctx[4] == "Guide — 6 DURABILITÉ DE LA RÉPARATION"          # footer ignored, heading carried
