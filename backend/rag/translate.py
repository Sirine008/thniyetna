"""Question translation for bilingual retrieval (RAG_BILINGUAL).

The corpus mixes French guides and English project docs / manuals; a question only matches
chunks in its own language well. The LLM rewrites the question into the other language
(fr -> en, en -> fr) and both versions are searched (see retrieve.retrieve).
"""
from functools import lru_cache

from . import config, ollama
from .lang import detect_lang

TARGET = {"fr": "en", "en": "fr"}
NAMES = {"fr": "French", "en": "English"}


def target_lang(question: str) -> str | None:
    """Language to translate into, None when the question is neither French nor English."""
    return TARGET.get(detect_lang(question))


def clean(raw: str) -> str:
    """First non-empty line, without quotes or a 'Translation:' label the model may add."""
    line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    if ":" in line[:20] and line.split(":", 1)[0].strip().lower() in ("translation", "traduction", "english", "french"):
        line = line.split(":", 1)[1].strip()
    return line.strip("\"'«» ").strip()


@lru_cache(maxsize=512)
def translate(question: str, model: str | None = None) -> str:
    """Translation of the question into the other language ('' if not applicable). Cached per (question, model)."""
    target = target_lang(question)
    if target is None:
        return ""
    messages = [
        {"role": "system", "content": f"Translate the user's question into {NAMES[target]}. "
                                      "Keep technical terms and codes (e.g. M2, PR-AUC) unchanged. "
                                      "Output only the translated question, nothing else."},
        {"role": "user", "content": question},
    ]
    return clean(ollama.chat(messages, model=model, options=config.TRANSLATE_OPTIONS))
