"""Agent loop for the equipment supervisor: the model chooses tools, we run them, it writes a short French answer.

- At most MAX_ROUNDS tool-call rounds, temperature 0. Tool name and arguments are validated; an unknown tool or
  bad arguments become an error message sent back to the model (never a crash).
- The trace is honest: if the model answers without calling any tool, nothing is faked; the response says so.
- Numbers: the answer must come from the tool results. The raw results are returned so the UI shows the real
  numbers; numbers of the answer that appear in no tool result are listed in `warnings`.
- Time budget: CPU rounds take 20–60 s each, so no new tool round starts after TIME_BUDGET_S; the model is then
  asked for its final answer (nginx cuts /api/assistant/ at 300 s).
"""
import json
import re
import time

from rag import config as rag_config
from rag import ollama

from . import tools

MAX_ROUNDS = 3
TIME_BUDGET_S = 150
AGENT_OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 500}

SYSTEM = (
    "Tu es l'agent du superviseur du Ministère de l'Équipement (réseau routier de Bizerte, application THNIYETNA). "
    "Tu disposes d'outils de lecture (base de données, guides techniques) et d'outils d'action qui ne font que "
    "PROPOSER une action : rien n'est exécuté sans la confirmation du superviseur. "
    "Règles :\n"
    "1. Pour toute question sur les segments, les priorités, les défauts, les signalements ou les compteurs, appelle "
    "d'abord l'outil adapté ; ne réponds jamais de mémoire.\n"
    "2. N'invente aucun chiffre, aucun code de segment, aucune date : recopie-les exactement depuis les résultats des "
    "outils. Si une information manque, dis-le.\n"
    "3. Pour une question de méthode (réparation, matériaux, signalisation), utilise search_guides et cite les "
    "extraits avec leur numéro [n].\n"
    "4. Si un résultat porte « demo »: true, précise « DÉMO — données fictives ».\n"
    "5. Réponds en français, en 5 à 8 lignes au plus, avec les codes de segment exacts.\n"
    "6. Une action proposée n'est jamais faite : écris « proposée, à confirmer », jamais « faite » ou « envoyée »."
)
# A rule « never use a segment code not seen in a tool result » was tried on 07/11 and removed: no fewer invented
# codes in the evaluation (3 → 3), and it made the model look for a segment code on a dashboard question
# (data/agent/eval/results_rule6.json, docs/AGENT.md).
FINAL_PROMPT = ("Rédige maintenant ta réponse finale en français, courte, à partir des seuls résultats d'outils "
                "ci-dessus, sans appeler d'autre outil.")
NO_CONCLUSION = (f"L'agent a atteint la limite de {MAX_ROUNDS} séries d'appels d'outils sans rédiger de conclusion. "
                 "Consultez les résultats des outils ci-dessous.")
NO_TOOL_WARNING = ("Le modèle a répondu sans consulter aucun outil : cette réponse ne s'appuie pas sur les données "
                   "de la plateforme. Vérifiez-la ou reformulez la question.")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
_SEGMENT = re.compile(r"\bOSM-\d+\b")


def _call_parts(call: dict) -> tuple[str, object]:
    fn = (call or {}).get("function") or {}
    return str(fn.get("name") or ""), fn.get("arguments")


def _canon(n: str) -> float:
    return float(n.replace(",", "."))


def ungrounded_numbers(answer: str, question: str, results: list[dict]) -> list[str]:
    """Numbers of the answer found in no tool result, in neither the question nor the tool descriptions
    (« 24 h », « 100 m »). Compared as numbers: 5 = 5.0, 0,18 = 0.18. Segment codes are ignored."""
    haystack = " ".join([question, json.dumps(results, ensure_ascii=False, default=str),
                         json.dumps(tools.ollama_schemas(), ensure_ascii=False)])
    known = {_canon(n) for n in _NUMBER.findall(_SEGMENT.sub(" ", haystack))}
    out = []
    for n in _NUMBER.findall(_SEGMENT.sub(" ", answer)):
        if _canon(n) not in known and n not in out:
            out.append(n)
    return out


def mentioned_segments(answer: str, results: list[dict]) -> list[dict]:
    """Segments named in the answer that exist in the tool results (for the « Fiche complète » buttons)."""
    names = {}
    for r in results:
        res = r.get("result") or {}
        for s in res.get("segments", []):
            names.setdefault(s["segment_code"], s.get("name"))
        if isinstance(res.get("segment"), dict):
            names.setdefault(res["segment"]["segment_code"], res["segment"].get("name"))
    out = []
    for code in dict.fromkeys(_SEGMENT.findall(answer)):
        if code in names:
            out.append({"segment_code": code, "name": names[code]})
    return out


def run_agent(db, question: str, chat=None, max_rounds: int = MAX_ROUNDS, time_budget_s: float = TIME_BUDGET_S,
              clock=time.perf_counter, propose=None) -> dict:
    """-> {answer, steps, tool_results, sources, segments, actions, warnings, rounds, stop_reason, calls}.
    `chat` = ollama.chat_with_tools (injected in tests). OllamaUnavailable / OllamaError propagate.
    `propose(proposal) -> stored proposal` stores an action proposal (the endpoint: agent_actions INSERT);
    without it (evaluation, tests) proposals are returned but stored nowhere. Nothing is ever executed here."""
    chat = chat or ollama.chat_with_tools
    tool_set, offered = tools.tools_for(question)      # action tools only when the question asks for an action
    schemas = tools.ollama_schemas(offered)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    steps, results, sources, calls, proposed = [], [], [], [], []
    citation_numbers: dict[str, int] = {}          # chunk_id -> global [n] for this run
    t0, rounds, answer, stop = clock(), 0, None, "answer"

    def timed_chat(tool_defs, kind):
        c0 = clock()
        reply = chat(messages, tool_defs, model=rag_config.RAG_LLM_MODEL, options=AGENT_OPTIONS)
        calls.append({"call": len(calls) + 1, "kind": kind, "llm_ms": int((clock() - c0) * 1000),
                      "tool_calls": len(reply["tool_calls"])})
        return reply

    while True:
        out_of_budget = clock() - t0 > time_budget_s
        if rounds >= max_rounds or out_of_budget:
            stop = "time_budget" if out_of_budget and rounds < max_rounds else "max_rounds"
            messages.append({"role": "user", "content": FINAL_PROMPT})
            final = timed_chat([], "final")
            answer = final["content"] if final["content"] and not final["tool_calls"] else NO_CONCLUSION
            break
        msg = timed_chat(schemas, "tools")
        if not msg["tool_calls"]:
            answer = msg["content"]
            break
        rounds += 1
        messages.append({"role": "assistant", "content": msg["content"], "tool_calls": msg["tool_calls"]})
        for call in msg["tool_calls"]:
            name, raw = _call_parts(call)
            s0 = clock()
            step = {"round": rounds, "tool": name, "arguments": raw if isinstance(raw, dict) else {"brut": raw}}
            try:
                args = tools.validate(name, raw, offered)
                step["arguments"] = args
                result = tools.run(db, name, args)
                if name == "search_guides":
                    result = renumber_excerpts(result, citation_numbers, sources)
                if tools.is_action(name):           # proposal only: stored for a human decision, never executed
                    result = propose(result) if propose else {**result, "id": None, "status": "non enregistrée"}
                    proposed.append(result)
                    content = json.dumps(tools.actions.for_model(result), ensure_ascii=False, default=str)
                else:
                    content = tools.for_model(name, result)
                step.update(ok=True, result_summary=tools.summarize(name, result))
                results.append({"round": rounds, "tool": name, "arguments": args, "result": result})
            except tools.ToolError as exc:
                step.update(ok=False, error=str(exc), result_summary=f"Erreur : {exc}")
                content = json.dumps({"erreur": str(exc)}, ensure_ascii=False)
            step["ms"] = int((clock() - s0) * 1000)
            steps.append(step)
            messages.append({"role": "tool", "tool_name": name or "inconnu", "content": content})

    answer = (answer or "").strip() or NO_CONCLUSION
    warnings = []
    if not steps:
        warnings.append(NO_TOOL_WARNING)
    numbers = ungrounded_numbers(answer, question, results)
    if numbers:
        warnings.append("Chiffres de la réponse absents des résultats d'outils (à ne pas utiliser sans vérification) : "
                        + ", ".join(numbers) + ".")
    if proposed:   # the 3B model may describe a proposed action as done (seen live on 07/11): say it, always
        warnings.append(f"{len(proposed)} action(s) proposée(s) : rien n'a été exécuté. Elles ne s'appliquent qu'après "
                        "votre confirmation ; si la réponse ci-dessus les présente comme faites, elle se trompe.")
    if stop == "time_budget":
        warnings.append(f"Temps de calcul limité : l'agent a conclu après {rounds} série(s) d'outils.")
    return {"answer": answer, "steps": steps, "tool_results": results, "sources": sources,
            "segments": mentioned_segments(answer, results), "actions": proposed, "warnings": warnings,
            "rounds": rounds, "stop_reason": stop, "calls": calls, "tool_set": tool_set, "offered_tools": offered}


def renumber_excerpts(result: dict, numbers: dict[str, int], sources: list[dict]) -> dict:
    """Global citation numbers for one run: every new excerpt gets the next [n] (never reused for another
    excerpt); an excerpt already returned by an earlier search keeps its first number. New excerpts are
    appended to `sources` (the UI list), so [n] in the answer always points to one excerpt."""
    excerpts = []
    for e in result["excerpts"]:
        if e["chunk_id"] not in numbers:
            numbers[e["chunk_id"]] = len(numbers) + 1
            sources.append({**e, "n": numbers[e["chunk_id"]]})
        excerpts.append({**e, "n": numbers[e["chunk_id"]]})
    return {**result, "excerpts": excerpts}
