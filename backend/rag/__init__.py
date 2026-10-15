"""RAG assistant: document ingestion, hybrid retrieval (pgvector + full text) and grounded answers.

LLM and embeddings are served by Ollama on the host; nothing heavy runs inside the API image.
"""
