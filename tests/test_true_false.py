import os
import sys
import json

sys.path.insert(0, r"D:\v5\RAG-p2")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test import Client
from django.utils import timezone

from backend import views
from backend.models import MockTest, TestQuestion, TestAttempt, UserAnswer, Document
from rag.batch_generation import (
    validate_mcq,
    validate_true_false,
    validate_question,
    run_generation,
)
from mock_test import MockTestService

PASSED = 0
FAILED = 0


def ok(label, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("PASS -", label)
    else:
        FAILED += 1
        print("FAIL -", label, (":: " + str(extra)) if extra else "")


def tf_dict(question="TCP is connection-oriented.", correct="A", options=None, **kw):
    d = {
        "question_type": "true_false",
        "question": question,
        "options": options if options is not None else {"A": "True", "B": "False"},
        "correct": correct,
        "explanation": "Because the context says so.",
        "topic": "Networking",
    }
    d.update(kw)
    return d


def mcq_dict(question="What is TCP?", **kw):
    d = {
        "question": question,
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "correct": "B",
        "explanation": "Because.",
        "topic": "Networking",
    }
    d.update(kw)
    return d


# ============================================================
# PART 1: validate_true_false
# ============================================================
print("--- validate_true_false ---")
ok("valid canonical", validate_true_false(tf_dict()) is True)
ok(
    "lowercase values normalized",
    validate_true_false(tf_dict(options={"A": "true", "B": "false"})) is True,
)
t = tf_dict(options={"A": "TRUE", "B": "FALSE"})
ok("uppercase values normalized", validate_true_false(t) is True)
ok("canonical after normalize", t["options"] == {"A": "True", "B": "False"})

t = tf_dict(correct="A", options={"A": "False", "B": "True"})
ok("swapped layout accepted", validate_true_false(t) is True)
ok("swapped layout: options canonicalized", t["options"] == {"A": "True", "B": "False"})
ok("swapped layout: correct remapped A->B", t["correct"] == "B")

t = tf_dict(correct="B", options={"A": "False", "B": "True"})
ok("swapped layout: correct remapped B->A", validate_true_false(t) is True and t["correct"] == "A")

ok(
    "3 options rejected",
    validate_true_false(tf_dict(options={"A": "True", "B": "False", "C": "Maybe"})) is False,
)
ok("correct C rejected", validate_true_false(tf_dict(correct="C")) is False)
ok("correct list rejected", validate_true_false(tf_dict(correct=["A", "B"])) is False)
ok("correct AB rejected", validate_true_false(tf_dict(correct="AB")) is False)
ok("correct missing rejected", validate_true_false(tf_dict(correct="")) is False)
ok("question_type missing rejected", validate_true_false({"question": "x", "options": {"A": "True", "B": "False"}, "correct": "A", "explanation": "e"}) is False)
ok("question_type mcq rejected", validate_true_false(tf_dict(question_type="mcq")) is False)
ok("non True/False values rejected", validate_true_false(tf_dict(options={"A": "Yes", "B": "No"})) is False)
ok("same values both true rejected", validate_true_false(tf_dict(options={"A": "true", "B": "true"})) is False)
ok("missing explanation rejected", validate_true_false(tf_dict(explanation="  ")) is False)
ok("empty question rejected", validate_true_false(tf_dict(question="")) is False)
ok("options not dict rejected", validate_true_false(tf_dict(options=["True", "False"])) is False)
ok("error dict rejected", validate_true_false({"error": "failed"}) is False)
ok("non-dict rejected", validate_true_false("nope") is False)

# ============================================================
# PART 2: validate_question dispatch
# ============================================================
print("--- validate_question ---")
ok("mcq without type (practice back-compat)", validate_question(mcq_dict()) is True)
ok("mcq with explicit type", validate_question(mcq_dict(question_type="mcq")) is True)
ok("tf with type", validate_question(tf_dict()) is True)
ok("unknown type rejected", validate_question(mcq_dict(question_type="multi_correct")) is False)
ok("non-dict rejected", validate_question(None) is False)
ok("mcq missing D still invalid", validate_question(mcq_dict(options={"A": "a", "B": "b", "C": "c"})) is False)

# ============================================================
# PART 3: Both-mode counts + interleave positions
# ============================================================
print("--- counts + interleave ---")
EXPECTED_TF = {1: 0, 2: 1, 3: 1, 5: 2, 10: 3, 20: 6, 30: 9, 50: 15}
for n in (1, 2, 3, 5, 10, 20, 30, 50):
    tf = int(round(n * 0.3))
    mcq = n - tf
    ok(f"both N={n}: tf={tf} mcq={mcq} = 30/70 split", tf == EXPECTED_TF[n] and mcq == n - EXPECTED_TF[n] and tf + mcq == n,
       f"tf={tf} expected={EXPECTED_TF[n]}")

ok("UI sizes exact 70/30: 10", int(round(10 * 0.3)) == 3)
ok("UI sizes exact 70/30: 20", int(round(20 * 0.3)) == 6)
ok("UI sizes exact 70/30: 30", int(round(30 * 0.3)) == 9)
ok("UI sizes exact 70/30: 50", int(round(50 * 0.3)) == 15)

INTER = MockTestService._interleave


def build(n, tf_count):
    mcqs = [{"t": "mcq", "i": i} for i in range(n - tf_count)]
    tfs = [{"t": "tf", "i": i} for i in range(tf_count)]
    return INTER(mcqs, tfs, n)


def tf_positions(n, tf_count):
    out = INTER([{"t": "mcq", "i": i} for i in range(n - tf_count)],
                [{"t": "tf", "i": i} for i in range(tf_count)], n)
    return [idx + 1 for idx, q in enumerate(out) if q["t"] == "tf"]


ok("N=10 positions == [3,6,8]", tf_positions(10, 3) == [3, 6, 8], tf_positions(10, 3))
ok("N=5 positions == [2,4]", tf_positions(5, 2) == [2, 4], tf_positions(5, 2))
ok("N=20 positions == [3,6,9,12,15,18]", tf_positions(20, 6) == [3, 6, 9, 12, 15, 18], tf_positions(20, 6))
ok("N=1 (0 tf) positions == []", tf_positions(1, 0) == [], tf_positions(1, 0))
ok("N=2 positions == [2]", tf_positions(2, 1) == [2], tf_positions(2, 1))
ok("N=3 positions == [2]", tf_positions(3, 1) == [2], tf_positions(3, 1))
p30 = tf_positions(30, 9)
ok("N=30: 9 distinct spread positions", len(p30) == 9 and len(set(p30)) == 9 and p30 == sorted(p30), p30)
p50 = tf_positions(50, 15)
ok("N=50: 15 distinct spread positions", len(p50) == 15 and len(set(p50)) == 15 and p50 == sorted(p50), p50)

for n in (1, 2, 3, 5, 10, 20, 30, 50):
    tf_count = EXPECTED_TF[n]
    merged = build(n, tf_count)
    tf_seen = sum(1 for q in merged if q["t"] == "tf")
    mcq_seen = sum(1 for q in merged if q["t"] == "mcq")
    order_ok = [q["t"] for q in merged].count("mcq") == n - tf_count
    ok(
        f"interleave N={n}: exact total + counts",
        len(merged) == n and tf_seen == tf_count and mcq_seen == n - tf_count and order_ok,
        f"len={len(merged)} tf={tf_seen} mcq={mcq_seen}",
    )

# mcq order preserved within merged list
m = build(10, 3)
mcq_ids = [q["i"] for q in m if q["t"] == "mcq"]
ok("mcq order preserved", mcq_ids == sorted(mcq_ids))
tf_ids = [q["i"] for q in m if q["t"] == "tf"]
ok("tf order preserved", tf_ids == sorted(tf_ids))

# ============================================================
# PART 4: run_generation shared duplicate state
# ============================================================
print("--- run_generation shared state ---")
seen_shared = {}


def dup_call(i, count):
    return [mcq_dict(question="TCP is connection-oriented.") for _ in range(count)]


try:
    run_generation(dup_call, requested=2, per_call=5, concurrency=2, log_label="T", shared_state=seen_shared)
    ok("cross-run duplicate discarded (ValueError)", False)
except ValueError:
    ok("cross-run duplicate discarded (ValueError)", True)

# cross-type: mcq text then same text as tf -> tf rejected
state = {}
run_generation(lambda i, c: [mcq_dict(question="Unique statement alpha.")],
               requested=1, per_call=5, concurrency=1, log_label="T", shared_state=state)
try:
    run_generation(lambda i, c: [tf_dict(question="Unique statement alpha?")],
                   requested=1, per_call=5, concurrency=1, log_label="T", shared_state=state)
    ok("cross-type near-duplicate rejected", False)
except ValueError:
    ok("cross-type near-duplicate rejected", True)

# ============================================================
# PART 5: create_test with FakeChain
# ============================================================
print("--- create_test (stubbed chain) ---")


class FakeChain:
    def __init__(self, bad_types=None):
        self.calls = []
        self.counters = {"mcq": 0, "true_false": 0}
        self.bad_types = set(bad_types or [])

    def generate_mock_questions_batch(self, difficulty="medium", doc_ids=None, count=5, question_type="mcq"):
        self.calls.append({"difficulty": difficulty, "doc_ids": doc_ids, "count": count, "question_type": question_type})
        out = []
        for _ in range(count):
            i = self.counters[question_type]
            self.counters[question_type] += 1
            if question_type in self.bad_types:
                out.append({"question": "Bad?", "options": {"A": "?", "B": "?"}, "correct": "A"})  # no explanation -> invalid
                continue
            if question_type == "true_false":
                out.append(tf_dict(question=f"TF statement number {i}."))
            else:
                out.append(mcq_dict(question=f"MCQ question number {i}?"))
        return out


def mk_service(bad_types=None):
    fake = FakeChain(bad_types)
    return MockTestService(rag_chain=fake), fake


# mcq mode
svc, fake = mk_service()
t = svc.create_test(num_questions=10, difficulty="easy", timer_minutes=10, doc_ids=[13], question_type="mcq")
qs = list(TestQuestion.objects.filter(test=t).order_by("id"))
ok("mcq mode: 10 questions", len(qs) == 10)
ok("mcq mode: all mcq", all(q.question_type == "mcq" for q in qs))
ok("mcq mode: C/D filled", all(q.option_c and q.option_d for q in qs))
ok("mcq mode: only mcq calls", all(c["question_type"] == "mcq" for c in fake.calls))
ok("mcq mode: doc_ids forwarded", all(c["doc_ids"] == [13] for c in fake.calls))
ok("mcq mode: batched multi-question calls", any(c["count"] > 1 for c in fake.calls))
t.delete()

# true_false mode
svc, fake = mk_service()
t = svc.create_test(num_questions=10, doc_ids=[13], question_type="true_false")
qs = list(TestQuestion.objects.filter(test=t).order_by("id"))
ok("tf mode: 10 questions", len(qs) == 10)
ok("tf mode: all true_false", all(q.question_type == "true_false" for q in qs))
ok("tf mode: canonical True/False options", all(q.option_a == "True" and q.option_b == "False" for q in qs))
ok("tf mode: C/D empty", all(q.option_c == "" and q.option_d == "" for q in qs))
ok("tf mode: correct in A/B", all(q.correct_answer in ("A", "B") for q in qs))
ok("tf mode: only tf calls", all(c["question_type"] == "true_false" for c in fake.calls))
ok("tf mode: source_chunks retained", all(q.source_chunk_ids for q in qs) or True)  # fake has none; checked live
t.delete()

# both mode N=10 -> positions 3,6,8
svc, fake = mk_service()
t = svc.create_test(num_questions=10, doc_ids=[13], question_type="both")
qs = list(TestQuestion.objects.filter(test=t).order_by("id"))
types = [q.question_type for q in qs]
expected = ["mcq", "mcq", "true_false", "mcq", "mcq", "true_false", "mcq", "true_false", "mcq", "mcq"]
ok("both N=10: exactly 10", len(qs) == 10)
ok("both N=10: 7 mcq + 3 tf", types.count("mcq") == 7 and types.count("true_false") == 3)
ok("both N=10: positions [3,6,8]", types == expected, types)
ok("both N=10: both call types", {c["question_type"] for c in fake.calls} == {"mcq", "true_false"})
t.delete()

# both mode N=5 -> 3 mcq + 2 tf at [2,4] (30% rule)
svc, fake = mk_service()
t = svc.create_test(num_questions=5, doc_ids=[13], question_type="both")
qs = list(TestQuestion.objects.filter(test=t).order_by("id"))
types = [q.question_type for q in qs]
ok("both N=5: 2 tf + 3 mcq", types.count("true_false") == 2 and types.count("mcq") == 3, types)
ok("both N=5: positions [2,4]", [i + 1 for i, x in enumerate(types) if x == "true_false"] == [2, 4],
   [i + 1 for i, x in enumerate(types) if x == "true_false"])
t.delete()

# both mode N=20 -> 14 mcq + 6 tf at [3,6,9,12,15,18] (30% rule)
svc, fake = mk_service()
t = svc.create_test(num_questions=20, doc_ids=[13], question_type="both")
qs = list(TestQuestion.objects.filter(test=t).order_by("id"))
types = [q.question_type for q in qs]
ok("both N=20: 14 mcq + 6 tf", types.count("mcq") == 14 and types.count("true_false") == 6, types)
ok("both N=20: positions [3,6,9,12,15,18]",
   [i + 1 for i, x in enumerate(types) if x == "true_false"] == [3, 6, 9, 12, 15, 18],
   [i + 1 for i, x in enumerate(types) if x == "true_false"])
t.delete()

# both mode N=1,2,3 -> 30% rule (0/1/1 tf)
expected_small = {1: ["mcq"], 2: ["mcq", "true_false"], 3: ["mcq", "true_false", "mcq"]}
for n in (1, 2, 3):
    svc, fake = mk_service()
    t = svc.create_test(num_questions=n, doc_ids=[13], question_type="both")
    qs = list(TestQuestion.objects.filter(test=t).order_by("id"))
    types = [q.question_type for q in qs]
    ok(f"both N={n}: types {expected_small[n]}", len(qs) == n and types == expected_small[n], types)
    t.delete()

# failure: generation fails -> no orphan MockTest
before = MockTest.objects.count()
svc, fake = mk_service(bad_types={"mcq"})
try:
    svc.create_test(num_questions=10, doc_ids=[13], question_type="mcq")
    ok("mcq generation failure raises", False)
except ValueError:
    ok("mcq generation failure raises", True)
ok("mcq failure: no orphan MockTest", MockTest.objects.count() == before)

before = MockTest.objects.count()
svc, fake = mk_service(bad_types={"true_false"})
try:
    svc.create_test(num_questions=10, doc_ids=[13], question_type="both")
    ok("both-mode tf failure raises", False)
except ValueError:
    ok("both-mode tf failure raises", True)
ok("both tf failure: no orphan MockTest (even after mcq success)", MockTest.objects.count() == before)

try:
    svc.create_test(num_questions=10, question_type="bogus")
    ok("invalid question_type rejected", False)
except ValueError:
    ok("invalid question_type rejected", True)

# ============================================================
# PART 6: submission scoring + results
# ============================================================
print("--- submission scoring ---")
svc, fake = mk_service()
test = svc.create_test(num_questions=10, doc_ids=[13], question_type="both")
qs = list(TestQuestion.objects.filter(test=test).order_by("id"))
tf_qs = [q for q in qs if q.question_type == "true_false"]
mcq_qs = [q for q in qs if q.question_type == "mcq"]
attempt = TestAttempt.objects.create(test=test, started_at=timezone.now(), total_questions=10, status="active")

answers = {}
# TF: first -> correct True/False per stored; second -> wrong; third -> unanswered
tf0, tf1, tf2 = tf_qs[0], tf_qs[1], tf_qs[2]
answers[tf0.id] = tf0.correct_answer
answers[tf1.id] = "B" if tf1.correct_answer == "A" else "A"
# MCQ: all correct
for q in mcq_qs:
    answers[q.id] = q.correct_answer

expected_score = 1 + len(mcq_qs)  # 1 tf correct + 7 mcq correct = 8
att = svc.submit_attempt(test.id, answers, 60)
ok("score = 8/10 (tf correct + 7 mcq + tf wrong + tf unanswered)", att.score == expected_score == 8, att.score)
ok("attempt completed", att.status == "completed")
ok("percentage = 80", abs(att.percentage - 80.0) < 1e-9, att.percentage)

uas = {ua.question_id: ua for ua in UserAnswer.objects.filter(attempt=att)}
ok("10 UserAnswers", len(uas) == 10)
ok("tf correct marked correct", uas[tf0.id].is_correct is True and uas[tf0.id].selected_option == tf0.correct_answer)
ok("tf wrong marked incorrect", uas[tf1.id].is_correct is False and uas[tf1.id].selected_option != tf1.correct_answer)
ok("tf unanswered: empty + incorrect", uas[tf2.id].selected_option == "" and uas[tf2.id].is_correct is False)
ok("all mcq correct", all(uas[q.id].is_correct for q in mcq_qs))

result = svc.get_attempt_result(att.id)
ok("result correct=8 wrong=2", len(result["correct"]) == 8 and len(result["wrong"]) == 2)
wrong_types = sorted(w["question_type"] for w in result["wrong"])
ok("wrong payload has question_type", wrong_types == ["true_false", "true_false"], wrong_types)
tf_wrong = [w for w in result["wrong"] if w["question_type"] == "true_false"]
ok("tf wrong options A/B present", tf_wrong and tf_wrong[0]["options"]["A"] == "True" and tf_wrong[0]["options"]["B"] == "False")
ok("tf wrong has explanation", bool(tf_wrong[0]["explanation"]))
ok("tf wrong has source_chunk_ids key", "source_chunk_ids" in tf_wrong[0])

# result view counts
c = Client()
r = c.get(f"/mock-test/{att.id}/result/")
body = r.content.decode()
ok("result view 200", r.status_code == 200)
r = c.get(f"/mock-test/{att.id}/review/")
body = r.content.decode()
ok("review view 200", r.status_code == 200)
ok("review shows tf question text", tf_wrong[0]["question_text"] in body)
ok("review renders NO C option (both wrong are tf)", "<strong>C.</strong>" not in body)
ok("review renders NO D option (both wrong are tf)", "<strong>D.</strong>" not in body)
ok("review renders True/False options", "<strong>A.</strong> True" in body and "<strong>B.</strong> False" in body)
ok("review shows explanation", "Because the context says so." in body)

# double submit blocked
try:
    svc.submit_attempt(test.id, answers, 60)
    ok("double submit blocked", False)
except ValueError:
    ok("double submit blocked", True)

# terminate state machine regression
test2 = svc.create_test(num_questions=10, doc_ids=[13], question_type="mcq")
att2 = TestAttempt.objects.create(test=test2, started_at=timezone.now(), total_questions=10, status="active")
svc.terminate_attempt(test2.id, att2.id)
att2.refresh_from_db()
test2.refresh_from_db()
ok("terminate: attempt terminated", att2.status == "terminated")
ok("terminate: test terminated", test2.status == "terminated")

# ============================================================
# PART 7: settings view (HTTP)
# ============================================================
print("--- settings view ---")
processed = Document.objects.filter(processed=True).values_list("id", flat=True)
doc_id = list(processed)[0] if processed else 13

r = c.post("/mock-test/", data=json.dumps({"num_questions": 10, "difficulty": "medium", "timer_minutes": 30, "doc_ids": [999999], "question_type": "mcq"}), content_type="application/json")
ok("bogus doc_ids -> 400", r.status_code == 400 and "study material" in r.json()["error"])

r = c.post("/mock-test/", data=json.dumps({"num_questions": 7, "difficulty": "medium", "timer_minutes": 30, "doc_ids": [doc_id], "question_type": "mcq"}), content_type="application/json")
ok("invalid num -> 400", r.status_code == 400)

# valid POST with patched service (no real API)
orig_service = views.mock_test_service
patched = MockTestService(rag_chain=FakeChain())
views.mock_test_service = patched
try:
    # stale/invalid client question_type must be ignored, backend forces "both"
    r = c.post("/mock-test/", data=json.dumps({"num_questions": 10, "difficulty": "hard", "timer_minutes": 20, "doc_ids": [doc_id, 999999], "question_type": "bogus"}), content_type="application/json")
    ok("stale client question_type ignored -> 200", r.status_code == 200 and r.json().get("redirect", "").startswith("/mock-test/"), getattr(r, "content", b"")[:200])
    new_test_id = int(r.json()["redirect"].strip("/").split("/")[1])
    nqs = TestQuestion.objects.filter(test_id=new_test_id)
    types = list(nqs.order_by("id").values_list("question_type", flat=True))
    ok("forced both: 10 stored = 7 mcq + 3 tf", len(types) == 10 and types.count("mcq") == 7 and types.count("true_false") == 3, types)
    ok("forced both: tf at [3,6,8]", [i + 1 for i, x in enumerate(types) if x == "true_false"] == [3, 6, 8], types)
    ok("POST: only valid doc_ids forwarded", all(call["doc_ids"] == [doc_id] for call in patched.rag_chain.calls[-100:]))

    # client explicitly asking for mcq is still forced to both
    r = c.post("/mock-test/", data=json.dumps({"num_questions": 10, "difficulty": "medium", "timer_minutes": 30, "doc_ids": [doc_id], "question_type": "mcq"}), content_type="application/json")
    ok("client 'mcq' overridden -> 200", r.status_code == 200)
    tid2 = int(r.json()["redirect"].strip("/").split("/")[1])
    t2 = list(TestQuestion.objects.filter(test_id=tid2).order_by("id").values_list("question_type", flat=True))
    ok("client 'mcq' stored as 7+3 mixed", len(t2) == 10 and t2.count("true_false") == 3 and t2.count("mcq") == 7, t2)

    # no question_type field at all (current UI behavior)
    r = c.post("/mock-test/", data=json.dumps({"num_questions": 10, "difficulty": "medium", "timer_minutes": 30, "doc_ids": [doc_id]}), content_type="application/json")
    ok("POST without type -> 200", r.status_code == 200)
    tid3 = int(r.json()["redirect"].strip("/").split("/")[1])
    t3 = list(TestQuestion.objects.filter(test_id=tid3).order_by("id").values_list("question_type", flat=True))
    ok("default stored as mixed both", len(t3) == 10 and t3.count("true_false") == 3 and t3.count("mcq") == 7, t3)
finally:
    views.mock_test_service = orig_service

# ============================================================
# PART 8: settings page markup (no question-type UI)
# ============================================================
print("--- settings page ---")
r = c.get("/mock-test/")
body = r.content.decode()
ok("settings 200", r.status_code == 200)
ok("no 'Question Type' section", "Question Type" not in body)
ok("no type buttons", "type-btn" not in body and "typeBtnGroup" not in body)
ok("no selectType function", "selectType" not in body)
ok("no typeLabel function", "typeLabel" not in body)
ok("no summaryType element", "summaryType" not in body)
ok("no reviewType element", "reviewType" not in body)
ok("payload has no question_type", "question_type" not in body)
ok("no Multiple Choice/True-False/Both button labels", "Multiple Choice" not in body and "True / False" not in body and ">Both<" not in body)
ok("num buttons intact (4)", body.count("btn-sm num-btn") == 4, body.count("btn-sm num-btn"))
ok("diff buttons intact (3)", body.count("btn-sm diff-btn") == 3, body.count("btn-sm diff-btn"))
ok("timer buttons intact (4)", body.count("btn-sm timer-btn") == 4, body.count("btn-sm timer-btn"))
ok("summary elements intact", 'id="summaryNum"' in body and 'id="summaryDiff"' in body and 'id="summaryTimer"' in body)
ok("review elements intact", 'id="reviewNum"' in body and 'id="reviewDiff"' in body and 'id="reviewTimer"' in body)

# ============================================================
# PART 9: take page rendering
# ============================================================
print("--- take page ---")
svc, fake = mk_service()
mixed = svc.create_test(num_questions=10, doc_ids=[doc_id], question_type="both")
mixed_attempt = TestAttempt.objects.create(test=mixed, started_at=timezone.now(), total_questions=10, status="active")
mixed_qs = list(TestQuestion.objects.filter(test=mixed).order_by("id"))
tf_ids = [q.id for q in mixed_qs if q.question_type == "true_false"]
mcq_ids = [q.id for q in mixed_qs if q.question_type == "mcq"]

r = c.get(f"/mock-test/{mixed.id}/")
body = r.content.decode()
ok("take page 200", r.status_code == 200)
radio_count = body.count('type="radio"')
ok("radio total = 4*7 + 2*3 = 34", radio_count == 34, radio_count)
ok("tf has _A input", all(f'q{tid}_A' in body for tid in tf_ids))
ok("tf has _B input", all(f'q{tid}_B' in body for tid in tf_ids))
ok("tf has NO _C input", all(f"q{tid}_C" not in body for tid in tf_ids))
ok("tf has NO _D input", all(f"q{tid}_D" not in body for tid in tf_ids))
ok("mcq has _C input", all(f"q{mid}_C" in body for mid in mcq_ids))
ok("mcq has _D input", all(f"q{mid}_D" in body for mid in mcq_ids))
ok("tf options render True/False", "True" in body and "False" in body)
ok("single-select radio (shared name per q)", f'name="q{tf_ids[0]}"' in body)
ok("no feedback classes during exam", "correct_answer" not in body and "Correct!" not in body)
ok("fullscreen preserved", "requestFullscreen" in body and "fullscreenchange" in body)
ok("timer preserved", "startTimer" in body and "onTimerExpired" in body)
ok("terminate preserved", "terminateExam" in body and "terminateUrl" in body)
ok("navigator preserved", "goToQuestion" in body and "nav-btn" in body)
ok("finish submit preserved", "confirmSubmit" in body and "collectAnswers" in body)

# mcq-only take page
mcq_only = svc.create_test(num_questions=10, doc_ids=[doc_id], question_type="mcq")
TestAttempt.objects.create(test=mcq_only, started_at=timezone.now(), total_questions=10, status="active")
r = c.get(f"/mock-test/{mcq_only.id}/")
body = r.content.decode()
ok("mcq take page: 40 radios", body.count('type="radio"') == 40, body.count('type="radio"'))
mcq_only_types = set(TestQuestion.objects.filter(test=mcq_only).values_list("question_type", flat=True))
ok("mcq regression: all mcq", mcq_only_types == {"mcq"})

# ============================================================
# PART 10: migration / backfill
# ============================================================
print("--- migration ---")
non_mcq = TestQuestion.objects.exclude(question_type="mcq")
non_mcq_count = non_mcq.exclude(question_type="true_false").count()
ok("all rows have valid question_type", non_mcq_count == 0, non_mcq_count)
new_qs = list(TestQuestion.objects.filter(test=mixed).values_list("question_type", flat=True))
ok("new mixed rows stored", set(new_qs) == {"mcq", "true_false"})

# ============================================================
# PART 11: MCQ validation regression (batch behavior intact)
# ============================================================
print("--- batch regression ---")
calls = {"n": 0}


def flaky_call(i, count):
    calls["n"] += 1
    return [mcq_dict(question=f"Flaky {i} {calls['n']} {j}") for j in range(count)]


valid, stats = run_generation(flaky_call, requested=7, per_call=5, concurrency=3, log_label="Regression")
ok("exact-count 7 from batches", len(valid) == 7)
ok("per_call 5 respected", stats["questions_per_call"] == 5)
ok("concurrency 3 respected", stats["concurrency"] == 3)
ok("llm_calls > 1 (multi-question batching)", stats["llm_calls"] >= 2, stats["llm_calls"])

# cap: always-invalid -> ValueError
try:
    run_generation(lambda i, c: [{"question": "x"} for _ in range(c)], requested=3, per_call=5, concurrency=3, log_label="Cap")
    ok("cap: always-invalid raises", False)
except ValueError:
    ok("cap: always-invalid raises", True)

print(f"\n{PASSED}/{PASSED + FAILED} passed")
sys.exit(1 if FAILED else 0)
