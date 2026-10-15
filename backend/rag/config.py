"""RAG settings (environment variables, defaults match .env.example)."""
import os
from pathlib import Path

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
RAG_LLM_MODEL = os.getenv("RAG_LLM_MODEL", "llama3.2:3b")
RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768                      # rag_chunks.embedding vector(768), nomic-embed-text

# Field corpus only (audience = supervisors); developer docs/ are not indexed.
CORPUS_DIR = Path(os.getenv("RAG_CORPUS_DIR", "/data/rag/corpus"))

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K = 4
CANDIDATES = 20                      # per retriever, before fusion
RRF_K = 60

# Quality options measured in docs/RAG_EVALUATION.md (A.6 defaults: prompt v2 + numbers rule, gate off)
RAG_BILINGUAL = os.getenv("RAG_BILINGUAL", "false").strip().lower() in ("1", "true", "yes", "on")
RAG_PROMPT_VERSION = os.getenv("RAG_PROMPT_VERSION", "v2").strip().lower()                  # v1 | v2
RAG_NUMBERS_RULE = os.getenv("RAG_NUMBERS_RULE", "true").strip().lower() in ("1", "true", "yes", "on")
RAG_FTS_CONFIG = os.getenv("RAG_FTS_CONFIG", "simple").strip().lower()          # simple | french (tsv_fr, 0005)
RAG_CHUNK_CONTEXT = os.getenv("RAG_CHUNK_CONTEXT", "false").strip().lower() in ("1", "true", "yes", "on")
RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0"))                # 0 = no confidence gate
TRANSLATE_OPTIONS = {"temperature": 0, "num_ctx": 1024, "num_predict": 120}

CHAT_TIMEOUT_S = 180
EMBED_TIMEOUT_S = 120
CHAT_OPTIONS = {"temperature": 0.2, "num_ctx": 4096, "num_predict": 400}
# Intervention sheet: 6 sources and up to 3 written sections need a longer answer.
INTERVENTION_TOP_K = 6
INTERVENTION_CHAT_OPTIONS = {"temperature": 0.2, "num_ctx": 4096, "num_predict": 700}
EXCERPT_CHARS = 400                  # source excerpt shown to users so they can verify the answer
