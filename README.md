# FinSight AI

**Your autonomous AI financial research analyst.**

An autonomous multi-agent, agentic RAG engine for financial analytics.
Upload annual reports, quarterly filings, SEC documents, and earnings
releases; ask complex analytical questions in natural language; get back a
cited, calculated, multi-agent-produced research report — not a "chat with
PDF" toy.

> **Status:** All 16 build phases complete. See [docs/PHASES.md](docs/PHASES.md)
> for what was built in each phase, the reasoning behind it, and honestly-
> flagged limitations (e.g. which tests need real Postgres/Redis and haven't
> been run against them in this dev environment).

---

## Why this exists

Most "chat with your PDF" projects are a single retrieval call feeding a
single LLM prompt. FinSight AI demonstrates what a *production* financial
research system looks like instead:

- **Real multi-agent orchestration** — a supervisor routes work to
  specialized agents (retrieval, financial extraction, calculation,
  comparison, report generation) and only invokes the agents a given
  question actually needs — extraction only runs if retrieval found
  evidence, calculation only if the query asked for one, comparison only
  for multi-company questions. Watch it happen live in the Research page's
  agent trace panel.
- **Calculations run in Python, never in the LLM's head.** CAGR, YoY growth,
  margins, ratios — computed deterministically by `app/services/calculations.py`,
  with the LLM responsible only for *deciding what to calculate*.
- **Hybrid retrieval** — dense (pgvector cosine similarity) + sparse
  (Postgres full-text search) combined via a configurable weighted fusion,
  then reranked by a cross-encoder — not just nearest-neighbor lookup.
- **Grounded generation** — every factual claim traces back to a source
  document and page, with clickable citations. When the evidence isn't
  there, the system says so explicitly instead of guessing.
- **Runs with zero API keys.** The default LLM provider is a mock (it
  never fabricates content — see [docs/PHASES.md](docs/PHASES.md)) and
  embeddings/reranking run locally via Hugging Face. Point `LLM_PROVIDER`
  at OpenAI, Anthropic, or a local Ollama server for real generation — one
  env var, no code changes.

## Architecture

```mermaid
flowchart TD
    User --> Frontend
    Frontend -->|REST + SSE| FastAPI

    FastAPI --> Supervisor

    Supervisor --> RetrievalAgent[Retrieval Agent]
    Supervisor --> ExtractionAgent[Financial Extraction Agent]
    Supervisor --> CalculationAgent[Calculation Agent]
    Supervisor --> ComparisonAgent[Comparison Agent]
    Supervisor --> ReportAgent[Report Generation Agent]

    RetrievalAgent --> HybridSearch[Hybrid Search + Reranker]
    HybridSearch --> PostgreSQL[(PostgreSQL)]
    HybridSearch --> PGVector[(pgvector)]

    ExtractionAgent --> FinancialMetrics[(financial_metrics)]
    CalculationAgent --> PythonTools[Deterministic Python Tools]
    ReportAgent --> LLM[LLM Provider\nOpenAI / Anthropic / Ollama / mock]

    FastAPI --> Redis[(Redis: cache + rate limit)]

    DocumentUpload[Document Upload] -->|queues job| Redis
    Redis --> IngestionWorker[Ingestion Worker]
    IngestionWorker --> PDFParser[Parser]
    PDFParser --> Chunker
    Chunker --> EmbeddingService[Embedding Service]
    EmbeddingService --> PGVector

    ReportAgent --> Frontend
```

## Multi-agent architecture

```text
User query
    │
    ▼
Supervisor ──── Query Understanding (companies, metrics, years, operations)
    │
    ▼
Retrieval Agent ──── hybrid search (dense + sparse) per company, CONCURRENTLY ──── rerank
    │  (skipped if nothing to search for; only runs when evidence exists downstream)
    ▼
Financial Extraction Agent ──── regex/keyword extraction of dated (metric, value) pairs
    │  (only if evidence was found)
    ▼
Calculation Agent ──── CAGR / growth / margin via app/services/calculations.py
    │  (only if the query asked for a calculation AND there's data to compute over)
    ▼
Comparison Agent ──── ranks companies by result, phrases the finding
    │  (only for 2+ company queries)
    ▼
Report Agent ──── source-grounded synthesis, citations, confidence
    │  (LLM never called if there's no evidence — fixed "insufficient evidence" response)
    ▼
Supervisor ──── persists Analysis + full agent trace
    │
    ▼
Answer (streamed live to the frontend via SSE)
```

Each agent is a plain async function operating on a shared `ResearchState`
(`backend/app/agents/state.py`) — not a graph-runtime framework. A single
agent failing doesn't take down the request: its trace records the failure
and the supervisor continues with whatever it has, degrading to
"insufficient evidence" rather than a 500 if nothing usable comes out the
other end.

## RAG pipeline

```text
Upload → Parse (PDF/HTML/TXT/MD) → Clean → Structure-aware Chunk
       → Embed (Hugging Face, local) → Store (pgvector) → Indexed
```

Runs entirely in a background worker (`backend/app/workers/main.py`)
consuming a Redis job queue — the upload endpoint returns as soon as the
file is saved, never blocking on parsing. Chunking tracks section headings
and page numbers so every chunk (and every citation built from it) carries
real provenance, not just raw text.

Retrieval: `hybrid_search()` runs dense (pgvector `<=>` cosine distance,
HNSW-indexed) and sparse (Postgres full-text, `ts_rank_cd`, GIN-indexed)
search concurrently, min-max normalizes both score sets, and fuses them —
`FinalScore = α·DenseScore + (1-α)·SparseScore` (`HYBRID_SEARCH_ALPHA`,
configurable) — before a cross-encoder reranks the pooled candidates.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend framework | FastAPI + Pydantic | async-first, typed request/response schemas, auto-generated OpenAPI |
| Database | PostgreSQL 16 + pgvector | one database for relational + vector data — no separate vector DB to operate |
| Cache / queue | Redis | query/retrieval caching, ingestion job queue, rate limiting, cache-hit stats |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic | typed async models, reviewable schema migrations |
| Embeddings | Hugging Face `sentence-transformers` (`BAAI/bge-small-en-v1.5` by default) | runs locally (CPU), no API key required to index or search |
| Reranker | Hugging Face `cross-encoder/ms-marco-MiniLM-L-6-v2` | jointly scores (query, chunk) pairs over the hybrid search candidate pool |
| LLM | Provider-agnostic abstraction (OpenAI-compatible / Anthropic / Ollama / mock) | never locks the project to one vendor; `mock` runs with zero keys |
| Frontend | Next.js 16 (App Router) + TypeScript + Tailwind v4 | modern SSR/streaming-capable React |
| Data fetching | TanStack Query | caching, polling, mutation state |
| Charts | Recharts | financial time-series/comparison visualizations |
| Containerization | Docker + Docker Compose | one command brings up the full stack |
| Testing | pytest (backend), Vitest + React Testing Library (frontend) | unit + integration coverage on both sides |

## Project structure

```text
finsight-ai/
├── frontend/
│   ├── app/
│   │   ├── (app)/             dashboard, documents, companies, research, admin — behind the nav shell
│   │   └── page.tsx           redirects to /dashboard
│   ├── components/
│   │   ├── ui/                 hand-rolled primitives (button/card/badge/table/modal/tabs)
│   │   ├── layout/              sidebar, topbar, app shell
│   │   ├── dashboard/ documents/ companies/ research/
│   │   └── providers/           TanStack Query provider
│   ├── lib/                     api-client.ts (typed fetch + SSE), utils.ts
│   └── types/                   API type mirrors of the backend Pydantic schemas
│
├── backend/
│   ├── app/
│   │   ├── api/routes/          thin route handlers (documents, companies, analysis, metrics, dashboard, health)
│   │   ├── agents/               supervisor + retrieval/extraction/calculation/comparison/report agents
│   │   ├── core/                 config, logging, redis, rate limiting, exceptions
│   │   ├── db/                   SQLAlchemy engine/session/base + portable GUID type
│   │   ├── models/                users, companies, documents, document_chunks, analyses, agent_runs, financial_metrics
│   │   ├── schemas/               Pydantic request/response schemas
│   │   ├── services/              document/analysis/metrics/dashboard/cache services + calculations.py
│   │   ├── rag/
│   │   │   ├── ingestion/          loader, parser, cleaner, chunker, metadata_extractor, pipeline
│   │   │   ├── embeddings/          EmbeddingService abstraction + Hugging Face backend
│   │   │   ├── retrieval/           vector store, hybrid search, reranker
│   │   │   └── llm/                 LLMProvider abstraction + OpenAI/Anthropic/mock backends
│   │   ├── workers/                background ingestion consumer
│   │   └── main.py                 FastAPI entrypoint
│   ├── tests/                     80 pytest tests (SQLite for portable models, Postgres-only fixtures skip gracefully)
│   ├── alembic/                    4 migrations
│   └── requirements.txt
│
├── docker-compose.yml              postgres, redis, backend, worker, frontend
├── .env.example
├── README.md
└── docs/
    └── PHASES.md                   what was built in each phase, and why
```

## Getting started

### Option A — Docker Compose (recommended)

Requires Docker Desktop (or the Docker Engine + Compose plugin).

```bash
cp .env.example .env          # edit if you want a real LLM provider — "mock" works out of the box
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/api/docs
- Health check: http://localhost:8000/api/health

Migrations run automatically on backend container startup. **First build
takes several minutes** — it downloads a CPU-only PyTorch wheel (~200MB)
and, on first use, two small Hugging Face models (~200MB combined,
cached in a named volume afterward so this only happens once).

### Option B — run natively (for backend/frontend development)

**Backend** — requires Python 3.12+, and a local Postgres (with the
`vector` extension available) and Redis, or point `DATABASE_URL`/`REDIS_URL`
at running containers:

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend** — requires Node.js 20.9+:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

## Testing

```bash
# Backend — runs fully offline; tests needing real Postgres/Redis skip
# automatically with a clear reason if that infra isn't available
cd backend && pytest

# Backend, including the Postgres-only tests (pgvector/full-text search,
# the full agent pipeline end to end): point at a disposable database
docker compose up -d postgres redis
TEST_DATABASE_URL=postgresql+asyncpg://finsight:finsight@localhost:5432/finsight_test pytest

# Frontend
cd frontend && npm test        # Vitest + React Testing Library
npm run lint
npm run build                  # also runs the TypeScript compiler
```

## Environment variables

See [`.env.example`](.env.example) for the full annotated list. Highlights:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` / `DATABASE_URL_SYNC` | async (asyncpg) / sync (psycopg, used by Alembic) Postgres connection strings |
| `REDIS_URL` | Redis connection string |
| `LLM_PROVIDER` | `openai` \| `anthropic` \| `ollama` \| `mock` — see `app/rag/llm` |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | provider credentials/target — never hardcoded, never committed |
| `EMBEDDING_MODEL_NAME` | Hugging Face embedding model used for indexing + retrieval (runs locally) |
| `RERANKER_MODEL_NAME` / `RERANKER_ENABLED` | cross-encoder reranker model; disable to save CPU/latency |
| `HYBRID_SEARCH_ALPHA` | weight on dense vs. sparse retrieval score, `[0,1]` |
| `RETRIEVAL_TOP_K` / `RERANK_TOP_N` | candidate pool size / final reranked result count |
| `REDIS_CACHE_TTL_SECONDS` / `REDIS_RATE_LIMIT_PER_MINUTE` | cache TTL and per-IP rate limit |
| `MAX_UPLOAD_MB` | upload size limit enforced by the API |

No API key is required to run the system end to end: `LLM_PROVIDER=mock`
(the default) and locally-run Hugging Face embeddings/reranking mean
ingestion, retrieval, calculation, and comparison all work with zero
external accounts. Plugging in a real LLM provider changes only the
executive-summary phrasing quality — retrieval, extraction, and
calculation are already fully functional either way.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/api/documents/upload` | upload a document; returns immediately, processing happens in the worker |
| GET | `/api/documents` | list documents (search, type filter, pagination) |
| GET | `/api/documents/{id}` | document detail incl. processing status |
| DELETE | `/api/documents/{id}` | delete a document + its chunks |
| GET | `/api/companies` / `/api/companies/{id}` | company list/detail |
| GET | `/api/companies/{id}/metrics` | per-metric time series for that company's charts |
| POST | `/api/analyze` | run the full agent pipeline synchronously; returns the persisted analysis + trace |
| POST | `/api/query` | same pipeline, streamed as Server-Sent Events (live agent trace) |
| GET | `/api/analyses` / `/api/analyses/{id}` | review past analyses |
| GET | `/api/metrics` | browse extracted `financial_metrics` |
| GET | `/api/dashboard/stats` | counts, cache hit rate, avg latency, recent activity |
| GET | `/api/health` | Postgres + Redis health, per-component |
| GET | `/api/docs` | interactive OpenAPI docs |

## Example queries

- "Compare Apple's and Microsoft's revenue growth from 2022 to 2025."
- "Calculate Microsoft's 3-year revenue CAGR."
- "Compare the net income margins of Amazon and Walmart."
- "Summarize the major risks mentioned in the latest annual report."
- "What was Apple's revenue in 2025?"

## Performance considerations

- Async SQLAlchemy + pooled connections keep the API responsive under
  concurrent load; expensive work (PDF parsing, embedding generation,
  agent workflows) runs in a separate worker process, never inline in a
  request handler.
- Multi-company retrieval runs concurrently via `asyncio.gather`, not
  sequentially — see the Retrieval Agent.
- Redis caches hybrid search results (`retrieval:{hash}`) with a TTL, and
  degrades to "always miss" rather than failing the request if Redis is
  unreachable — same pattern for rate limiting.
- Embedding/reranker models load lazily (first use, not process startup)
  and run off the event loop via `asyncio.to_thread`.

## Known limitations

Documented in detail in [docs/PHASES.md](docs/PHASES.md), summarized here:

- **Postgres-only tests weren't run against a live Postgres in this dev
  environment** (no Docker available) — they're believed correct and
  exercise real pgvector/full-text SQL, but verify with
  `docker compose up -d postgres redis && TEST_DATABASE_URL=... pytest`
  before trusting them blindly.
- **Cross-company metric comparison assumes matching units** — no
  automatic billions/millions normalization across two companies' source
  documents yet.
- **Citations open a structured source-detail modal, not a rendered PDF
  page** — full PDF.js-style viewing with highlighted spans needs
  per-chunk bounding boxes, which the current text-only extraction doesn't
  capture.
- **No authentication/authorization** — `users`/`analyses.user_id` exist in
  the schema for when it's added, but there's no login flow today.
- **Docker containers run as root** — evaluated and deliberately deferred
  rather than shipped half-verified (see `backend/Dockerfile`).

## Future improvements

- Real LLM-based query understanding/extraction as an *enhancement* layered
  on the current deterministic path (which stays as the reliable fallback).
- Cross-company unit normalization in the Comparison Agent.
- Full PDF.js document viewer with highlighted source spans.
- Authentication and per-user analysis history.
- Horizontal worker scaling (the Redis queue already supports multiple
  consumers — just add `docker compose up --scale worker=3`).
- Non-root Docker containers, verified against real Docker.
