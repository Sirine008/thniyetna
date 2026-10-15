"""Grounded prompt (French): answer only from the numbered sources, cite them, refuse otherwise.

v1 = part A prompt. v2 (RAG_PROMPT_VERSION=v2) asks for a partial answer when the sources are related,
refuses only when none is, and shows one short French example; citations [n] stay mandatory.
RAG_NUMBERS_RULE adds: copy numbers, units and comparison signs exactly as written in the source.
"""
from . import config

REFUSAL = "Je ne trouve pas cette information dans les documents"

SYSTEM = (
    "Tu es l'assistant documentaire de THNIYETNA (réseau routier de Bizerte). "
    "Réponds en français, uniquement à partir des sources numérotées fournies ci-dessous. "
    "Cite chaque information avec le numéro de sa source entre crochets, par exemple [1] ou [2]. "
    "N'utilise pas tes connaissances générales et n'invente rien. "
    f"Si les sources ne contiennent pas la réponse, réponds exactement : « {REFUSAL}. »"
)

SYSTEM_V2 = (
    "Tu es l'assistant documentaire de THNIYETNA (réseau routier de Bizerte). "
    "Tu reçois des sources numérotées, puis une question. Réponds en français, de façon brève, "
    "en utilisant les sources même si elles ne répondent qu'en partie ; dans ce cas, dis ce qui manque. "
    "Chaque information doit être suivie du numéro de sa source entre crochets, par exemple [1] ou [2]. "
    "N'utilise pas tes connaissances générales et n'invente rien. Les sources peuvent être en anglais : "
    "réponds quand même en français. "
    f"Refuse seulement si aucune source n'a de rapport avec la question, en écrivant exactement : « {REFUSAL}. »"
)

NUMBERS_RULE = ("Recopie les nombres, les unités et les signes de comparaison (≤, ≥, <, >) exactement "
                "comme ils sont écrits dans la source.")

# One short French example (fictive sources): a partial answer with citations.
FEW_SHOT_USER = (
    "Sources :\n\n"
    "[1] Guide d'entretien (p. 4)\nLes fissures de plus de 6 mm doivent être scellées avant l'hiver "
    "pour limiter l'infiltration d'eau.\n\n"
    "[2] Rapport annuel (p. 2)\nLe budget de l'année a été voté en mars.\n\n"
    "Question : Quand faut-il sceller les fissures et avec quel produit ?"
)
FEW_SHOT_ANSWER = (
    "Les fissures de plus de 6 mm doivent être scellées avant l'hiver, pour limiter l'infiltration d'eau [1]. "
    "Les sources ne précisent pas le produit à utiliser."
)


def source_label(src: dict) -> str:
    page = f" (p. {src['page']})" if src.get("page") else ""
    return f"[{src['n']}] {src['title']}{page}"


def system_prompt(version: str, numbers_rule: bool) -> str:
    base = SYSTEM_V2 if version == "v2" else SYSTEM
    return f"{base} {NUMBERS_RULE}" if numbers_rule else base


def build_messages(question: str, sources: list[dict], version: str | None = None,
                   numbers_rule: bool | None = None) -> list[dict]:
    """version: RAG_PROMPT_VERSION (v1 | v2); numbers_rule: RAG_NUMBERS_RULE (appended to the system prompt)."""
    version = version or config.RAG_PROMPT_VERSION
    system = system_prompt(version, config.RAG_NUMBERS_RULE if numbers_rule is None else numbers_rule)
    blocks = "\n\n".join(f"{source_label(s)}\n{s['text']}" for s in sources)
    if version == "v2":
        user = f"Sources :\n\n{blocks}\n\nQuestion : {question}"
        return [{"role": "system", "content": system},
                {"role": "user", "content": FEW_SHOT_USER},
                {"role": "assistant", "content": FEW_SHOT_ANSWER},
                {"role": "user", "content": user}]
    user = f"Sources :\n\n{blocks}\n\nQuestion : {question}\n\nRéponse (en citant les sources) :"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
