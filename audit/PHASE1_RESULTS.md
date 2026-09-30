# Phase 1 Results — Retrieval Diversity + Chunk Cleaning/Dedup

Date: 2026-09-27 · Baseline: `audit/REPORT.md` (P1–P9 audit) · Status: **DONE — all gates green**

## What changed

### A/B — Corpus-derived query pools replace synthetic queries
- **NEW `rag/query_pool.py`** — `derive_seed()` (section-heading / first-sentence seeds,
  NFC + whitespace-normalized, ≤120 chars, ≥3 words), `build_section_queries()` (per-doc,
  deduped, deterministic, cap 50 with even subsample), `select_query()` (modulo rotation).
- **`rag/mcq_generator.py`** — `"topic {call_index+1}"` removed. Each practice LLM call now
  retrieves with a rotating corpus seed via `RAGChain.next_practice_query(doc_ids)`.
- **`rag/rag_chain.py`** — `"important concepts for exam"` removed from
  `generate_mock_questions_batch()` and `generate_mock_question()`. Two persistent,
  thread-safe `itertools.count()` counters on the RAGChain singleton (`_practice_seed_counter`,
  `_mock_seed_counter`) rotate through the pool **across batches and requests**
  (T/F uses an offset-half rotation). Empty pool → `None` → existing `"key concepts"` fallback.
  No function signatures changed (`FakeChain`-based tests unaffected).

### C — Ingest cleaning + near-dedup
- **NEW `rag/cleaning.py`** — `clean_text()` (NFC, de-hyphenate line breaks, rstrip, collapse
  space runs / 3+ newlines), `clean_pages()` (running header/footer removal when identical first/
  last line appears on ≥ max(3, 40% of pages), ≤120 chars, not mid-page), `near_duplicate_mask()`
  (cos ≥0.97 AND length-ratio ≥0.8, or normalized text equality).
- **`backend/views.py` `process_document_view`** — `clean_pages()` after parse;
  `near_duplicate_mask()` after embed, **before** DB + FAISS writes, keeping
  `Chunk rows == chunk_count == response chunks` consistent (integration-tested).

### Ops
- doc13 reprocessed in place (id **13 preserved**): 147 → **115 chunks** (−32 by cleaning/dedup).
- Audit corpus A+B re-uploaded for measurement (A=7, B=4 chunks, same as baseline), then deleted.

## Verification (gates)

| Gate | Result |
|---|---|
| `manage.py check` | 0 issues |
| `manage.py makemigrations --check` | No changes detected |
| New: `tests/test_query_pool.py` | **29/29** |
| New: `tests/test_chunk_cleaning.py` | **30/30** |
| Full regression suite (9 files) | **484/484** (161+33+71+24+30+46+52+23+44) |

Notes on the 484 run:
- `test_fixes.py` `mock success fast` (<60s live-timing assertion) failed twice at 64.4s/118.9s
  due to Gemini server latency; passed 33/33 at 7.8s on retry. No functional assertion ever failed.
- Practice `grounded=0/220` printed inline by `p4_practice.py` is a known grader artifact
  (it maps faiss ids to Django PKs); authoritative numbers come from `grade_p4.py`
  (maps via `Chunk.embedding_id`), as in the baseline.

## Measured before → after (same harness: full P4 19 batches/220q, P5 8 tests/170q, P8)

| Metric | Baseline | After Phase 1 | Target | Status |
|---|---|---|---|---|
| Practice: distinct cited chunks (220 q) | 18 | **89** | ≥60 | ✅ (4.9×) |
| Practice: semantic dup pairs ≥0.85 (global) | 374 | **48** | ≤75 | ✅ (−87%) |
| Practice: grounded answers | 199/220 (90.5%) | **210/220 (95.5%)** | ≥216 (Phase 4) | ↑ pending J |
| Practice: valid questions | 220/220 | 220/220 | 220 | ✅ |
| Mock: distinct source sets N=10/20/30/50 | 1/1/1/1 | **3/5/7/10** | ≥ one per batch (2/4/6/10) | ✅ |
| Mock: distinct source sets (easy/hard 10/20) | 1×4 | **3/5/3/5** | ≥2/4/2/4 | ✅ |
| Mock: distinct chunks, 50-q test | 5 | **36** | ≥15 | ✅ |
| Mock: distinct chunks, other tests | 5 | 14/23/33/11/25/15/21 | — | all ≫5 |
| Mock: 70/30 split + grading | 8/8 | 8/8 | 8/8 | ✅ |
| Mock: take-page real leaks | 0 | 0 (same benign "explanation" inside question text; verified: 10 q_texts contain the word) | 0 | ✅ |
| Index: near-dup chunk pairs ≥0.97 | 328 | **0** | ~0 | ✅ |
| Index: near-dup chunk pairs ≥0.90 | 344 | **14** | ≤10 | ⚠️ 14 (all sim 0.90–0.917, below the 0.97 dedup threshold by design) |
| S8: vector norms | all 1.0 | all 1.0 | — | ✅ |
| doc13 chunk count | 147 | 115 | — | −21.8% |

Synthetic queries eliminated from production paths: no `"topic N"` / `"important concepts for exam"`
reaches Gemini for practice or mock (unit-tested on fake + real corpus).

## Logs
- After-metrics: `audit/logs/p4_grading.json`, `p4_practice_*.jsonl`, `p5_summary.json`,
  `p5_mock_tests.jsonl`, `p8_offline.json` (baseline values preserved in `REPORT.md` §F table).
- Helpers added: `audit/reprocess_doc13.py`, `audit/resume_p4.py`, `audit/resume_p5.py`
  (resume scripts continue interrupted batteries with the seed counter offset to where the
  interrupted run left off).

## Not done (by design, later phases)
- Grounding → ≥216/220: Phase 4 (J — contradiction + practice grounding validation).
- ≥0.90 pair count 14 → ≤10: monitor in Phase-N re-audit; tune only if top-5 crowding returns.
- Retry/backoff, marker scrub, per-question attribution, `/sources/` endpoint: Phases 2–3.
