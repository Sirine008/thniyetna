"""Read-only tools of the equipment agent (Ollama tool calling).

Every tool reuses existing backend code (SQL / functions), never an HTTP call to our own API, and never
writes to the database. Each tool returns a JSON-serialisable dict; `summarize()` gives the one-line French
summary shown in the trace, `for_model()` the compact JSON sent back to the model.

Numbers are returned exactly as stored. Rows built on demo data carry `demo: true` (DÉMO — données fictives).
"""
import json
import re
import unicodedata

from rag import intervention
from rag.config import EXCERPT_CHARS
from rag.retrieve import passes_gate, retrieve_scored, snippet

from . import actions
from .errors import ToolError  # noqa: F401  (re-exported: tools.ToolError)

DEMO_LABEL = intervention.DEMO_LABEL
PRIORITIES = ["P1", "P2", "P3", "P4"]
MAX_SEGMENTS = 20
MODEL_RESULT_CHARS = 3500          # tool result sent back to the model (num_ctx is small on CPU)




# ---------------------------------------------------------------- tools

def list_priority_segments(db, limit: int = 5, min_priority: str = "P3") -> dict:
    """Latest valid M2 score per segment (same subquery as /platform/map), priorities P1..min_priority,
    ordered by maintenance_priority then risk_score. Read-only (unlike /prediction/segments, which can
    write contextual-fallback rows)."""
    from sqlalchemy import text
    from platform_app.router import LATEST_SCORE_LATERAL

    allowed = PRIORITIES[:PRIORITIES.index(min_priority) + 1]
    rows = db.execute(text(f"""
        SELECT s.segment_code, s.name, s.road_class, rs.maintenance_priority, coalesce(rs.risk_level, rs.risk_category) risk_level,
               rs.risk_score, rs.predicted_condition, rs.model_version,
               (SELECT count(*) FROM road_events e WHERE e.segment_id = s.id AND e.status <> 'closed')
               + (SELECT count(*) FROM complaints c WHERE c.status NOT IN ('resolved', 'rejected')
                  AND ST_DWithin(c.geom::geography, s.geom::geography, :r)) open_defects,
               (EXISTS (SELECT 1 FROM road_events e WHERE e.segment_id = s.id AND e.status <> 'closed'
                          AND coalesce((e.payload->>'demo')::boolean, false))
                OR EXISTS (SELECT 1 FROM complaints c WHERE c.status NOT IN ('resolved', 'rejected')
                          AND coalesce((c.payload->>'demo')::boolean, false)
                          AND ST_DWithin(c.geom::geography, s.geom::geography, :r))) demo
        FROM road_segments s {LATEST_SCORE_LATERAL}
        WHERE rs.maintenance_priority = ANY(CAST(:p AS text[]))
        ORDER BY rs.maintenance_priority, rs.risk_score DESC, s.segment_code
        LIMIT :n"""), {"p": allowed, "n": limit, "r": intervention.COMPLAINT_RADIUS_M}).mappings().all()
    out = {"priorities": allowed, "count": len(rows), "segments": [dict(r) for r in rows]}
    if not rows and min_priority != "P4":
        out["hint"] = (f"Aucun segment de priorité {'/'.join(allowed)}. Relancez avec min_priority=\"P3\" "
                       "(P1, P2 et P3) pour voir les segments à planifier.")
    return out


def get_segment_facts(db, segment_code: str) -> dict:
    """Facts of one segment from the database (intervention.gather_facts)."""
    facts = intervention.gather_facts(db, segment_code)
    if facts is None:
        raise ToolError(f"Segment inconnu : {segment_code}. Utilisez un code renvoyé par list_priority_segments.")
    return {**facts, "demo": _facts_demo(facts)}


def get_intervention_sheet(db, segment_code: str) -> dict:
    """Database part of the intervention sheet (Constat, Priorité, Données manquantes), no LLM call.
    The full sheet with the guides' advice (~100 s on CPU) is a button in the interface."""
    facts = intervention.gather_facts(db, segment_code)
    if facts is None:
        raise ToolError(f"Segment inconnu : {segment_code}. Utilisez un code renvoyé par list_priority_segments.")
    return {"segment": facts["segment"], "demo": _facts_demo(facts), "no_defect": not intervention.has_defect(facts),
            "sections": [{"title": s["title"], "text": s["text"]} for s in intervention.template_sections(facts)],
            "note": "Fiche partielle (données de la plateforme). La fiche complète avec les conseils des guides "
                    "s'ouvre avec le bouton « Fiche d'intervention complète »."}


def search_guides(db, question: str) -> dict:
    """Numbered excerpts of the field guides (hybrid retrieval), no LLM call."""
    sources, best = retrieve_scored(db, question)
    if not passes_gate(best):
        sources = []
    return {"question": question, "count": len(sources),
            "excerpts": [{"n": s["n"], "title": s["title"], "page": s["page"], "chunk_id": s["chunk_id"],
                          "excerpt": snippet(s["text"], EXCERPT_CHARS)} for s in sources]}


def get_equipment_dashboard(db) -> dict:
    """The counters of /platform/dashboard/equipment (same function, same SQL)."""
    from platform_app.router import equipment_dashboard
    return dict(equipment_dashboard(db=db, user={"role": "equipment_supervisor"}))


def _facts_demo(facts: dict) -> bool:
    return any(r.get("demo") for r in facts["events"] + facts["complaints"])


# ---------------------------------------------------------------- registry, schemas, validation

def _code_param(desc="Code exact du segment, de la forme OSM-<chiffres>, recopié d'un résultat de list_priority_segments "
                     "(n'en invente jamais)."):
    return {"type": "string", "description": desc, "minLength": 3, "maxLength": 64}


TOOLS = {
    "list_priority_segments": {
        "fn": list_priority_segments,
        "description": "Liste les segments routiers à entretenir selon le modèle M2, triés par priorité d'entretien "
                       "(P1 urgent → P4 surveiller) puis par score de risque. À utiliser pour « quels segments traiter "
                       "en priorité ».",
        "parameters": {"limit": {"type": "integer", "description": "Nombre de segments (1 à 20, défaut 5).",
                                 "minimum": 1, "maximum": MAX_SEGMENTS, "default": 5},
                       "min_priority": {"type": "string", "enum": PRIORITIES, "default": "P3",
                                        "description": "Priorité la plus basse incluse. Défaut P3 = P1, P2 et P3 "
                                                       "(recommandé). P1 = urgences seulement."}},
        "required": [],
    },
    "get_segment_facts": {
        "fn": get_segment_facts,
        "description": "Faits enregistrés sur UN segment : détections M1 ouvertes, signalements citoyens à moins de "
                       "100 m, score de risque M2, dernier passage d'inspection.",
        "parameters": {"segment_code": _code_param()},
        "required": ["segment_code"],
    },
    "get_intervention_sheet": {
        "fn": get_intervention_sheet,
        "description": "Fiche d'intervention d'UN segment, partie données (Constat, Priorité, Données manquantes). "
                       "À utiliser pour « que faut-il faire sur ce segment ».",
        "parameters": {"segment_code": _code_param()},
        "required": ["segment_code"],
    },
    "search_guides": {
        "fn": search_guides,
        "description": "Cherche des extraits dans les guides techniques de terrain (réparation des nids-de-poule, "
                       "enrobés, signalisation de chantier, déviations). À utiliser pour une question de méthode.",
        "parameters": {"question": {"type": "string", "description": "La question, en français.",
                                    "minLength": 3, "maxLength": 300}},
        "required": ["question"],
    },
    "get_equipment_dashboard": {
        "fn": get_equipment_dashboard,
        "description": "Compteurs du tableau de bord Équipement : signalements ouverts, détections à valider, "
                       "événements des dernières 24 h, inspections en cours.",
        "parameters": {},
        "required": [],
    },
}


def ollama_schemas(names: list[str] | None = None) -> list[dict]:
    """Tool definitions in the Ollama / OpenAI function format (all tools, or only `names`)."""
    out = []
    for name, spec in TOOLS.items():
        if names is not None and name not in names:
            continue
        props = {k: {kk: vv for kk, vv in v.items() if kk in ("type", "description", "enum")}
                 for k, v in spec["parameters"].items()}
        out.append({"type": "function", "function": {
            "name": name, "description": spec["description"],
            "parameters": {"type": "object", "properties": props, "required": spec["required"]}}})
    return out


def validate(name: str, raw_args, offered: list[str] | None = None) -> dict:
    """Checked, typed arguments; ToolError with a French message otherwise.
    Small models often send numbers as strings or the arguments as a JSON string: both are accepted.
    `offered` = the tools given to the model for this question: any other one is refused."""
    if name not in TOOLS:
        raise ToolError(f"Outil inconnu : {name}. Outils disponibles : {', '.join(offered or TOOLS)}.")
    if offered is not None and name not in offered:
        raise ToolError(f"Outil non proposé pour cette question : {name}. La question ne demande aucune action ; "
                        f"outils disponibles : {', '.join(offered)}.")
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError:
            raise ToolError(f"Arguments illisibles pour {name} (JSON attendu).")
    if raw_args is None:
        raw_args = {}
    if not isinstance(raw_args, dict):
        raise ToolError(f"Arguments de {name} : un objet est attendu.")
    spec = TOOLS[name]
    unknown = set(raw_args) - set(spec["parameters"])
    if unknown:
        raise ToolError(f"Argument(s) inconnu(s) pour {name} : {', '.join(sorted(unknown))}.")
    out = {}
    for key, p in spec["parameters"].items():
        if key not in raw_args or raw_args[key] in (None, ""):
            if key in spec["required"]:
                raise ToolError(f"Argument manquant pour {name} : {key}.")
            if "default" in p:
                out[key] = p["default"]
            continue
        value = raw_args[key]
        if p["type"] == "integer":
            try:
                if isinstance(value, bool) or float(value) != int(float(value)):
                    raise ValueError
                value = int(float(value))
            except (TypeError, ValueError):
                raise ToolError(f"{name} : {key} doit être un entier.")
            if not p["minimum"] <= value <= p["maximum"]:
                raise ToolError(f"{name} : {key} doit être entre {p['minimum']} et {p['maximum']}.")
        else:
            if not isinstance(value, str):
                raise ToolError(f"{name} : {key} doit être un texte.")
            value = value.strip()
            if "enum" in p:
                value = value.upper()
                if value not in p["enum"]:
                    raise ToolError(f"{name} : {key} doit valoir {', '.join(p['enum'])}.")
            elif not p["minLength"] <= len(value) <= p["maxLength"]:
                raise ToolError(f"{name} : {key} doit faire entre {p['minLength']} et {p['maxLength']} caractères.")
        out[key] = value
    return out


def run(db, name: str, args: dict) -> dict:
    return TOOLS[name]["fn"](db, **args)


def is_action(name: str) -> bool:
    return TOOLS.get(name, {}).get("kind") == "action"


# ---------------------------------------------------------------- summaries

def summarize(name: str, result: dict) -> str:
    """One French line for the trace (counts only; the numbers themselves are in the raw result)."""
    demo = f" · {DEMO_LABEL}" if result.get("demo") or any(s.get("demo") for s in result.get("segments", [])) else ""
    if is_action(name):
        return f"Action proposée, à confirmer : {result['summary']}{demo}"
    if name == "list_priority_segments":
        return f"{result['count']} segment(s) de priorité {'/'.join(result['priorities'])}{demo}"
    if name == "get_segment_facts":
        return (f"{result['segment']['segment_code']} : {len(result['events'])} détection(s) ouverte(s), "
                f"{len(result['complaints'])} signalement(s) à moins de 100 m, "
                f"{'score M2 disponible' if result['risk'] else 'pas de score M2 valide'}{demo}")
    if name == "get_intervention_sheet":
        return (f"Fiche (données) de {result['segment']['segment_code']} : "
                f"{'aucun défaut ouvert' if result['no_defect'] else 'défaut(s) ouvert(s)'}{demo}")
    if name == "search_guides":
        return f"{result['count']} extrait(s) des guides"
    if name == "get_equipment_dashboard":
        return "Compteurs du tableau de bord Équipement"
    return ""


COMPACT_SEGMENT_KEYS = ("segment_code", "name", "maintenance_priority", "risk_level", "risk_score", "open_defects", "demo")


def model_view(name: str, result: dict) -> dict:
    """What the model reads. list_priority_segments: compact rows (the UI keeps the full result)."""
    if name == "list_priority_segments":
        return {**{k: v for k, v in result.items() if k != "segments"},
                "segments": [{("priority" if k == "maintenance_priority" else k): s.get(k) for k in COMPACT_SEGMENT_KEYS}
                             for s in result["segments"]]}
    if name == "search_guides":
        return {**result, "excerpts": [{k: v for k, v in e.items() if k != "chunk_id"} for e in result["excerpts"]]}
    return result


def for_model(name: str, result: dict) -> str:
    """Compact JSON for the model, truncated to keep the context small."""
    text = json.dumps(model_view(name, result), ensure_ascii=False, default=str, separators=(",", ":"))
    return text if len(text) <= MODEL_RESULT_CHARS else text[:MODEL_RESULT_CHARS] + "…(tronqué)"


# ---------------------------------------------------------------- action tools (propose only, see actions.py)
_PROPOSE_ONLY = " PROPOSE seulement : rien n'est exécuté tant que le superviseur n'a pas confirmé."
TOOLS.update({
    "plan_intervention": {
        "kind": "action", "fn": actions.plan_intervention,
        "description": "Propose de planifier une intervention sur UN segment : ses signalements citoyens ouverts "
                       "(à moins de 100 m) passeraient à « Intervention planifiée »." + _PROPOSE_ONLY,
        "parameters": {"segment_code": _code_param(),
                       "note": {"type": "string", "description": "Note courte pour l'historique (facultative).",
                                "minLength": 0, "maxLength": 300, "default": ""}},
        "required": ["segment_code"],
    },
    "notify_transport": {
        "kind": "action", "fn": actions.notify_transport,
        "description": "Propose d'envoyer un message au superviseur Transport au sujet d'UN segment (danger, "
                       "chantier prévu)." + _PROPOSE_ONLY,
        "parameters": {"segment_code": _code_param(),
                       "message": {"type": "string", "description": "Le message, en français, court.",
                                   "minLength": 3, "maxLength": 500}},
        "required": ["segment_code", "message"],
    },
    "generate_full_sheet": {
        "kind": "action", "fn": actions.generate_full_sheet,
        "description": "Propose de générer la fiche d'intervention complète d'UN segment, avec les conseils des guides "
                       "(environ 100 s)." + _PROPOSE_ONLY,
        "parameters": {"segment_code": _code_param()},
        "required": ["segment_code"],
    },
    "propose_validation": {
        "kind": "action", "fn": actions.propose_validation,
        "description": "Propose de valider UNE détection M1 à valider ; le superviseur vérifie d'abord la photo et la "
                       "confiance." + _PROPOSE_ONLY,
        "parameters": {"event_id": {"type": "string", "description": "« id » exact d'une détection renvoyé par "
                                                                     "get_segment_facts (n'en invente jamais).",
                                    "minLength": 36, "maxLength": 36}},
        "required": ["event_id"],
    },
})


# ---------------------------------------------------------------- which tools for which question
READ_TOOLS = [n for n, spec in TOOLS.items() if spec.get("kind") != "action"]
ACTION_TOOL_NAMES = [n for n, spec in TOOLS.items() if spec.get("kind") == "action"]
# The 4 action tools are offered only when the question asks for an action (simple French keyword rule, accents and
# case ignored). With all 9 tools a 3B model proposed actions on plain questions (eval 07/11, task a07).
ACTION_STEMS = ("planifi", "alert", "preven", "previen", "notifi", "transport", "valid", "fiche", "trait")
_ACTION_RE = re.compile(r"\b(" + "|".join(ACTION_STEMS) + r")\w*", re.IGNORECASE)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def wants_action(question: str) -> bool:
    return bool(_ACTION_RE.search(_fold(question)))


def tools_for(question: str) -> tuple[str, list[str]]:
    """-> ("actions", all 9 tools) when the question asks for an action, else ("lecture", the 5 read tools)."""
    return ("actions", list(TOOLS)) if wants_action(question) else ("lecture", list(READ_TOOLS))
