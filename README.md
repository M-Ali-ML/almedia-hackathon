# AudiTrace

AudiTrace is an evidence-led fraud analysis MVP for accounting dossiers. Upload a GDPdU ZIP to identify suspicious journal entries and control failures, inspect source-linked findings, and ask follow-up questions in chat.

## Run locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22+, and an OpenAI API key.

### 1. Backend

```bash
cp backend/.env.example backend/.env
# Add OPENAI_API_KEY to backend/.env

cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## How it works

1. The backend extracts and normalizes ZIP contents, including TXT/CSV, Excel, PDF, and Word files, into DuckDB. Each source row receives a traceable `_row_id`.
2. Pre-analysis extracts company policies, terminology, and document relationships.
3. Deterministic Journal Entry Testing checks (K1–K7) generate fraud candidates covering vendor, authorization, cut-off, threshold, amount, and timing anomalies.
4. An LLM auditor investigates candidates with read-only SQL and document tools, searches for counter-evidence, and produces concise findings with verified source citations.
5. The React UI displays findings, evidence-strength scoring, source files, pre-analysis context, and finding-scoped AI chat.

## Technology

- **Backend:** Python, FastAPI, Pydantic AI, DuckDB, pandas
- **Document ingestion:** openpyxl, pypdf, python-docx
- **AI:** OpenAI Responses API through Pydantic AI; configurable with `AUDITOR_MODEL`
- **Frontend:** React, TypeScript, Vite, Tailwind CSS
- **Streaming chat:** AG-UI over server-sent events

## Checks

```bash
cd frontend && npm run build && npm run lint
cd backend && uv run python scripts/smoke_test.py [optional-dossier.zip]
```
