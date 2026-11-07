"""Equipment agent endpoints.

POST /assistant/agent                              the model chooses tools; action tools only PROPOSE (agent_actions)
POST /assistant/agent/actions/{action_id}/confirm  a human executes one proposal, once, as the logged-in user
POST /assistant/agent/actions/{action_id}/reject   a human ignores it; it will never run
GET  /assistant/agent/actions?ids=a,b             current state of proposals (marks the stale ones expired)
"""
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from rag import config as rag_config
from rag.ollama import OllamaError, OllamaUnavailable
from rag.router import UNAVAILABLE, UTF8JSONResponse, log_query
from shared.auth import require_role
from shared.db import get_db

from . import actions
from .loop import run_agent

router = APIRouter(default_response_class=UTF8JSONResponse)


class AgentRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@router.post("/agent")
def agent(req: AgentRequest, db: Session = Depends(get_db), user=Depends(require_role("equipment_supervisor"))):
    """The model chooses tools (read-only, or action tools that only propose), then answers in French. The response
    carries the trace, the raw tool results and the proposed actions (status 'proposed', to confirm or ignore)."""
    question = req.question.strip()
    run_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    try:
        out = run_agent(db, question, propose=lambda p: actions.store_proposal(db, run_id, user, p))
    except OllamaUnavailable:
        raise HTTPException(503, UNAVAILABLE)
    except OllamaError as exc:
        raise HTTPException(502, f"Erreur du service de langage : {exc}")
    latency_ms = int((time.perf_counter() - t0) * 1000)
    # The log line says which tool set the model had (« lecture » = 5 read tools, « actions » = + 4 action tools).
    log_query(db, user, f"Agent [{out['tool_set']}] : {question}", out["sources"], out["answer"], latency_ms)  # commits
    return {**out, "run_id": run_id, "question": question, "model": rag_config.RAG_LLM_MODEL,
            "expiry_minutes": actions.EXPIRY_MINUTES, "latency_ms": latency_ms}


@router.get("/agent/actions")
def list_agent_actions(ids: str = Query(default="", max_length=2000), db: Session = Depends(get_db),
                       user=Depends(require_role("equipment_supervisor"))):
    """State of the given proposals (comma-separated ids). Reading the list first marks every proposal older than
    30 min as 'expired', so the UI shows « Expirée » instead of « À confirmer »."""
    return actions.list_actions(db, [i.strip() for i in ids.split(",") if i.strip()])


def _decide(fn, action_id: str, db, user):
    try:
        return fn(db, action_id, user)
    except actions.ActionRefused as exc:
        raise HTTPException(exc.status_code, str(exc))


@router.post("/agent/actions/{action_id}/confirm")
def confirm_action(action_id: str, db: Session = Depends(get_db), user=Depends(require_role("equipment_supervisor"))):
    """Executes the proposal once with the existing code, the logged-in supervisor being the actor.
    409 if already decided, 410 if older than 30 min, 404 if unknown. A failure is stored (status 'failed')."""
    return _decide(actions.confirm, action_id, db, user)


@router.post("/agent/actions/{action_id}/reject")
def reject_action(action_id: str, db: Session = Depends(get_db), user=Depends(require_role("equipment_supervisor"))):
    """« Ignorer »: the proposal is closed (status 'rejected') and will never run."""
    return _decide(actions.reject, action_id, db, user)
