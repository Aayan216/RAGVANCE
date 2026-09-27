import os
import sys

sys.path.insert(0, r"D:\v5\RAG-p2")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from backend import views
from backend.models import Chunk, Document

PASSED = 0
FAILED = 0
DOC = None


def ok(label, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("PASS -", label, flush=True)
    else:
        FAILED += 1
        print("FAIL -", label, (":: " + str(extra)) if extra else "", flush=True)


PHRASE = "Quantum Flux Capacitor Regulation Protocol"
CONTENT = (
    f"{PHRASE} is a fictional engineering standard used for regression testing.\n\n"
    + " ".join(f"Paragraph {i} describes calibration steps, voltage thresholds, "
              f"and maintenance windows for the flux capacitor assembly line {i}."
              for i in range(30))
)

c = Client()

try:
    # ---------- upload ----------
    up = SimpleUploadedFile("ragvance_regression_fixture.txt", CONTENT.encode("utf-8"), content_type="text/plain")
    r = c.post("/", {"title": "RegressionFixture", "file": up})
    ok("upload POST -> 302 redirect", r.status_code == 302, r.status_code)
    DOC = Document.objects.filter(title="RegressionFixture").first()
    ok("Document row created", DOC is not None)
    if not DOC:
        raise SystemExit("fixture missing")
    ok("file_type detected as txt", DOC.file_type == "txt", DOC.file_type)
    ok("starts unprocessed", DOC.processed is False)
    file_path = DOC.file.path
    ok("file exists on disk", os.path.exists(file_path), file_path)

    # upload page lists it
    body = c.get("/").content.decode()
    ok("upload page lists new doc", "RegressionFixture" in body)

    # ---------- process ----------
    ntotal_before = len(views.vector_store)
    r = c.post(f"/process/{DOC.id}/")
    data = r.json()
    ok("process -> 200 success", r.status_code == 200 and data.get("status") == "success", data)
    chunks_n = data.get("chunks", 0)
    ok("chunks extracted > 0", chunks_n > 0, chunks_n)

    DOC.refresh_from_db()
    ok("doc marked processed", DOC.processed is True)
    db_chunks = Chunk.objects.filter(document=DOC).count()
    ok("Chunk rows == chunk_count", db_chunks == DOC.chunk_count == chunks_n, (db_chunks, DOC.chunk_count, chunks_n))
    ok("FAISS grew by chunks", len(views.vector_store) == ntotal_before + chunks_n,
       (ntotal_before, len(views.vector_store), chunks_n))

    # re-process idempotent
    r = c.post(f"/process/{DOC.id}/")
    ok("re-process -> already_processed", r.json().get("status") == "already_processed", r.json())

    # ---------- RAG retrieval ----------
    res = views.rag_chain._retrieve_context(PHRASE, doc_ids=[DOC.id])
    ok("doc_ids-filtered retrieval returns chunks", len(res) >= 1, len(res))
    ok("filtered retrieval only our doc", all(x.get("doc_id") == DOC.id for x in res),
       [x.get("doc_id") for x in res])
    ok("retrieved text contains distinctive phrase", any(PHRASE in (x.get("text") or x.get("content") or "") for x in res))

    # embeddings present for our doc
    our_metas = [m for m in views.vector_store.metadata if m.get("doc_id") == DOC.id]
    ok("FAISS metadata has our doc entries", len(our_metas) == chunks_n, len(our_metas))

    # ---------- delete ----------
    r = c.post(f"/delete/{DOC.id}/")
    data = r.json()
    ok("delete -> 200 success", r.status_code == 200 and data.get("status") == "success", data)
    ok("Document row gone", not Document.objects.filter(id=DOC.id).exists())
    ok("Chunks cascade-deleted", Chunk.objects.filter(document_id=DOC.id).count() == 0)
    ok("file removed from disk", not os.path.exists(file_path))
    res2 = views.rag_chain._retrieve_context(PHRASE, doc_ids=[DOC.id])
    ok("FAISS no longer returns deleted doc", res2 == [], res2)
    ok("FAISS size restored", len(views.vector_store) == ntotal_before, (ntotal_before, len(views.vector_store)))
    our_metas2 = [m for m in views.vector_store.metadata if m.get("doc_id") == DOC.id]
    ok("FAISS metadata entries removed", len(our_metas2) == 0, len(our_metas2))
    body = c.get("/").content.decode()
    ok("upload page no longer lists doc", "RegressionFixture" not in body)

except SystemExit:
    pass
finally:
    # cleanup fixture if anything left behind
    d = Document.objects.filter(title="RegressionFixture").first()
    if d:
        fp = d.file.path if d.file else None
        views.vector_store.delete_document(d.id)
        d.delete()
        if fp and os.path.exists(fp):
            os.remove(fp)
        print("[cleanup] removed leftover fixture", flush=True)

print(f"\n{PASSED}/{PASSED + FAILED} passed", flush=True)
sys.exit(1 if FAILED else 0)
