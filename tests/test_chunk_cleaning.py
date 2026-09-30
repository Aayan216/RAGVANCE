import os
import sys

sys.path.insert(0, r"D:\v5\RAG-p2")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import numpy as np

from rag.cleaning import clean_pages, clean_text, near_duplicate_mask

PASSED = 0
FAILED = 0


def ok(label, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("PASS -", label, flush=True)
    else:
        FAILED += 1
        print("FAIL -", label, (":: " + str(extra)) if extra else "", flush=True)


# ---------------- clean_text ----------------
ok("dehyphenates line-break hyphens",
   clean_text("inter-\nconnection is used") == "interconnection is used",
   clean_text("inter-\nconnection is used"))
ok("keeps real hyphens",
   clean_text("well-known fact") == "well-known fact")
ok("strips trailing whitespace per line",
   clean_text("line one   \nline two\t\n") == "line one\nline two")
ok("collapses runs of spaces", clean_text("a    b   c") == "a b c")
ok("collapses 3+ newlines to one blank line", clean_text("a\n\n\n\n\nb") == "a\n\nb",
   repr(clean_text("a\n\n\n\n\nb")))
ok("preserves paragraph break", clean_text("para one\n\npara two") == "para one\n\npara two")
ok("NFC-normalizes unicode", clean_text("cafe\u0301") == "caf\u00e9")
ok("empty stays empty", clean_text("") == "" and clean_text(None) == "")

# ---------------- clean_pages ----------------
HDR = "ACME CORP ANNUAL REPORT 2024"
pages = [
    {"content": f"{HDR}  \nBody text of page one with real content.\nPage {i + 1} of 5",
     "page_number": i + 1, "file_name": "r.pdf"}
    for i in range(5)
]
pages[2]["content"] = pages[2]["content"].replace(
    "Body text of page one with real content.",
    f"Body text of page two.\n{HDR}\nMore body text on page two.",
)
out = clean_pages(pages)
ok("running header removed from page tops",
   all(not p["content"].startswith(HDR) for p in out),
   out[0]["content"][:60])
ok("mid-page occurrence of header kept",
   HDR in out[2]["content"], out[2]["content"])
ok("varying footers kept", all(f"Page {i + 1} of 5" in out[i]["content"] for i in range(5)))
ok("body content preserved",
   "real content" in out[0]["content"] and "More body text" in out[2]["content"])
ok("page metadata untouched",
   [p["page_number"] for p in out] == [1, 2, 3, 4, 5]
   and all(p["file_name"] == "r.pdf" for p in out))

two = [
    {"content": f"{HDR}\nAlpha body text here.", "page_number": 1, "file_name": "x"},
    {"content": f"{HDR}\nBeta body text here.", "page_number": 2, "file_name": "x"},
]
out2 = clean_pages(two)
ok("docs <3 pages: no header/footer removal",
   all(HDR in p["content"] for p in out2), out2)

long_hdr = "H" * 130
three = [
    {"content": f"{long_hdr}\nBody {i}", "page_number": i + 1, "file_name": "y"} for i in range(4)
]
out3 = clean_pages(three)
ok("over-long header line kept", all(p["content"].startswith(long_hdr) for p in out3))

# ---------------- near_duplicate_mask ----------------
def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)

emb = np.array([unit([1, 0]), unit([1, 0.01]), unit([0.7, 0.7]), unit([0, 1])])
texts = ["same chunk text here", "same chunk text here", "different chunk text here",
         "another chunk text here"]
mask = near_duplicate_mask(emb, texts)
ok("identical normalized text dropped", mask == [True, False, True, True], mask)

emb2 = np.array([unit([1, 0]), unit([1, 0.01])])
mask2 = near_duplicate_mask(emb2, ["aaaa " + "x" * 100, "bbbb " + "y" * 101])
ok("sim>=0.97 + similar length dropped", mask2 == [True, False], mask2)

emb3 = np.array([unit([1, 0]), unit([1, 1])])
mask3 = near_duplicate_mask(emb3, ["aaaa " + "x" * 100, "bbbb " + "y" * 50])
ok("sim<0.97 kept (length ratio irrelevant)", mask3 == [True, True], mask3)

emb4 = np.array([unit([1, 0]), unit([1, 0.01])])
mask4 = near_duplicate_mask(emb4, ["aaaa " + "x" * 100, "bbbb " + "y" * 40])
ok("high sim but low length ratio kept (0.5 < 0.8)", mask4 == [True, True], mask4)

emb5 = np.array([unit([1, 0]), unit([0, 1])])
mask5 = near_duplicate_mask(emb5, ["Exact same words here now", "Exact same words here now"])
ok("equal text dropped even with orthogonal vectors", mask5 == [True, False], mask5)

ok("empty input -> empty mask",
   near_duplicate_mask(np.zeros((0, 2), dtype=np.float32), []) == [])

# ---------------- ingest integration: upload -> clean+dedup ----------------
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from backend import views
from backend.models import Chunk, Document
from rag.chunker import TextChunker
from rag.embedder import Embedder

c = Client()
p = (
    "The Zephyr protocol review checklist states that operators must verify each relay node "
    "before deployment and confirm heartbeat intervals are configured correctly across the "
    "regional cluster. Operators must record every check in the operations log. "
)
p = p + p[:110]  # ~310 chars so the two copies cannot merge under chunk_size=500
q = (
    "Marigold nutrient guidelines require pH between 5.8 and 6.2 with an ideal target of 6.0 "
    "and electrical conductivity near 1.4 mS/cm for lettuce crops. Water temperature must stay "
    "at 20 degrees Celsius throughout the growth cycle for stable dissolved oxygen. "
)
q = q + q[:80]  # ~310 chars, unique content
body = p + "\n\n" + p + "\n\n" + q

# Independently compute what the pipeline should keep
probe_pages = clean_pages([{"content": body, "page_number": 1, "file_name": "probe.txt"}])
raw_chunks = TextChunker().chunk_pages(probe_pages)
raw_texts = [ch["content"] for ch in raw_chunks]
raw_emb = Embedder().embed(raw_texts)
expected_keep = sum(near_duplicate_mask(raw_emb, raw_texts))
ok("fixture produces >=3 raw chunks with a duplicate pair",
   len(raw_chunks) >= 3 and expected_keep < len(raw_chunks),
   (len(raw_chunks), expected_keep, [t[:40] for t in raw_texts]))

before = len(views.vector_store)
up = SimpleUploadedFile("dedup_probe.txt", body.encode("utf-8"), content_type="text/plain")
r = c.post("/", {"title": "ZZDedupProbe", "file": up})
ok("probe uploaded", r.status_code == 302, r.status_code)
doc = Document.objects.get(title="ZZDedupProbe")
r2 = c.post(f"/process/{doc.id}/")
data = r2.json()
doc.refresh_from_db()
chunks = list(Chunk.objects.filter(document=doc))
after = len(views.vector_store)
ok("process success", data.get("status") == "success", data)
ok("view dedup result == independently computed kept count",
   doc.chunk_count == expected_keep == data.get("chunks"),
   (doc.chunk_count, expected_keep, data))
ok("DB rows == chunk_count == returned", len(chunks) == doc.chunk_count == data["chunks"])
ok("FAISS grew by kept chunks only", after == before + expected_keep,
   (before, after, expected_keep))
ok("duplicate content stored once",
   sum(1 for ch in chunks if ch.content == raw_texts[0]) <= 1)

rc = c.post(f"/delete/{doc.id}/")
ok("probe cleaned up", rc.status_code == 200, rc.content[:120])
ok("FAISS restored", len(views.vector_store) == before, (before, len(views.vector_store)))

print(f"\n{PASSED}/{PASSED + FAILED} passed", flush=True)
sys.exit(1 if FAILED else 0)
