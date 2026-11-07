# Equipment agent (`POST /assistant/agent`)

An "agentic" layer on top of the RAG assistant, for the **equipment supervisor** only. The supervisor asks in
French, for example « Quels segments dois-je traiter en priorité cette semaine et que faut-il faire ? ». The local
model (`llama3.2:3b` through Ollama tool calling) decides which tools to call. The backend runs them and the model
writes a short French summary.

**Status (07/11/2026):**
- The agent runs live and its read-only part has been evaluated against the real Ollama. Tool choice is mostly right
  for single-tool questions, but the model **invents segment codes** when a question needs two tools and **never
  takes a second round** (see « Measured behaviour »).
- Since the same day it can also **propose actions**, which run only after a human confirms (see « Acting with human
  confirmation »).

## Agent levels

| Level | What the model may do | Who writes to the database | Status |
|---|---|---|---|
| 0. Assistant (`/assistant/ask`) | answer from the guides | nobody (log line only) | live |
| 1. Read-only agent | choose read tools, summarize | nobody (log line only) | live, evaluated |
| **2. Acting agent, human in the loop** | choose read tools **and propose** actions | the supervisor, by confirming one proposal at a time | live (this document) |
| 3. Autonomous agent | execute actions itself | the model | **not built, on purpose** |

**Why no autonomous writes with a 3B model.** The measurements below show what `llama3.2:3b` does:
- it invents segment codes (3 in 8 tasks);
- it misreads arguments (`min_priority = P1` for « P1 et P2 »);
- it chooses the wrong tool on some wordings;
- on 07/11 it described a proposed sheet as already produced, with invented content (« Longueur 12,5 km, en bon
  état… »).

Any of these, executed automatically, would change a citizen's report, send a false message to the transport side,
or validate a detection nobody looked at. The model may only fill in a proposal, which validation and the existing
code then check. A human reads what will change, with the photo when a detection is involved, and decides.

## Acting with human confirmation (propose → confirm → execute)

| Action tool | Proposal (no write) | Execution on « Confirmer » (existing code, the logged-in supervisor is the actor) |
|---|---|---|
| `plan_intervention(segment_code, note)` | lists the open complaints within 100 m of the segment (refused if there is none) | `platform_app.router.update_complaint(..., status="planned", note)` for each complaint: status, `complaint_status_history`, `complaint.status` notification to the citizen |
| `notify_transport(segment_code, message)` | checks the segment, shows the message | `shared.realtime.publish(db, "equipment.segment.notice", {...}, "transport_supervisor")` |
| `generate_full_sheet(segment_code)` | checks the segment | `rag.router.intervention_sheet(...)` (LLM, about 100 s; one `rag_queries` line) |
| `propose_validation(event_id)` | only for an event in status `observed`; attaches the **photo / evidence frame, confidence, severity, source, date** | `perception.router.validate_event(...)` |

- **During the agent loop** an action tool reads, checks, and returns a proposal: type, arguments, French summary,
  « Ce qui changera », evidence and `demo`. The endpoint stores it in **`agent_actions`** (Alembic `0008`). That is
  the only insert of the run; no business table is touched.
- **What the model is told:** that the action is « en attente de confirmation humaine », that nothing was executed,
  and that it must say so. The response also always carries the warning « N action(s) proposée(s) : rien n'a été
  exécuté… », because the model does not always respect that.
- **Confirming:** `POST /assistant/agent/actions/{id}/confirm` (equipment_supervisor) runs an atomic claim,
  `UPDATE … SET status='confirmed' WHERE status='proposed' AND proposed_at >= now() - 30 min`. The claim is committed
  **before** execution, so a second (or concurrent) confirm finds the row already decided and gets **409**. One
  confirmation means one execution.
- **The other answers:**
  - an expired proposal (older than 30 min) gets **410** and is marked `expired`;
  - an unknown id gets 404;
  - a failure is stored as `failed` with the error, and never retried;
  - `…/reject` (« Ignorer ») sets `rejected`, and a rejected action can never run.
- **Table columns:** `id, run_id, type, arguments, proposal, status (proposed | confirmed | rejected | expired |
  failed), proposed_by, proposed_at, decided_by, decided_at, result`.
- **UI (Agent tab):** each proposal is a card with the summary, « Ce qui changera », the evidence (complaints, or the
  photo with the confidence) and the « DÉMO — données fictives » badge when needed. It has « Confirmer » /
  « Ignorer » buttons, the expiry time, and then the result of the execution (for the sheet, its sections and
  sources). Decisions are kept in the session history.

**Live check (07/11, through nginx, as equipment.supervisor):**
- **Agent run:** « Propose de générer la fiche d'intervention complète du segment OSM-100663969 ». It called
  `generate_full_sheet` in 1 round (43.5 s + 39.7 s model calls), and the proposal was stored as `proposed` with its
  expiry.
- **Business tables unchanged:** planned complaints, status history, outbox and validated events all stayed the
  same. The answer itself presented the sheet as done, with invented content; that is why the fixed warning was
  added.
- **Decisions over HTTP:**

| Step | Result |
|---|---|
| Ignorer | 200, rejected |
| Confirm after Ignorer | 409 |
| Confirm an expired proposal | 410 |
| Confirm as transport.supervisor | 403 |
| Confirm the agent's `generate_full_sheet` | 200 in 107.4 s, 6 sections |
| Second confirm | 409 |

- **Overall:** only `agent_actions` and one `rag_queries` line were written.
**The 3 write actions, live on demo rows only (07/11, through nginx, as equipment.supervisor).** Each proposal came
from the agent itself (no fallback needed). Before every confirm, the script checked that every row the action
changes was demo (`payload.demo = true`):

| Action (agent question) | Before | After confirming |
|---|---|---|
| `plan_intervention` on OSM-713546524 (Route Nationale Tunis – Bizerte, only demo complaints within 100 m) | complaint `ee9eb31a` (demo) `validated`, 2 history rows | `planned`, 3 history rows (`validated → planned`, by equipment.supervisor) |
| `notify_transport` on OSM-713546524 | 0 `equipment.segment.notice` | 1 notice returned by `GET /platform/alerts` as transport.supervisor (`demo: true`, message, segment, sent_by) |
| `propose_validation` on `2863ed7f…` (L1's demo detection, alligator crack, photo, confidence 0.3538, severity 0.7264) | `observed` | `validated`, `validated_by = equipment.supervisor` |

- **Real rows unchanged:** real complaints planned 3 → 3, real events validated 1 → 1, real history 6 → 6.
- **Second confirms:** all three got 409.
- **The validation answer** again said the detection « a été validée » before confirmation; the fixed warning stays
  necessary.
- **Reset:** `seed_demo.py --reset` then deleted the demo rows plus their traces: the 3 `agent_actions` rows, the
  notice (its payload carries `demo`), and the 28 history rows of demo complaints. Real complaints, real events and
  the earlier non-demo `agent_actions` rows were untouched. Reset now includes `agent_actions` rows linked to demo
  data: `proposal.demo`, a demo event, or a planned demo complaint.
- **Why OSM-713546524 and not L1's segment:** L1's segment (OSM-125567491) carries demo *detections* but no complaint
  within 100 m (the demo layout keeps citizen reports at least 2 km from the lines), so `plan_intervention`
  correctly refuses there.

**Design points (changed after review):**
- **Expiry on read:** `GET /assistant/agent/actions?ids=…` first marks every proposal older than 30 min as
  `expired`; the Agent tab calls it on opening, so a stale card shows « Expirée ». A decision on an expired proposal
  gets 410 if it was still `proposed`, 409 if already marked.
- **`plan_intervention` is all or nothing.** It reuses `platform_app.router.apply_complaint_status()`, the body of the
  complaint-status endpoint, now without its commit. That covers the status, the history and the citizen
  notification, and there is **one commit** for all complaints. Any error rolls everything back and the action is
  stored `failed`.
- **Demo flag:** `notify_transport` and `generate_full_sheet` proposals carry `demo` when the segment has open demo
  data, and the notice payload carries it too.
- **Transport side:** card « Alertes de l'Équipement » on the Transport home, showing the
  `equipment.segment.notice` items of `GET /platform/alerts`.

**Rows left in `agent_actions` from the first live check (non-demo, kept until a decision):** 4
`notify_transport` proposals on OSM-100663969 (none executed: 2 rejected, 1 expired, 1 old proposal), and the
confirmed `generate_full_sheet`.

## Architecture

```
Ministry.jsx  « Agent »  ──POST /api/assistant/agent──►  agent/router.py (equipment_supervisor, UTF-8 JSON)
(components/Agent.jsx)     nginx: location = …/agent      │
                           proxy_read_timeout 600s        ▼
                                       agent/loop.py  run_agent()  ◄──►  rag/ollama.py chat_with_tools()
                                          │  ≤ 3 tool rounds, temperature 0,        (/api/chat + "tools", stdlib)
                                          │  validation, 150 s time budget
                                          ▼
                                       agent/tools.py  (read-only, reuses existing code)
                                          ├─ list_priority_segments → platform_app.router.LATEST_SCORE_LATERAL
                                          ├─ get_segment_facts      → rag.intervention.gather_facts
                                          ├─ get_intervention_sheet → rag.intervention.template_sections (no LLM)
                                          ├─ search_guides          → rag.retrieve.retrieve_scored (no LLM)
                                          └─ get_equipment_dashboard→ platform_app.router.equipment_dashboard
```

| File | Role |
|---|---|
| `backend/rag/ollama.py` | `chat_with_tools(messages, tools, model, options)`: `/api/chat` with `tools`. It returns `{role, content, tool_calls}` and uses the same `OllamaUnavailable` / `OllamaError` classes as `chat()`. |
| `backend/agent/tools.py` | Tool registry, Ollama schemas, argument validation, one-line French summaries. `model_view()` / `for_model()` give the compact JSON the model reads (max 3,500 characters). |
| `backend/agent/loop.py` | The loop, global citation numbering (`renumber_excerpts`), the answer checks (`ungrounded_numbers`, `mentioned_segments`), the system prompt. |
| `backend/agent/router.py` | Endpoints `/agent`, `/agent/actions/{id}/confirm`, `/agent/actions/{id}/reject`; 503 in French when Ollama is down, 502 on an Ollama error; logs the question to `rag_queries`. |
| `backend/agent/actions.py` | Action tools: proposals (read-only), `store_proposal`, the atomic claim, the 30-minute expiry, the executors (existing code). |
| `backend/alembic/versions/0008_agent_actions.py` | Table `agent_actions`. |
| `backend/agent/evaluate.py` + `data/agent/eval/` | Tool-choice evaluation against the real Ollama (8 tasks) and its results. |
| `frontend/src/components/Agent.jsx` | « Agent » section of the Équipement ministry. |
| `frontend/nginx.conf` | `location = /api/assistant/agent` with a 600 s timeout. |
| `tests/test_agent.py`, `tests/test_agent_actions.py` | 24 + 12 tests: mocked Ollama, fake database (actions: proposals do not write, confirm once, second confirm 409, expired 410, expiry on list read, all-or-nothing planning, rejected never runs, 403). |

## Tools (all read-only)

| Tool | Arguments | Reuses | Returns |
|---|---|---|---|
| `list_priority_segments` | `limit` 1–20 (**default 5**), `min_priority` P1–P4 (default P3) | the latest-score subquery of `/platform/map` (`LATEST_SCORE_LATERAL`, a shared constant) | segments P1…`min_priority`, ordered by priority then `risk_score`, with `open_defects` (open M1 events on the segment + open complaints within 100 m) and `demo`; a `hint` to widen to P3 when the list is empty |
| `get_segment_facts` | `segment_code` | `intervention.gather_facts` | M1 events, complaints within 100 m, M2 risk, last inspection, `demo` |
| `get_intervention_sheet` | `segment_code` | `intervention.template_sections` | Constat / Priorité / Données manquantes only. The full sheet with the guides' advice takes about 100 s on CPU, so it stays a button in the UI. |
| `search_guides` | `question` | `retrieve_scored` + the confidence gate | excerpts (title, page, 400-character excerpt), numbered for the whole run |
| `get_equipment_dashboard` | — | `equipment_dashboard()` | the 4 counters of the equipment dashboard |

- **What the model reads vs what the UI shows:** for `list_priority_segments` the model only reads compact rows
  (`segment_code, name, priority, risk_level, risk_score, open_defects, demo`), which keeps the context small. The
  response's `tool_results` keep the full rows for the UI.
- **No real example codes in the descriptions:** the `segment_code` descriptions only show a placeholder
  (`OSM-<chiffres>`). On 07/11, `llama3.2:3b` copied a real code that an earlier description gave as an example.
- **Why not `/prediction/segments`:** it is not used, because it can write contextual-fallback rows.
- **No tool writes:** the only write is the `rag_queries` log line of the endpoint (`Agent : <question>`). A test
  runs every tool on a recording fake session and checks that no INSERT / UPDATE / DELETE is sent.
- **The map is unchanged by the refactor:** on 07/11, the segments query of git `HEAD` (before the
  `LATEST_SCORE_LATERAL` constant) and the refactored `map_snapshot()` returned the same 675 rows, compared as
  identical JSON. The live `GET /platform/map` also returned the same 675 segments, scores and priorities.

## Loop rules

- **Rounds:** at most **3** tool-call rounds (`MAX_ROUNDS`, chosen below), with `temperature 0`, `num_ctx 8192` and
  `num_predict 500`. After the last round, or once the time budget (150 s) is spent, the model is asked once more,
  without tools, for its final answer. If it still calls a tool, the answer is a fixed French message.
- **Validation:** the tool name and its arguments are checked. An unknown tool, an unknown argument, a missing
  argument, a wrong type, an out-of-range value or an unknown segment code each become `{"erreur": "..."}`. That
  error is sent back to the model as the tool result, and the step is marked `ok: false` in the trace. The request
  never crashes. Small-model habits are tolerated: `"5"` for 5, `p2` for P2, and arguments sent as a JSON string.
- **Citations:** excerpts are numbered **globally for the run**. A new excerpt gets the next `[n]`, and an excerpt
  already returned by an earlier search keeps its first number. So `[n]` always means one excerpt, and the
  `sources` list holds each excerpt once.
- **No faked calls:** if the model answers without calling any tool, the answer is kept as it is. The response then
  contains `steps: []` and a warning.
- **Numbers:** every number in the answer is compared, as a value, with the tool results, the question and the tool
  descriptions; any number found nowhere is listed in `warnings`. The UI shows the raw tool results (scores as
  stored) under the answer. This check is weak on page numbers: on 07/11 it did not flag « annexe 2, page 10/11/12 »,
  because those numbers occur somewhere in the excerpts.
- **Timing:** `calls` = `[{call, kind: tools|final, llm_ms, tool_calls}]`, one entry per model call. The UI shows
  the duration of each call.
- **Demo data:** rows built on demo data carry `demo: true`; the UI shows « DÉMO — données fictives ».

Response:
`{answer, steps[{round, tool, arguments, ok, result_summary, error?, ms}], tool_results[{round, tool, arguments, result}], sources, segments[{segment_code, name}], warnings, rounds, stop_reason, calls, question, model, latency_ms}`.

## Measured behaviour (07/11/2026, CPU server, `llama3.2:3b`)

### Live calls (equipment.supervisor)

| When | Question | Tools called (one round each time) | Model calls | Total |
|---|---|---|---|---|
| before the fixes (api :8000) | « Combien de signalements citoyens sont ouverts et combien de détections attendent une validation ? » | `get_equipment_dashboard` ✓ | 34.8 s + 8.0 s | 42.8 s |
| before the fixes | « Quels segments dois-je traiter en priorité cette semaine et que faut-il faire ? » | `list_priority_segments(P1)` → 0 rows; `get_intervention_sheet(OSM-125567491)`, a code copied from the old description example | 24.0 s + 30.1 s | 54.3 s |
| after the fixes | dashboard question | `get_equipment_dashboard` ✓ | 14.9 s + 6.2 s | 21.2 s |
| after the fixes | priorities question | `list_priority_segments(P1)` → 0 rows + hint; `get_intervention_sheet(OSM-12345)` → « Segment inconnu »; `search_guides` ✓; then answer from the guides only | 26.0 s + 47.2 s | 74.9 s |

- **The dashboard answer was correct:** « 15 signalements ouverts, 54 détections » matches the dashboard counters.
- **The priorities question was answered with no segment at all.** The hint suggesting P3 was ignored, because the
  model never takes a second round.
- **No warnings** were raised in any of these runs.

### Evaluation (`python -m agent.evaluate`, `data/agent/eval/`)

| File | Configuration | first tool correct | all expected called | all expected called **successfully** | invented codes | median latency |
|---|---|---|---|---|---|---|
| `results_run1.json` (12:48) | final tools, MAX_ROUNDS 5 | 0.875 | 0.875 | — (not measured in this run) | — (3 invalid calls) | 50.0 s |
| `results_rule6.json` (12:58) | + prompt rule « no code not seen in a result » | 0.875 | 0.75 | 0.75 | 3 | 39.2 s |
| `results_5tools.json` (13:06) | rule removed, MAX_ROUNDS 3, 5 read-only tools | 0.875 | 0.875 | 0.75 | 3 | 40.8 s |
| **`results.json` (13:54)** | **9 tools (+ 4 action tools), 11 tasks** | **0.909** | **0.909** | **0.727** | **3** | **63.0 s** |

**With the 9 tools (`results.json`, 13:54).**

| Task | Tools called | OK | Model calls | Total |
|---|---|---|---|---|
| a01 priorities + what to do | `list_priority_segments(P1)`; `get_intervention_sheet(OSM-12345)` ✗ | ✓ | 56.6 + 23.5 s | 80.7 s |
| a02 5 most urgent (P1 and P2) | `list_priority_segments(limit "5", min_priority "P1,P2")` ✗ (rejected) | ✗ | 40.0 + 19.4 s | 59.4 s |
| a03 open reports / detections to validate | `get_equipment_dashboard` | ✓ | 39.2 + 8.0 s | 47.2 s |
| a04 facts of OSM-125567491 | `get_segment_facts` | ✓ | 40.5 + 42.5 s | 83.1 s |
| a05 sheet of OSM-116022841 | `get_intervention_sheet` | ✓ | 5.8 + 58.5 s | 64.4 s |
| a06 minimum temperature hot mix | `search_guides` | ✓ | 8.5 + 27.0 s | 38.3 s |
| a07 signing a pothole work zone | `notify_transport(RN1234, …)` ✗ (an action instead of the guides, invented code) | ✗ | 7.6 + 21.8 s | 29.4 s |
| a08 top segment + its defects | `list_priority_segments(P1)`; `get_segment_facts(OSM-123456)` ✗ | ✗ | 41.8 + 24.5 s | 66.4 s |
| a09 plan OSM-713546524 | `plan_intervention(OSM-713546524)` | ✓ | 44.8 + 15.5 s | 60.4 s |
| a10 notify Transport about OSM-713546524 | `notify_transport(OSM-713546524, …)` | ✓ | 49.1 + 13.9 s | 63.0 s |
| a11 propose validating `2863ed7f…` | `propose_validation(2863ed7f…)` | ✓ | 51.4 + 16.1 s | 67.5 s |

- **The 3 action tasks:** correct tool with the exact segment or event 3/3. **Claimed as already done 1/3**: a11
  answered « a été validée », detected by the French patterns of `claims_done` (a heuristic; the answers are in the
  results file).
- **What the action tools changed for the read tasks:**
  - a07 (a guide question) now proposes `notify_transport` with an invented code;
  - a02 sends a combined priority « P1,P2 », which is rejected;
  - a03 (dashboard) is now correct.
- **Latency:** the median rose from 40.8 s to 63.0 s; the first model call is longer with 9 schemas (39–57 s on the
  segment tasks).

**Previous shipped run with 5 tools (`results_5tools.json`, 13:06), per task:**

| Task | Tools called | OK | Model calls | Total |
|---|---|---|---|---|
| a01 priorities + what to do | `list_priority_segments(P1)`; `get_intervention_sheet(OSM-12345)` ✗; `search_guides` | ✓ | 39.1 + 50.2 s | 92.2 s |
| a02 5 most urgent (P1 and P2) | `list_priority_segments(P1)` (0 rows: P2 not asked) | ✓ | 6.2 + 10.6 s | 16.8 s |
| a03 open reports / detections to validate | `get_segment_facts(OSM-123456)` ✗ (wrong tool, invented code) | ✗ | 22.1 + 13.1 s | 35.1 s |
| a04 facts of OSM-125567491 | `get_segment_facts` | ✓ | 22.9 + 25.4 s | 48.4 s |
| a05 sheet of OSM-116022841 | `get_intervention_sheet` | ✓ | 5.6 + 40.7 s | 46.3 s |
| a06 minimum temperature hot mix | `search_guides` | ✓ | 7.0 + 26.0 s | 35.2 s |
| a07 signing a pothole work zone | `search_guides` | ✓ | 6.8 + 55.3 s | 64.3 s |
| a08 top segment + its defects | `list_priority_segments(P1)`; `get_segment_facts(OSM-12345)` ✗ | ✗ | 8.0 + 22.0 s | 30.0 s |

- **Prompt rule 6 was removed.** It ("never use a segment code that is not in a tool result") did not reduce
  invented codes (3 → 3). It also made the model look for a segment code on the dashboard question, which had worked
  twice live without it (live check through nginx, 34.5 s, failed).
- **"correct tool" counts failed calls.** `first_tool_correct` / `all_expected_called` count a call even when it
  failed; `all_expected_ok` only counts successful calls.

## Timeout and `MAX_ROUNDS`: the choice

**Measured on 07/11, over 32 runs (24 evaluation, 3 detailed reruns, 5 live):**
- **Rounds:** every run used exactly **1** tool round. The model sends its tool calls in parallel, then answers. It
  never took a second round, even after a « Segment inconnu » error or the widen-to-P3 hint.
- **Tool-choice model call:** 4.8–42.5 s.
- **Final-answer model call:** 6.2–55.3 s.
- **Longest request:** 99.3 s (a01: 42.5 + 53.6 s).

**Choice: `MAX_ROUNDS = 3`.**
- One round is all this model uses. Two spare rounds still let a better model react to a tool error, and cost
  nothing when unused.
- At the slowest measured call (55 s), 3 rounds plus the final answer take about 4 × 55 ≈ 220 s.
- 5 rounds bought nothing measurable and only lengthened the worst case.

**nginx:** `location = /api/assistant/agent` with `proxy_read_timeout 600s` (exact match, so it wins over the
`/api/assistant/` prefix, which stays at 300 s).
- **Hard bound:** no new round starts after 150 s, but one in-flight round and the final call can each take up to
  `CHAT_TIMEOUT_S = 180` s. That gives 150 + 180 + 180 = 510 s, which is under 600 s.
- **Checked live on 07/11:** HTTP 200 through `http://web/api/assistant/agent`.

## Evaluation (re-run it yourself)

```powershell
cd backend
$env:DATABASE_URL = "postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5433/thniyetna"
$env:OLLAMA_URL = "http://localhost:11434"
..\ml\.venv\Scripts\python.exe -m agent.evaluate                      # all 8 tasks -> data/agent/eval/results.json
..\ml\.venv\Scripts\python.exe -m agent.evaluate --ids a01,a08 --out ..\data\agent\eval\x.json
```

- **Metrics per task:** `first_tool_correct`, `all_expected_called`, `all_expected_ok`, `invented_codes`,
  `invalid_calls`, rounds, the steps with their arguments and errors, the per-call timings, the answer.
- **Data needed:** a04 / a05 need the demo data (`scripts/seed_demo.py`).

## Limits of a 3B model for tool calling (observed)

- **Invented segment codes.** When a question needs a list and then a segment, the model calls both tools at once and
  makes up the code (`OSM-12345`, `OSM-123456`): 3 times in 8 tasks. Validation rejects them, but the model does not
  retry.
- **No multi-step reasoning.** In 32 runs the model never used a second round. "List, then look at the first segment"
  therefore fails (a08), and so does "the list was empty, widen to P3" (live priorities question).
- **Arguments are misread.** `min_priority` is « the lowest priority included »; the model sets P1 to mean
  "priority", even for « P1 et P2 » (a02). With no P1 segment in the data, the list comes back empty.
- **Some tool choices are wrong.** « signalements ouverts / détections à valider » went to `get_segment_facts`
  instead of the dashboard in a03, even though the same question with a different wording worked live.
- **Numbers.** The number check catches values missing from the results, but not a real number attached to the wrong
  thing, nor page numbers that happen to occur in an excerpt.
- **Next steps** (not done): a larger local model (`gemma4` is installed, untested; any new download needs Wi-Fi), or a
  deterministic plan for "priorities" questions (list first in code, then the model), or a `max_priority` parameter
  that matches how the model reads the word.

## Tests

`ml\.venv\Scripts\python.exe -m pytest -q tests/test_agent.py` (24 tests). It covers:
- a correct tool call with coerced arguments and a grounded answer;
- an unknown tool;
- 6 kinds of bad arguments;
- the 3-round limit followed by the final call without tools;
- the time budget;
- an answer without any tool;
- invented-number warnings;
- read-only tools;
- the schemas, with no real segment code in any description;
- global citation numbering across two searches;
- compact rows for the model and full rows for the UI, the default limit of 5 and the per-call timings;
- the empty-list hint;
- 503 when Ollama is down, the `rag_queries` log and the UTF-8 response class;
- 403 for transport_supervisor;
- the `chat_with_tools` payload;
- evaluation scoring, including `all_expected_ok` and `invented_codes`.
