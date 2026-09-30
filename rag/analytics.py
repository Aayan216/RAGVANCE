"""Retrieval score analytics (B10 / roadmap item 9): measure, don't gate.

Appends one JSONL record per retrieval (operation, per-result scores, docs)
to logs/retrieval_analytics.jsonl so a labeled calibration set can be built
later. Logging must never break a request: every failure is swallowed.
"""
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings

_LOCK = threading.Lock()


def analytics_path() -> Path:
    return Path(getattr(settings, "BASE_DIR", Path.cwd())) / "logs" / "retrieval_analytics.jsonl"


def log_retrieval(
    operation: str,
    scores: List[Optional[float]],
    doc_ids: Optional[List[int]] = None,
    docs: Optional[List[Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one analytics record. Never raises."""
    try:
        clean_scores = [
            None if s is None else round(float(s), 6) for s in (scores or [])
        ]
        record: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "operation": operation,
            "n": len(clean_scores),
            "top1": clean_scores[0] if clean_scores else None,
            "scores": clean_scores,
            "doc_ids": list(doc_ids) if doc_ids is not None else None,
            "docs": list(docs) if docs is not None else None,
        }
        if extra:
            record.update(extra)
        line = json.dumps(record, separators=(",", ":"), default=str) + "\n"
        path = analytics_path()
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:
        pass
