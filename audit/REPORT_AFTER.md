# RAGVANCE RAG-Pipeline AI Quality Audit — After Report (post Phases 1–5)

Date: 2026-09-30 · Method: same harness (`audit/P1–P8` scripts, `audit/ground_truth.json`,
`audit/corpus/` unchanged) re-run after the roadmap fixes; regression suite re-run in full.
Baseline = `audit/REPORT.md`. Phase evidence: `PHASE1_RESULTS.md` … `PHASE5_RESULTS.md`.

**Headline metrics — before → after**

| Area | Baseline | After Phases 1–5 |
|---|---|---|
| Tutor + hallucination battery (65 live GT ×3) | 62/65, **3 false refusals** | **64/65 every repeat; 0 false refusals ×3; 0 wrong-fact answers** |
| Gemini 429 / HTTP 500 under load | 4 failures, 500 after ~35 s, no retry | **0** — 195/195 tutor calls HTTP 200, backoff retried; 44/44 retry tests |
| Retrieval hit@5 (answer questions, no LLM) | 45/45 any-keyword | **51/51 any-keyword** (49/51 all-keyword; only known T06/H04 artifacts) |
| Practice (19 batches, 220 MCQs) | 220/220 valid, **199/220 grounded**, **18** distinct chunks cited | 220/220 valid, **220/220 grounded**, **94** distinct chunks cited |
| Practice source attribution (B3) | 1 distinct set per batch | **75 distinct per-question sets / 220 q** (up to 11 per batch) |
| Mock grid (8 tests, 170 questions) | src_sets = 1 in all 8; 5 distinct chunks; probe-5 match 100% | **src_sets [5,8,12,14,3,10,7,8] (all ≥⌈N/5⌉)**; up to 43 distinct chunks; probe-5 **25.9%** |
| Corpus near-dup chunk pairs | 344 ≥0.90 (328 ≥0.97) | **14 ≥0.90, 0 ≥0.97** |
| Citation markers in stored questions/explanations | 4 | **0** |
| Tutor sources shown to user | all 5 retrieved, 1 wasted Gemini call per review modal | **1–3 answer-supporting chunks; 0 Gemini calls for source display** |
| Regression suites | 484/484 | **484/484 + 298 new = 782/782** |

---

## A. What's working well (updated)

1. **Pipeline reliability held through every phase.** Upload→parse→clean→chunk→embed→FAISS
   green in all runs; FAISS round-trips (115 ↔ probe uploads) restore exactly; doc13 id
   stable; audit corpus bootstrap/teardown through real endpoints worked (126 → 115).
2. **Retrieval recall improved.** All 51 answer questions hit at rank ≤5 by any keyword;
   MRR ≥0.67 in every category; the only all-keyword misses are the two known grading
   artifacts (`8192` vs `8,192`, H04 arithmetic).
3. **Zero false refusals, zero hallucinated facts** across 3 full GT repeats — the
   contradicted-premise rule (B7) fixed all three baseline failures (H14, H15, T47), and
   every wrong premise (4710, 60 s, "Twilight deprecated", 30 °C, "keys never expire") is
   corrected with evidence.
4. **Rate limits are survivable.** Phase-2 retry/backoff turned the baseline's hard 500s
   into 100% HTTP 200 (worst case 35–47 s of backoff); exhausted retries degrade to the
   designed 503 transient JSON with byte-identical `[ERROR]`/failure strings.
5. **Grounding is structural now.** The Phase-4 `extra_validate` loop enforces the same
   ≥0.6 coverage predicate that `grade_p4.py` audits — live battery scored **220/220**.
6. **Citations are trustworthy.** Per-question `source_chunks` (live: 75 distinct sets),
   direct-id `/sources/?ids=` (exact ids, ordered, 0 Gemini calls), answer-supporting
   source filter (1–3 per answer), `doc_/chunk_` markers gone from every user surface.
7. **Mock integrity maintained:** 8/8 exact 70/30 splits, 8/8 correct grading,
   leak-free take pages (the scanner's `explanation` hits are the bare word inside
   question/option text — verified correlated 5/5 flagged vs 0/0 unflagged).
8. **Diversity root cause removed:** corpus cleaning + ≥0.97 dedup (328 → 0 pairs) plus
   rotating corpus-derived seed queries kill the fixed 5-chunk boilerplate context.
9. **PDF page numbers remain accurate**; `.txt` no longer renders fake page numbers.

## B. Problem scorecards (baseline findings → status)

| # | Finding | Status | Evidence after |
|---|---|---|---|
| B1 | Mock: every question from one fixed 5-chunk context | **Fixed** | src_sets `[5,8,12,14,3,10,7,8]` all ≥⌈N/5⌉; 50q test cites 43 distinct chunks; probe-5 overlap 100% → 25.9% |
| B2 | Practice default query = literal `"topic N"` | **Fixed** | rotating corpus-derived query pool; `"topic N"` only exists as an explicit-topic probe; distinct cited 18 → 94 |
| B3 | `source_chunks` = whole batch; review modal asks the tutor | **Fixed** | per-question sets live (75/220, up to 11/batch); `/sources/?ids=` exact ids, 0 Gemini calls (24/24 + 17/17 tests) |
| B4 | No cleaning/dedup: 344 near-dup pairs | **Mostly fixed** | ≥0.97: 328 → **0**; ≥0.90: 344 → **14** (target ≤10, short by 4 — all doc13 boilerplate cross-boundary overlaps) |
| B5 | 429 → HTTP 500, no retry | **Fixed** | `invoke_with_retry` + transient classifier; 195/195 tutor 200; 44/44 retry tests; 503 transient JSON path |
| B6 | Citation markers in questions/explanations | **Fixed** | prompt ban + `scrub_citation_markers`; stored markers **0** (practice 0/0, mock 0×8); 26/26 scrub tests |
| B7 | 3 false refusals on contradicted premises | **Fixed** | contradiction rule in `TUTOR_PROMPT`; **0 false refusals ×3 repeats**, stable 64/65 ×3 |
| B8 | Cross-doc contamination; sources = all retrieved | **Fixed (chosen approach)** | answer-supporting filter, ≤3 sources live (18/18); *top-5 contamination itself unchanged (19) — doc scoping deliberately not built, per user decision; §F marks that cell conditional* |
| B9 | 21/220 answers ungrounded | **Fixed** | grounding loop live: **220/220** (target ≥216) |
| B10 | No score/relevance analytics | **Done (measure-only, as recommended)** | `logs/retrieval_analytics.jsonl` — operation-labelled score records (532 from live runs); no threshold gated (calibration = future work by design) |
| B11 | Difficulty has no measurable effect | **Not attempted** | out of the approved roadmap (needs difficulty-conditioned retrieval/A-B study) |
| B12 | txt page numbers; markers in review explanations | **Fixed** | `pageSuffix` txt-aware labels (node-verified) + `get_attempt_result` scrub; 29/29 tests |

## F. Before/after acceptance table

Same harness, same corpus/GT. `After` measured 2026-09-30 (batches bootstrapped per
`PHASE5_RESULTS.md`).

| Metric | Baseline | Target | After | Verdict |
|---|---|---|---|---|
| Tutor + hallucination pass (65 GT) | 62/65 | 65/65, stable ×3 | **64/65, 64/65, 64/65** (single non-pass per run is a wording/regex nuance: contextualized 4710 warn; paraphrased refusal; declined-with-tangential-fact) | ⚠️ close — quality criteria (correctness) met, literal string grade 1 short ×3 |
| False refusals | 3 | 0 | **0 ×3** | ✅ |
| HTTP 500 / raw 429s (65 queries ×3) | 4 | 0 | **0** (195/195 HTTP 200) | ✅ |
| Mock: distinct source sets per test | 1 | ≥ ⌈N/5⌉ | **[5,8,12,14,3,10,7,8]** — all 8 pass | ✅ |
| Mock: distinct chunks per test (50q) | 5 | ≥15 (≥20 in §F) | **43** | ✅ |
| Mock: questions citing fixed probe-5 | 100% (N/N) | ≤20% | **25.9%** (44/170; per-test 0–80%) | ❌ close miss |
| Practice: distinct cited chunks (220q) | 18 | ≥60 | **94** | ✅ |
| Practice: multi-doc batches citing ≥2 docs (topic=None) | ~0 | ≥80% | **4/9 batches (44%)**, 12/105 q; all of docs 13/34/35 cited across the battery | ❌ |
| Practice: semantic dup pairs ≥0.85 (global) | 374 | ≤75 | **69** | ✅ |
| Practice: grounded answers | 199/220 (90.5%) | ≥216/220 | **220/220 (100%)** | ✅ |
| `doc_N:chunk_M` markers in stored Q/E | 4 | 0 | **0** | ✅ |
| Review "View Source" returns requested ids | 0/5 | 5/5, 0 Gemini calls | **5/5, 0 calls** (order + whitelist locked by tests) | ✅ |
| Contaminated tutor top-5 | 19/45 | ≤3/45 *if doc filter implemented* | **19** (unchanged — doc scoping not built; replaced by ≤3-chunk answer-supporting source list ✅) | ➖ deferred by decision |
| Near-dup chunk pairs ≥0.90 in index | 344 | ≤10 | **14** (≥0.97: 328 → 0) | ⚠️ close miss |
| Regression suites | 484/484 | must stay green | **484/484** (+298 new = 782/782) | ✅ |

Score: **10 ✅ · 3 ⚠️/❌ close · 1 ❌ (multi-doc concentration) · 1 ➖ deferred by decision.**

### Remaining gaps (honest list, none blocking)
1. **Multi-doc practice concentration** (44% vs 80%): doc-filtered rotation seeds still
   skew to doc13's dense boilerplate. Next lever: cross-doc seed interleaving or
   per-batch doc scheduling — no signature changes needed (`_next_pool_query`).
2. **Near-dup ≥0.90 = 14 vs ≤10**: remaining pairs are genuine cross-boundary repeats of
   doc13 boilerplate that pass the ≥0.97 collapse rule; a sliding-window dedup or lower
   threshold with length guard would close it (B4's own note: retune after dedup).
3. **Probe-5 overlap 25.9% vs ≤20%**: chance overlap between rotated seeds and the legacy
   probe query's top-5; not user-visible, but the metric is what §F set.
4. **Tutor literal grade 64/65**: to reach the literal 65/65 the prompt could pin the
   refusal phrase harder ("use this exact sentence"), at the cost of unnatural wording —
   functional criterion (0 false refusals, 0 wrong facts) is already met.
5. **Difficulty effect (B11)**: untouched, out of scope of the approved roadmap.

## Runs & method (this re-audit)

| Run | Command | Result |
|---|---|---|
| Bootstrap | `audit/p1_setup.py` | docs 34/35, FAISS 126 |
| P2 (offline) | `audit/p2_retrieval.py` | hit@5 51/51 any; contamination list unchanged (19) |
| P3 ×3 (live) | `audit/p3_tutor.py` + `grade_p3.py` | 64/65 ×3, 0 false refusals ×3, 195/195 HTTP 200 |
| P4 (live) | `audit/p4_practice.py` + `grade_p4.py` | 220/220 valid, **220/220 grounded**, 94 fids, dup 69 |
| P5 (live) | `audit/p5_mock.py` | 8/8 splits+scores, src_sets ≥⌈N/5⌉, markers 0 |
| P8 (offline) | `audit/p8_offline.py` | ≥0.90: 14, ≥0.97: 0; unit norms confirmed |
| Regression | `tests/` (all 19 suites) | **782/782** |
| Teardown | delete 34/35 via `/delete/<id>/`, remove today's 15 battery tests + attempts | docs=[13], chunks=115, FAISS 115, tests 74, attempts 67 |
| Post-cleanup smoke | sources 24 + per-question 17 + query_pool 29 + display_scrub 29 | 99/99 |

## Artifacts

- Phase reports: `audit/PHASE1_RESULTS.md` … `audit/PHASE5_RESULTS.md` (this report's
  detailed evidence chains live there).
- Logs (all regenerated 2026-09-30): `audit/logs/p1_pipeline_stats.json`,
  `p2_retrieval.jsonl`+`p2_summary.json`, `p3_tutor.jsonl` (latest of 3 repeats)+
  `p3_grading.json`, `p4_practice_*.jsonl`+`p4_summary.json`+`p4_grading.json`,
  `p5_mock_tests.jsonl`+`p5_summary.json`+`p5_mock_prompts.pkl`, `p8_offline.json`;
  runtime analytics: `logs/retrieval_analytics.jsonl` (gitignored).
- New/changed code per phase is enumerated in the phase reports (query_pool, cleaning,
  llm_resilience, sanitize, grounding, analytics, batch `extra_validate`, `sources_view`,
  `filter_supporting_results`, template `pageSuffix`).
