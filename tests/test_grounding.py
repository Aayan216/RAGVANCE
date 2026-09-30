import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, r"D:\v5\RAG-p2")
os.chdir(r"D:\v5\RAG-p2")
import django

django.setup()

from rag.grounding import (
    GROUNDING_THRESHOLD,
    content_words,
    grounding_score,
    is_grounded,
    make_grounding_validator,
    normalize_text,
)
from rag.batch_generation import run_generation
from rag.mcq_generator import MCQGenerator

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


TEXT = "Glycolysis breaks glucose down into pyruvate and produces atp energy for the cell."


def make_q(n, grounded=True):
    """Distinct structurally-valid MCQ; option A grounded, option B not."""
    return {
        "question": f"Question {n}: what does glycolysis do in the cell?",
        "options": {
            "A": "It breaks glucose down into pyruvate",
            "B": "It runs the krebs cycle in mitochondria",
            "C": "It stores genetic information",
            "D": "It builds cell membranes",
        },
        "correct": "A" if grounded else "B",
        "explanation": "Because the context says so.",
        "topic": "Glycolysis",
        "source_chunks": [1],
    }


class FakeStore:
    def __init__(self, texts):
        self.texts = texts

    def get_by_id(self, fid):
        t = self.texts.get(fid)
        return {"faiss_id": fid, "text": t} if t is not None else None


# ---------- 1. normalize / content_words mirror grade_p4 ----------
ok("normalize lowercases and strips punctuation",
   normalize_text("Glycolysis, ATP!").split() == ["glycolysis", "atp"])
ok("normalize non-string -> empty", normalize_text(None) == "")
ok("content_words minlen=2 means len > 2", content_words("is of the atp") == {"the", "atp"})
ok("content_words empty", content_words("") == set())
ok("threshold is 0.6", GROUNDING_THRESHOLD == 0.6)

# ---------- 2. grounding_score / is_grounded ----------
cited = [TEXT]
ok("full answer coverage -> 1.0",
   grounding_score("produces atp energy", cited) == 1.0)
ok("exact 0.6 boundary accepted (3/5)",
   is_grounded(make_q(0), ["Glycolysis breaks glucose down into pyruvate and produces atp energy krebs"])
   and grounding_score("breaks glucose down pyruvate krebs", ["x glucose x x pyruvate krebs"]) == 0.6)
ok("0.5 coverage rejected (2/4)",
   grounding_score("glucose pyruvate krebs mitochondria", ["glucose and pyruvate here"]) == 0.5
   and not is_grounded(
       {"options": {"A": "glucose pyruvate krebs mitochondria"}, "correct": "A"},
       ["glucose and pyruvate here"]))
ok("empty answer -> 0.0", grounding_score("", cited) == 0.0)
ok("empty cited texts -> 0.0", grounding_score("glucose", []) == 0.0)
ok("case and punctuation insensitive",
   grounding_score("Glycolysis!", ["glycolysis occurs in the cell"]) == 1.0)
ok("is_grounded non-dict -> False", not is_grounded(["nope"], cited))
ok("is_grounded lowercase correct letter works",
   is_grounded({"options": {"A": "produces atp energy"}, "correct": "a"}, cited))
ok("is_grounded missing option letter -> False",
   not is_grounded({"options": {"A": "produces atp energy"}, "correct": "D"}, cited))
ok("is_grounded uses options[correct], not options[A]",
   not is_grounded({"options": {"A": "produces atp energy", "B": "stores fat"},
                    "correct": "B"}, cited))

# ---------- 3. make_grounding_validator ----------
store = FakeStore({1: TEXT})
validator = make_grounding_validator(store)
ok("validator accepts grounded question", validator(make_q(1)))
q = make_q(2, grounded=False)
ok("validator rejects ungrounded answer", not validator(q))
bad = dict(make_q(3), source_chunks=[99])
ok("validator rejects unresolvable chunk id", not validator(bad))
ok("validator rejects missing source_chunks",
   not validator({k: v for k, v in make_q(4).items() if k != "source_chunks"}))
ok("validator rejects non-list source_chunks", not validator(dict(make_q(5), source_chunks=1)))
ok("validator coerces string chunk ids", validator(dict(make_q(6), source_chunks=["1"])))
ok("validator skips bool chunk ids", not validator(dict(make_q(7), source_chunks=[True])))
ok("validator uses non-bool ids alongside bools",
   validator(dict(make_q(8), source_chunks=[True, 1])))
ok("validator rejects non-dict", not validator("not a dict"))
ok("validator rejects empty source list", not validator(dict(make_q(9), source_chunks=[])))

# ---------- 4. run_generation extra_validate ----------
calls = {"n": 0}


def reject_then_accept(i, count):
    calls["n"] += 1
    if calls["n"] == 1:
        return [make_q(100 + i, grounded=False)]
    return [make_q(100 + i + 10 * calls["n"] + j, grounded=True) for j in range(count)]


valid, stats = run_generation(
    reject_then_accept, requested=2, per_call=1, concurrency=1,
    log_label="GroundTest", extra_validate=validator)
ok("extra_validate: ungrounded rejected, run completes", len(valid) == 2, len(valid))
ok("extra_validate: rejection consumed a retry slot", stats["llm_calls"] == 3, stats)
ok("extra_validate: survivors all pass the validator", all(validator(v) for v in valid))
ok("extra_validate: survivors distinct",
   len({v["question"] for v in valid}) == 2)

try:
    run_generation(lambda i, c: [make_q(200 + i * 10 + j) for j in range(c)],
                   requested=2, per_call=1, concurrency=1,
                   log_label="GroundTest",
                   extra_validate=lambda q: (_ for _ in ()).throw(RuntimeError("boom")))
    ok("extra_validate: exception treated as reject", False, "no ValueError")
except ValueError as e:
    ok("extra_validate: exception treated as reject",
       str(e) == "Could only generate 0 of 2 questions. Please try again.", str(e))

seen_by_extra = []


def spy(q):
    seen_by_extra.append(q)
    return True


run_generation(lambda i, c: [{"question": ""}, make_q(300 + i * 10 + c)],
               requested=1, per_call=5, concurrency=1,
               log_label="GroundTest", extra_validate=spy)
ok("extra_validate runs after structural validation",
   len(seen_by_extra) == 1, len(seen_by_extra))

plain, _ = run_generation(lambda i, c: [make_q(400 + i * 10 + j) for j in range(c)],
                          requested=2, per_call=2, concurrency=1, log_label="GroundTest")
ok("no extra_validate: unchanged acceptance", len(plain) == 2)

# ---------- 5. practice wiring + integration ----------
src = open(r"D:\v5\RAG-p2\rag\mcq_generator.py", encoding="utf-8").read()
ok("practice imports make_grounding_validator", "make_grounding_validator" in src)
ok("practice passes extra_validate", "extra_validate=make_grounding_validator" in src)
ok("practice resolves rag_chain.vector_store", "self.rag_chain.vector_store" in src)
gen_src = open(r"D:\v5\RAG-p2\rag\batch_generation.py", encoding="utf-8").read()
ok("run_generation hook present", "if not extra_validate(mcq):" in gen_src)
ok("validator exceptions never crash the loop", "except Exception:" in gen_src)


class FakeChain:
    def __init__(self):
        self.vector_store = FakeStore({1: TEXT})
        self.calls = 0

    def next_practice_query(self, doc_ids=None):
        return "seed query"

    def generate_mcq_batch(self, topic=None, difficulty="medium", doc_ids=None, count=5):
        self.calls += 1
        out = []
        for j in range(count):
            n = self.calls * 10 + j
            out.append(make_q(n, grounded=(n % 3 != 2)))
        return out


gen = MCQGenerator(rag_chain=FakeChain())
result = gen.generate_practice_set(num_questions=4, difficulty="medium",
                                   topic=None, doc_ids=[13])
ok("integration: requested count produced", len(result) == 4, len(result))
ok("integration: every returned question grounded",
   all(validator(v) for v in result))
ok("integration: ungrounded questions never escape",
   all(v["correct"] == "A" for v in result),
   [v["correct"] for v in result])

print(f"\n===== {PASSED}/{PASSED + FAILED} passed =====", flush=True)
sys.exit(1 if FAILED else 0)
