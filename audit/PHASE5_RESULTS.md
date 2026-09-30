# Phase 5 Results — Tutor Source Filter (B8) + Retrieval Analytics (B10) + Display Scrub & txt Labels (B12)

Date: 2026-09-30 · Baseline: `audit/REPORT.md` §B8, §B10, §B12 · Plan items **8 + 9** · Status: **Implemented; all gates green — 782/782 (484 baseline + 298 new). All previously quota-blocked live runs completed (Gemini daily quota recovered 2026-09-30).**

## Deliverables

### 5A — B8: answer-supporting source filter (roadmap #8)
User decision: **backend source filter, no UI change** (tutor card / modal unchanged).
- **`rag/grounding.py`** — added `SOURCE_SUPPORT_THRESHOLD = 0.4` and
  `filter_supporting_results(answer_text, results, threshold, max_sources=3)`: keeps only
  retrieval results whose text covers ≥ 40% of the answer's content words (same
  normalization as `grounding_score`), ranked by coverage (stable), capped at **3**;
  when nothing qualifies (refusals), falls back to top-3 retrieval order so the payload
  is never empty.
- **`rag/rag_chain.py:297`** — `tutor_query` now builds `sources` from
  `supported = filter_supporting_results(answer, results)`; context/prompt/retrieval are
  untouched (the filter is display-side only) and the response payload keys are unchanged.
- Cost: pure string coverage over ≤ top_k results — no embed, no LLM.

### 5B — B10: retrieval analytics (roadmap #10)
- **NEW `rag/analytics.py`** — `log_retrieval(operation, scores, doc_ids, docs)` appends one
  JSONL record to `settings.BASE_DIR/logs/retrieval_analytics.jsonl`
  (`ts, operation, n, top1, scores` rounded to 6 dp, `doc_ids`, `docs`), thread-locked, and
  swallows every exception (analytics can never break retrieval).
- **`rag/rag_chain.py:265`** — `_retrieve_context(query, doc_ids, operation)` logs after
  every search; labels wired at all five call sites: `tutor`, `practice`
  (single + batch), `mock` (single + batch).
- **`.gitignore`** — added `logs/`.
- Scope (per §B10's own recommendation): **measure, don't gate** — no score threshold was
  introduced; the log backs a future calibration decision.
- Live log after this phase's batteries: **532 records** with operation labels.

### 5C — B12: legacy marker scrub + txt-aware page labels
- **`mock_test/mock_test.py` `get_attempt_result`** — now scrubs
  `question_text`, all four options, `explanation`, and `topic` through
  `scrub_citation_markers` before they reach the review view (single choke point; the only
  consumer is `mock_test_review_view`).
- **`frontend/templates/tutor.html`, `mock_test/review.html`, `practice.html`** — new
  `pageSuffix(src, sep)` helper: returns `` `${sep}${src.page_number}` `` for real pages and
  `''` for `.txt` files or missing pages. Card/modal labels are now
  `${src.file_name}${pageSuffix(src, ' · Page ')}` (tutor modal meta:
  `pageSuffix(src, ' | Page: ')`) — the literal ` · Page` no longer renders for txt.
- **`tests/test_sources_endpoint.py:87`** — tutor label lock updated to the pageSuffix form.

## Gates (Phase 5 full regression, all green)

| Gate | Result |
|---|---|
| `manage.py check` | 0 issues |
| `manage.py makemigrations --check` | No changes detected |
| NEW `tests/test_source_filter.py` | **18/18** |
| NEW `tests/test_analytics.py` | **24/24** |
| NEW `tests/test_display_scrub.py` | **29/29** |
| `tests/test_true_false.py` | 161/161 |
| `tests/regression_pages.py` | 71/71 |
| `tests/test_persistence.js` | 52/52 |
| `tests/test_query_pool.py` / `test_chunk_cleaning.py` | 29/29 + 30/30 |
| `tests/test_marker_scrub.py` / `test_llm_retry.py` | 26/26 + 44/44 |
| `tests/test_tutor_prompt.py` / `test_grounding.py` | 17/17 + 40/40 |
| `tests/test_sources_endpoint.py` / `test_per_question_sources.py` | 24/24 + 17/17 |
| `node regression_darkmode.js` / `regression_takejs.js` | 23 + 44 = 67/67 |
| `tests/regression_documents.py` | 24/24 |
| `tests/test_fixes.py` | **33/33** (live — quota recovered) |
| `tests/regression_http.py` | **30/30** (live) |
| `tests/test_live_tf.py` | **46/46** (live) |

Green total: **782/782** = 484 baseline (fully green, incl. every formerly quota-blocked
assert) + 298 new (P1 59 + P2 70 + P3 41 + P4 57 + P5 71).

## Live measurements (quota recovered — Phase 2–5 pendings all closed)

### Environment bootstrap (required before batteries)
The audit corpus docs A/B were absent (only doc13 in the DB), which made the first tutor
battery run invalid (65/65 refusals — retrieval could not reach Zephyr/Marigold content).
Fixed per the audit design: `audit/p1_setup.py` uploaded `AuditZephyr` (doc 34, 7 chunks)
and `AuditMarigold` (doc 35, 4 chunks) through the real endpoints → FAISS 115→126.
After all batteries: both docs deleted via the real `/delete/<id>/` endpoint (FAISS
126→115, media files removed), today's 15 battery mock tests + 15 attempts removed
(tests 89→74, attempts 82→67). Final state: docs=[13], chunks=115, FAISS 115 (all doc13),
doc13 file intact — and post-cleanup smoke 99/99 (sources 24 + per-question 17 +
query_pool 29 + display_scrub 29).

### Tutor + hallucination battery (65 GT) — ×3 repeats (B7 acceptance)

| Run | Grade | False refusals | Expected refusals | HTTP | Sources/answer | Non-pass detail |
|---|---|---|---|---|---|---|
| 1 | 64/65 | **0** | 14/14 | 65/65 ×200 | 1–3 (27×1, 15×2, 23×3) | T01 **warn** — correctly gives 4709 and contextualizes obsolete 4710 |
| 2 | 64/65 | **0** | 14/14 (H12 paraphrased the refusal: "does not contain any information…") | 65/65 ×200 | 1–3 | H12 regex miss — functionally a correct refusal |
| 3 | 64/65 | **0** | 14/14 (T31 declined then appended a tangential corpus fact) | 65/65 ×200 | 1–3 (28×1, 16×2, 21×3) | T31 used no refusal phrase |

- Baseline was **62/65 with 3 false refusals** (H14, H15, T47). After Phases 4+5:
  **0 false refusals in every repeat**, **0 wrong-fact hallucinations** (no answer ever
  asserts a `wrong_keyword`; contradicted premises H13–H15 / T32–T34 corrected with
  evidence in all runs) → B7 success criterion met.
- 195/195 tutor calls returned HTTP 200 (429s absorbed by the Phase-2 retry wrapper;
  3 calls per run took 35–47 s of backoff). Average latency ≈ 3.3–3.8 s.
- B8: sources per answer never exceeded 3 (filter active; refusals get the top-3 fallback).

### P4 practice battery (19 batches, 220 MCQs) — `grade_p4` (authoritative)
- valid **220/220**, grounded **220/220** (target ≥216) — Phase-4 loop held live.
- distinct cited faiss ids **94** (baseline 18; target ≥60); exact dups 0;
  global semantic dup pairs ≥0.85 = **69** (baseline 374; target ≤75).
- multi-doc citations: docs {13, 34, 35} all cited; topic=None multi batches citing ≥2 docs:
  **4/9 batches (44%)**, 12/105 questions — target ≥80% **not met** (MiniLM still skews to
  doc13 boilerplate even with doc-filtered rotation seeds).

### Live B3 metric (per-question attribution, one battery = 19 live batches)
- Distinct per-question `source_chunks` sets: **75 across 220 questions**; per-batch
  1–11 sets (single/easy/n=20 → 11/20, multi/hard/n=20 → 7/20).
- Baseline: exactly **1** set per batch (every question carried the whole batch list).
- Remaining equal-set batches are the designed fallback (model cited nothing valid) or
  genuinely shared citations — never a fixed whole-batch assignment.

### P5 mock grid (8 live tests, 170 questions)
- 8/8 exact 70/30 splits, 8/8 correct grading.
- distinct source sets per test **[5, 8, 12, 14, 3, 10, 7, 8]** — all ≥ ⌈N/5⌉ (baseline: 1 in all 8).
- distinct cited chunks per test **[15, 19, 30, 43, 15, 23, 15, 23]** — 50q test = **43** (baseline 5; target ≥15/20).
- fixed probe-5 overlap: **44/170 = 25.9%** (baseline 100%; target ≤20% — close miss).
- `doc_/chunk_` markers in stored explanations: **0/8 tests** (baseline 4).
- take-page "leaks": the scanner's bare `explanation` word matched question/option content
  in exactly the 5 flagged tests (1+2+11+1+1 occurrences) and in 0 unflagged tests; the
  template renders no explanation/topic fields → **real leaks 0**.

### Offline audits (no LLM)
- P2 retrieval: any-keyword hit@5 **51/51**; all-keyword 49/51 (known artifacts T06
  `8192` vs `8,192`, H04 arithmetic); MRR ≥0.67 every category.
- P8 index: near-dup pairs ≥0.90 **344 → 14** (target ≤10 — close miss), ≥0.97 **328 → 0**;
  all 126 vectors unit-norm (IP ≡ cosine, ranking unchanged).

## Before → after (Phase-5 scope)

| Metric | Baseline | After P5 | Target | Status |
|---|---|---|---|---|
| Tutor sources shown | all 5 retrieved (contaminated) | answer-supporting, **1–3**, ≥0.4 coverage (18/18 + live) | ≤3 relevant | ✅ |
| Tutor source-list Gemini waste (review modal) | 1 call per open (wrong ids) | **0 calls** (direct `/sources/`) | 0 | ✅ |
| Retrieval observability | none | JSONL log w/ operation+scores, **532 live records**, exceptions swallowed | logging, no gating | ✅ |
| `doc_/chunk_` markers in stored Q/E | 4 | **0** (practice 0/0 + mock 0×8) | 0 | ✅ |
| txt page labels | ` · Page 1` always | suppressed for `.txt`/missing page (node-verified) | no fake pages | ✅ |
| Legacy marker scrub on review path | none | `get_attempt_result` scrubs 7 fields (29/29) | 0 visible markers | ✅ |
| Baseline regression | 484/484 | **484/484** (+298 new = 782/782) | stay green | ✅ |

## Incidents & notes
1. **`test_display_scrub` 1-node failure was a test bug**: node emits UTF-8 but
   `subprocess(text=True)` decoded with the locale codec (cp1252) → `Â·` instead of `·`.
   Fixed by decoding stdout as UTF-8 explicitly → 29/29. Product code untouched.
2. **First tutor battery run invalidated by missing corpus** (docs A/B not uploaded —
   environment, not code): 65/65 refusals at score ~0.1. Discarded; re-ran after
   `p1_setup.py` bootstrap. All reported numbers come from bootstrapped runs only.
3. **`p4_practice.py`'s inline `grounded=` counter always prints 0** and its `cited_docs`
   field is always `[]` — both resolve `source_chunks` through `Chunk.id`, but the ids are
   faiss ids (`Chunk.embedding_id`). `audit/grade_p4.py` does it correctly (letter →
   `options[letter]`, faiss id → `embedding_id`) and is the authoritative grader —
   220/220 grounded, `resolved 94/94`. Multi-doc stats for this report were recomputed via
   `embedding_id` for the same reason.
4. **Grading nuances in the 3 tutor repeats** are all model-wording, not quality defects:
   T01 (warn) corrected the premise explicitly; H12 refused in paraphrase; T31 declined
   the asked question but appended a true corpus fact. None asserts a wrong fact; none is
   a false refusal.
5. Battery residue cleaned through real endpoints/ORM as documented above; `db.sqlite3`
   was **not** restored from git (Phase-1 re-ingested doc13 lives only in the working DB).

## §F verdicts that miss their targets (carried to `REPORT_AFTER.md`)
- near-dup ≥0.90: **14** vs ≤10 (≥0.97 = 0; baseline 344).
- mock probe-5 overlap: **25.9%** vs ≤20%.
- multi-doc practice batches citing ≥2 docs: **4/9 (44%)** vs ≥80%.
- tutor GT literal grade: **64/65 ×3** vs 65/65 (0 false refusals ×3 ✅; the single
  non-pass per run is a wording/regex nuance, never a wrong fact).
- contamination 19 (unchanged): doc-scoping deliberately not built — §F marks that cell
  "if doc filter implemented"; B8 was solved at the source-list level instead (≤3 sources ✅).

## Pending to close Phase 5
- [x] `tests/test_live_tf.py` → 46/46
- [x] `tests/test_fixes.py` → 33/33, `tests/regression_http.py` → 30/30
- [x] Live B3 metric → 75 distinct sets / 220 q (19 live batches)
- [x] Live GT tutor battery ×3 → 64/65 each, 0 false refusals ×3
- [x] Live P4 battery → 220/220 grounded
- [x] Final re-audit runs (P1, P2, P4, P5, P8) → `audit/REPORT_AFTER.md`
