import json
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, r"D:\v5\RAG-p2")
os.chdir(r"D:\v5\RAG-p2")
import django

django.setup()

from rag import analytics
from rag.analytics import log_retrieval
from rag.rag_chain import RAGChain

PASSED = 0
FAILED = 0


def ok(label, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("PASS:", label, flush=True)
    else:
        FAILED += 1
        print("FAIL:", label, ("| " + str(extra)) if extra != "" else "", flush=True)


def read_lines(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


tmp = Path(tempfile.mkdtemp())
target = tmp / "retrieval_analytics.jsonl"
orig_path = analytics.analytics_path
analytics.analytics_path = lambda: target
try:
    log_retrieval("tutor", [0.9123456, 0.5], doc_ids=[13], docs=[13, 14])
    ok("record written", target.exists())
    lines = read_lines(target)
    ok("one line", len(lines) == 1, len(lines))
    rec = lines[0]
    ok("fields present",
       set(rec.keys()) == {"ts", "operation", "n", "top1", "scores", "doc_ids", "docs"},
       list(rec.keys()))
    ok("operation recorded", rec["operation"] == "tutor")
    ok("n and top1", rec["n"] == 2 and rec["top1"] == 0.912346, rec)
    ok("scores rounded", rec["scores"] == [0.912346, 0.5], rec["scores"])
    ok("doc_ids and docs recorded", rec["doc_ids"] == [13] and rec["docs"] == [13, 14])
    ok("ts is float", isinstance(rec["ts"], float))

    log_retrieval("practice", [0.3])
    ok("appends (2 lines)", len(read_lines(target)) == 2)

    log_retrieval("mock", [None, 0.2])
    rec3 = read_lines(target)[2]
    ok("None score tolerated", rec3["top1"] is None and rec3["scores"] == [None, 0.2], rec3)

    log_retrieval("tutor", ["garbage"], docs=[13])
    ok("non-float score never raises", True)

    bad_orig = analytics.analytics_path
    analytics.analytics_path = lambda: (_ for _ in ()).throw(RuntimeError("disk gone"))
    log_retrieval("tutor", [0.1])
    analytics.analytics_path = bad_orig
    ok("path failure swallowed (never raises)", True)

    multi = tmp / "threaded.jsonl"
    analytics.analytics_path = lambda: multi

    def worker(n):
        for i in range(50):
            log_retrieval(f"op{n}", [0.1, 0.2], doc_ids=[13])

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    tlines = read_lines(multi)
    ok("thread-safe appends", len(tlines) == 500, len(tlines))
    ok("all threaded lines valid JSON", all(r["operation"].startswith("op") for r in tlines))
finally:
    analytics.analytics_path = orig_path

# integration: real retrieval logs one record per call
integ_target = tmp / "integration.jsonl"
analytics.analytics_path = lambda: integ_target
try:
    rag = RAGChain()
    ids1 = [r["faiss_id"] for r in rag._retrieve_context("database systems", operation="tutor")]
    ids2 = [r["faiss_id"] for r in rag._retrieve_context("database systems", operation="tutor")]
    recs = read_lines(integ_target)
    ok("integration: one record per retrieval", len(recs) == 2, len(recs))
    ok("integration: operation recorded", recs[0]["operation"] == "tutor")
    ok("integration: n == top_k results", recs[0]["n"] == len(ids1) == 5, recs[0]["n"])
    ok("integration: real scores logged",
       isinstance(recs[0]["top1"], float) and recs[0]["scores"][0] is not None, recs[0])
    ok("integration: retrieval unchanged by logging", ids1 == ids2, (ids1, ids2))
finally:
    analytics.analytics_path = orig_path

src = open(r"D:\v5\RAG-p2\rag\rag_chain.py", encoding="utf-8").read()
ok("wired: log_retrieval called in _retrieve_context", "log_retrieval(" in src)
ok("wired: tutor operation", 'operation="tutor"' in src)
ok("wired: practice operation", 'operation="practice"' in src)
ok("wired: mock operation", 'operation="mock"' in src)
gi = open(r"D:\v5\RAG-p2\.gitignore", encoding="utf-8").read()
ok("logs/ gitignored", "logs/" in gi)

print(f"\n===== {PASSED}/{PASSED + FAILED} passed =====", flush=True)
sys.exit(1 if FAILED else 0)
