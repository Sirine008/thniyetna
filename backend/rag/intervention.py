"""Intervention sheet for one road segment (equipment supervisors).

FACTS come from the database only (latest valid M2 risk score, open M1 road events on the segment,
open complaints within 100 m, last inspection pass). The "Constat", "Priorité" and "Données manquantes"
sections are written from these facts by a template, numbers copied as stored; the LLM never writes them.
The LLM only writes the advice sections, from the retrieved guide excerpts, with citations [n].
"""
import re

from .prompt import NUMBERS_RULE, REFUSAL

COMPLAINT_RADIUS_M = 100
INSPECTION_RADIUS_M = 30
DEMO_LABEL = "DÉMO — données fictives"  # rows tagged payload.demo by scripts/seed_demo.py
MISSING = "Non fourni par l'assistant — consultez les sources ci-dessous."

PRIORITY_LABELS = {"P1": "P1 · Urgent", "P2": "P2 · Prioritaire", "P3": "P3 · Planifier", "P4": "P4 · Surveiller"}
RISK_LABELS = {"low": "faible", "medium": "moyen", "high": "élevé", "critical": "critique"}
CONDITION_LABELS = {"no_observed_defect": "aucun défaut observé", "good": "bon", "fair": "moyen",
                    "poor": "dégradé", "critical": "critique"}
DEFECT_LABELS = {"pothole": "nid-de-poule", "road_damage": "dégradation de chaussée (nid-de-poule)",
                 "crack": "fissure", "cracking": "fissuration", "flooding": "inondation / eau sur la chaussée",
                 "obstacle": "obstacle sur la chaussée"}
# French retrieval terms per defect type (the corpus is French); unknown types get a generic query.
DEFECT_QUERY = {"pothole": "réparation nid-de-poule enrobé température",
                "road_damage": "réparation nid-de-poule enrobé température",
                "crack": "fissures scellement colmatage", "cracking": "fissures scellement colmatage",
                "flooding": "drainage eau chaussée", "obstacle": "signalisation temporaire obstacle"}
GENERIC_QUERY = "réparation chaussée"
NO_DEFECT_QUERY = "inspection annuelle état de la chaussée entretien préventif nids-de-poule fissures"

ADVICE_SECTIONS = [("intervention", "Intervention recommandée"),
                   ("conditions", "Conditions de mise en œuvre"),
                   ("signalisation", "Signalisation et sécurité du chantier")]
INSPECTION_SECTIONS = [("inspection", "Conseils d'inspection")]


# ---------------------------------------------------------------- facts (database)

def gather_facts(db, segment_code: str) -> dict | None:
    """All facts from the database; None if the segment does not exist."""
    from sqlalchemy import text

    seg = db.execute(text("""SELECT id::text, segment_code, name, road_class FROM road_segments
                             WHERE segment_code = CAST(:c AS text)"""), {"c": segment_code}).mappings().first()
    if not seg:
        return None
    risk = db.execute(text("""
        SELECT risk_level, risk_score, maintenance_priority, predicted_condition, top_factors, model_version,
               created_at computed_at, valid_until
        FROM risk_scores WHERE segment_id = CAST(:s AS uuid) AND risk_level IS NOT NULL
          AND (valid_until IS NULL OR valid_until > now())
        ORDER BY created_at DESC LIMIT 1"""), {"s": seg["id"]}).mappings().first()
    events = db.execute(text("""
        SELECT event_type, severity, confidence, status IN ('validated', 'closed') validated, observed_at, source,
               coalesce((payload->>'demo')::boolean,false) demo
        FROM road_events WHERE segment_id = CAST(:s AS uuid) AND status <> 'closed'
        ORDER BY observed_at DESC"""), {"s": seg["id"]}).mappings().all()
    complaints = db.execute(text("""
        SELECT c.payload->>'category' category, c.status, c.created_at,
               round(ST_Distance(c.geom::geography, s.geom::geography)::numeric, 0)::float distance_m,
               coalesce((c.payload->>'demo')::boolean, false) demo
        FROM complaints c, road_segments s
        WHERE s.id = CAST(:s AS uuid) AND c.status NOT IN ('resolved', 'rejected')
          AND ST_DWithin(c.geom::geography, s.geom::geography, :r)
        ORDER BY distance_m"""), {"s": seg["id"], "r": COMPLAINT_RADIUS_M}).mappings().all()
    last_inspection = db.execute(text("""
        SELECT max(p.captured_at) FROM inspection_positions p, road_segments s
        WHERE s.id = CAST(:s AS uuid) AND ST_DWithin(p.geom::geography, s.geom::geography, :r)"""),
        {"s": seg["id"], "r": INSPECTION_RADIUS_M}).scalar()
    return {
        "segment": {"segment_code": seg["segment_code"], "name": seg["name"], "road_class": seg["road_class"]},
        "risk": _jsonable(dict(risk)) if risk else None,
        "events": [_jsonable(dict(e)) for e in events],
        "complaints": [_jsonable(dict(c)) for c in complaints],
        "last_inspection_at": _iso(last_inspection),
    }


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _jsonable(row: dict) -> dict:
    return {k: _iso(v) for k, v in row.items()}


# ---------------------------------------------------------------- pure parts

def defect_types(facts: dict) -> list[str]:
    """Open defect types: M1 events first, then complaint categories, without duplicates."""
    out = []
    for t in [e["event_type"] for e in facts["events"]] + [c["category"] for c in facts["complaints"]]:
        if t and t not in out:
            out.append(t)
    return out


def has_defect(facts: dict) -> bool:
    return bool(facts["events"] or facts["complaints"])


def retrieval_query(facts: dict) -> str:
    if not has_defect(facts):
        return NO_DEFECT_QUERY
    terms = []
    for t in defect_types(facts):
        q = DEFECT_QUERY.get(t, GENERIC_QUERY)
        if q not in terms:
            terms.append(q)
    return " ".join(terms + ["signalisation chantier"])


def _num(v) -> str:
    """Number as stored (no rounding); missing -> 'non renseignée'."""
    return "non renseignée" if v is None else str(v)


def _date(v) -> str:
    return "date inconnue" if not v else str(v)[:16].replace("T", " ")


def _label(table: dict, v) -> str:
    return table.get(v, v) if v else "non renseigné"


def _demo(row: dict) -> str:
    return f"[{DEMO_LABEL}] " if row.get("demo") else ""


def template_sections(facts: dict) -> list[dict]:
    """Constat, Priorité, Données manquantes — from the database facts only."""
    seg, risk, events, complaints = facts["segment"], facts["risk"], facts["events"], facts["complaints"]
    where = f"{seg['name'] or 'Segment sans nom'} ({seg['segment_code']}, route {seg['road_class'] or 'classe inconnue'})"

    constat = [f"Segment : {where}."]
    if not has_defect(facts):
        constat.append("Aucun défaut ouvert n'est enregistré sur ce segment : aucune détection M1 ouverte et aucun "
                       f"signalement citoyen ouvert à moins de {COMPLAINT_RADIUS_M} m. "
                       "Les conseils ci-dessous sont des conseils généraux d'inspection, pas une intervention.")
    for e in events:
        constat.append(f"{_demo(e)}Détection M1 : {_label(DEFECT_LABELS, e['event_type'])} — sévérité {_num(e['severity'])}, "
                       f"confiance {_num(e['confidence'])}, {'validée' if e['validated'] else 'non validée'}, "
                       f"observée le {_date(e['observed_at'])}.")
    for c in complaints:
        constat.append(f"{_demo(c)}Signalement citoyen ({_label(DEFECT_LABELS, c['category'])}) à {_num(c['distance_m'])} m, "
                       f"statut {c['status']}, reçu le {_date(c['created_at'])}.")
    if risk:
        constat.append(f"État prédit (M2) : {_label(CONDITION_LABELS, risk['predicted_condition'])}.")

    if risk:
        prio = [f"Priorité d'entretien : {_label(PRIORITY_LABELS, risk['maintenance_priority'])}.",
                f"Niveau de risque : {_label(RISK_LABELS, risk['risk_level'])} (score {_num(risk['risk_score'])} sur 1).",
                f"Modèle {risk['model_version'] or 'inconnu'}, calculé le {_date(risk['computed_at'])}"
                + (f", valable jusqu'au {_date(risk['valid_until'])}." if risk["valid_until"] else ".")]
        factors = risk.get("top_factors") or []
        if factors:
            prio.append("Facteurs principaux du modèle (valeur ; contribution) :")
            prio += [f"- {f.get('feature')} : {_num(f.get('value'))} ; {_num(f.get('contribution'))}" for f in factors]
    else:
        prio = ["Aucun score de risque M2 valide pour ce segment : priorité non déterminée."]

    missing = []
    if not events:
        missing.append("Aucune détection M1 ouverte sur ce segment.")
    elif not any(e["validated"] for e in events):
        missing.append("Aucun défaut validé : les détections M1 sont à confirmer sur place.")
    if any(e["severity"] is None or e["confidence"] is None for e in events):
        missing.append("Sévérité ou confiance non renseignée pour au moins une détection.")
    if not complaints:
        missing.append(f"Aucun signalement citoyen ouvert à moins de {COMPLAINT_RADIUS_M} m.")
    if not facts["last_inspection_at"]:
        missing.append(f"Aucun passage de véhicule d'inspection enregistré à moins de {INSPECTION_RADIUS_M} m du segment.")
    else:
        missing.append(f"Dernier passage d'inspection : {_date(facts['last_inspection_at'])}.")
    if not risk:
        missing.append("Aucun score de risque M2 valide.")

    return [{"key": "constat", "title": "Constat", "origin": "données", "text": "\n".join(constat)},
            {"key": "priorite", "title": "Priorité", "origin": "données", "text": "\n".join(prio)},
            {"key": "manquant", "title": "Données manquantes", "origin": "données",
             "text": "\n".join(f"- {m}" if not m.startswith("- ") else m for m in missing)}]


def llm_sections_spec(facts: dict) -> list[tuple[str, str]]:
    return ADVICE_SECTIONS if has_defect(facts) else INSPECTION_SECTIONS


def llm_messages(facts: dict, sources: list[dict]) -> list[dict]:
    """Numbered guide excerpts + defect types only (the numbers stay in the template sections)."""
    from .prompt import source_label
    spec = llm_sections_spec(facts)
    headings = "\n".join(f"### {title}" for _, title in spec)
    if has_defect(facts):
        situation = ("Défauts ouverts sur le segment : "
                     + ", ".join(_label(DEFECT_LABELS, t) for t in defect_types(facts)) + ".")
        task = ("Rédige une fiche d'intervention pour réparer ces défauts : quoi faire, dans quelles conditions "
                "(météo, température, matériaux), et comment signaler et sécuriser le chantier.")
    else:
        situation = "Aucun défaut ouvert n'est enregistré sur ce segment."
        task = ("Donne uniquement des conseils généraux d'inspection de la chaussée (quand et quoi inspecter, "
                "quels défauts rechercher). Ne propose aucune réparation.")
    system = (
        "Tu es l'assistant documentaire de THNIYETNA pour les équipes d'entretien routier de Bizerte. "
        "Réponds en français, brièvement, uniquement à partir des sources numérotées. Chaque information doit être "
        "suivie du numéro de sa source entre crochets, par exemple [1] ou [2]. N'utilise pas tes connaissances "
        f"générales et n'invente rien. {NUMBERS_RULE} Utilise exactement ces titres, dans cet ordre :\n{headings}\n"
        f"Si aucune source ne traite d'une section, écris sous son titre : « {REFUSAL}. »"
    )
    blocks = "\n\n".join(f"{source_label(s)}\n{s['text']}" for s in sources)
    user = f"Sources :\n\n{blocks}\n\n{situation}\n{task}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _norm(s: str) -> str:
    return re.sub(r"[^a-zàâçéèêëîïôûùüœ' ]", "", s.lower()).strip()


def parse_sections(text: str, spec: list[tuple[str, str]]) -> list[dict]:
    """Split the LLM answer on the expected headings (markdown '#', bold or plain line); missing -> MISSING."""
    titles = {_norm(title): key for key, title in spec}
    found: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        head = _norm(re.sub(r"^\s*#+\s*|\*\*|:\s*$", "", line))
        if head in titles:
            current = titles[head]
            found.setdefault(current, [])
            continue
        if current:
            found[current].append(line)
    out = []
    for key, title in spec:
        body = "\n".join(found.get(key, [])).strip()
        out.append({"key": key, "title": title, "origin": "assistant", "text": body or MISSING})
    if not found and text.strip():          # no heading at all: keep the answer under the first section
        out[0]["text"] = text.strip()
    for sec in out:                          # the model sometimes drops the [n]: flag it, never hide it
        sec["uncited"] = (sec["text"] != MISSING and REFUSAL not in sec["text"]
                          and not re.search(r"\[\d+(?:\s*,\s*\d+)*\]", sec["text"]))
    return out


def assemble(template: list[dict], advice: list[dict]) -> list[dict]:
    """Constat, Priorité, advice sections, Données manquantes."""
    return template[:2] + advice + template[2:]
