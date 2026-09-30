# Phase 2 Results — Gemini Retry/Backoff + Citation-Marker Scrub

Date: 2026-09-27
Status: **Implemented; gates green except `test_live_tf` (46) — environment-blocked by Gemini free-tier daily quota (verified with probe evidence).**

## Deliverables

### 2A — Transient-error retry (`rag/llm_resilience.py`, NEW)
- `is_transient_llm_error(exc)` — strictly **type/attribute-based**, never message-based:
  - generic `Exception` (even with "503" in its text — the `BoomLLM` pattern) is **never** transient;
  - `google.genai.errors.APIError/ServerError` with code in {429,500,502,503,504};
  - `ConnectionError`/`TimeoutError`, `httpx` timeout/transport errors;
  - numeric `.status`/`.status_code`/`.code` attr in the retry set;
  - class-name MRO scan for `RateLimit`, `ResourceExhausted`, `ServiceUnavailable`, `Timeout`,
    `Connection`, etc. — this catches langchain's `GoogleRateLimitError` /
    `ModelRateLimitError` (found during a live 429 incident, see below).
- `invoke_with_retry(llm, prompt, sleep=, max_attempts=, base_delay=)`:
  total attempts = `GEMINI_MAX_RETRIES + 1`, exponential backoff `GEMINI_RETRY_BASE_DELAY × 2^n`,
  **re-raises the ORIGINAL exception** on exhaustion (keeps `[ERROR] … Exception: msg` and
  `Could only generate …` paths byte-compatible).
- `config/settings.py`: `GEMINI_MAX_RETRIES = 2`, `GEMINI_RETRY_BASE_DELAY = 1.0`
  (both env-overridable: `GEMINI_MAX_RETRIES`, `GEMINI_RETRY_BASE_DELAY`).
- `rag/rag_chain.py`: new `RAGChain._invoke(prompt)`; all 5 former `self.llm.invoke(prompt)`
  sites (tutor, single mcq, single mock, practice batch, mock batch) now route through it.
  `try/except` blocks and `[ERROR]` log formats untouched.
- `backend/views.py tutor_ask_view`: transient LLM errors → **503 JSON**;
  everything else → 500 JSON (original behavior).

### 2B — Citation-marker scrub (`rag/sanitize.py`, NEW)
- `scrub_citation_markers(text)` removes `[doc_N:chunk_M]`-style labels (the exact
  `_format_context` format), collapses stray whitespace and space-before-punctuation;
  clean text is returned byte-identical; non-strings pass through.
- `scrub_question(q)` touches only `question`/`explanation`/`topic`/`options.*` —
  never `source_chunks`/`correct`/`question_type`.
- Wired: (1) `batch_generation.run_generation` **before** `validate_question`
  → covers practice + mock MCQ/T-F in one choke point (a question scrubbed to
  empty is rejected by the unchanged validator and retried by existing logic);
  (2) `RAGChain.tutor_query` scrubs the tutor answer (approved scope extension).
- Validators intentionally unchanged.

## Gates

| Suite | Result |
|---|---|
| `manage.py check` | 0 issues |
| `manage.py makemigrations --check` | No changes |
| tests/test_llm_retry.py (NEW) | **44/44** |
| tests/test_marker_scrub.py (NEW) | **26/26** |
| tests/test_query_pool.py (P1) | 29/29 |
| tests/test_chunk_cleaning.py (P1) | 30/30 |
| tests/test_fixes.py | 33/33 (4th run; see latency note) |
| tests/test_true_false.py | 161/161 |
| tests/regression_pages.py | 71/71 |
| tests/regression_documents.py | 24/24 (FAISS restored to 115) |
| tests/regression_http.py | 30/30 (incl. live tutor + sources keys) |
| node test_persistence.js / regression_darkmode.js / regression_takejs.js | 52 + 23 + 44 = **119/119** |
| tests/test_live_tf.py | **BLOCKED** — Gemini 429 daily quota (below) |

Green total: **567** = 438 of the 484 baseline (484 − 46 pending) + 59 Phase-1 + 70 Phase-2.

### `test_live_tf` status
- First run: LIVE 1 (mcq 10) and LIVE 2 (true_false 10) **passed**; died at LIVE 3 when the
  free-tier quota (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 500) was hit —
  `GoogleRateLimitError: 429 RESOURCE_EXHAUSTED`.
- Verified environment-block: after a 180-second quiet period, a single probe call still
  returned 429 (`retryDelay` oscillated 56→49→5→47→56→43 s across attempts).
- **Resume (after quota reset, typically midnight PT):**
  `.\.venv\Scripts\python.exe tests\test_live_tf.py` → expect 46/46.
  No code changes needed; earlier live suites (test_fixes, regression_http) already pass.

## Incidents & notes
1. **Classifier gap found by production traffic:** live 429 raised
   `langchain_google_genai.chat_models.GoogleRateLimitError` (no numeric status attr), which the
   first classifier version missed. Fixed via the class-name MRO scan; +7 regression tests cover
   the real langchain error classes (`GoogleRateLimitError`, `ModelRateLimitError`,
   `ModelTimeoutError`, `GoogleInvalidRequestError`→not transient, `GoogleAPIError` 500/503).
2. **`mock success fast` (<60 s) latency flake:** failed 3× (438.4 s / 123.7 s / 93.6 s) purely
   from Gemini per-call latency (generation itself healthy: `retries=0`, valid 14/14 + 6/6),
   passed 4th run at 6.6 s. Protocol: rerun, not "fix" — same flake class as Phase 1.
   Phase 2 retry never triggered on those runs (no typed errors; backoff adds ≤3 s/call).
3. **Attempt-count locks preserved:** `BoomLLM` still `n == 2` (generic exceptions never
   retried; batch-level retry only). Typed-transient end-to-end: 6 attempts
   ((2 retries+1) × 2 batch attempts) with exact 500 message and `[ERROR]` line intact.
4. The one observed mid-suite transient (`GoogleRateLimitError`) confirmed the wiring works:
   per-call retries engaged, then the original exception surfaced through the unchanged
   `[ERROR] practice/mock … batch failed` path.

## Pending to close Phase 2
- [ ] `tests/test_live_tf.py` → 46/46 once Gemini quota resets.
