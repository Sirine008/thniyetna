"""Equipment agent: tool calling loop, validation, read-only tools, endpoint (503 / 403).
Ollama is mocked (a scripted chat function, or urlopen refused); the database is a fake session."""
import inspect
import json
import re
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("fastapi")
sys.path.insert(0, str(ROOT / "backend"))
from fastapi import HTTPException  # noqa: E402

from agent import evaluate as E  # noqa: E402
from agent import loop as L  # noqa: E402
from agent import router as R  # noqa: E402
from agent import tools as T  # noqa: E402
from rag import intervention, ollama  # noqa: E402

EQUIPMENT = {"sub": "equipment.supervisor", "role": "equipment_supervisor"}
TRANSPORT = {"sub": "transport.supervisor", "role": "transport_supervisor"}
SEGMENTS = [
    {"segment_code": "OSM-125567491", "name": "Route de Menzel", "road_class": "national", "maintenance_priority": "P1",
     "risk_level": "high", "risk_score": 0.612345, "predicted_condition": "poor", "model_version": "2026.10.11-2054",
     "open_defects": 2, "demo": True},
    {"segment_code": "OSM-116022841", "name": None, "road_class": "regional", "maintenance_priority": "P2",
     "risk_level": "medium", "risk_score": 0.431, "predicted_condition": "fair", "model_version": "2026.10.11-2054",
     "open_defects": 0, "demo": False},
]
DASHBOARD = {"open_complaints": 7, "unvalidated_events": 3, "events_24h": 2, "active_inspections": 0}


class Result:
    def __init__(self, rows):
        self.rows = rows if isinstance(rows, list) else [rows]

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        return self.rows[0]


class FakeDb:
    """Answers by SQL keyword; records every statement and its parameters."""

    def __init__(self):
        self.calls = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.calls.append((sql, params))
        if "maintenance_priority = ANY" in sql:
            return Result([s for s in SEGMENTS if s["maintenance_priority"] in params["p"]][:params["n"]])
        if "open_complaints" in sql:
            return Result(DASHBOARD)
        return Result([])

    def commit(self):
        pass


def scripted(*messages):
    """Chat function returning the given assistant messages in order; records what it received."""
    seen, queue = [], list(messages)

    def chat(msgs, tools, model=None, options=None):
        seen.append({"messages": [dict(m) for m in msgs], "tools": tools, "options": options})
        return queue.pop(0) if queue else {"role": "assistant", "content": "", "tool_calls": []}
    chat.seen = seen
    return chat


def call(name, args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def say(text):
    return {"role": "assistant", "content": text, "tool_calls": []}


# ---------------------------------------------------------------- loop

def test_tool_is_called_with_validated_arguments_and_answer_is_grounded():
    db = FakeDb()
    chat = scripted(call("list_priority_segments", {"limit": "2", "min_priority": "p2"}),
                    say("Traiter d'abord OSM-125567491 (P1, risque 0.612345, DÉMO — données fictives), "
                        "puis OSM-116022841 (P2, risque 0.431)."))
    out = L.run_agent(db, "Quels segments traiter en priorité ?", chat=chat)
    assert db.calls[0][1]["p"] == ["P1", "P2"] and db.calls[0][1]["n"] == 2          # string "2" / "p2" coerced
    assert [s["tool"] for s in out["steps"]] == ["list_priority_segments"] and out["steps"][0]["ok"]
    assert out["steps"][0]["arguments"] == {"limit": 2, "min_priority": "P2"}
    assert "2 segment(s) de priorité P1/P2" in out["steps"][0]["result_summary"]
    assert "DÉMO" in out["steps"][0]["result_summary"]
    assert out["tool_results"][0]["result"]["segments"][0]["risk_score"] == 0.612345   # raw numbers for the UI
    assert [s["segment_code"] for s in out["segments"]] == ["OSM-125567491", "OSM-116022841"]
    assert out["warnings"] == [] and out["stop_reason"] == "answer" and out["rounds"] == 1
    tool_msg = chat.seen[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_name"] == "list_priority_segments"
    assert json.loads(tool_msg["content"])["count"] == 2
    assert chat.seen[0]["options"]["temperature"] == 0 and len(chat.seen[0]["tools"]) == 9   # 5 read + 4 action
    assert not any(w in sql.upper() for sql, _ in db.calls for w in ("INSERT", "UPDATE ", "DELETE"))


def test_unknown_tool_goes_back_to_the_model_as_an_error():
    chat = scripted(call("delete_segment", {"segment_code": "OSM-1"}), say("Je ne peux pas faire cela."))
    out = L.run_agent(FakeDb(), "Supprime le segment OSM-1", chat=chat)
    step = out["steps"][0]
    assert step["ok"] is False and "Outil inconnu : delete_segment" in step["error"]
    assert "erreur" in json.loads(chat.seen[1]["messages"][-1]["content"])
    assert out["answer"] == "Je ne peux pas faire cela." and out["tool_results"] == []


@pytest.mark.parametrize("name, args, message", [
    ("get_segment_facts", {}, "Argument manquant"),
    ("list_priority_segments", {"limit": 99}, "entre 1 et 20"),
    ("list_priority_segments", {"limit": "beaucoup"}, "doit être un entier"),
    ("list_priority_segments", {"min_priority": "P9"}, "doit valoir P1"),
    ("get_equipment_dashboard", {"since": "hier"}, "Argument(s) inconnu(s)"),
    ("search_guides", "{pas du json", "Arguments illisibles"),
])
def test_bad_arguments_never_crash(name, args, message):
    out = L.run_agent(FakeDb(), "question", chat=scripted(call(name, args), say("Désolé.")))
    assert out["steps"][0]["ok"] is False and message in out["steps"][0]["error"]
    assert out["answer"] == "Désolé."


def test_max_rounds_then_one_final_call_without_tools():
    chat = scripted(*[call("get_equipment_dashboard", {})] * 7)      # never concludes
    out = L.run_agent(FakeDb(), "Compteurs ?", chat=chat)
    assert out["rounds"] == L.MAX_ROUNDS == 3 and len(out["steps"]) == 3   # chosen from the 07/11 measurements
    assert out["stop_reason"] == "max_rounds" and out["answer"] == L.NO_CONCLUSION
    assert len(chat.seen) == 4 and chat.seen[-1]["tools"] == []
    assert chat.seen[-1]["messages"][-1]["content"] == L.FINAL_PROMPT


def test_time_budget_stops_tool_rounds():
    ticks = iter([0, 0, 0, 0, 500, 500, 500, 500, 500])
    chat = scripted(call("get_equipment_dashboard", {}), say("7 signalements ouverts."))
    out = L.run_agent(FakeDb(), "Compteurs ?", chat=chat, clock=lambda: next(ticks))
    assert out["rounds"] == 1 and out["stop_reason"] == "time_budget" and chat.seen[-1]["tools"] == []
    assert any("Temps de calcul limité" in w for w in out["warnings"])


def test_answer_without_any_tool_is_kept_and_flagged():
    out = L.run_agent(FakeDb(), "Quels segments traiter ?", chat=scripted(say("Traitez OSM-999, risque 0.9.")))
    assert out["steps"] == [] and out["answer"] == "Traitez OSM-999, risque 0.9."
    assert out["warnings"][0] == L.NO_TOOL_WARNING
    assert any("0.9" in w for w in out["warnings"]) and out["segments"] == []    # not in any tool result


def test_invented_numbers_are_flagged_but_tool_numbers_are_not():
    chat = scripted(call("get_equipment_dashboard", {}),
                    say("7 signalements ouverts, 3 détections à valider sur 24 h, et 42 chantiers prévus."))
    out = L.run_agent(FakeDb(), "Compteurs ?", chat=chat)
    assert out["tool_results"][0]["result"] == DASHBOARD
    assert len(out["warnings"]) == 1 and "42" in out["warnings"][0] and "7" not in out["warnings"][0].split(":")[1]


def test_ungrounded_numbers_compare_values_and_ignore_segment_codes():
    results = [{"result": {"risk_score": 0.5, "count": 5}}]
    assert L.ungrounded_numbers("Score 0,5 ; 5 segments ; OSM-125567491", "q", results) == []
    assert L.ungrounded_numbers("Score 0.55", "q", results) == ["0.55"]


def test_citations_are_numbered_globally_across_searches(monkeypatch):
    def chunk(cid):
        return {"n": 0, "title": f"Guide {cid}", "page": 1, "chunk_id": cid, "text": f"Texte {cid}."}
    batches = iter([[chunk("c1"), chunk("c2")], [chunk("c2"), chunk("c3")]])

    def fake_retrieve(db, q):
        rows = next(batches)
        return [{**r, "n": i} for i, r in enumerate(rows, start=1)], 0.8     # each search numbers from 1
    monkeypatch.setattr(T, "retrieve_scored", fake_retrieve)
    chat = scripted(call("search_guides", {"question": "enrobé chaud température"}),
                    call("search_guides", {"question": "signalisation chantier"}),
                    say("Température > 10 °C [1] ; panneaux [3]."))
    out = L.run_agent(FakeDb(), "Comment réparer ?", chat=chat)
    assert [(s["n"], s["chunk_id"]) for s in out["sources"]] == [(1, "c1"), (2, "c2"), (3, "c3")]
    second = out["tool_results"][1]["result"]["excerpts"]
    assert [(e["n"], e["chunk_id"]) for e in second] == [(2, "c2"), (3, "c3")]       # c2 keeps its first number
    sent = json.loads(chat.seen[2]["messages"][-1]["content"])
    assert [e["n"] for e in sent["excerpts"]] == [2, 3] and "chunk_id" not in sent["excerpts"][0]
    assert len({s["n"] for s in out["sources"]}) == len(out["sources"])               # never reused


def test_model_reads_compact_priority_rows_ui_keeps_full_rows():
    db = FakeDb()
    chat = scripted(call("list_priority_segments", {}), say("OSM-125567491 d'abord."))
    out = L.run_agent(db, "Priorités ?", chat=chat)
    assert db.calls[0][1]["n"] == 5 and db.calls[0][1]["p"] == ["P1", "P2", "P3"]       # defaults: 5 rows, P1..P3
    sent = json.loads(chat.seen[1]["messages"][-1]["content"])
    assert list(sent["segments"][0]) == ["segment_code", "name", "priority", "risk_level", "risk_score",
                                         "open_defects", "demo"]
    assert sent["segments"][0]["open_defects"] == 2 and sent["segments"][0]["priority"] == "P1"
    full = out["tool_results"][0]["result"]["segments"][0]
    assert full["predicted_condition"] == "poor" and full["model_version"] == "2026.10.11-2054"
    assert [c["kind"] for c in out["calls"]] == ["tools", "tools"] and out["calls"][0]["tool_calls"] == 1
    assert all(isinstance(c["llm_ms"], int) for c in out["calls"])


def test_empty_priority_list_tells_the_model_to_widen_the_filter():
    class Empty(FakeDb):
        def execute(self, stmt, params=None):
            self.calls.append((str(stmt), params))
            return Result([])
    out = T.list_priority_segments(Empty(), limit=5, min_priority="P1")
    assert out["count"] == 0 and 'min_priority="P3"' in out["hint"]
    assert "hint" not in T.list_priority_segments(Empty(), limit=5, min_priority="P4")


def test_no_real_segment_code_in_the_tool_descriptions():
    # llama3.2:3b copied an example code from a description on 07/11 (live check): placeholders only.
    assert not re.search(r"OSM-\d", json.dumps(T.ollama_schemas(), ensure_ascii=False))


# ---------------------------------------------------------------- tools

def test_tools_are_read_only_and_reuse_existing_code(monkeypatch):
    facts = {"segment": {"segment_code": "OSM-1", "name": None, "road_class": "local"}, "risk": None,
             "events": [{"event_type": "pothole", "severity": 0.8, "confidence": 0.9, "validated": False,
                         "observed_at": "2026-10-23T08:00:00", "source": "citizen", "demo": True}],
             "complaints": [], "last_inspection_at": None}
    monkeypatch.setattr(intervention, "gather_facts", lambda db, code: facts if code == "OSM-1" else None)
    monkeypatch.setattr(T, "retrieve_scored", lambda db, q: ([{"n": 1, "title": "Guide", "page": 27, "chunk_id": "c1",
                                                               "text": "Température > 10 °C. " * 40}], 0.7))
    db = FakeDb()
    assert T.get_equipment_dashboard(db) == DASHBOARD
    sheet = T.get_intervention_sheet(db, "OSM-1")
    assert [s["title"] for s in sheet["sections"]] == ["Constat", "Priorité", "Données manquantes"]
    assert sheet["demo"] is True and "DÉMO" in T.summarize("get_intervention_sheet", sheet)
    assert T.get_segment_facts(db, "OSM-1")["demo"] is True
    with pytest.raises(T.ToolError, match="Segment inconnu"):
        T.get_segment_facts(db, "OSM-404")
    guides = T.search_guides(db, "température enrobé")
    assert guides["excerpts"][0]["page"] == 27 and len(guides["excerpts"][0]["excerpt"]) <= 402
    T.list_priority_segments(db, limit=5, min_priority="P4")
    assert all(not any(w in sql.upper() for w in ("INSERT", "UPDATE ", "DELETE")) for sql, _ in db.calls)
    from platform_app.router import LATEST_SCORE_LATERAL
    assert LATEST_SCORE_LATERAL in db.calls[-1][0]                 # same latest-score subquery as /platform/map


def test_schemas_match_the_registry():
    schemas = T.ollama_schemas()
    assert [s["function"]["name"] for s in schemas] == list(T.TOOLS)
    facts = next(s for s in schemas if s["function"]["name"] == "get_segment_facts")["function"]
    assert facts["parameters"]["required"] == ["segment_code"] and "minLength" not in facts["parameters"]["properties"]["segment_code"]


# ---------------------------------------------------------------- endpoint

@pytest.fixture
def ollama_down(monkeypatch):
    def refuse(*args, **kwargs):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
    monkeypatch.setattr(ollama.urllib.request, "urlopen", refuse)


def test_endpoint_returns_french_503_when_ollama_is_down(ollama_down):
    db = FakeDb()
    with pytest.raises(HTTPException) as exc:
        R.agent(R.AgentRequest(question="Quels segments traiter ?"), db=db, user=EQUIPMENT)
    assert exc.value.status_code == 503 and "injoignable" in exc.value.detail
    assert not any("rag_queries" in sql for sql, _ in db.calls)


def test_endpoint_logs_the_question_and_returns_trace(monkeypatch):
    monkeypatch.setattr(R, "run_agent", lambda db, q, **kw: {"answer": "OK", "steps": [], "tool_results": [], "sources": [],
                                                       "segments": [], "warnings": [L.NO_TOOL_WARNING], "rounds": 0,
                                                       "stop_reason": "answer", "tool_set": "lecture"})
    db = FakeDb()
    out = R.agent(R.AgentRequest(question="Bonjour agent"), db=db, user=EQUIPMENT)
    assert out["answer"] == "OK" and out["question"] == "Bonjour agent" and "latency_ms" in out
    log = [p for sql, p in db.calls if "INSERT INTO rag_queries" in sql][0]
    assert log["q"] == "Agent [lecture] : Bonjour agent" and log["u"] == "equipment.supervisor"   # tool set logged
    assert R.router.default_response_class.media_type == "application/json; charset=utf-8"


def test_only_the_equipment_supervisor_can_call_the_agent():
    checker = inspect.signature(R.agent).parameters["user"].default.dependency
    with pytest.raises(HTTPException) as exc:
        checker(user=TRANSPORT)
    assert exc.value.status_code == 403
    assert checker(user=EQUIPMENT) == EQUIPMENT


def test_chat_with_tools_sends_tools_and_normalises_the_reply(monkeypatch):
    sent = {}

    def fake_request(path, payload=None, timeout=10):
        sent.update(path=path, payload=payload)
        return {"message": {"role": "assistant", "content": None,
                            "tool_calls": [{"function": {"name": "get_equipment_dashboard", "arguments": {}}}]}}
    monkeypatch.setattr(ollama, "_request", fake_request)
    msg = ollama.chat_with_tools([{"role": "user", "content": "q"}], T.ollama_schemas(), options={"temperature": 0})
    assert sent["path"] == "/api/chat" and sent["payload"]["tools"] and sent["payload"]["stream"] is False
    assert msg == {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_equipment_dashboard",
                                                                                     "arguments": {}}}]}


# ---------------------------------------------------------------- evaluation script

def test_eval_tasks_and_scoring():
    tasks = E.load_tasks()
    assert len(tasks) == 11 and all(set(t["expected_tools"]) <= set(T.TOOLS) for t in tasks)
    assert [t["id"] for t in tasks if t.get("expected_target")] == ["a09", "a10", "a11"]
    plan = next(t for t in tasks if t["id"] == "a09")
    ok = E.score_task(plan, {"steps": [{"tool": "plan_intervention", "ok": True,
                                        "arguments": {"segment_code": "OSM-713546524", "note": ""}}],
                             "rounds": 1, "stop_reason": "answer", "warnings": [], "answer": "Proposée, à confirmer.",
                             "actions": [{"type": "plan_intervention"}]})
    assert ok["target_ok"] and not ok["claims_done"] and ok["proposals"] == ["plan_intervention"]
    bad = E.score_task(plan, {"steps": [{"tool": "plan_intervention", "ok": False, "error": "Segment inconnu : OSM-1.",
                                         "arguments": {"segment_code": "OSM-1"}}],
                              "rounds": 1, "stop_reason": "answer", "warnings": [], "answer": "L'intervention a été planifiée."})
    assert not bad["target_ok"] and bad["claims_done"] and bad["invented_codes"] == 1
    assert E.summarize([{**ok, "latency_s": 1.0}, {**bad, "latency_s": 3.0}])["action_target_ok"] == 0.5
    assert E.claims_done("J'ai prévenu le Transport.") and not E.claims_done("Elle sera validée après votre confirmation.")
    row = E.score_task(tasks[7], {"steps": [{"tool": "list_priority_segments", "ok": True},
                                            {"tool": "get_segment_facts", "ok": False}],
                                  "rounds": 2, "stop_reason": "answer", "warnings": [], "answer": "x"})
    assert row["first_tool_correct"] and row["all_expected_called"] and row["invalid_calls"] == 1
    none = E.score_task(tasks[0], {"steps": [], "rounds": 0, "stop_reason": "answer", "warnings": [], "answer": "x"})
    assert none["no_tool"] and not none["first_tool_correct"]
    assert not row["all_expected_ok"]                       # the get_segment_facts call failed
    invented = E.score_task(tasks[7], {"steps": [{"tool": "list_priority_segments", "ok": True},
                                                 {"tool": "get_segment_facts", "ok": False, "error": "Segment inconnu : OSM-12345."}],
                                       "rounds": 1, "stop_reason": "answer", "warnings": [], "answer": "x"})
    assert invented["invented_codes"] == 1 and invented["all_expected_called"] and not invented["all_expected_ok"]
    summary = E.summarize([{**row, "latency_s": 40.0}, {**none, "latency_s": 20.0}])
    assert summary["first_tool_correct"] == 0.5 and summary["median_latency_s"] == 30.0
    assert summary["all_expected_ok"] == 0.0
