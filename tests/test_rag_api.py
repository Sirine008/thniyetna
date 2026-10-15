"""Assistant endpoints with Ollama down: clear French 503 on /ask, status reports it without failing.
Router functions are called directly with a fake session (no database, no network)."""
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("fastapi")
sys.path.insert(0, str(ROOT / "backend"))
from fastapi import HTTPException  # noqa: E402

from rag import ollama  # noqa: E402
from rag import router as R  # noqa: E402

SUPERVISOR = {"sub": "transport.supervisor", "role": "transport_supervisor"}


class _Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def one(self):
        return self.value


class FakeDb:
    def __init__(self):
        self.statements = []

    def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        return _Result({"documents": 3, "chunks": 42})

    def commit(self):
        pass


@pytest.fixture
def ollama_down(monkeypatch):
    def refuse(*args, **kwargs):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
    monkeypatch.setattr(ollama.urllib.request, "urlopen", refuse)


def test_ask_returns_503_in_french_when_ollama_is_down(ollama_down):
    db = FakeDb()
    with pytest.raises(HTTPException) as exc:
        R.ask(R.AskRequest(question="Quelles sont les limites du modèle M2 ?"), db=db, user=SUPERVISOR)
    assert exc.value.status_code == 503
    assert "Ollama" in exc.value.detail and "injoignable" in exc.value.detail
    assert not any("INSERT INTO rag_queries" in s for s in db.statements)


def test_status_reports_unreachable_without_failing(ollama_down):
    out = R.status(db=FakeDb(), user=SUPERVISOR)
    assert out["ollama"]["reachable"] is False
    assert out["ollama"]["models"] == {R.config.RAG_LLM_MODEL: False, R.config.RAG_EMBED_MODEL: False}
    assert (out["documents"], out["chunks"]) == (3, 42)


def test_status_matches_latest_tags(monkeypatch):
    monkeypatch.setattr(ollama, "tags", lambda: ["nomic-embed-text:latest", "llama3.2:3b"])
    out = R.status(db=FakeDb(), user=SUPERVISOR)
    assert out["ollama"]["reachable"] is True and all(out["ollama"]["models"].values())


def test_assistant_json_declares_utf8():
    assert R.router.default_response_class.media_type == "application/json; charset=utf-8"
    resp = R.UTF8JSONResponse({"answer": "réseau"})
    assert resp.headers["content-type"] == "application/json; charset=utf-8"
    assert resp.body.decode("utf-8") == '{"answer":"réseau"}'


class LogDb(FakeDb):
    def __init__(self):
        super().__init__()
        self.params = []

    def execute(self, stmt, params=None):
        self.params.append(params)
        return super().execute(stmt, params)


SRC = {"n": 1, "chunk_id": "00000000-0000-0000-0000-000000000001", "title": "Guide", "source_path": "corpus/g.pdf",
       "page": 27, "snippet": "court", "text": "La durabilité de l'intervention peut aller jusqu'à 5 ans. " * 20,
       "score": 0.03}
EQUIPMENT = {"sub": "equipment.supervisor", "role": "equipment_supervisor"}


def _facts(events=()):
    return {"segment": {"segment_code": "OSM-1", "name": None, "road_class": "regional"}, "risk": None,
            "events": list(events), "complaints": [], "last_inspection_at": None}


def test_ask_sources_carry_an_excerpt(monkeypatch):
    monkeypatch.setattr(R, "retrieve_scored", lambda db, q: ([SRC], 0.8))
    monkeypatch.setattr(ollama, "chat", lambda *a, **k: "Jusqu'à 5 ans [1].")
    out = R.ask(R.AskRequest(question="Durée de vie ?"), db=LogDb(), user=SUPERVISOR)
    ex = out["sources"][0]["excerpt"]
    assert 300 < len(ex) <= 402 and ex.startswith("La durabilité") and out["sources"][0]["page"] == 27


def test_intervention_sheet_order_sources_and_log(monkeypatch):
    pothole = {"event_type": "pothole", "severity": 0.85, "confidence": 0.9, "validated": True,
               "observed_at": "2026-10-14T08:30:00", "source": "m1"}
    monkeypatch.setattr(R.intervention, "gather_facts", lambda db, code: _facts([pothole]))
    seen = {}
    monkeypatch.setattr(R, "retrieve_scored", lambda db, q, k: (seen.update(q=q, k=k) or [SRC], 0.8))
    monkeypatch.setattr(ollama, "chat", lambda *a, **k: "### Intervention recommandée\nA [1].\n"
                        "### Conditions de mise en œuvre\nB [1].\n### Signalisation et sécurité du chantier\nC [1].")
    db = LogDb()
    out = R.intervention_sheet("OSM-1", db=db, user=EQUIPMENT)
    assert seen == {"q": "réparation nid-de-poule enrobé température signalisation chantier", "k": 6}
    assert [s["key"] for s in out["sections"]] == ["constat", "priorite", "intervention", "conditions",
                                                   "signalisation", "manquant"]
    assert [s["origin"] for s in out["sections"]] == ["données", "données", "assistant", "assistant", "assistant", "données"]
    assert out["sections"][2]["text"] == "A [1]." and not out["no_defect"] and out["assistant_available"]
    assert out["sources"][0]["excerpt"] and out["sources"][0]["title"] == "Guide"
    log = [p for p in db.params if p and "ids" in p][0]
    assert log["q"].startswith("Fiche d'intervention OSM-1 :") and log["ids"] == [SRC["chunk_id"]]


def test_intervention_unknown_segment_404(monkeypatch):
    monkeypatch.setattr(R.intervention, "gather_facts", lambda db, code: None)
    with pytest.raises(HTTPException) as exc:
        R.intervention_sheet("NOPE", db=LogDb(), user=EQUIPMENT)
    assert exc.value.status_code == 404


def test_intervention_without_ollama_keeps_the_database_sections(monkeypatch, ollama_down):
    monkeypatch.setattr(R.intervention, "gather_facts", lambda db, code: _facts())
    db = LogDb()
    out = R.intervention_sheet("OSM-1", db=db, user=EQUIPMENT)
    assert out["assistant_available"] is False and out["no_defect"] and out["sources"] == []
    assert [s["key"] for s in out["sections"]] == ["constat", "priorite", "inspection", "manquant"]
    assert "Aucun défaut ouvert" in out["sections"][0]["text"] and "injoignable" in out["sections"][2]["text"]
    assert not any(p and "ids" in p for p in db.params)            # nothing logged without an answer
