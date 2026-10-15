"""Assistant API: grounded answers over the indexed documents (supervisors only)."""
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.auth import require_role
from shared.db import get_db

from . import config, ollama
from .ollama import OllamaError, OllamaUnavailable
from .prompt import REFUSAL, build_messages
from .retrieve import passes_gate, retrieve_scored


class UTF8JSONResponse(JSONResponse):
    """Explicit charset: PowerShell 5.1 (Invoke-RestMethod) otherwise decodes the French text as Latin-1."""
    media_type = "application/json; charset=utf-8"


router = APIRouter(default_response_class=UTF8JSONResponse)
SUPERVISORS = ("equipment_supervisor", "transport_supervisor")
UNAVAILABLE = ("Le service de langage (Ollama) est injoignable. Vérifiez qu'Ollama tourne sur l'hôte "
               "et écoute sur toutes les interfaces (OLLAMA_HOST=0.0.0.0), puis réessayez.")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@router.post("/ask")
def ask(req: AskRequest, db: Session = Depends(get_db), user=Depends(require_role(*SUPERVISORS))):
    question = req.question.strip()
    t0 = time.perf_counter()
    try:
        sources, best = retrieve_scored(db, question)
        if not passes_gate(best):        # nothing close enough in the documents: refuse without the LLM
            sources = []
        answer = ollama.chat(build_messages(question, sources)) if sources else f"{REFUSAL}."
    except OllamaUnavailable:
        raise HTTPException(503, UNAVAILABLE)
    except OllamaError as exc:
        raise HTTPException(502, f"Erreur du service de langage : {exc}")
    latency_ms = int((time.perf_counter() - t0) * 1000)
    db.execute(text("""
        INSERT INTO rag_queries (asked_by, question, retrieved_chunk_ids, model, latency_ms, answer)
        VALUES (CAST(:u AS text), CAST(:q AS text), CAST(:ids AS uuid[]), CAST(:m AS text), :ms, CAST(:a AS text))"""),
        {"u": user.get("sub"), "q": question, "ids": [s["chunk_id"] for s in sources],
         "m": config.RAG_LLM_MODEL, "ms": latency_ms, "a": answer})
    db.commit()
    return {"answer": answer,
            "sources": [{k: s[k] for k in ("n", "title", "source_path", "page", "snippet", "score")} for s in sources],
            "model": config.RAG_LLM_MODEL, "latency_ms": latency_ms}


@router.get("/status")
def status(db: Session = Depends(get_db), user=Depends(require_role(*SUPERVISORS))):
    try:
        names, reachable, error = ollama.tags(), True, None
    except (OllamaUnavailable, OllamaError) as exc:
        names, reachable, error = [], False, str(exc)
    present = lambda m: m in names or f"{m}:latest" in names  # noqa: E731
    counts = db.execute(text("SELECT (SELECT count(*) FROM rag_documents) documents, "
                             "(SELECT count(*) FROM rag_chunks) chunks")).mappings().one()
    return {"ollama": {"url": config.OLLAMA_URL, "reachable": reachable, "error": error,
                       "models": {config.RAG_LLM_MODEL: present(config.RAG_LLM_MODEL),
                                  config.RAG_EMBED_MODEL: present(config.RAG_EMBED_MODEL)}},
            "documents": counts["documents"], "chunks": counts["chunks"]}
