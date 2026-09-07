# Build Phases

FinSight AI is built incrementally rather than all at once — each phase adds
one working, testable layer. This file tracks status so it's obvious what
exists today vs. what's planned.

| # | Phase | Status |
|---|-------|--------|
| 1 | Project setup + Docker + PostgreSQL + Redis | ✅ done |
| 2 | Document upload + PDF parsing | ✅ done |
| 3 | Chunking + embeddings + pgvector | ✅ done |
| 4 | Semantic retrieval | ✅ done (built alongside Phase 3 — see below) |
| 5 | Hybrid search + reranking | ✅ done (built alongside Phase 3 — see below) |
| 6 | Basic RAG question answering | ✅ done (delivered as part of the full agent pipeline — see below) |
| 7 | Supervisor agent | ✅ done |
| 8 | Specialized agents (retrieval/extraction/comparison/report) | ✅ done |
| 9 | Python calculation tools | ✅ done |
| 10 | Async parallel agent execution | ✅ done |
| 11 | Redis caching | ✅ done |
| 12 | Frontend dashboard | ✅ done |
| 13 | Financial charts + citations | ✅ done (citations are structured + clickable; full PDF-page rendering is scoped down — see below) |
| 14 | Agent observability | ✅ done |
| 15 | Testing + optimization | ✅ done (backend + frontend suites; see Testing in README) |
| 16 | Dockerized production setup | ✅ done |

## Phase 1 — what was built

**Goal:** a working skeleton that proves the infrastructure choices out —
FastAPI, async SQLAlchemy, Postgres+pgvector, Redis, a separate worker
process, and a Next.js frontend — all wired together and runnable with one
command, before any domain logic exists.

**Backend** (`backend/`)
- `app/core/config.py` — typed, env-driven settings (`pydantic-settings`).
  Includes placeholders for later phases (LLM provider, embedding model,
  hybrid search alpha, chunking) so those phases add behavior, not new
  plumbing.
- `app/core/logging.py` — structured logging (structlog), JSON in
  non-local envs, colorized console in dev.
- `app/core/redis.py` — shared async Redis connection pool.
- `app/db/session.py` — async SQLAlchemy engine + pooled session factory,
  `get_db()` FastAPI dependency, `session_scope()` for use outside requests
  (workers, scripts).
- `app/db/base.py` — declarative `Base` + `UUIDPrimaryKeyMixin` /
  `TimestampMixin` every future model will use.
- `app/api/routes/health.py` — `GET /api/health`, checks Postgres + Redis
  independently and reports per-component status without ever raising —
  this backs both container healthchecks and the future admin/monitoring
  page (Section 26).
- `app/workers/main.py` — the worker process entrypoint. Currently an idle
  heartbeat loop that proves the process boots and can reach Postgres +
  Redis; Phase 2/10 replace the loop body with a real job consumer.
- `alembic/` — migration setup against the *sync* DB URL (Alembic doesn't
  drive an event loop); migration `0001` enables the `vector`, `pg_trgm`,
  and `unaccent` Postgres extensions.
- `tests/test_health.py` — verifies the health endpoint never 500s even
  with no live Postgres/Redis (degrades to per-component `error` instead).

**Frontend** (`frontend/`)
- Next.js 16 (App Router) + TypeScript + Tailwind v4, scaffolded via
  `create-next-app`.
- `next.config.ts` sets `output: "standalone"` for a slim Docker image.
- A minimal landing page (`app/page.tsx`) with a live `SystemStatus`
  component that polls `GET /api/health` — this is the first end-to-end
  proof that frontend → backend → Postgres/Redis is wired correctly. The
  real dashboard/documents/companies/research pages arrive in Phase 12+.

**Infra**
- `docker-compose.yml` — five services: `postgres` (pgvector/pgvector:pg16),
  `redis`, `backend`, `worker`, `frontend`. Postgres/Redis have healthchecks;
  backend/worker wait on those via `depends_on: condition: service_healthy`.
- `backend/entrypoint.sh` — waits for Postgres, runs `alembic upgrade head`,
  then execs the real command. Only the API container runs migrations
  (`entrypoint.worker.sh` just waits) so two containers never race to apply
  them concurrently at boot.
- `.env.example` (root) and `frontend/.env.example` — every configurable
  value, no real secrets, `LLM_PROVIDER=mock` by default so the app runs
  with zero external API keys.

## Phase 2 — what was built

**Goal:** upload a real financial document and watch it move through the
pipeline asynchronously, with the API never blocking on parsing.

**Backend**
- `app/models/{user,company,document,enums}.py` — the `users`, `companies`,
  `documents` tables (Section 20). `app/db/types.py` adds a portable `GUID`
  type so the same models run against Postgres in production and SQLite in
  tests (Section 30) — no live Postgres needed to run the suite.
- `alembic/versions/0002_*.py` — creates those tables + the
  `document_type`/`document_status` Postgres enums.
- `app/rag/ingestion/{document_loader,document_parser,text_cleaner}.py` —
  the modular pipeline stages Section 5 asks for: validate + save the
  upload, extract text (PDF via `pypdf`, HTML via `BeautifulSoup`, TXT/MD
  as-is), then normalize it (de-hyphenate, collapse whitespace).
- `app/services/job_queue.py` — a Redis list used as a FIFO job queue
  (RPUSH/BLPOP) plus a Redis hash for task status. Deliberately simpler
  than Celery/arq — one job type, at-least-once delivery is enough.
- `app/rag/ingestion/pipeline.py` — `process_document()`, the single
  coordinator that owns a document's status transitions
  (`uploaded → parsing → chunking → ...`), run only from the worker.
- `app/workers/main.py` — now a real consumer: blocks on the ingestion
  queue and runs each job through the pipeline, instead of idling.
- `POST /api/documents/upload`, `GET /api/documents`, `GET
  /api/documents/{id}`, `DELETE /api/documents/{id}`, `GET /api/companies`,
  `GET /api/companies/{id}` — upload returns as soon as the file is saved
  and the job is queued, never waiting on parsing.
- `app/core/exceptions.py` + a FastAPI exception handler — every domain
  error (unsupported file type, oversized file, empty/corrupted document,
  not found) becomes a consistent `{"error": {"code", "message"}}` body
  instead of a generic 500 (Section 32).

**Update (Phase 3):** `process_document()` was extended in place with
chunking + embedding + indexing rather than adding a second pipeline
function — see below. A document's status now genuinely reaches `indexed`.

## Phases 3-5 — what was built

Chunking, embeddings, pgvector storage, dense retrieval, sparse retrieval,
hybrid fusion, and reranking are tightly coupled (a chunker with nowhere to
store output isn't testable; a vector store with no way to query it isn't
either), so they were built as one coherent pass rather than three
artificially separated diffs.

**Ingestion (`app/rag/ingestion/`)**
- `chunker.py` — structure-aware chunking: walks the document tracking the
  current section heading (heuristic: short, title-cased/all-caps lines
  with no trailing punctuation), then produces overlapping word-windows
  (a whitespace-based token proxy — swapping in a real tokenizer later
  only changes word-counting, not the windowing algorithm). Every chunk
  keeps its page number and section.
- `metadata_extractor.py` — pulls `year` out of a free-form reporting
  period string ("Q4 2025" -> 2025) for denormalization onto chunks.

**Models / migration**
- `app/models/document_chunk.py` + `alembic/versions/0003_*.py` —
  `document_chunks`: pgvector `Vector` column (HNSW index, cosine ops) for
  dense search, plus a functional GIN index over
  `to_tsvector('english', content)` for sparse search — no second mapped
  tsvector column needed. Denormalizes `company_id`/`document_type`/`year`
  onto every chunk so metadata filtering (Section 7) never needs a join.

**Embeddings (`app/rag/embeddings/`)**
- `base.py` — `EmbeddingService` Protocol every caller depends on.
- `huggingface.py` — real backend: `sentence-transformers` running
  `BAAI/bge-small-en-v1.5` locally (CPU, no API key). Lazily loaded
  (first call, not import time) and run via `asyncio.to_thread` so the
  blocking encode call never stalls the event loop.
- Tests use `tests/fakes.FakeEmbeddingService` (a deterministic hashed
  bag-of-words embedding) instead of downloading a model — Section 30.

**Retrieval (`app/rag/retrieval/`)**
- `vector_store.py` — `insert_chunks` + `dense_search`. Cosine similarity
  is computed by Postgres itself via pgvector's `<=>` operator against the
  HNSW index — `1 - cosine_distance` is exactly the textbook formula from
  Section 7, just evaluated in the database instead of Python.
- `hybrid_search.py` — `sparse_search` (Postgres full-text, `ts_rank_cd`)
  and `hybrid_search`, which runs dense + sparse concurrently
  (`asyncio.gather`), min-max normalizes both score sets to `[0,1]`, and
  fuses them: `FinalScore = alpha * DenseScore + (1-alpha) * SparseScore`
  (`HYBRID_SEARCH_ALPHA`, configurable).
- `reranker.py` — a cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
  re-scores hybrid search's top-N pool by jointly reading (query, chunk)
  pairs — more accurate than embedding/keyword scores alone, too slow to
  run over the whole corpus, so it only sees the already-narrowed
  candidates. `RERANKER_ENABLED=false` swaps in a no-op `IdentityReranker`.

**Pipeline** — `app/rag/ingestion/pipeline.py` now runs the full
`parsing -> chunking -> embedding -> indexed` lifecycle (previously stopped
at `chunking`); `app/services/indexing_service.py` is the chunk-embed-store
glue, injectable with a fake embedding service for tests.

**Testing note:** `document_chunks` uses Postgres-only types (pgvector
`Vector`, `JSONB`) that don't compile against SQLite, so it's excluded from
the SQLite table set the rest of the suite uses (`tests/conftest.py`).
Retrieval tests (`test_vector_store.py`, `test_hybrid_search.py`,
`test_indexing_service.py`) instead use a `pg_session` fixture that's
skipped unless `TEST_DATABASE_URL` points at a real Postgres — they were
written and are believed correct, but have not been run against a live
Postgres in this environment (no Docker available here). Run them with:
`docker compose up -d postgres && TEST_DATABASE_URL=postgresql+asyncpg://finsight:finsight@localhost:5432/finsight pytest`.

## Phases 6-11 — LLM abstraction, the multi-agent pipeline, calculations, caching

Basic RAG QA, the supervisor, all five specialized agents, deterministic
calculations, parallel retrieval, and Redis caching are one connected
system — a supervisor with nothing to route to isn't demonstrable, and
agents with no calculation tool or cache underneath aren't the real thing
— so, like Phases 3-5, they landed as one pass.

**LLM abstraction (`app/rag/llm/`)** — Section 9/35. `base.py` defines the
`LLMProvider` Protocol (`chat(messages, *, temperature, json_mode) ->
LLMResponse`); `providers/` has `openai_compatible.py` (OpenAI and anything
speaking the same protocol — Groq, Together, a local vLLM/Ollama endpoint),
`anthropic.py` (native Messages API), and `mock.py` — the default
(`LLM_PROVIDER=mock`), so the whole app runs with zero API keys. The mock
deliberately doesn't fake intelligence (returns `{}` for JSON calls, a
labeled placeholder otherwise) — see the Report Agent below for why that's
a feature, not a gap.

**Agents (`app/agents/`)** — plain async functions over a shared
`ResearchState` dataclass, not a graph-runtime framework (Section 36: avoid
unnecessary complexity where a framework wouldn't earn its keep at this
scale).
- `query_understanding.py` (Section 9) — regex/keyword extraction of
  companies (matched against the `companies` table), metrics, years (incl.
  "2022 to 2025" range expansion), requested operations (cagr/growth/
  margin/comparison/summary), and document types. Deterministic by design
  — Section 35 puts extraction/reasoning on the LLM's side of the line in
  general, but query parsing specifically benefits from being reliable
  regardless of which provider (including `mock`) is configured.
- `retrieval_agent.py` (Section 11) — resolves mentioned companies to IDs,
  runs `hybrid_search` **concurrently per company** via `asyncio.gather`
  (Section 31's worked example), reranks the pooled candidates, and caches
  the resulting evidence in Redis (`retrieval:{hash}`, Section 17) keyed by
  query+filters so a repeated question skips re-embedding and re-ranking
  entirely.
- `extraction_agent.py` (Section 12) — regex-based, not an LLM call (same
  reasoning as query understanding: auditable and provider-independent).
  Finds every value in a chunk carrying a currency/magnitude/percent
  signal (never a bare number — that's usually a year), attributes each to
  its nearest metric keyword, and pairs it with the nearest year **in
  either direction** — necessary for a single sentence like "$391B in
  fiscal 2025, up from $383B in fiscal 2024" to yield two dated data
  points instead of one, which is what CAGR needs. Successfully extracted
  metrics are persisted to `financial_metrics` (Section 20) so the Company
  Explorer's trend charts don't require re-running extraction.
- `calculation_agent.py` (Section 13) — groups extracted data points by
  (company, metric) and calls `app/services/calculations.py` — deterministic
  Python, never the LLM (Section 35's clearest requirement). Supports CAGR,
  YoY growth, average growth, percentage change, margin, ratio, difference,
  and percentage-point difference; every result carries its formula and
  inputs so the Report Agent can show its work.
- `comparison_agent.py` (Section 14) — only runs for multi-company
  queries; ranks companies by calculated result per metric and phrases the
  finding ("Microsoft's revenue CAGR (+14.9%) outpaced Apple's (+9.6%)...").
  Documented limitation: cross-company comparison assumes both companies'
  source documents report the metric in the same unit — no cross-unit
  normalization yet (see the module docstring).
- `report_agent.py` (Section 15/16) — if retrieval found nothing, the LLM
  is never called; the report is the fixed "insufficient evidence" message,
  verbatim. Otherwise the LLM gets ONLY the retrieved evidence text in its
  prompt (never "use your training knowledge"), and if it has nothing real
  to say (the mock provider, or an empty response from any provider), the
  executive summary falls back to a **deterministic template** built from
  the comparison insights / calculations / top evidence already computed —
  still fully grounded, just not LLM-phrased. Confidence is the average
  retrieval score, halved if a calculation was requested but couldn't be
  produced. Citations are structured (`Citation`: company, document id,
  filename, page — not just a display string) for the frontend's clickable
  source chips.
- `supervisor.py` (Section 10) — `stream_research()` is the single
  orchestration implementation (an async generator yielding a progress
  event after every agent); `run_research()` just drains it. Extraction
  only runs if retrieval found evidence; calculation only runs if the query
  asked for one AND there's data to compute over; comparison only runs for
  2+ companies. One agent failing doesn't take down the request — its
  trace records the failure and the supervisor continues with whatever it
  has.

**Persistence** — `app/models/analysis.py` (`analyses`, `agent_runs`) and
`financial_metric.py`. `app/services/analysis_service.py` serializes a
`ResearchState`'s report + full agent trace and persists it after every
`/api/analyze` or `/api/query` call.

**API** — `POST /api/analyze` (blocking, returns the persisted analysis
+trace), `POST /api/query` (Server-Sent Events: an `agent_status` frame per
finished agent, then one `final` frame with the report — Section 19/25),
`GET /api/analyses`, `GET /api/analyses/{id}`, `GET /api/metrics`, `GET
/api/companies/{id}/metrics`, `GET /api/dashboard/stats`.

**Caching (Section 17)** — `app/services/cache_service.py`: generic
`cache_get_json`/`cache_set_json` plus a running hit/miss counter Redis
key, surfaced in `/api/dashboard/stats`. Every cache call is wrapped to
degrade to "cache miss" / no-op on a Redis error (Section 32) rather than
failing the request — proven by `tests/test_cache_service.py` and by every
other test in the suite passing with no Redis running at all in this
environment.

**Rate limiting (Section 17/27)** — `app/core/rate_limit.py`, a fixed-window
Redis counter (`ratelimit:{ip}:{minute}`) as ASGI middleware on every
`/api/*` route; same degrade-on-Redis-outage behavior.

## Phases 12-14 — frontend dashboard, charts, citations, agent observability

Next.js 16 (App Router) + TypeScript, TanStack Query for data fetching,
Recharts for charts, a small hand-rolled component set (Button/Card/Badge/
Table/Modal/Tabs — Tailwind + `class-variance-authority`, in the spirit of
shadcn/ui without pulling in Radix for a project this size) instead of a
UI kit. Single committed dark theme (`app/globals.css`) — a financial
research tool is inherently a dark, data-dense "terminal" aesthetic
(Section 21), not something that needs light-mode parity.

- **`/dashboard`** — every number is read from `GET /api/dashboard/stats`
  (Section 40: no hardcoded demo data): document/company/embedding/analysis
  counts, a documents-by-status bar chart, cache hit rate, avg query
  latency, recent documents, recent research queries, and an "AI Market
  Intelligence" panel showing the most recently extracted `financial_metrics`
  rows.
- **`/documents`** — upload (modal form, Section 4's accepted types),
  search/filter by type, a status pipeline rail (`Uploaded → Parsing →
  Chunking → Embedding → Indexed`) that polls every 3s while anything is
  mid-pipeline, row-click detail modal, delete.
- **`/companies`** and **`/companies/[id]`** — company cards; the detail
  page charts every extracted metric's trend line (Recharts `LineChart`,
  Section 21/23) and lists that company's documents.
- **`/research`** — the main AI interface (Section 21). A question streams
  through `POST /api/query`'s SSE endpoint; the **agent trace panel**
  renders all six agents with live waiting/running/completed/failed status
  and per-agent timing, and marks any agent the supervisor decided not to
  run as visually "skipped" once the stream ends — the clearest way to
  *show*, not just claim, that the supervisor routes rather than always
  running everything (Section 10/25). The result renders the executive
  summary, key findings, a comparison table, a calculation bar chart, the
  calculations with their formulas, and clickable citation chips.
- **Citations (Section 24)**, scoped down: each chip opens a modal with the
  real structured source (company, exact filename, page number — from the
  backend's `Citation`, not a parsed string) and a link into the document
  library. This is deliberately not a full PDF.js-style page renderer with
  highlighted spans — that needs per-chunk bounding boxes, which today's
  text-only extraction doesn't capture. Tracked as a real next step, not
  hidden.
- **`/admin`** — Section 26's system monitoring, built from what's actually
  measured: `/api/health`'s per-component Postgres/Redis status plus
  `/api/dashboard/stats`'s counts/cache/latency/failed-document count.
  "Worker status" isn't a separate endpoint (there's no worker heartbeat
  today) — noted rather than faked.

## Phase 15 — testing

**Backend**: 80 passing tests (`pytest`) covering ingestion (loader/parser/
cleaner/chunker/metadata), embeddings (fake + real-service construction),
retrieval (vector store/hybrid search/reranker — Postgres-only, see below),
every agent individually plus one full-pipeline integration test, LLM
providers (mocked HTTP via `respx` — no real keys/network), calculations
(CAGR/growth/margin/etc., including the exact worked example from Section
13), the cache service's Redis-outage degradation, rate limiting, and every
API route. Tests needing real Postgres/Redis skip automatically (with a
clear reason) rather than failing when that infra isn't running — proven
in this environment, which has neither.

**Frontend**: Vitest + React Testing Library, 25 passing tests — utils
(currency/percent/duration formatting), the document status pipeline,
the agent trace panel's waiting/running/skipped logic, citation chips
(open/close, structured detail), the upload dialog (success and a
server-rejection error path), the dashboard page (real data rendering +
error state), and the research page (a mocked SSE stream end to end,
including clicking an example query).

## Phase 16 — Docker

`docker-compose.yml`'s five services (Phase 1) now do real work: `backend`/
`worker` share a `backend_hf_cache` volume for the downloaded embedding +
reranker model weights (so they aren't re-fetched on every `docker compose
up`), and `alembic upgrade head` runs automatically via `entrypoint.sh`
before the API starts. First build downloads a CPU-only PyTorch wheel
(~200MB) plus two small Hugging Face models on first run (~200MB combined)
— expect the first `docker compose up --build` to take several minutes;
subsequent runs are fast. Non-root containers were evaluated and
deliberately deferred (see the comment in `backend/Dockerfile`) rather than
shipped half-verified: without real Docker to test against here, getting
named-volume ownership wrong would silently break uploads or model
downloads, which is worse than staying root for now.

## Why this order

Postgres/Redis/Docker before any AI code so every later phase has a real
place to persist and cache against instead of building on mocks that get
thrown away. The worker process is separated from the API from the start
(Section 18) because retrofitting that split after ingestion logic already
lives in a request handler is much more disruptive than starting with it.
