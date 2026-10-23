"""Intervention sheet, pure parts: retrieval query, template sections from facts, LLM section parsing.
No database, no Ollama, no FastAPI."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from rag import intervention as I  # noqa: E402
from rag.prompt import NUMBERS_RULE, REFUSAL  # noqa: E402

RISK = {"risk_level": "low", "risk_score": 0.043498, "maintenance_priority": "P3",
        "predicted_condition": "no_observed_defect", "model_version": "m2-risk:2026.10.11-2054",
        "computed_at": "2026-10-15T09:12:44+00:00", "valid_until": "2026-11-14T09:12:44+00:00",
        "top_factors": [{"feature": "segment:road_class=regional", "value": 2.34, "contribution": 0.8501}]}


def facts(events=(), complaints=(), risk=RISK, inspection=None):
    return {"segment": {"segment_code": "OSM-1", "name": "Route de Menzel", "road_class": "regional"},
            "risk": risk, "events": list(events), "complaints": list(complaints), "last_inspection_at": inspection}


POTHOLE = {"event_type": "pothole", "severity": 0.85, "confidence": 0.9132, "validated": False,
           "observed_at": "2026-10-14T08:30:00+00:00", "source": "m1"}


def test_demo_rows_are_labelled_in_the_constat():
    complaint = {"category": "road_damage", "status": "open", "created_at": "2026-10-13T10:00:00+00:00",
                 "distance_m": 12.0}
    constat = I.template_sections(facts([{**POTHOLE, "demo": True}, POTHOLE],
                                        [{**complaint, "demo": True}]))[0]["text"].splitlines()
    assert constat[1].startswith("[DÉMO — données fictives] Détection M1 : nid-de-poule")
    assert constat[2].startswith("Détection M1 : nid-de-poule")  # a real detection keeps no label
    assert constat[3].startswith("[DÉMO — données fictives] Signalement citoyen")


def test_query_from_defect_types_and_no_defect():
    assert I.retrieval_query(facts()) == I.NO_DEFECT_QUERY
    assert I.retrieval_query(facts([POTHOLE])) == "réparation nid-de-poule enrobé température signalisation chantier"
    q = I.retrieval_query(facts([POTHOLE, {**POTHOLE, "event_type": "crack"}],
                                [{"category": "road_damage", "status": "open", "created_at": None, "distance_m": 12.0}]))
    assert q == "réparation nid-de-poule enrobé température fissures scellement colmatage signalisation chantier"
    assert I.retrieval_query(facts([{**POTHOLE, "event_type": "manhole"}])) == "réparation chaussée signalisation chantier"


def test_no_defect_sheet_says_so_and_lists_missing_data():
    secs = I.template_sections(facts())
    assert [s["key"] for s in secs] == ["constat", "priorite", "manquant"] and all(s["origin"] == "données" for s in secs)
    assert "Aucun défaut ouvert n'est enregistré sur ce segment" in secs[0]["text"]
    assert "pas une intervention" in secs[0]["text"]
    missing = secs[2]["text"]
    assert "Aucune détection M1 ouverte" in missing and "Aucun passage de véhicule d'inspection" in missing
    assert "Aucun signalement citoyen ouvert à moins de 100 m" in missing
    assert I.llm_sections_spec(facts()) == I.INSPECTION_SECTIONS


def test_numbers_are_copied_exactly_from_the_facts():
    secs = I.template_sections(facts([POTHOLE], [{"category": "road_damage", "status": "open",
                                                  "created_at": "2026-10-13T10:00:00+00:00", "distance_m": 37.0}]))
    constat, prio = secs[0]["text"], secs[1]["text"]
    assert "sévérité 0.85, confiance 0.9132, non validée, observée le 2026-10-14 08:30" in constat
    assert "à 37.0 m" in constat
    assert "P3 · Planifier" in prio and "score 0.043498 sur 1" in prio
    assert "- segment:road_class=regional : 2.34 ; 0.8501" in prio
    assert "Aucun défaut validé" in secs[2]["text"]
    assert I.llm_sections_spec(facts([POTHOLE])) == I.ADVICE_SECTIONS


def test_missing_risk_and_unknown_values():
    secs = I.template_sections(facts([{**POTHOLE, "severity": None}], risk=None, inspection="2026-10-01T07:00:00"))
    assert "sévérité non renseignée" in secs[0]["text"]
    assert "Aucun score de risque M2 valide pour ce segment" in secs[1]["text"]
    missing = secs[2]["text"]
    assert "Sévérité ou confiance non renseignée" in missing and "Dernier passage d'inspection : 2026-10-01 07:00" in missing


def test_llm_prompt_has_headings_rules_and_no_fact_numbers():
    srcs = [{"n": 1, "title": "Guide", "page": 27, "text": "La température doit être supérieure à 10°C."}]
    msgs = I.llm_messages(facts([POTHOLE]), srcs)
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert all(f"### {t}" in system for _, t in I.ADVICE_SECTIONS) and NUMBERS_RULE in system and REFUSAL in system
    assert "[1] Guide (p. 27)" in user and "nid-de-poule" in user
    assert "0.85" not in user and "0.043498" not in user          # facts numbers stay in the template
    assert "Ne propose aucune réparation" in I.llm_messages(facts(), srcs)[1]["content"]


def test_parse_sections_headings_variants_and_missing():
    text = ("### Intervention recommandée\nRapiécer à l'enrobé chaud [1].\n\n**Conditions de mise en œuvre :**\n"
            "Température > 10 °C [2].\nSignalisation et sécurité du chantier\nPanneaux KC 1 [3].")
    out = I.parse_sections(text, I.ADVICE_SECTIONS)
    assert [s["text"] for s in out] == ["Rapiécer à l'enrobé chaud [1].", "Température > 10 °C [2].", "Panneaux KC 1 [3]."]
    assert not any(s["uncited"] for s in out)
    flagged = I.parse_sections("### Conseils d'inspection\nInspecter en avril – mai.", I.INSPECTION_SECTIONS)[0]
    assert flagged["uncited"] and flagged["text"] == "Inspecter en avril – mai."
    assert not I.parse_sections(f"### Conseils d'inspection\n{REFUSAL}.", I.INSPECTION_SECTIONS)[0]["uncited"]
    out = I.parse_sections("### Intervention recommandée\nX [1].", I.ADVICE_SECTIONS)
    assert out[1]["text"] == I.MISSING and out[2]["text"] == I.MISSING
    assert I.parse_sections("Texte sans titre [1].", I.INSPECTION_SECTIONS)[0]["text"] == "Texte sans titre [1]."
    sheet = I.assemble(I.template_sections(facts()), I.parse_sections("x", I.INSPECTION_SECTIONS))
    assert [s["key"] for s in sheet] == ["constat", "priorite", "inspection", "manquant"]
