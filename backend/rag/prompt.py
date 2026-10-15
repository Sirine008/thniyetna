"""Grounded prompt (French): answer only from the numbered sources, cite them, refuse otherwise."""

REFUSAL = "Je ne trouve pas cette information dans les documents"

SYSTEM = (
    "Tu es l'assistant documentaire de THNIYETNA (réseau routier de Bizerte). "
    "Réponds en français, uniquement à partir des sources numérotées fournies ci-dessous. "
    "Cite chaque information avec le numéro de sa source entre crochets, par exemple [1] ou [2]. "
    "N'utilise pas tes connaissances générales et n'invente rien. "
    f"Si les sources ne contiennent pas la réponse, réponds exactement : « {REFUSAL}. »"
)


def source_label(src: dict) -> str:
    page = f" (p. {src['page']})" if src.get("page") else ""
    return f"[{src['n']}] {src['title']}{page}"


def build_messages(question: str, sources: list[dict]) -> list[dict]:
    blocks = "\n\n".join(f"{source_label(s)}\n{s['text']}" for s in sources)
    user = f"Sources :\n\n{blocks}\n\nQuestion : {question}\n\nRéponse (en citant les sources) :"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
