import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, r"D:\v5\RAG-p2")
os.chdir(r"D:\v5\RAG-p2")
import django

django.setup()

from rag.rag_chain import TUTOR_PROMPT

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


t = TUTOR_PROMPT.template

ok("input contract unchanged", TUTOR_PROMPT.input_variables == ["context", "question"],
   TUTOR_PROMPT.input_variables)
ok("contradicted-premise rule present", "premise contradicts the context" in t)
ok("do-not-refuse instruction present", "do not refuse" in t)
ok("premise-correction answer instruction present",
   "stating what the context actually says" in t)
ok("multi-document guidance present", "several documents" in t)
ok("refuse-only-when-genuine rule present", "Refuse only when" in t)
ok("original refusal phrase kept", 'I don\'t have enough information about this.' in t)
ok("answer-only-from-context rule kept", "ONLY the provided context" in t)
ok("no-markdown rule kept", "No markdown" in t)
ok("study-assistant persona kept", "You are a study assistant" in t)

i_refuse = t.find("do not refuse")
i_fallback = t.find("I don't have enough information")
ok("contradiction rule precedes the refusal fallback",
   0 < i_refuse < i_fallback, (i_refuse, i_fallback))

rendered = TUTOR_PROMPT.format(context="CTX-CONTENT", question="Q-CONTENT")
ok("format renders context", "CTX-CONTENT" in rendered)
ok("format renders question", "Q-CONTENT" in rendered)
ok("format keeps Answer header", rendered.rstrip().endswith("Answer:"))
ok("no stray placeholder braces", "{" not in rendered.replace("{context}", "").replace("{question}", ""),
   rendered[-200:])

src = open(r"D:\v5\RAG-p2\rag\rag_chain.py", encoding="utf-8").read()
ok("tutor_query formats TUTOR_PROMPT with context+question",
   "TUTOR_PROMPT.format(context=context, question=question)" in src)
ok("tutor answer still marker-scrubbed", "scrub_citation_markers(self._extract_text(response))" in src)

print(f"\n===== {PASSED}/{PASSED + FAILED} passed =====", flush=True)
sys.exit(1 if FAILED else 0)
