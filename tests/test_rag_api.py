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
