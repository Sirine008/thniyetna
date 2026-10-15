"""RAG settings (environment variables, defaults match .env.example)."""
import os
from pathlib import Path

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
RAG_LLM_MODEL = os.getenv("RAG_LLM_MODEL", "llama3.2:3b")
RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768                      # rag_chunks.embedding vector(768), nomic-embed-text

CORPUS_DIR = Path(os.getenv("RAG_CORPUS_DIR", "/data/rag/corpus"))
DOCS_DIR = Path(os.getenv("RAG_DOCS_DIR", "/data/docs"))

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K = 4
CANDIDATES = 20                      # per retriever, before fusion
RRF_K = 60

CHAT_TIMEOUT_S = 180
EMBED_TIMEOUT_S = 120
CHAT_OPTIONS = {"temperature": 0.2, "num_ctx": 4096, "num_predict": 400}
