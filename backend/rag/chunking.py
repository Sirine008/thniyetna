"""Paragraph-aware chunking (~800 chars, 150 overlap). Pure Python, no dependency.

Chunks never cross a page boundary, so every chunk keeps the page it comes from.
Each chunk after the first on a page starts with the last ~`overlap` characters of the
previous one (cut at a word boundary), so a sentence split between two chunks stays findable.
"""
import re
from dataclasses import dataclass

_SPACES = re.compile(r"[ \t\f\v ]+")
_PARA_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


@dataclass(frozen=True)
class Chunk:
    index: int
    page: int | None
    text: str


def paragraphs(text: str) -> list[str]:
    """Blank-line separated paragraphs; hard line wraps inside a paragraph are joined."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for block in _PARA_BREAK.split(text):
        p = _SPACES.sub(" ", " ".join(line.strip() for line in block.split("\n"))).strip()
        if p:
            out.append(p)
    return out


def _split_long(text: str, limit: int) -> list[str]:
    """Pieces of at most `limit` chars, cut at sentence ends, then words, then hard."""
    pieces, cur = [], ""
    for unit in _SENTENCE_END.split(text):
        words = [unit] if len(unit) <= limit else unit.split(" ")
        for w in words:
            while len(w) > limit:                       # a single overlong token
                if cur:
                    pieces.append(cur)
                    cur = ""
                pieces.append(w[:limit])
                w = w[limit:]
            if not w:
                continue
            if cur and len(cur) + 1 + len(w) > limit:
                pieces.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}" if cur else w
    if cur:
        pieces.append(cur)
    return pieces


def _tail(text: str, overlap: int) -> str:
    if len(text) <= overlap:
        return text
    t = text[-overlap:]
    i = t.find(" ")
    return t[i + 1:] if 0 <= i < len(t) - 1 else t


def chunk_pages(pages: list[tuple[int | None, str]], size: int = 800, overlap: int = 150) -> list[Chunk]:
    """pages: [(page_number or None, text)]. Returns chunks of at most `size` chars."""
    if not 0 <= overlap < size // 2:
        raise ValueError("overlap must be in [0, size/2)")
    limit = size - overlap - 1                          # room left for the overlap prefix
    chunks: list[Chunk] = []
    for page, text in pages:
        units = []
        for p in paragraphs(text or ""):
            units.extend(_split_long(p, limit) if len(p) > limit else [p])
        cur, fresh = "", False                          # fresh = holds content not yet emitted
        for u in units:
            if cur and len(cur) + 1 + len(u) > size:
                if fresh:
                    chunks.append(Chunk(len(chunks), page, cur))
                cur, fresh = _tail(cur, overlap) if overlap else "", False
            cur = f"{cur}\n{u}" if cur else u
            fresh = True
        if fresh:
            chunks.append(Chunk(len(chunks), page, cur))
    return chunks
