"""RAG evaluation: question set shape and metric maths (no database, no Ollama)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from rag import evaluate as E  # noqa: E402
from rag.prompt import REFUSAL  # noqa: E402

Q = {"id": "x", "answerable": True, "expected_document": "Guide", "expected_pages": [10]}


def test_question_set_shape():
    qs = E.load_questions()
    assert len(qs) == 20 and len({q["id"] for q in qs}) == 20
    ans = [q for q in qs if q["answerable"]]
    assert sum(q["lang"] == "fr" for q in ans) == 12 and sum(q["lang"] == "en" for q in ans) == 4
    assert all(q["expected_document"] for q in ans)
    assert all(q["expected_document"] is None for q in qs if not q["answerable"])
    assert set(E.VARIANTS["combined_gemma4"]["ids"]) <= {q["id"] for q in qs}


def test_hit_rank_needs_document_and_page():
    srcs = [{"title": "Guide", "page": 9}, {"title": "Autre", "page": 10}, {"title": "Guide", "page": 10}]
    assert E.hit_rank(srcs, Q) == 3
    assert E.hit_rank(srcs, {**Q, "expected_pages": None}) == 1
    assert E.hit_rank(srcs[:2], Q) is None
    alt = {**Q, "also_accepted": [{"document": "Autre", "pages": [10]}]}
    assert E.hit_rank(srcs, alt) == 2


def test_refusal_and_citations():
    assert E.is_refusal(f"« {REFUSAL}. »") and E.is_refusal("je ne trouve pas cette information dans les documents")
    assert E.is_refusal("  ") and not E.is_refusal("Il faut 25 mm [1].")
    assert E.citations("A [2], B [1, 2] et C [7] [3][1]", n_sources=4) == [2, 1, 3]
    assert E.citations("Sans citation.", 4) == []


def test_summary_maths():
    recs = [
        {"answerable": True, "hit_rank": 1, "refused": False, "cited": [1], "cited_expected": True, "latency_ms": 1000},
        {"answerable": True, "hit_rank": 2, "refused": False, "cited": [], "cited_expected": False, "latency_ms": 3000},
        {"answerable": True, "hit_rank": None, "refused": True, "cited": [], "cited_expected": False, "latency_ms": 2000},
        {"answerable": False, "hit_rank": None, "refused": True, "cited": [], "cited_expected": False, "latency_ms": 500},
    ]
    s = E.summarize(recs)
    assert s["hit_at_1"]["value"] == round(1 / 3, 4) and s["hit_at_4"]["num"] == 2
    assert s["mrr_at_4"] == round((1 + 0.5) / 3, 4)
    assert (s["refusal_on_answerable"]["num"], s["refusal_on_answerable"]["den"]) == (1, 3)
    assert s["correct_refusal_on_unanswerable"]["value"] == 1.0
    assert (s["citation_present"]["num"], s["citation_present"]["den"]) == (1, 2)
    assert s["expected_source_cited"]["value"] == 0.5
    assert s["median_latency_s"] == 1.5
    assert s["labels"] == {"correct": 0, "partial": 0, "wrong": 0, "unlabelled": 2}
    row = E.report_row("`v`", {"model": "m", "bilingual": True, "prompt": "v2"}, s, "2026-10-15 10:00")
    assert row.startswith("| `v` | 2026-10-15 10:00 | m | on | simple | off | off | v2 | 3 + 1 | 0.33 (1/3) |")
    assert "| not labelled (2) |" in row
    recs[0]["label"], recs[1]["label"] = "correct", "wrong"
    row = E.report_row("`v`", {"model": "m", "fts": "french", "context": True, "min_similarity": 0.6},
                       E.summarize(recs), "d")
    assert "| french | on | 0.60 |" in row and "| 1 / 0 / 1 |" in row


def test_variants_add_one_fix_at_a_time():
    V = E.VARIANTS
    assert not any(V[n]["bilingual"] for n in ("fts_french", "chunk_context", "confidence_gate", "numbers_rule"))
    assert (V["fts_french"]["fts"], V["fts_french"]["context"], V["fts_french"]["prompt"]) == ("french", False, "v2")
    assert V["chunk_context"]["context"] and V["chunk_context"]["min_similarity"] == 0
    assert (V["numbers_rule"]["prompt"], V["numbers_rule"]["numbers_rule"]) == ("v2", True)
    assert not any(V[n]["numbers_rule"] for n in V if n != "numbers_rule")      # runs so far: no rule
    assert V["numbers_rule"]["min_similarity"] == V["confidence_gate"]["min_similarity"]


def _r(id_, answerable, hit, sim, refused=False, label=None):
    return {"id": id_, "answerable": answerable, "hit_rank": 1 if hit else None, "best_similarity": sim,
            "refused": refused, "cited": [] if refused else [1], "cited_expected": hit and not refused,
            "label": label, "latency_ms": 1000}


def test_gate_threshold_is_the_midpoint_rule():
    recs = [_r("a", True, True, 0.80, label="correct"), _r("b", True, True, 0.70, label="correct"),
            _r("c", True, False, 0.55, label="wrong"), _r("u1", False, False, 0.60, refused=True),
            _r("u2", False, False, 0.50)]
    g = E.gate_threshold(recs)
    assert (g["lowest_answerable_hit"], g["highest_unanswerable"], g["threshold"], g["separable"]) == (0.70, 0.60, 0.65, True)
    out = E.gate_outcomes(recs, {r["id"]: g["threshold"] for r in recs})
    assert [o["gated"] for o in out] == [False, False, True, True, True]
    assert out[2]["refused"] and out[2]["label"] is None and out[4]["refused"]   # wrong answer and u2 now refused


def test_gate_leave_one_out_recomputes_without_k():
    recs = [_r("a", True, True, 0.80, label="correct"), _r("b", True, True, 0.70, label="correct"),
            _r("u1", False, False, 0.60, refused=True), _r("u2", False, False, 0.50, refused=True)]
    st = E.gate_study(recs)
    loo = {q["id"]: q["loo_threshold"] for q in st["per_question"]}
    assert st["threshold"] == 0.65
    assert loo["b"] == 0.70 and loo["u1"] == 0.60          # without b: (0.80+0.60)/2; without u1: (0.70+0.50)/2
    gated = {q["id"]: q["gated_loo"] for q in st["per_question"]}
    assert gated == {"a": False, "b": False, "u1": False, "u2": True}   # u1 escapes the gate out of sample
    assert st["leave_one_out"]["correct_refusal_on_unanswerable"]["value"] == 1.0
