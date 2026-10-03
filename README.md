# RAGVANCE — AI Study Assistant

> **Your documents. Your knowledge base. Your AI study partner.**

RAGVANCE is a **Retrieval-Augmented Generation (RAG)** study assistant that turns your own study materials into an interactive learning environment. Upload your documents, ask questions, practise MCQs, or take timed mock exams — with responses grounded in your uploaded content and backed by **per-question source citations**.

### 🚀 Live Demo

**[Open RAGVANCE →](https://ragvance.onrender.com)**

### ✨ What You Can Do

| Mode | Purpose |
|---|---|
| 📚 **Tutor** | Ask questions and receive grounded explanations from your study material |
| 📝 **Practice** | Generate topic-focused MCQs with immediate feedback and source citations |
| 🎯 **Mock Test** | Take timed, exam-style tests with results, analysis, and answer review |
| 📄 **Sources** | Inspect the exact document passages used to support generated answers |

### 📊 Project Validation

- **782 / 782** automated checks passing
- **220 / 220** practice questions passed grounding validation
- **0** false tutor refusals across repeated live test batteries
- **Per-question source citations** with direct source retrieval
- **Transient Gemini errors** handled with automatic retry and backoff

> **Status:** This repository represents the tested **Phase 1–5 release**. See the [audit reports](#audit-reports) for the validation details.

---

## Features

- **Upload** — PDF, DOCX, PPTX, TXT documents, processed into a local FAISS index
- **Tutor Mode** — ask questions, get grounded answers with citations; contradictory premises are corrected instead of refused; *View Sources* shows the exact supporting chunks
- **Practice Mode** — generate and answer MCQs with per-question sources and strict grounding checks
- **Mock Test** — timed exams with per-question sources, performance analysis, and review
- **`/sources/` endpoint** — resolves cited chunk IDs to passages without any LLM call
- **Gemini resilience** — automatic retry with exponential backoff on rate limits / transient errors
- **Answer-supporting source filter** — tutor responses cite only chunks that actually support the answer (1–3 chunks)

## Quick Start

For a new user:

1. Clone and install:

   ```bash
   git clone https://github.com/Aayan216/RAGVANCE.git
   cd RAGVANCE
   uv sync
   ```

2. Create `.env` from `.env.example` and add your own `GEMINI_API_KEY`.

3. Run:

   ```bash
   uv run python manage.py migrate
   uv run python manage.py runserver
   ```

4. Open: http://127.0.0.1:8000/

5. First use: **Upload → Process → Tutor / Practice / Mock Test**

Documents must be processed before they can be searched. A fresh clone starts with an empty local FAISS index.

## Tech Stack

- Django 5.x (Python 3.12+)
- LangChain + Google Gemini (`gemini-3.5-flash-lite`)
- Sentence Transformers (`all-MiniLM-L6-v2`) + FAISS
- Bootstrap 5 + Chart.js (no login/signup; mock-test state persists in `localStorage`)

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — dependency/environment manager (uses `uv.lock`); or plain **pip** with the provided `requirements.txt`
- **Node.js** — only for the JavaScript regression suites
- **Git**
- **Your own Google Gemini API key** — this project ships **no API keys**; you must create and use your own (free tier works)

## Environment Setup

```bash
git clone https://github.com/Aayan216/RAGVANCE.git
cd RAGVANCE
uv sync            # creates .venv and installs all dependencies from uv.lock
```

## Installing Dependencies

**Option A — uv (recommended):**

```bash
uv sync            # installs everything declared in pyproject.toml, locked by uv.lock
```

**Option B — pip:**

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` lists all runtime dependencies with pinned `==` versions and `# via` comments (showing why each package is needed). It is auto-generated from `uv.lock` — regenerate it with:

```bash
uv export --no-hashes --no-dev --no-emit-project -o requirements.txt
```

Key packages installed either way:

- `django`, `langchain`, `langchain-community`, `langchain-core`, `langchain-google-genai`
- `faiss-cpu`, `sentence-transformers`
- `pymupdf`, `pypdf`, `python-docx`, `python-pptx`
- `numpy`, `pandas`, `python-dotenv`

## `.env` Setup (required)

**Bring your own API keys.** This repository contains **no API keys** — no shared, embedded, or default Google key. Every user must create and use their **own** Google Gemini API key (free at [Google AI Studio](https://aistudio.google.com/apikey)). The same applies to any other API key you ever add to `.env`: use your own, keep it only in your local `.env` (gitignored), and never commit it.

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your-gemini-api-key-here
DJANGO_SECRET_KEY=any-long-random-string
DEBUG=True
```

| Key | Required | Purpose |
|-----|----------|---------|
| `GEMINI_API_KEY` | **Yes** | Your own Google Gemini API key (not provided by this project) — used for tutor/practice/mock generation |
| `DJANGO_SECRET_KEY` | Recommended | Django signing secret (falls back to a dev placeholder) |
| `DEBUG` | Optional | `True` in development; `False` would be for production |

`.env` is gitignored and is **never** committed to GitHub.

## Database Migration

```bash
uv run python manage.py migrate
```

Creates `db.sqlite3` (document/test metadata). The file is generated locally and excluded from GitHub.

## Running RAGVANCE Locally

```bash
uv run python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.

## Uploading Documents

1. Go to **/** — choose a file (PDF, DOCX, PPTX, or TXT)
2. Click **Upload**
3. Click **Process** on the listed document (`/process/<id>/`) — this parses, chunks, embeds, and indexes it; the document is **not searchable until processed**
4. Use **Tutor**, **Practice**, or **Mock Test** to query your documents
5. **Delete** (`/delete/<id>/`) removes the uploaded file, its DB rows, and its vectors from the index

## How RAG / FAISS Data Is Generated Locally

Everything under `data/` and `db.sqlite3` is **built locally** by the Process step:

```
upload → parse (pymupdf/pypdf/python-docx/python-pptx/plain text)
       → chunk (CHUNK_SIZE=500 chars, CHUNK_OVERLAP=50)
       → embed (all-MiniLM-L6-v2 — downloaded from HuggingFace on first use, ~90 MB)
       → FAISS index + metadata
```

Outputs written to disk:

| Path | Contents |
|------|----------|
| `data/vector_store/faiss.index` | FAISS vector index |
| `data/vector_store/metadata.pkl` | chunk id → document/page metadata |
| `data/media/documents/` | uploaded original files |
| `db.sqlite3` | documents, chunks, mock tests, attempts |

**A fresh clone starts with an empty index** (these files are excluded from GitHub — see below). Upload and *Process* your documents to rebuild it.

## Running the Full 782-Test Suite

The suite is 20 standalone scripts (17 Python + 3 JavaScript). Each prints its own `===== N/N passed =====` line; totals: **484 baseline + 298 new = 782**.

**Python suites** (use Django's test `Client` — no running server needed):

```bash
# From the project root, with the venv active:
uv run python tests/test_query_pool.py
uv run python tests/test_chunk_cleaning.py
uv run python tests/test_marker_scrub.py
uv run python tests/test_llm_retry.py
uv run python tests/test_sources_endpoint.py
uv run python tests/test_per_question_sources.py
uv run python tests/test_tutor_prompt.py
uv run python tests/test_grounding.py
uv run python tests/test_source_filter.py
uv run python tests/test_analytics.py
uv run python tests/test_display_scrub.py
uv run python tests/test_true_false.py
uv run python tests/test_fixes.py
uv run python tests/regression_http.py
uv run python tests/regression_pages.py
uv run python tests/regression_documents.py
```

**JavaScript suites** (pure Node, no server):

```bash
node tests/test_persistence.js
node tests/regression_takejs.js
node tests/regression_darkmode.js
```

Notes:

- **`tests/test_live_tf.py` calls the real Gemini API** — it requires a valid `.env` and consumes API quota; all other suites run offline (Gemini is mocked).
- Several test scripts hardcode the original development path `D:\v5\RAG-p2` (`sys.path.insert` / `os.chdir`). On another machine, either check out the repo at that path or adjust those path lines in the test scripts.
- Some Python suites create mock tests/attempts in `db.sqlite3`; this is expected.

## Project Structure

```
RAGVANCE/
├── manage.py
├── config/                 # Django project (settings, urls, wsgi)
├── backend/                # views, urls, forms, models (upload, tutor, practice, sources)
├── rag/                    # RAG core
│   ├── rag_chain.py        #   retrieval + tutor/answer pipeline
│   ├── query_pool.py       #   rotating corpus-derived seed queries
│   ├── cleaning.py         #   text normalization + near-dedup at ingest
│   ├── grounding.py        #   grounding score + answer-supporting filter
│   ├── llm_resilience.py   #   retry/backoff for transient Gemini errors
│   ├── sanitize.py         #   citation-marker scrubbing
│   ├── analytics.py        #   retrieval event logging (logs/)
│   ├── chunker.py / embedder.py / vector_store.py / file_parser.py
│   ├── batch_generation.py #   batched MCQ/TF generation with validation
│   └── mcq_generator.py    #   practice-question generation
├── mock_test/              # mock-test engine, analyzer, result scrubbing
├── frontend/               # templates (tutor/practice/mock) + static CSS/JS
├── tests/                  # 20 standalone suites (782 checks total)
├── audit/                  # audit reports (.md, committed) + harness (local only)
│   ├── REPORT.md           #   baseline audit
│   ├── REPORT_AFTER.md     #   final re-audit with before/after table
│   └── PHASE1_RESULTS.md … PHASE5_RESULTS.md
├── data/                   # generated locally: media + vector store (not in git)
└── logs/                   # runtime logs (not in git)
```

## Audit Reports

| Report | Contents |
|--------|----------|
| [audit/REPORT.md](audit/REPORT.md) | Baseline quality audit — original scorecard and gaps |
| [audit/REPORT_AFTER.md](audit/REPORT_AFTER.md) | Final re-audit — side-by-side before/after, §F target table |
| [audit/PHASE1_RESULTS.md](audit/PHASE1_RESULTS.md) | Retrieval diversity + corpus cleaning |
| [audit/PHASE2_RESULTS.md](audit/PHASE2_RESULTS.md) | Gemini retry/backoff + citation-marker scrubbing |
| [audit/PHASE3_RESULTS.md](audit/PHASE3_RESULTS.md) | Per-question sources + `/sources/` endpoint |
| [audit/PHASE4_RESULTS.md](audit/PHASE4_RESULTS.md) | Contradicted-premise rule + grounding loop |
| [audit/PHASE5_RESULTS.md](audit/PHASE5_RESULTS.md) | Answer-supporting source filter + analytics + display scrub |

## Files Intentionally Excluded from GitHub

| Excluded | Why |
|----------|-----|
| `.env` | Contains `GEMINI_API_KEY` / secrets — never committed |
| `db.sqlite3`, `data/media/`, `data/vector_store/` | Generated locally by migrate + upload/Process; rebuildable |
| `.venv/`, `staticfiles/`, `__pycache__/`, `*.pyc` | Environment/build artifacts |
| `logs/` | Runtime logs |
| `audit/*.py`, `audit/ground_truth.json`, `audit/corpus/`, `audit/logs/` | Audit harness scripts, test corpus, and raw battery logs kept local; the **audit report `.md` files are committed** |
