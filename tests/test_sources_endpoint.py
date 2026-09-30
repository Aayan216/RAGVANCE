import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, r"D:\v5\RAG-p2")
os.chdir(r"D:\v5\RAG-p2")
import django
django.setup()

from django.test import Client

from backend.views import vector_store
from rag.rag_chain import MCQ_BATCH_PROMPT, MOCK_BATCH_PROMPT, TRUE_FALSE_BATCH_PROMPT

RESULTS = []


def ok(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" | {extra}" if extra else ""), flush=True)


meta = vector_store.metadata
ok("corpus has chunks", len(meta) >= 2, f"n={len(meta)}")
id_a = meta[0]["faiss_id"]
id_b = meta[1]["faiss_id"]

c = Client()

# ---------- happy path: exact ids, order, whitelist keys ----------
r = c.get("/sources/", {"ids": f"{id_a},{id_b}"})
body = r.json()
sources = body.get("sources", [])
ok("GET /sources/ -> 200 JSON", r.status_code == 200 and r["Content-Type"].startswith("application/json"))
ok("returns exactly the requested count", len(sources) == 2, str(len(sources)))
ok("order matches request",
   len(sources) == 2 and sources[0]["faiss_id"] == id_a and sources[1]["faiss_id"] == id_b,
   str([s["faiss_id"] for s in sources]))
expected_keys = {"faiss_id", "doc_id", "chunk_index", "page_number", "file_name", "text"}
ok("whitelist keys only", all(set(s.keys()) == expected_keys for s in sources),
   str(list(sources[0].keys()) if sources else None))
ok("text content non-empty", all(isinstance(s["text"], str) and s["text"].strip() for s in sources))
ok("doc/chunk metadata present", all(isinstance(s["doc_id"], int) and isinstance(s["chunk_index"], int) for s in sources))

# ---------- unknown ids omitted, valid kept ----------
r2 = c.get("/sources/", {"ids": f"{id_a},999999"})
s2 = r2.json().get("sources", [])
ok("unknown id omitted, valid kept", r2.status_code == 200 and len(s2) == 1 and s2[0]["faiss_id"] == id_a, str(s2))

r3 = c.get("/sources/", {"ids": "999998,999999"})
ok("all unknown -> empty list 200", r3.status_code == 200 and r3.json().get("sources") == [], str(r3.json()))

# ---------- validation ----------
r4 = c.get("/sources/", {})
ok("missing ids -> 400", r4.status_code == 400 and "error" in r4.json(), str(r4.json()))

r5 = c.get("/sources/", {"ids": "abc,1"})
ok("non-int id -> 400", r5.status_code == 400, str(r5.json()))

r6 = c.get("/sources/", {"ids": "-3"})
ok("negative id -> 400", r6.status_code == 400, str(r6.json()))

r7 = c.get("/sources/", {"ids": ",".join(str(i) for i in range(51))})
ok("more than 50 ids -> 400", r7.status_code == 400, str(r7.status_code))

r8 = c.post("/sources/", {"ids": str(id_a)})
ok("POST -> 405", r8.status_code == 405, str(r8.status_code))

r9 = c.get("/sources/", {"ids": f" {id_a} , {id_b} "})
ok("whitespace tolerated", r9.status_code == 200 and len(r9.json().get("sources", [])) == 2)

# ---------- templates: no marker labels, real endpoint wired ----------
BASE = os.path.join(os.getcwd(), "frontend", "templates")
def read(path):
    with open(os.path.join(BASE, path), encoding="utf-8") as fh:
        return fh.read()

review = read("mock_test/review.html")
practice = read("practice.html")
tutor = read("tutor.html")

ok("review uses direct sources endpoint", '{% url "sources" %}?ids=' in review)
ok("review no longer asks the tutor", "Show source context for chunks" not in review and "tutor_ask" not in review)
ok("review has no doc/chunk marker label", "doc_${src.doc_id}:chunk_" not in review)
ok("practice has sources button + modal", "showPracticeSources" in practice and "practiceSourceModal" in practice and '{% url "sources" %}' in practice)
ok("tutor card has no doc/chunk marker label", "doc_${src.doc_id}:chunk_" not in tutor)
ok("tutor label is file · Page (txt-aware)", "${src.file_name}${pageSuffix(src, ' · Page ')}" in tutor)

# ---------- batch prompts request per-question source_chunks ----------
ok("MCQ batch prompt asks for source_chunks",
   "source_chunks" in MCQ_BATCH_PROMPT.template and "[doc_N:chunk_M]" in MCQ_BATCH_PROMPT.template)
ok("MOCK batch prompt asks for source_chunks",
   "source_chunks" in MOCK_BATCH_PROMPT.template and "[doc_N:chunk_M]" in MOCK_BATCH_PROMPT.template)
ok("T/F batch prompt asks for source_chunks",
   "source_chunks" in TRUE_FALSE_BATCH_PROMPT.template and "[doc_N:chunk_M]" in TRUE_FALSE_BATCH_PROMPT.template)

# ---------- summary ----------
failed = [n for n, p in RESULTS if not p]
print(f"\n===== {len(RESULTS) - len(failed)}/{len(RESULTS)} passed =====", flush=True)
if failed:
    print("FAILED:", *failed, sep="\n  - ", flush=True)
    sys.exit(1)
