"""Small evaluation of the agent's tool choice against the real Ollama (run it yourself; nothing is precomputed).

    cd backend
    $env:DATABASE_URL = "postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5433/thniyetna"
    $env:OLLAMA_URL = "http://localhost:11434"
    ..\\ml\\.venv\\Scripts\\python.exe -m agent.evaluate [--ids a01,a02]

Tasks: data/agent/eval/tasks.jsonl ({id, question, expected_tools}). Metrics per task:
- first_tool_correct: the first tool called is one of expected_tools;
- all_expected_called: every expected tool was called at least once (even if the call failed);
- all_expected_ok: every expected tool was called successfully (stricter);
- invented_codes: calls rejected with « Segment inconnu » (a segment code not taken from a tool result);
- action tasks (with expected_target): target_ok = the expected action tool was called successfully with exactly
  that segment code / event id; claims_done = the answer says the action already ran (French patterns, heuristic:
  read the answers too). Proposals are not stored during the evaluation (no write).
- no_tool: the model answered without any tool;
- latency_s, rounds, warnings.
Results: data/agent/eval/results.json (overwritten). Read-only: same tools as the endpoint, no rag_queries log.
"""
import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "data" / "agent" / "eval" / "tasks.jsonl"
RESULTS = ROOT / "data" / "agent" / "eval" / "results.json"


def load_tasks(path: Path = TASKS) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


# « done » claims for a proposal that only waits for confirmation (heuristic, French)
_CLAIM_DONE = re.compile(r"\b(a été|ont été|est maintenant|sont maintenant)\s+(planifiée?s?|envoyée?s?|validée?s?|"
                         r"générée?s?|notifiée?s?|prévenue?s?)|\bj'ai\s+(planifié|envoyé|validé|généré|prévenu|notifié)"
                         r"|c'est fait", re.IGNORECASE)


def claims_done(answer: str) -> bool:
    return bool(_CLAIM_DONE.search(answer or ""))


def score_task(task: dict, out: dict) -> dict:
    """Tool-choice metrics of one run (pure)."""
    called = [s["tool"] for s in out["steps"]]
    expected = task["expected_tools"]
    return {"id": task["id"], "question": task["question"], "expected_tools": expected, "called_tools": called,
            "first_tool_correct": bool(called) and called[0] in expected,
            "all_expected_called": all(t in called for t in expected),
            "no_tool": not called, "invalid_calls": sum(not s.get("ok") for s in out["steps"]),
            "tool_set": out.get("tool_set"),
            "ok_calls": [s["tool"] for s in out["steps"] if s.get("ok")],
            "all_expected_ok": all(t in [s["tool"] for s in out["steps"] if s.get("ok")] for t in expected),
            "invented_codes": sum("Segment inconnu" in (s.get("error") or "") for s in out["steps"]),
            "rounds": out["rounds"], "stop_reason": out["stop_reason"], "warnings": out["warnings"],
            "steps": [{k: s.get(k) for k in ("round", "tool", "arguments", "ok", "error", "ms")} for s in out["steps"]],
            "calls": out.get("calls", []), "answer": out["answer"],
            **({"target_ok": any(s.get("ok") and s["tool"] in expected
                                 and all(s.get("arguments", {}).get(k) == v for k, v in task["expected_target"].items())
                                 for s in out["steps"]),
                "claims_done": claims_done(out["answer"]),
                "proposals": [a.get("type") for a in out.get("actions", [])]} if task.get("expected_target") else {})}


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    rate = lambda key: round(sum(r[key] for r in rows) / n, 3) if n else None  # noqa: E731
    acts = [r for r in rows if "target_ok" in r]
    action = {"action_tasks": len(acts),
              "action_target_ok": round(sum(r["target_ok"] for r in acts) / len(acts), 3) if acts else None,
              "action_claims_done": sum(r["claims_done"] for r in acts)} if acts else {}
    return {**action, "tasks": n, "first_tool_correct": rate("first_tool_correct"),
            "all_expected_called": rate("all_expected_called"), "all_expected_ok": rate("all_expected_ok"),
            "no_tool": rate("no_tool"), "invalid_calls": sum(r["invalid_calls"] for r in rows),
            "invented_codes": sum(r["invented_codes"] for r in rows),
            "median_latency_s": round(statistics.median(r["latency_s"] for r in rows), 1) if n else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the agent's tool choice against the real Ollama")
    ap.add_argument("--ids", help="comma-separated task ids")
    ap.add_argument("--out", type=Path, default=RESULTS, help="results file (default data/agent/eval/results.json)")
    args = ap.parse_args(argv)
    from rag import config, ollama
    from shared.db import SessionLocal

    from .loop import run_agent

    tasks = [t for t in load_tasks() if not args.ids or t["id"] in args.ids.split(",")]
    print(f"Agent eval: {len(tasks)} task(s), {config.RAG_LLM_MODEL} via {config.OLLAMA_URL}")
    try:
        ollama.chat([{"role": "user", "content": "OK"}], options={"num_predict": 1})   # load the model, untimed
    except ollama.OllamaUnavailable as exc:
        print(f"Ollama unreachable: {exc}", file=sys.stderr)
        return 2
    rows = []
    with SessionLocal() as db:
        for task in tasks:
            t0 = time.perf_counter()
            out = run_agent(db, task["question"])
            row = {**score_task(task, out), "latency_s": round(time.perf_counter() - t0, 1)}
            rows.append(row)
            print(f"  {task['id']} first_ok={row['first_tool_correct']} all={row['all_expected_called']} "
                  f"called={row['called_tools']} {row['latency_s']} s")
    result = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "model": config.RAG_LLM_MODEL,
              "summary": summarize(rows), "tasks": rows}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
