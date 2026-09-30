import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, r"D:\v5\RAG-p2")
os.chdir(r"D:\v5\RAG-p2")
import django

django.setup()

from rag.grounding import SOURCE_SUPPORT_THRESHOLD, filter_supporting_results
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


def res(text, idx, doc=13, score=0.9, fname="doc.pdf"):
    return {"text": text, "doc_id": doc, "chunk_index": idx, "page_number": 1,
            "file_name": fname, "score": score}


ANSWER = "Water temperature should be raised to 30 degrees."
SUP_A = "The water temperature is raised to 30 degrees inside the reactor."
SUP_B = "Water temperature should remain steady while degrees rise slowly."
SUP_C = "For the raised water temperature, degrees are monitored closely."
XDOC_1 = "Marigold hydroponics nutrients are stored in the solution."
XDOC_2 = "Zephyr handbook describes onboarding rituals for new interns."

results = [res(SUP_A, 0), res(XDOC_1, 1, doc=99, fname="other.pdf"),
           res(SUP_B, 2), res(XDOC_2, 3, doc=77, fname="third.pdf"), res(SUP_C, 4)]

ok("threshold is 0.4", SOURCE_SUPPORT_THRESHOLD == 0.4)

kept = filter_supporting_results(ANSWER, results)
ok("only answer-supporting chunks kept",
   [r["chunk_index"] for r in kept] == [0, 2, 4],
   [r["chunk_index"] for r in kept])
ok("cross-doc chunks excluded",
   all(r["doc_id"] == 13 for r in kept))
ok("never more than 3 sources", len(kept) <= 3, len(kept))

more = [res(SUP_A, 0), res(SUP_B, 1), res(SUP_C, 2), res(SUP_A, 3)]
ok("cap applies when many qualify",
   len(filter_supporting_results(ANSWER, more)) == 3)

REFUSAL = "I don't have enough information about this."
fb = filter_supporting_results(REFUSAL, results)
ok("refusal -> fallback to top-3 retrieval order",
   [r["chunk_index"] for r in fb] == [0, 1, 2], [r["chunk_index"] for r in fb])
ok("fallback still capped at 3", len(fb) == 3)

ok("empty results -> []", filter_supporting_results(ANSWER, []) == [])
ok("no-content answer -> fallback",
   [r["chunk_index"] for r in filter_supporting_results("!!!", results)] == [0, 1, 2])
ok("missing text key treated as empty",
   [r["chunk_index"] for r in filter_supporting_results(
       ANSWER, [{"doc_id": 1, "chunk_index": 5}])] == [5])

ok("coverage order: highest support first",
   kept[0]["chunk_index"] == 0)


class StubResponse:
    def __init__(self, text):
        self.content = text


rag = RAGChain()
FAKE = list(results)
rag._retrieve_context = lambda question, doc_ids=None, operation=None: list(FAKE)
rag._invoke = lambda prompt: StubResponse(ANSWER)

out = rag.tutor_query("what temperature?")
ok("tutor integration: only supporting sources",
   [s["chunk_index"] for s in out["sources"]] == [0, 2, 4],
   [s["chunk_index"] for s in out["sources"]])
ok("tutor integration: payload keys unchanged",
   set(out["sources"][0].keys()) == {"doc_id", "chunk_index", "page_number",
                                     "file_name", "text", "score"},
   list(out["sources"][0].keys()))
ok("tutor integration: text still sliced <=200",
   all(len(s["text"]) <= 200 for s in out["sources"]))
ok("tutor integration: answer passthrough", out["answer"] == ANSWER)

rag._invoke = lambda prompt: StubResponse(REFUSAL)
out2 = rag.tutor_query("unknown topic?")
ok("tutor integration: refusal falls back to top-3",
   [s["chunk_index"] for s in out2["sources"]] == [0, 1, 2],
   [s["chunk_index"] for s in out2["sources"]])

src = open(r"D:\v5\RAG-p2\rag\rag_chain.py", encoding="utf-8").read()
ok("tutor_query wires filter_supporting_results", "filter_supporting_results(answer, results)" in src)
ok("rag_chain imports the filter", "from .grounding import filter_supporting_results" in src)

print(f"\n===== {PASSED}/{PASSED + FAILED} passed =====", flush=True)
sys.exit(1 if FAILED else 0)
