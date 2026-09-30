# RAGVANCE RAG-Pipeline AI Quality Audit — Final Report

Scope: Tutor, Practice, Mock Test flows (upload → chunk → embed → FAISS → prompt → Gemini → answer/question).
No application code was changed. All findings below are backed by logs in `audit/logs/`.

**Headline metrics**

| Area | Result |
|---|---|
| Tutor + hallucination battery (65 live queries) | **62/65** (48/51 answer, 14/14 correct refusals, **0 hallucinated facts**) |
| Retrieval hit@5 (45 answer questions, no LLM) | **45/45** (any-keyword), MRR ≥0.67 every category |
| Practice (19 batches, 220 MCQs) | 220/220 valid, **199/220 (90.5%) grounded**, but only **18 distinct chunks cited in total** |
| Mock grid (8 tests, 170 questions) | 8/8 exact 70/30 split, 8/8 correct grading, take-page leak-free — but **every question in every test cites the same 5 chunks** |
| Gemini 429 handling | 4 failures → **HTTP 500 after ~35 s, no retry** |
| Baseline restoration | docs A/B deleted, FAISS 158→147, tests/att. 29/24, `git status` clean (only `.gitignore` + `audit/`) |

---

## A. What's working well

1. **Pipeline reliability.** Upload→parse→chunk→embed→FAISS worked for every run: 2 corpus files (11 chunks) + 19 practice batches + 8 mock tests, zero processing errors. FAISS stayed consistent with the DB (158 in, 147 out after cleanup).
2. **Retrieval recall.** For all 45 ground-truth answer questions, top-5 contained the answer keywords (P2); only metric-artifact misses (T06 `8192` vs `8,192` alternatives, H04 arithmetic) under a strict all-keyword rule. MRR ≈ 1.0 in most categories, ≥ 0.67 everywhere; rank-6..10 never needed.
3. **Grounded answers + zero hallucinations.** No answer ever asserted a `wrong_keyword` (P3 grading: no wrong-keyword warnings). Misleading premises and traps were corrected with evidence: T32 (4709 not 4710), T33/T34 (42 s not 60 s), T38–T40, H08, H13.
4. **Refusal on genuinely absent info: 14/14.** `not_present`, `outside_scope`, `absent`, `out_of_scope` all returned the exact refusal phrase ("I don't have enough information about this.").
5. **Structured multi-fact answers.** T11–T14, T43, T44, H07, H09 combined facts from multiple chunks/sections correctly.
6. **Mock integrity.** 70/30 MCQ/T-F split exact in all 8 tests; interleave positions correct ([3,6,8] for n=10 etc.); grading score matched expected exactly 8/8; take page is **leak-free** (precise scan: 0× `correct_answer`/`is_correct`/explanation content/`source_chunk`/chunk markers); review page badges the correct option, shows explanations, result/analysis render 200.
7. **Validator + exact-dedup layer.** 220/220 practice MCQs and all mock questions passed `validate_mcq`/`validate_true_false`; zero exact-duplicate questions within batches.
8. **Prompt-side grounding rules work.** The tutor prompt's "ONLY from context" rule and refusal phrase behave as designed (see B7 for exceptions).
9. **PDF page numbers** are accurate for doc13 and surfaced in sources UI.

## B. Problems (scorecards)

### B1 — HIGH — Mock tests draw every question from one fixed 5-chunk boilerplate context (S3)
- **Problem:** All 170 questions across all 8 tests (10–50 questions, easy/medium/hard, doc_ids=[A,B,C]) cite **the same 5 FAISS chunks** (`src_sets=1, uniq_fids=5` in every test; probe `"important concepts for exam"` matches N/N questions in all 8 tests).
- **Evidence:** `p5_summary.json` (`distinct_source_sets_total=[1×8]`, `unique_fids_total=[5×8]`, `probe_match_counts` all N/N); the 5 chunks are doc13 fids 19/68/73/83/110 whose texts all begin "ask for a definition, a sequence of operations, a comparison…" (pairwise sim 0.78–0.89); 46 captured prompts share one context start (`p5_mock_prompts.pkl`).
- **Likely cause:** `rag/rag_chain.py:368` — retrieval query is hard-coded `"important concepts for exam"` for every batch; combined with near-duplicate boilerplate chunks in doc13 dominating that embedding.
- **Suggested improvement:** Retrieve per-question using per-question topic/seeds (or sample N chunks from the doc-selection pool randomly/by diversity), and dedup corpus chunks (B4). Success = ≥1 distinct context set per batch and ≥X distinct chunks per test (see F).

### B2 — HIGH — Practice default retrieval uses literal `"topic 1"… "topic N"` (S4)
- **Problem:** With `topic=null` (the default UI path), each generation call retrieves with query `"topic 1"`, `"topic 2"`, … — generic vectors unrelated to user intent. Multi-doc selection ([A,B,C]) effectively ignored: only doc13 chunks were ever cited; Zephyr/Marigold content appeared only with explicit `topic='Zephyr'`.
- **Evidence:** `p4_practice_batches.jsonl`; probe: `'topic 1'` top-5 == batch-1 cited fids (13/83,13/73,13/124,13/19,13/63); across 220 questions only **18 distinct cited chunks**; `p4_grading.json` topic-N Jaccard mean 0.26 (overlapping, not identical).
- **Likely cause:** `rag/mcq_generator.py:24` — `query = topic or f"topic {call_index}"`.
- **Suggested improvement:** Build retrieval query from document titles/section headings (or random chunk sampling across selected docs); never emit `"topic N"`. Success = multi-doc batches cite chunks from ≥2 selected docs, distinct-cited-chunks grows with batch size.

### B3 — HIGH — `source_chunks` is the whole per-call batch, not per-question support (S9) + source modal shows wrong chunks (S12)
- **Problem:** Every MCQ in a batch cites identical chunk ids; and the review page's "View Source Context" fetches sources by asking the tutor `/tutor/ask/` a meta-question instead of looking up the stored ids — it returns **wrong chunks and wastes a Gemini call**.
- **Evidence:** Code `rag/rag_chain.py:353,393`; practice batch uniq-cited = 5/8/13 for 5/10/20 questions (== call count); mock `src_sets=1`. S12 live test: requested chunks `19,68,73,83,110` → modal received `(13,128),(21,3),(13,95),(13,86),(13,104)` + answer "I don't have enough information about this."
- **Likely cause:** Batch generators attach `results` (full retrieval) to every question; `review.html:135` re-embeds a meta-query; `vector_store.get_by_id` exists but is unused.
- **Suggested improvement:** (a) Ask the model to name which of the provided chunks support each question (or verify answer keywords per chunk); (b) add a lightweight `/sources/?ids=…` endpoint backed by `get_by_id`. Success = cited sets differ per question; modal returns exactly requested ids; zero Gemini calls for source display.

### B4 — HIGH — No corpus cleaning or chunk dedup; index contains 344 near-duplicate chunk pairs (S5/S6)
- **Problem:** 344 chunk pairs ≥0.90 cosine (328 ≥0.97; many exactly 1.0, e.g. fid 3 ↔ 8/23/38/52/77/119/139) — doc13's repeated boilerplate. Near-dup chunks crowd top-5 (root cause of B1) and waste the fetch budget. `.txt` parsing yields one page → `page_number` always 1.
- **Evidence:** `p8_offline.json` (`near_dup_chunks`, `mock_fixed_context_similarity`); `p1_pipeline_stats.json` (txt pages=1, "no cleaning stage exists").
- **Likely cause:** `rag/file_parser.py` raw extraction; `rag/chunker.py` no dedup; `rag/batch_generation.py:87-109` dedupes only generated questions (exact/Jaccard), never chunks.
- **Suggested improvement:** Normalize text (whitespace, headers/footers, line de-hyphenation), drop chunks that are ≥0.97 duplicates of an existing chunk (or collapse into one), keep per-page mapping only when real. Success = duplicate-pair count near 0; top-5 diversity up.

### B5 — HIGH — Gemini rate-limit failures surface as HTTP 500 after ~35 s, no retry (S14)
- **Problem:** 4/69 tutor calls returned `429 RESOURCE_EXHAUSTED` → view caught nothing → "Internal Server Error" with 35 s latency; user gets an error, no answer.
- **Evidence:** P3 logs: T17, T34, H04 first attempts (`http_status` 500 equivalents, `{"error": "Error calling model … RESOURCE_EXHAUSTED"}`), succeeded on manual retry after pause.
- **Likely cause:** `backend/views.py` tutor/practice/mock call paths have no retry/backoff; `langchain-google-genai` raises.
- **Suggested improvement:** Retry with exponential backoff (2–3 attempts, honor `retry-after`), degrade to a friendly 503 JSON instead of 500. Success = 0 raw 500s under burst load.

### B6 — HIGH — Gemini citation markers leak into user-visible practice questions (S13)
- **Problem:** Practice questions contain literal context markers, e.g. *"How many total review components are explicitly stated in the instructions for **doc_13:chunk_102**?"* Explanations sometimes do too (3 mock questions, visible in review).
- **Evidence:** `p4_practice_questions.jsonl` (ungrounded sample list); `p5_mock_tests.jsonl` `explanations_mention_doc_markers` (tests 268: 2, 269: 1).
- **Likely cause:** `_format_context` emits `[doc_13:chunk_102]` tags (`rag_chain.py:221-228`); prompts don't forbid echoing them; no post-generation scrub.
- **Suggested improvement:** Prompt instruction ("never mention doc/chunk markers") + deterministic regex scrub of generated question/explanation fields. Success = 0 markers in stored questions/explanations.

### B7 — MEDIUM — False refusals + nondeterministic cross-doc refusal (S15/S16)
- **Problem:** H14 ("water temp should be raised to 30 °C?") and H15 ("keys never expire?") were refused although the correct contradicting facts were in context (20 °C at score 0.663; "expire after 900 seconds"). T47 (needs A + B facts, both in context) **refused in one run, answered correctly in another** — same question, same retrieval.
- **Evidence:** `p3_grading.json` (H14/H15/T47 fails, all "false refusal"); P7 traces + observed flip across runs; `p7_traces.json`.
- **Likely cause:** Prompt says refuse when "the answer is not found"; model treats a contradicted premise as absent rather than correcting; temperature nondeterminism.
- **Suggested improvement:** Prompt: "If the context contradicts the premise, state the correct fact; only refuse when the topic is absent." Retry-on-refusal for answer-expected questions is not possible without metadata — so fix prompt + add regression tests. Success = 0 false refusals on the GT set, stable across 3 repeats.

### B8 — MEDIUM — Top-5 contamination: cross-doc chunks crowd context (S10/S2)
- **Problem:** 19/45 single-doc tutor questions had chunks from other documents in top-5; sources shown to users include irrelevant chunks (sources = all retrieved, not answer-supporting).
- **Evidence:** `p2_summary.json` `contaminated` list (T08, T09, T10, T13, T15, T17, T18, T21, T22, T23, T25, T26, T39, T42, H02, H06, H08, H09, H14); tutor view passes no `doc_ids` (`backend/views.py:164`).
- **Likely cause:** No document scoping in tutor; `fetch_k=k*3` without filter; mixed corpus.
- **Suggested improvement:** Optional doc selector in tutor UI; filter retrieved sources to those actually supporting the answer (or re-rank). Success = contamination ≤5%, source list per answer ≤3 relevant chunks.

### B9 — MEDIUM — 9.5% of practice answers not grounded in cited chunks
- **Problem:** 21/220 answers' content words absent from cited chunk text (stem overlap also ~0 for those).
- **Evidence:** `p4_grading.json` (grounded 199/220; per-batch list; ungrounded samples in `p4_inspect` output).
- **Likely cause:** Batch-level context (B3) lets Gemini write answers from general knowledge; no post-hoc grounding check.
- **Suggested improvement:** Validate answer-vs-cited-chunk support at generation; regenerate on failure (existing `run_generation` loop makes this cheap). Success = ≥98% grounded.

### B10 — MEDIUM — No relevance calibration: refuse-question scores overlap answer scores (S1)
- **Problem:** Refuse-question top-1 scores run 0.067→**0.65** (avg 0.375) vs answer 0.62 avg — any threshold would misfire. The system never filters low-relevance context; refusal depends entirely on prompt compliance (currently working 14/14, but see B7).
- **Evidence:** `p2_summary.json` `refuse_top1_scores` / `answer_top1_scores`.
- **Likely cause:** `_retrieve_context` always returns top-k (`rag_chain.py:217-219`); MiniLM raw scores on this corpus are not calibrated.
- **Suggested improvement:** Do **not** bolt on a threshold now (would break answers); instead log score+hit analytics per corpus and revisit with a labeled calibration set. Success = defined decision rule backed by measured precision/recall.

### B11 — MEDIUM — Difficulty has no measurable effect on content (S7)
- **Problem:** Easy/medium/hard generate from the same context with only a prompt-phrase change; grounding rates are flat (easy 65/70, medium 63/70, hard 62/70 on practice; mock topics identical across difficulties). Users cannot rely on difficulty to get harder material.
- **Evidence:** P4 per-batch grounding table; P5 `topics_seen` (same "Study Methods/Trade-offs/Transactions" clusters at every difficulty).
- **Likely cause:** Difficulty only alters prompt wording (`rag_chain.py:72,97,166`); retrieval and corpus identical.
- **Suggested improvement:** Couple difficulty to retrieval scope (hard → multi-chunk/cross-section sampling, distractor-rich options) or difficulty-conditioned exemplars; validate with an A/B set graded for difficulty perception. Success = blinded raters distinguish difficulty levels ≥80%.

### B12 — LOW — txt page numbers meaningless; markers in review explanations
- **Evidence:** `p1_pipeline_stats.json` (txt = 1 page); 3 mock explanations contain `doc_13:chunk_*` shown in review.
- **Cause/suggestion:** file-type-aware page labeling; scrub markers (B6).

## C. Worthwhile improvements (prioritized)

**High**
1. Per-batch/per-question context diversity for mock + practice (fixes B1/B2) — biggest content-quality win, no UI change.
2. Corpus cleaning + chunk near-dedup before embedding (B4) — removes root cause of B1, improves every flow.
3. 429 retry/backoff + graceful 503 (B5) — removes hard user-facing failures.
4. Per-question `source_chunks` + direct-id source endpoint (B3) — makes citations trustworthy, kills wasted tutor calls.
5. Marker scrub + prompt ban (B6).

**Medium**
6. Prompt fix for contradicted-premise refusals + flakiness regression tests (B7).
7. Grounding validation loop for practice answers (B9).
8. Tutor doc scoping / source filtering (B8).

**Low**
9. txt page handling + explanation scrub (B12).
10. Score-logging analytics to prepare future relevance calibration (B10) — measure, don't gate yet.

## D. Improvements that are NOT worthwhile (or already fine)

1. **Vector normalization / cosine-vs-IP change (old suspicion S8): refuted.** All 158 stored vectors have ‖v‖ = 1.0 (cv 4e-8) — the embedding model already emits unit vectors; IP ≡ cosine; top-5 identical on all 51 answer questions. No code change needed.
2. **Take-page leak hardening (S11): already clean.** Precise scan found 0 leaks; the earlier "explanation" hit was the word appearing inside question text. No extra client-side scrub required.
3. **Cross-encoder reranker / hybrid BM25:** top-5 answer recall is already 45/45; a reranker adds latency/cost for no measurable recall gain here. Revisit only if corpus grows or recall drops.
4. **Tightening Jaccard dedup threshold alone:** would shrink symptoms, not the cause (duplicate context); fix retrieval/dedup first (B1/B4), then retune.
5. **LLM-as-judge scoring pipeline:** grading was done deterministically against planted facts; a judge adds cost and noise without changing decisions.
6. **Conversation memory / multi-turn tutor:** out of scope for accuracy; single-turn behavior is solid.

## E. Prioritized roadmap

| # | Priority | Item | Fixes | Effort |
|---|---|---|---|---|
| 1 | High | Diversify mock/practice retrieval (per-question/per-doc seeds) | B1, B2 | S |
| 2 | High | Chunk cleaning + near-dedup at process time | B4 (root cause) | M |
| 3 | High | Gemini retry/backoff + graceful errors | B5 | S |
| 4 | High | Per-question source attribution + `/sources/?ids=` | B3, S12 | M |
| 5 | High | Marker scrub (prompt + regex) | B6, B12b | S |
| 6 | Medium | Contradicted-premise prompt fix + flake tests | B7 | S |
| 7 | Medium | Practice grounding validation loop | B9 | S |
| 8 | Medium | Tutor doc filter / relevant-source filtering | B8 | M |
| 9 | Low | txt page labeling, score analytics | B10, B12 | S |

## F. Before/after test plan (acceptance criteria)

Re-run the identical harness (P1–P8 scripts in `audit/`) after fixes; corpus and GT unchanged (`audit/corpus/`, `audit/ground_truth.json`).

| Metric | Baseline (now) | Target |
|---|---|---|
| Tutor + hallucination pass (65 GT) | 62/65 | **65/65**, stable across 3 repeats (B7) |
| False refusals | 3 | 0 |
| HTTP 500 / raw 429s under burst (65 rapid queries) | 4 | 0 (auto-retried) |
| Mock: distinct source sets per test | 1 | ≥ ⌈N/5⌉ (one per batch), ≥20 distinct chunks in a 50q test |
| Mock: distinct chunks per test (50q) | 5 | ≥ 15 |
| Mock: questions citing fixed probe-5 | N/N | ≤ 20% |
| Practice: distinct cited chunks (220q) | 18 | ≥ 60 |
| Practice: multi-doc batches citing ≥2 docs | ~0 (topic=None) | ≥ 80% |
| Practice: semantic dup pairs ≥0.85 (global) | 374 | ≤ 75 |
| Practice: grounded answers | 199/220 (90.5%) | ≥ 216/220 (98%) |
| `doc_13:chunk_*` markers in stored questions/explanations | 4 | 0 |
| Review "View Source" returns requested ids | 0/5 | 5/5, 0 Gemini calls |
| Contaminated tutor top-5 | 19/45 | ≤ 3/45 (if doc filter implemented) |
| Near-dup chunk pairs ≥0.90 in index | 344 | ≤ 10 |
| Regression suites (tests/) | 484/484 | **484/484 must stay green** |

## Artifacts

- `audit/ground_truth.json` — 65-question bank (planted facts, traps, absent-info, contradicted premises)
- `audit/corpus/doc_A_zephyr_handbook.txt`, `doc_B_marigold_hydroponics.txt` — controlled corpus
- `audit/logs/` — `p1_pipeline_stats.json`, `p2_retrieval.jsonl`+`p2_summary.json`, `p3_tutor.jsonl`+`p3_grading.json`, `p4_practice_*.jsonl`+`p4_summary.json`+`p4_grading.json`, `p5_mock_tests.jsonl`+`p5_summary.json`+`p5_mock_prompts.pkl`, `p7_traces.json` (full prompts), `p8_offline.json`
- Scripts: `audit/harness.py`, `p1_setup.py`, `p2_retrieval.py`, `p3_tutor.py`, `grade_p3.py`, `p4_practice.py`, `grade_p4.py`, `p5_mock.py`, `p7_traces.py`, `p8_offline.py`
- Cleanup: docs 21/22 deleted via real endpoints, audit mock tests/attempts removed, `db.sqlite3` restored from git; FAISS 147 vectors, tests 29, attempts 24 (= baseline); `git status` shows only `.gitignore` (audit/ ignore rule); `audit/` untracked by design.
