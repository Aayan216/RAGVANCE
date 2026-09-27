import os
import sys

sys.path.insert(0, r"D:\v5\RAG-p2")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.test import Client
from django.contrib.staticfiles import finders

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


c = Client()

PAGES = [
    ("/", "upload", ["uploadForm", 'enctype="multipart/form-data"']),
    ("/tutor/", "tutor", ["questionForm", "clearChatBtn"]),
    ("/practice/", "practice", ["generateBtn", "doc-checkbox"]),
    ("/mock-test/", "settings", ["selectNum", "btn-sm num-btn"]),
    ("/mock-test/terminated/", "terminated", []),
]

for url, name, markers in PAGES:
    r = c.get(url)
    body = r.content.decode()
    ok(f"GET {url} -> 200", r.status_code == 200, r.status_code)
    for m in markers:
        ok(f"{name}: contains '{m}'", m in body)
    # navbar on every page
    ok(f"{name}: nav Upload", 'href="/"' in body or ">Upload<" in body.replace(" ", ""), body[:0])
    ok(f"{name}: nav Tutor", 'href="/tutor/"' in body)
    ok(f"{name}: nav Practice", 'href="/practice/"' in body)
    ok(f"{name}: nav Mock Test", 'href="/mock-test/"' in body)
    # dark mode markers
    ok(f"{name}: theme init script", "ragvance-theme" in body)
    ok(f"{name}: themeToggle button", 'id="themeToggle"' in body)
    ok(f"{name}: main.js included", "js/main.js" in body)
    # footer
    ok(f"{name}: footer", "BY TESSERACT" in body)

# settings page: no question-type UI (regression)
r = c.get("/mock-test/")
body = r.content.decode()
ok("settings: no type buttons", "type-btn" not in body and "Question Type" not in body)
ok("settings: num buttons 5/10/20/30/50 practice-style count for mock = 4", body.count("btn-sm num-btn") == 4, body.count("btn-sm num-btn"))

# tutor/practice render extra markers
r = c.get("/tutor/")
body = r.content.decode()
ok("tutor: chat form action endpoint", "tutor/ask" in body)
r = c.get("/practice/")
body = r.content.decode()
ok("practice: num buttons = 5 (5,10,20,30,50)", body.count("btn-sm num-btn") == 5, body.count("btn-sm num-btn"))
ok("practice: no question-type UI", "type-btn" not in body)

# static assets resolvable via staticfiles finder
ok("static js/main.js found", finders.find("js/main.js") is not None)
ok("static css/style.css found", finders.find("css/style.css") is not None)
ok("static logo found", finders.find("images/FullLogo_Transparent_NoBuffer.png") is not None)

# HTTP method guards
ok("GET /process/<id>/ -> 405", c.get("/process/1/").status_code == 405)
ok("GET /delete/<id>/ -> 405", c.get("/delete/1/").status_code == 405)
ok("GET /tutor/ask/ -> 405", c.get("/tutor/ask/").status_code == 405)
ok("GET /practice/generate/ -> 405", c.get("/practice/generate/").status_code == 405)
ok("GET /practice/submit/ -> 405", c.get("/practice/submit/").status_code == 405)
ok("GET /mock-test/terminate/ -> 405", c.get("/mock-test/terminate/").status_code == 405)

# 404s
ok("GET bogus attempt result -> 404", c.get("/mock-test/999999/result/").status_code == 404)
ok("GET bogus attempt analysis -> 404", c.get("/mock-test/999999/analysis/").status_code == 404)
ok("GET bogus attempt review -> 404", c.get("/mock-test/999999/review/").status_code == 404)
ok("GET bogus delete doc -> 404", c.post("/delete/999999/").status_code == 404)

print(f"\n{PASSED}/{PASSED + FAILED} passed", flush=True)
sys.exit(1 if FAILED else 0)
