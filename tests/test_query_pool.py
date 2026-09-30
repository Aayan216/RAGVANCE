import os
import re
import sys

sys.path.insert(0, r"D:\v5\RAG-p2")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from rag.query_pool import build_section_queries, derive_seed, select_query

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


class FakeStore:
    def __init__(self, metadata):
        self.metadata = metadata


# ---------------- derive_seed ----------------
ok("numbered heading seed",
   derive_seed("4.2 Chunking Strategy\nDetails follow about splitting text here.")
   == "4.2 Chunking Strategy",
   derive_seed("4.2 Chunking Strategy\nDetails follow about splitting text here."))

ok("chapter heading seed",
   derive_seed("Chapter 4. Varieties\nThe Crimson Glory blooms in 56 days.")
   == "Chapter 4. Varieties",
   derive_seed("Chapter 4. Varieties\nThe Crimson Glory blooms in 56 days."))

ok("title-case heading seed",
   derive_seed("Water Chemistry Basics\nThe nutrient solution must be kept stable.")
   == "Water Chemistry Basics",
   derive_seed("Water Chemistry Basics\nThe nutrient solution must be kept stable."))

sent = derive_seed("All current deployments listen on TCP port 4709 for messaging.")
ok("sentence seed kept whole", sent.startswith("All current deployments") and sent.endswith("."),
   sent)

mid = derive_seed(
    "Zephyr uses a three-layer architecture for\n"
    "message framing across unreliable links in sensor networks today."
)
ok("mid-sentence line break -> flattened sentence", " " in mid and "\n" not in mid, mid)

long_line = derive_seed(
    "This is a very long first line that runs well past the eighty character heading "
    "limit so it can never be treated as a heading of any kind in this module"
)
ok("long first line not heading -> sentence cap",
   long_line != long_line.split("\n")[0] or len(long_line) <= 122, long_line)

ok("empty text -> empty seed", derive_seed("") == "" and derive_seed("   \n  ") == "")

# ---------------- build_section_queries (fake store) ----------------
meta = [
    {"doc_id": 1, "text": "Overview of the Protocol\nIntroductory material for the protocol."},  # heading
    {"doc_id": 1, "text": "The protocol runs on TCP port 4709 in all current deployments."},  # sentence
    {"doc_id": 1, "text": "The protocol runs on TCP port 4709 in all current deployments."},  # dup -> dropped
    {"doc_id": 1, "text": "boiler"},  # <3 words -> dropped
    {"doc_id": 2, "text": "Water Chemistry Guide\nNutrient management details for growers."},  # other doc
    {"doc_id": 2, "text": "The nutrient solution must be kept between pH 5.8 and 6.2."},  # sentence
]
pool_all = build_section_queries(FakeStore(meta))
ok("heading seed in pool", "Overview of the Protocol" in pool_all, pool_all)
ok("sentence seed in pool",
   any(s.startswith("The protocol runs") for s in pool_all), pool_all)
ok("duplicate text collapsed to one seed",
   sum(1 for s in pool_all if s.startswith("The protocol runs")) == 1, pool_all)
ok("sub-3-word text dropped", not any(s == "boiler" for s in pool_all), pool_all)
ok("multi-doc pool has seeds from both docs",
   any(s.startswith("Water Chemistry") for s in pool_all)
   and any(s.startswith("The nutrient") for s in pool_all), pool_all)

pool_doc1 = build_section_queries(FakeStore(meta), doc_ids=[1])
ok("doc filter restricts pool",
   all(not s.startswith(("Water Chemistry", "The nutrient")) for s in pool_doc1)
   and len(pool_doc1) >= 2, pool_doc1)
ok("doc filter is a strict subset", len(pool_doc1) < len(pool_all), (pool_doc1, pool_all))

ok("empty store -> empty pool", build_section_queries(FakeStore([])) == [])

# no synthetic queries anywhere
bad = [s for s in pool_all if re.match(r"^topic \d+$", s.strip().lower())
       or s.strip().lower() in ("important concepts for exam", "key concepts")]
ok("no synthetic 'topic N'/generic queries", not bad, bad)

# determinism
ok("deterministic across builds",
   build_section_queries(FakeStore(meta)) == pool_all)

# cap + deterministic subsample
big = [{"doc_id": 1, "text": f"Section {i} Unique Heading {i}\nBody text number {i} here."}
       for i in range(200)]
pool_big = build_section_queries(FakeStore(big))
ok("pool capped at 50", len(pool_big) == 50, len(pool_big))
ok("cap is deterministic",
   pool_big == build_section_queries(FakeStore(big)))

# ---------------- select_query ----------------
ok("select wraps modulo", select_query(pool_all, 0) == pool_all[0]
   and select_query(pool_all, len(pool_all)) == pool_all[0])
ok("select rotates to distinct entries", select_query(pool_all, 1) != pool_all[0])
ok("select on empty -> None", select_query([], 0) is None)

# ---------------- rotation counters (RAGChain wiring) ----------------
import itertools

from rag.rag_chain import RAGChain

rc = RAGChain.__new__(RAGChain)
rc.vector_store = FakeStore(meta)  # 4 seeds for doc_ids [1, 2]
rc._mock_seed_counter = itertools.count()
rc._practice_seed_counter = itertools.count()

p1 = rc.next_practice_query([1, 2])
p2 = rc.next_practice_query([1, 2])  # a second HTTP request must NOT restart at 0
p3 = rc.next_practice_query([1, 2])
ok("practice rotation advances across requests",
   None not in (p1, p2, p3) and len({p1, p2, p3}) == 3, (p1, p2, p3))

rc2 = RAGChain.__new__(RAGChain)
rc2.vector_store = FakeStore(meta)
rc2._practice_seed_counter = itertools.count()
seq = [rc2.next_practice_query([1, 2]) for _ in range(9)]
ok("practice rotation cycles the pool of 4 after 4 steps",
   seq[4] == seq[0] and seq[5] == seq[1] and len(set(seq[:4])) == 4, seq)

m1 = rc._next_mock_query([1, 2])
m2 = rc._next_mock_query([1, 2], offset_half=True)
ok("mock rotation advances and T/F offset picks a different seed",
   m1 is not None and m2 is not None and m1 != m2, (m1, m2))

rc_empty = RAGChain.__new__(RAGChain)
rc_empty.vector_store = FakeStore([])
rc_empty._practice_seed_counter = itertools.count()
rc_empty._mock_seed_counter = itertools.count()
ok("empty pool -> None (fallback stays in rag_chain)",
   rc_empty.next_practice_query([1]) is None and rc_empty._next_mock_query([1]) is None)

# ---------------- integration: real corpus ----------------
from backend import views  # noqa: E402

real_pool = build_section_queries(views.vector_store)
ok("real corpus yields a non-empty pool", len(real_pool) >= 1, len(real_pool))
all_text = " ".join(
    re.sub(r"\s+", " ", (m.get("text") or "").lower()) for m in views.vector_store.metadata
)
missing = [s for s in real_pool if re.sub(r"\s+", " ", s.lower()) not in all_text]
ok("every real seed comes from corpus text", not missing, missing[:3])
ok("real pool has no synthetic queries",
   not [s for s in real_pool if re.match(r"^topic \d+$", s.strip().lower())
        or s.strip().lower() in ("important concepts for exam", "key concepts")],
   [s for s in real_pool[:5]])

print(f"\n{PASSED}/{PASSED + FAILED} passed", flush=True)
sys.exit(1 if FAILED else 0)
