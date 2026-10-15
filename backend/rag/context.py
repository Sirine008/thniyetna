"""Chunk context for retrieval: "<document title> — <page header> — <nearest section heading>".

PDF text extraction loses the layout, so headings are found inline with two heuristics:
- page header: a page that starts with its page number followed by a short lowercase phrase
  (e.g. "27 réparation de nids-de-poule avec un enrobé Chaud 5.2 NIVEAU ...") -> that phrase;
- section heading: a run of UPPERCASE words, either numbered ("6. DURABILITÉ DE LA RÉPARATION",
  "13 RAVELING") or of at least two words ("RÉPARATION PERMANENTE").
Candidates repeated on many pages (running footers such as "CONSEIL PERMANENT") are ignored.
The heading carries over to the following chunks until a new one appears.
"""
import re

_UP = "A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŒ"
_WORD = rf"[{_UP}][{_UP}'’\-]+"
# numbered heading: "6. DURABILITÉ ...", "5.2 NIVEAU ...", "13 RAVELING"
_NUMBERED = re.compile(rf"(?<![\w.])(\d{{1,2}}(?:\.\d{{1,2}})?\.?)\s+({_WORD}(?:\s+(?:{_WORD}|[DL]['’]|À|ET|DE|DU|DES|LA|LE|LES|OF|AND))*)")
# unnumbered heading: >= 2 uppercase words
_PLAIN = re.compile(rf"(?<![\w])({_WORD}(?:\s+(?:{_WORD}|DE|DU|DES|LA|LE|LES|ET|À|OF|AND)){{1,}})(?![\w])")
_PAGE_HEADER = re.compile(rf"^\s*\d{{1,3}}\s+([a-zà-ÿ][^\n]{{8,80}}?)\s+(?=\d{{1,2}}(?:\.\d{{1,2}})?\.?\s+[{_UP}]{{3}})")
MAX_HEADING = 80


def _clean(s: str) -> str:
    return " ".join(s.split()).strip(" -–—:;,.")


def heading_candidates(text: str) -> list[tuple[int, str]]:
    """(position, heading) found in a chunk, in reading order."""
    found = {}
    for m in _NUMBERED.finditer(text):
        h = _clean(m.group(2))
        if len(h) >= 4:
            found.setdefault(m.start(), f"{m.group(1).rstrip('.')} {h}"[:MAX_HEADING])
    for m in _PLAIN.finditer(text):
        h = _clean(m.group(1))
        if sum(c.isalpha() for c in h) >= 8 and not any(abs(m.start() - p) < 6 for p in found):
            found.setdefault(m.start(), h[:MAX_HEADING])
    return sorted(found.items())


def page_header(text: str) -> str:
    m = _PAGE_HEADER.match(text)
    return _clean(m.group(1)) if m else ""


def _key(h: str) -> str:
    return re.sub(r"^[\d.]+\s+", "", h).lower()


def build_contexts(title: str, chunks: list[tuple[int | None, str]]) -> list[str]:
    """chunks: [(page, text)] in document order -> one context string per chunk.

    Heading part = the headings that appear in the chunk (at most 2), otherwise the last
    heading seen before it. Candidates found on >= 3 pages (and >= 5 % of the pages) are
    running headers/footers and are skipped.
    """
    per_chunk = [heading_candidates(t) for _, t in chunks]
    seen_on = {}
    for (page, _), cands in zip(chunks, per_chunk):
        for _, h in cands:
            seen_on.setdefault(_key(h), set()).add(page)
    n_pages = len({p for p, _ in chunks}) or 1
    repeated = {k for k, pages in seen_on.items() if len(pages) >= 3 and len(pages) >= 0.05 * n_pages}

    out, carried, header, header_page = [], "", "", object()
    for (page, text), cands in zip(chunks, per_chunk):
        if page != header_page:                         # page header only applies to its own page
            header, header_page = page_header(text), page
        inside = [h for _, h in cands if _key(h) not in repeated]
        heading = "; ".join(inside[:2]) if inside else carried
        if inside:
            carried = inside[-1]
        out.append(" — ".join(p for p in (title, header, heading) if p))
    return out
