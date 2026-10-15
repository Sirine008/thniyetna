"""Minimal Ollama HTTP client (stdlib only).

OllamaUnavailable = the server cannot be reached (down, wrong host, timeout) -> API answers 503.
OllamaError       = the server answered with an error (e.g. model not pulled).
"""
import json
import socket
import urllib.error
import urllib.request

from . import config

# nomic-embed-text is trained with task prefixes; documents and questions use different ones.
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class OllamaUnavailable(RuntimeError):
    pass


class OllamaError(RuntimeError):
    pass


def _request(path: str, payload: dict | None = None, timeout: float = 10):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(config.OLLAMA_URL + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:  # reached Ollama, it refused
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise OllamaError(f"{path} HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise OllamaUnavailable(f"{config.OLLAMA_URL}: {exc}") from exc


def tags() -> list[str]:
    """Names of the models available on the Ollama server."""
    return [m["name"] for m in _request("/api/tags", timeout=5).get("models", [])]


def embed(texts: list[str], kind: str = "document") -> list[list[float]]:
    prefix = QUERY_PREFIX if kind == "query" else DOC_PREFIX
    out = _request("/api/embed", {"model": config.RAG_EMBED_MODEL, "input": [prefix + t for t in texts]},
                   timeout=config.EMBED_TIMEOUT_S).get("embeddings", [])
    if len(out) != len(texts) or any(len(v) != config.EMBED_DIM for v in out):
        raise OllamaError(f"expected {len(texts)} embeddings of {config.EMBED_DIM} dims from {config.RAG_EMBED_MODEL}")
    return out


def chat(messages: list[dict]) -> str:
    out = _request("/api/chat", {"model": config.RAG_LLM_MODEL, "messages": messages, "stream": False,
                                 "options": config.CHAT_OPTIONS}, timeout=config.CHAT_TIMEOUT_S)
    return (out.get("message") or {}).get("content", "").strip()
