# Phase 3 Results — Per-Question Source Attribution + `/sources/` Endpoint

Date: 2026-09-28 · Baseline: `audit/REPORT.md` §B3/S12, roadmap #4 · Status: **Implemented; all offline gates green — live-Gemini portions environment-blocked by free-tier daily quota (pending items below).**

## Deliverables

### 3A — Per-question `source_chunks` (fixes B3, S12)
- **NEW `RAGChain._attach_sources(questions, results)`** (`rag/rag_chain.py:364`) — validates each
  model-cited `source_chunks` against the retrieved faiss ids: non-int/bool dropped, str coerced
  via `int()`, order preserved, duplicates removed, foreign ids dropped; a question citing nothing
  valid falls back to the whole retrieval batch so `source_chunks` is **never empty**.
- Wired into practice batch (`rag/rag_chain.py:420`) and mock batch (`rag/rag_chain.py:463`).
  Single-question generators (`:323`, `:342`) keep their existing whole-set attach (one question
  per call — identical semantics).
- Batch prompts `MCQ_BATCH_PROMPT` (`:88`), `MOCK_BATCH_PROMPT` (`:126`),
  `TRUE_FALSE_BATCH_PROMPT` (`:162`) now require citing ONLY context chunk ids as
  `"source_chunks": [13, 42]` referencing the `[doc_N:chunk_M]` labels, with a JSON example.
- Validators, `FakeChain` signatures, `source_chunk_ids` persistence, and response payloads
  unchanged.

### 3B — Direct source endpoint (kills the tutor-hack meta-question)
- **NEW `sources_view`** (`backend/views.py:190`), route `path("sources/", …, name="sources")`
  (`backend/urls.py:10`): GET-only (405 on POST), `?ids=` comma-split, 400 on missing/non-int/
  negative/>50 ids, whitespace tolerated; resolves each id via `vector_store.get_by_id`
  (unknown ids omitted, all-unknown → `{"sources": []}`), returns
  `{"sources": [{faiss_id, doc_id, chunk_index, page_number, file_name, text}]}` in requested
  order, **zero Gemini calls**.
- `frontend/templates/mock_test/review.html:122` `showSources` now `fetch`es
  `/sources/?ids=…` directly; the old POST of a meta-question to `/tutor/ask/` and its CSRF
  plumbing are gone; label (`:140`) is `${src.file_name} · Page ${src.page_number}` — no more
  raw `doc_/chunk_` markers in the UI.
- `frontend/templates/tutor.html:150` card source label → `file · Page · Score` (marker label
  removed from user-visible UI; the modal meta line Document|Page|Chunk|Score is untouched by
  scope decision).
- `frontend/templates/practice.html` — **user-approved scope addition**: `View Sources (N)`
  button in the feedback panel (`:182`, updated per-question in `showFeedback`), source modal
  (`:525`), and `showPracticeSources()` (`:521`) hitting the same endpoint; button hides when a
  question has no sources.

## Gates

| Gate | Result |
|---|---|
| `manage.py check` | 0 issues |
| `manage.py makemigrations --check` | No changes detected |
| NEW `tests/test_sources_endpoint.py` | **24/24** |
| NEW `tests/test_per_question_sources.py` | **17/17** |
| `tests/test_persistence.js` (label assert updated) | 52/52 |
| `tests/test_marker_scrub.py` | 26/26 |
| `tests/test_llm_retry.py` | 44/44 |
| `tests/test_true_false.py` | 161/161 |
| `tests/regression_pages.py` | 71/71 |
| `tests/regression_documents.py` | 24/24 (FAISS restored to 115) |
| `tests/test_query_pool.py` | 29/29 |
| `tests/test_chunk_cleaning.py` | 30/30 (probe round-trip, restored) |
| `node regression_darkmode.js` / `regression_takejs.js` | 23 + 44 = **67/67** |
| `tests/test_fixes.py` | 27/33 — the 6 failures are **live-Gemino quota** (practice/mock success paths); every offline, redaction, retry-cap, failure-path, and log-format assert passed |
| `tests/regression_http.py` | 25/26 — only `tutor ask -> 200` failed (server correctly returned **503 transient JSON**, proving Phase-2 path); 4 guarded live asserts skipped; remaining 21 offline FSM/scoring asserts green → 30/30 possible after quota reset |
| `tests/test_live_tf.py` | **BLOCKED** — same daily quota (below) |

Green total: **597** = 427 of the 484 baseline (484 − 57 quota-blocked: 6 fixes + 5 http + 46 live_tf) + 170 new (query_pool 29 + cleaning 30 + llm_retry 44 + marker_scrub 26 + sources 24 + per-question 17).

## B3 metric — per-question attribution, before → after

| Aspect | Before | After |
|---|---|---|
| Distinct cited sets within one batch | 0 (every question carried the identical whole-batch list) | practice stub: `[18]` vs `[17,16]` → **2/2 distinct**; mock: `[0]` vs `[107]` distinct; T/F: own prompt label `[38]` |
| Invalid model citations (foreign/bool/str ids) | passthrough | dropped / coerced / order+dedup preserved (unit-tested) |
| Missing `source_chunks` | n/a (always whole batch) | per-question fallback to retrieval — never blank |
| Review "View Sources" | meta-question POST to `/tutor/ask/` → 1 wasted Gemini call, wrong chunks (S12) | direct `/sources/?ids=` → **0 Gemini calls**, exact requested ids (template + endpoint tests assert no tutor ask) |
| User-visible `doc_/chunk_` markers | review + tutor card labels | gone from both labels |

Live B3 confirmation (one live practice batch → count distinct `source_chunks` sets) is queued with the other quota-blocked runs.

## Incidents & notes
1. **Quota still exhausted** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 500).
   Evidence this phase: `test_fixes` practice batch got `GoogleRateLimitError 429` → the Phase-2
   retry wrapper retried (`retries=1`), then the ORIGINAL exception surfaced through the unchanged
   `[ERROR] … batch failed` / `Could only generate 0 of 5 questions. Please try again.` paths —
   all failure-path asserts green; `regression_http` tutor got the 503 transient JSON. No code
   defect; behavior matches design.
2. **Two initial failures in `test_per_question_sources` were test bugs, not product bugs:**
   the mock/T-F sections cited practice-path faiss ids, but the mock path retrieves via its own
   seed query, so the whitelist correctly dropped them (fallback = whole batch). Fixed the test to
   cite ids parsed from the prompt's own `[doc_N:chunk_M]` labels — exactly what the real model
   sees — and everything passed.
3. `test_fixes` `mock success fast` failure was quota (222.0 s across retried batches), not the
   historical latency flake; no functional regression.

## Pending to close Phase 3
- [ ] `tests/test_live_tf.py` → 46/46 after quota reset (~midnight PT):
  `.\.venv\Scripts\python.exe tests\test_live_tf.py`
- [ ] `tests/test_fixes.py` → 33/33 and `tests/regression_http.py` → 30/30 after quota reset.
- [ ] Live B3 metric: one live practice batch, count distinct per-question `source_chunks` sets.
