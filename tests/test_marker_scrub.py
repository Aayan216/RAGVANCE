import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, r"D:\v5\RAG-p2")
os.chdir(r"D:\v5\RAG-p2")
import django
django.setup()

from backend.views import rag_chain
from rag.batch_generation import run_generation, validate_question
from rag.sanitize import scrub_citation_markers, scrub_question

RESULTS = []


def ok(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" | {extra}" if extra else ""), flush=True)


# ---------- 1. scrub_citation_markers unit ----------
ok("bracketed leading marker removed",
   scrub_citation_markers("[doc_13:chunk_102] The mitochondria is the powerhouse.") ==
   "The mitochondria is the powerhouse.")
ok("bare mid-text marker removed",
   scrub_citation_markers("See doc_13:chunk_5 for details") == "See for details")
ok("multiple markers removed",
   scrub_citation_markers("[doc_1:chunk_0] A [doc_2:chunk_9] B") == "A B")
ok("trailing bracket marker removed",
   scrub_citation_markers("based on doc_1:chunk_7] text") == "based on text")
ok("clean text byte-identical", scrub_citation_markers("No markers here.") == "No markers here.")
ok("non-str passthrough", scrub_citation_markers(None) is None and
   scrub_citation_markers(42) == 42 and scrub_citation_markers(["a"]) == ["a"])
ok("space collapsed and stripped",
   scrub_citation_markers("  [doc_13:chunk_5]   extra   spaces  ") == "extra spaces")
ok("explanation-style inline marker",
   scrub_citation_markers("Because the enzyme binds. [doc_13:chunk_42]") ==
   "Because the enzyme binds.")


# ---------- 2. scrub_question field scoping ----------
q = {
    "question": "[doc_13:chunk_9] What is glycolysis?",
    "options": {
        "A": "[doc_13:chunk_9] Breaking down glucose",
        "B": "Building proteins",
        "C": "Copying DNA",
        "D": "Cell division",
    },
    "correct": "B",
    "explanation": "Glycolysis splits glucose [doc_13:chunk_9].",
    "topic": "Metabolism [doc_13:chunk_9]",
    "source_chunks": [101, 102],
    "question_type": "mcq",
}
scrubbed = scrub_question(q)
ok("question field scrubbed", scrubbed["question"] == "What is glycolysis?", scrubbed["question"])
ok("option value scrubbed", scrubbed["options"]["A"] == "Breaking down glucose", scrubbed["options"]["A"])
ok("clean option untouched", scrubbed["options"]["B"] == "Building proteins")
ok("explanation scrubbed", scrubbed["explanation"] == "Glycolysis splits glucose.", scrubbed["explanation"])
ok("topic scrubbed", scrubbed["topic"] == "Metabolism", scrubbed["topic"])
ok("source_chunks preserved", scrubbed["source_chunks"] == [101, 102])
ok("correct/question_type preserved",
   scrubbed["correct"] == "B" and scrubbed["question_type"] == "mcq")
ok("non-dict passthrough", scrub_question("text") == "text")

marker_only = {"question": "[doc_1:chunk_2]", "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
               "correct": "A", "explanation": "e"}
ok("marker-only question scrubs to empty string", scrub_question(marker_only)["question"] == "")


# ---------- 3. validators unchanged (markers never reach them via run_generation) ----------
marker_q = {"question": "Q [doc_1:chunk_1]", "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct": "A", "explanation": "e"}
ok("validate_question still accepts markers (scrub is upstream)", validate_question(dict(marker_q)))


# ---------- 4. run_generation integration ----------
def make_mcq(call_index):
    return {
        "question": f"[doc_13:chunk_{call_index}] Question number {call_index}?",
        "options": {
            "A": f"[doc_13:chunk_{call_index}] Option A text",
            "B": "Option B text",
            "C": "Option C text",
            "D": "Option D text",
        },
        "correct": "C",
        "explanation": f"[doc_13:chunk_{call_index}] Because reasons.",
        "topic": f"[doc_13:chunk_{call_index}] Topic {call_index}",
    }


calls = {"n": 0}


def one_ok(call_index, count):
    calls["n"] += 1
    return [make_mcq(call_index) for _ in range(count)]


valid, stats = run_generation(one_ok, requested=2, per_call=1, concurrency=1, log_label="test")
no_markers = all(
    "[doc_" not in str(v.get(k, ""))
    for v in valid for k in ("question", "explanation", "topic")
) and all("[doc_" not in str(opt) for v in valid for opt in v["options"].values())
ok("run_generation strips markers from all text fields", no_markers and len(valid) == 2)
ok("run_generation scrubbed question values", valid[0]["question"] == "Question number 0?", valid[0]["question"])
ok("run_generation scrubbed option values", valid[0]["options"]["A"] == "Option A text", valid[0]["options"]["A"])
ok("run_generation preserved source-tracking fields", valid[0]["correct"] == "C")


retry_calls = {"n": 0}


def marker_then_valid(call_index, count):
    retry_calls["n"] += 1
    if retry_calls["n"] == 1:
        return [{
            "question": "[doc_1:chunk_2]",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct": "A",
            "explanation": "kept",
        }]
    return [{
        "question": "Recovered question?",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "correct": "A",
        "explanation": "kept",
    }]


valid2, _ = run_generation(marker_then_valid, requested=1, per_call=1, concurrency=1, log_label="test")
ok("marker-only question rejected then retried",
   retry_calls["n"] == 2 and len(valid2) == 1 and valid2[0]["question"] == "Recovered question?",
   f"calls={retry_calls['n']}")

tf_calls = {"n": 0}


def tf_with_marker(call_index, count):
    tf_calls["n"] += 1
    return [{
        "question_type": "true_false",
        "question": "[doc_13:chunk_8] Water boils at 100C.",
        "options": {"A": "True", "B": "False"},
        "correct": "A",
        "explanation": "[doc_13:chunk_8] Standard pressure.",
    }]


valid3, _ = run_generation(tf_with_marker, requested=1, per_call=1, concurrency=1, log_label="test")
ok("T/F question scrubbed through run_generation",
   len(valid3) == 1 and valid3[0]["question"] == "Water boils at 100C." and
   valid3[0]["explanation"] == "Standard pressure.", str(valid3))


# ---------- 5. tutor answer scrub via tutor_query ----------
class StubResponse:
    content = "Paris is the capital [doc_13:chunk_7] of France."


class StubLLM:
    def __init__(self):
        self.n = 0

    def invoke(self, prompt):
        self.n += 1
        return StubResponse()


orig_llm = rag_chain.llm
rag_chain.llm = StubLLM()
result = rag_chain.tutor_query("What is the capital of France?")
rag_chain.llm = orig_llm

ok("tutor answer markers scrubbed",
   result.get("answer") == "Paris is the capital of France.", str(result.get("answer")))
ok("tutor sources payload untouched",
   isinstance(result.get("sources"), list) and len(result["sources"]) > 0 and
   "doc_id" in result["sources"][0] and "chunk_index" in result["sources"][0],
   str(list(result.get("sources")[0].keys()) if result.get("sources") else None))

# ---------- summary ----------
failed = [n for n, p in RESULTS if not p]
print(f"\n===== {len(RESULTS) - len(failed)}/{len(RESULTS)} passed =====", flush=True)
if failed:
    print("FAILED:", *failed, sep="\n  - ", flush=True)
    sys.exit(1)
