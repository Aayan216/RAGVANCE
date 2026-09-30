# Phase 4 Results — Contradicted-Premise Tutor Rule + Practice Grounding Loop

Date: 2026-09-28 · Baseline: `audit/REPORT.md` §B7, §B9 · Plan item **J** · Status: **Implemented; all offline gates green — live batteries (GT tutor pass, live P4 grounding) environment-blocked by Gemini daily quota.**

## Deliverables

### 4A — Contradicted-premise prompt fix (B7, roadmap #6)
- **`rag/rag_chain.py` `TUTOR_PROMPT`** now contains, in order:
  1. the original contract (context-only, plain text, no markdown);
  2. **multi-document rule** — "The context may contain sections from several documents;
     use whichever section actually addresses the question" (targets the nondeterministic
     cross-doc refusal);
  3. **contradiction rule** — "If the question's premise contradicts the context (wrong fact,
     date, subject or edition), do not refuse. Answer by stating what the context actually
     says and briefly correct the premise." (targets the 3 false refusals on contradicted
     premises);
  4. the refusal fallback, now explicitly narrowed: refuse **only** when the context genuinely
     has no information, keeping the exact user-facing phrase
     `"I don't have enough information about this."`.
- No code-path change: `tutor_query` still formats `TUTOR_PROMPT`, still scrubs markers, still
  returns the same payload (`sources` keys unchanged).

### 4B — Practice grounding validation loop (B9, roadmap #7)
- **NEW `rag/grounding.py`** — mirrors the deterministic criterion of `audit/grade_p4.py`:
  `normalize_text` / `content_words(minlen=2)` (len > 2 words), `grounding_score` =
  |answer content words present in cited chunk texts| / |answer content words|,
  `is_grounded` (threshold **0.6**, applied to `options[correct]`), and
  `make_grounding_validator(vector_store)` which resolves a question's **own**
  `source_chunks` through the in-memory FAISS metadata (`get_by_id`, no embedding/LLM cost)
  and returns the `extra_validate` predicate. Unresolvable/missing sources → not grounded.
- **`rag/batch_generation.py` `run_generation(..., extra_validate=None)`** — new optional
  keyword-only parameter; runs **after** structural validation and **before** duplicate
  detection; `False` or an exception rejects that one question without failing the run
  (cap/retry/log formats unchanged; existing callers unaffected — all pass kwargs).
- **`rag/mcq_generator.py` `generate_practice_set`** wires
  `extra_validate=make_grounding_validator(self.rag_chain.vector_store)` — practice only;
  mock/T-F generation untouched (no extra_validate → identical behavior, locked by tests).
- Effect: an ungrounded practice answer is discarded pre-delivery and regenerated inside the
  existing 2× slot cap — never shown to the user.

## Gates

| Gate | Result |
|---|---|
| `manage.py check` | 0 issues |
| `manage.py makemigrations --check` | No changes detected |
| NEW `tests/test_tutor_prompt.py` | **17/17** |
| NEW `tests/test_grounding.py` | **40/40** |
| `tests/test_marker_scrub.py` (run_generation lock) | 26/26 |
| `tests/test_llm_retry.py` (run_generation lock) | 44/44 |
| `tests/test_true_false.py` (run_generation shared-state, mock FSM) | 161/161 |
| `tests/test_sources_endpoint.py` / `test_per_question_sources.py` | 24/24 + 17/17 |
| `tests/regression_pages.py` | 71/71 |
| `tests/test_persistence.js` | 52/52 |
| `tests/test_query_pool.py` / `test_chunk_cleaning.py` | 29/29 + 30/30 |
| `tests/regression_documents.py` | 24/24 (FAISS restored to 115) |
| `node regression_darkmode.js` / `regression_takejs.js` | 23 + 44 = **67/67** |
| `tests/test_fixes.py` | 27/33 — the same 6 **live-quota** failures as Phase 3; every offline, retry-cap, redaction, failure-path assert green |
| `tests/regression_http.py` | 25/26 — same single live-quota failure (tutor → 503 transient JSON = designed behavior); 21 offline asserts green |
| `tests/test_live_tf.py` | **BLOCKED** — same daily quota |

Green total: **654** = 427 of the 484 baseline (484 − 57 quota-blocked) + 227 new
(P1 59 + P2 70 + P3 41 + P4 57). Corpus size 711.

## Before → after (metrics)

| Metric | Baseline | After P1 | After P4 | Target | Status |
|---|---|---|---|---|---|
| Practice grounded answers (grade_p4 criterion) | 199/220 (90.5%) | **210/220 (95.5%)** | **structurally enforced**: every delivered answer scores ≥0.6 against its own cited chunks (unit-tested at the 0.6 boundary); live re-measure pending | ≥216/220 (98%) | ⏳ live battery |
| Tutor pass + hallucination (65 GT, incl. contradicted premises) | 62/65 (3 false refusals) | unchanged | prompt rule in place (17/17 prompt-contract locks); live GT run pending | 65/65, stable ×3 | ⏳ live battery |
| Mock generation | — | unchanged | unchanged (no extra_validate) | no regression | ✅ (161/161, 24/24 FSM) |

Equivalence note: `rag/grounding.py` implements the **same formula** as `audit/grade_p4.py`
(same normalization, same len>2 content words, same ≥0.6 coverage on `options[correct]`) —
verified at the 0.6 accept / 0.5 reject boundary — so in-loop acceptance and the audited
metric are the same predicate by construction.

## Incidents & notes
1. **Grounding loop observed working in tests:** the integration case logged
   `Practice generation: requested=4 llm_calls=3 valid=4 retries=2` — two ungrounded
   questions were rejected and regenerated within the cap; the mock-style tests confirm
   `extra_validate=None` paths behave byte-identically to before.
2. **Quota still exhausted** (same 429 `GenerateRequestsPerDayPerProjectPerModel-FreeTier`,
   `retryDelay 54s` observed). test_fixes: retry wrapper engaged (`retries=1`), original
   exception preserved through `[ERROR]`/`Could only generate …` paths; regression_http tutor
   correctly degraded to 503 transient JSON.
3. Grounding adds zero latency/cost per question: metadata lookup only (no embed, no LLM).

## Pending to close Phase 4 (all quota-blocked, resume ~midnight PT)
- [ ] Live tutor battery: `.\.venv\Scripts\python.exe audit\p3_tutor.py` + `audit\grade_p3.py`
  → expect 65/65, false refusals 0, stable across 3 repeats (B7 acceptance).
- [ ] Live P4 battery: `.\.venv\Scripts\python.exe audit\p4_practice.py` + `audit\grade_p4.py`
  → expect grounded ≥216/220 with valid 220/220 (B9 acceptance).
- [ ] `tests/test_fixes.py` → 33/33, `tests/regression_http.py` → 30/30,
  `tests/test_live_tf.py` → 46/46.
