# RAG corpus

Documents the THNIYETNA assistant (`POST /assistant/ask`) answers from. Everything in this
folder except this README is ignored by git: the files are not versioned.
The project docs (`docs/**/*.md`) are indexed too, without being copied here.

## What to put here
- Road maintenance and traffic guides, technical circulars, procedures, and repair methods (potholes,
  diversions, winter maintenance, signage).
- Formats: `.pdf` **with a text layer**, `.md`, `.txt`. Scanned PDFs without OCR have no extractable
  text. Ingestion reports them and skips them, so OCR them first.
- Prefer French sources: the assistant answers in French.

## Naming convention
`<source>_<sujet>_<année>.<ext>`, lowercase, words separated by hyphens, no spaces or accents.
For example: `<organisme>_nids-de-poule-reparation_2014.pdf`, `<organisme>_guide-deviations_2019.pdf`
(`<organisme>` = publisher abbreviation). Existing files may keep their original names.
Sub-folders per theme are allowed (`entretien/`, `signalisation/`). The PDF metadata title, or the file
name when there is none, is shown as the source title in answers.

## Indexing
```powershell
docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 exec api python -m rag.ingest
```
Unchanged files (same sha256) are skipped; a modified file is re-indexed. To index a single file, run
`... exec api python -m rag.ingest --path /data/rag/corpus/<fichier>.pdf`.
