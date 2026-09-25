# Real-Data Test Plan

Validates FinSight AI end-to-end against real, current SEC 10-K filings
(not synthetic test fixtures) before moving toward auth/multi-user support.

## Test data

Real, current 10-K filings pulled live from SEC EDGAR (`data.sec.gov` /
`www.sec.gov/Archives`), not copied/redistributed — legitimate public
record, fetched fresh for this test run:

| Company | Form | Fiscal year end | Filed | Source |
|---|---|---|---|---|
| Apple | 10-K | 2025-09-27 | 2025-10-31 | accession 0000320193-25-000079 |
| Microsoft | 10-K | 2026-06-30 | 2026-07-29 | accession 0001193125-26-323660 |
| Amazon | 10-K | 2025-12-31 | 2026-02-06 | accession 0001018724-26-000004 |
| Walmart | 10-K | 2026-01-31 | 2026-03-13 | accession 0000104169-26-000055 |

Ground truth (verified directly from the raw filing before testing, so
extraction/calculation results can be checked against real numbers):
Apple FY2025 net sales $416,161M, FY2024 $391,035M, FY2023 $383,285M.

Format note: SEC 10-Ks are XBRL-tagged HTML, not clean PDFs — every number
in the financial statements is its own `<span>`, so plain tag-stripping
scrambles the visual row/column association between a value and its year
header. This is a real, expected stress test of the chunker/extraction
agent beyond what the hand-written unit-test sentences cover.

## Environment for this run

- `docker ps`: `finsight-postgres` (pgvector/pg16, port 5433), `finsight-redis` — both healthy, already running.
- Backend: `uvicorn app.main:app` (native, port 8000), `LLM_PROVIDER=mock`.
- Worker: `python -m app.workers.main` (native).
- Frontend: `npm run dev` (native, port 3000).

## Steps (maps to the 20 numbered checks requested)

1-3. Start Postgres/Redis (already running), backend, worker, frontend — done above.
4-10. Upload each filing via `POST /api/documents/upload`; poll `GET /api/documents/{id}` until `status=indexed` or `failed`; inspect `document_chunks`/`financial_metrics` directly via `psql` for chunk count, page numbers, embeddings non-null.
11-13. Direct retrieval check: call `hybrid_search`/rerank via a quick script against the indexed chunks for a known-answer query; inspect scores.
14-19. Run the 6 target queries via `POST /api/analyze` (full trace) and `POST /api/query` (SSE) for at least one; record agent trace, citations, calculations, confidence, latency.
20. Confirm the same result renders correctly through the actual frontend page (not just the API).

Results, failures, fixes, and the final report are recorded in
[`REAL_DATA_TEST_REPORT.md`](REAL_DATA_TEST_REPORT.md).
