import json
import os
import re
import subprocess
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, r"D:\v5\RAG-p2")
os.chdir(r"D:\v5\RAG-p2")
import django

django.setup()

from django.test import Client
from backend import views
from backend.models import MockTest, TestAttempt, TestQuestion, UserAnswer

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


# ---------- legacy stored questions: scrub at display (B12) ----------
MARK_Q = "[doc_13:chunk_7] What is acidosis?"
MARK_OPT_A = "[doc_13:chunk_7] pH below 7.35"
MARK_EXP = "Because the blood pH falls [doc_13:chunk_7]."
MARK_TOPIC = "Acidosis [doc_13:chunk_7]"

created = []
try:
    test = MockTest.objects.create(num_questions=5, difficulty="medium",
                                   timer_minutes=30, doc_ids=[13], status="completed")
    q = TestQuestion.objects.create(
        test=test, question_text=MARK_Q, question_type="mcq",
        option_a=MARK_OPT_A, option_b="pH above 7.45",
        option_c="pH 7.40 exactly", option_d="None of these",
        correct_answer="A", difficulty="medium", topic=MARK_TOPIC,
        explanation=MARK_EXP, source_chunk_ids=[7])
    att = TestAttempt.objects.create(test=test, total_questions=1, score=0,
                                     percentage=0.0, status="completed")
    ua = UserAnswer.objects.create(attempt=att, question=q,
                                   selected_option="B", is_correct=False)
    created = [ua, att, q, test]

    result = views.mock_test_service.get_attempt_result(att.id)
    ok("one wrong question", len(result["wrong"]) == 1, len(result["wrong"]))
    w = result["wrong"][0]
    ok("question_text scrubbed", w["question_text"] == "What is acidosis?", w["question_text"])
    ok("explanation scrubbed", w["explanation"] == "Because the blood pH falls.",
       w["explanation"])
    ok("option scrubbed", w["options"]["A"] == "pH below 7.35", w["options"]["A"])
    ok("topic scrubbed", w["topic"] == "Acidosis", w["topic"])
    ok("marker-free fields byte-identical",
       w["options"]["B"] == "pH above 7.45" and w["options"]["C"] == "pH 7.40 exactly")
    ok("payload keys unchanged",
       set(w.keys()) == {"question_id", "question_type", "question_text", "options",
                         "correct_answer", "selected", "is_correct", "explanation",
                         "topic", "source_chunk_ids"}, list(w.keys()))

    c = Client()
    r = c.get(f"/mock-test/{att.id}/review/")
    ok("review page 200", r.status_code == 200, r.status_code)
    body = r.content.decode()
    ok("review page has no raw marker", "doc_13:chunk_" not in body)
    ok("review shows scrubbed explanation", "Because the blood pH falls." in body)
finally:
    for obj in created:
        obj.delete()
    ok("fixture rows cleaned up",
       not MockTest.objects.filter(doc_ids=[13], status="completed",
                                   num_questions=5).exists())

# ---------- txt-aware page labels (B12) ----------
BASE = os.path.join(os.getcwd(), "frontend", "templates")


def read(path):
    with open(os.path.join(BASE, path), encoding="utf-8") as fh:
        return fh.read()


tutor = read("tutor.html")
review = read("mock_test/review.html")
practice = read("practice.html")

for name, body in (("tutor", tutor), ("review", review), ("practice", practice)):
    ok(f"{name}: has pageSuffix helper", "function pageSuffix" in body)
    ok(f"{name}: txt check present", ".endsWith('.txt')" in body)
    ok(f"{name}: label uses pageSuffix", "${pageSuffix(src, ' · Page ')}" in body)
    ok(f"{name}: raw page label removed",
       "${src.file_name} · Page ${src.page_number}" not in body)
ok("tutor: modal meta txt-aware", "pageSuffix(src, ' | Page: ')" in tutor)

# runtime check of pageSuffix via node (extracted from tutor.html)
m = re.search(r"function pageSuffix\(src, sep\) \{.*?\n\}", tutor, re.S)
ok("pageSuffix extractable", bool(m))
if m:
    script = (
        m.group(0)
        + "\nconst pdf = {file_name: 'a.pdf', page_number: 3};"
        + "\nconst txt = {file_name: 'notes.txt', page_number: 1};"
        + "\nconst nopage = {file_name: 'b.pdf'};"
        + "\nconsole.log(JSON.stringify([pageSuffix(pdf, ' \u00b7 Page '),"
        + " pageSuffix(txt, ' \u00b7 Page '), pageSuffix(nopage, ' \u00b7 Page ')]));"
    )
    proc = subprocess.run(["node", "-e", script], capture_output=True, timeout=30)
    ok("node ran", proc.returncode == 0, proc.stderr[:300].decode("utf-8", "replace"))
    if proc.returncode == 0:
        vals = json.loads(proc.stdout.decode("utf-8").strip().splitlines()[-1])
        ok("pageSuffix pdf -> ' \u00b7 Page 3'", vals[0] == " \u00b7 Page 3", vals)
        ok("pageSuffix txt -> '' (page suppressed)", vals[1] == "", vals)
        ok("pageSuffix missing page -> ''", vals[2] == "", vals)

print(f"\n===== {PASSED}/{PASSED + FAILED} passed =====", flush=True)
sys.exit(1 if FAILED else 0)
