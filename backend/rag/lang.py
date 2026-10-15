"""Tiny language guess (fr / en / ar) from function words; used for documents and questions."""
import re

_FR = set("le la les des du une est et pour dans sur par au aux que qui".split())
_EN = set("the and of to is in for on with that by are be this".split())


def detect_lang(sample: str) -> str:
    letters = [c for c in sample if c.isalpha()]
    if letters and sum("؀" <= c <= "ۿ" for c in letters) / len(letters) > 0.3:
        return "ar"
    words = re.findall(r"[a-zà-ÿ]+", sample.lower())
    fr, en = sum(w in _FR for w in words), sum(w in _EN for w in words)
    return "fr" if fr >= en else "en"
