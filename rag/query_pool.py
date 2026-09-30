"""Meaningful retrieval-query seeds derived from corpus content.

Replaces synthetic queries like "topic 1" / "important concepts for exam"
with seeds taken from actual document material (section headings or leading
sentences), so different generation batches retrieve different, relevant
parts of the corpus. Deterministic: same corpus -> same ordered pool.
"""
import math
import re
from typing import Any, Dict, List, Optional

MAX_POOL = 50
MAX_SEED_LEN = 120

_NUMBERED = re.compile(r"^\s*(?:chapter|section|part|appendix|module|unit)\b", re.I)
_NUMBER_LIST = re.compile(r"^\s*\d+(\.\d+)*[.)]?\s+\S")
_SENTENCE_END = re.compile(r"[.!?;:,]$")


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _heading_like(line: str) -> bool:
    if not line or len(line) > 80:
        return False
    if _SENTENCE_END.search(line):
        return False
    if _NUMBERED.search(line) or _NUMBER_LIST.match(line):
        return True
    words = line.split()
    if len(words) > 10:
        return False
    # Title Case / ALL CAPS heuristic
    cased = [w for w in words if any(c.isalpha() for c in w)]
    if not cased:
        return False
    titleish = sum(1 for w in cased if w[0].isupper())
    if titleish >= max(2, (len(cased) + 1) // 2) and cased[0][0].isupper():
        return True
    return line.isupper() and len(cased) >= 2


def _first_sentence(text: str) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    if not flat:
        return ""
    m = re.search(r"[.!?](\s|$)", flat)
    if m:
        sent = flat[: m.start() + 1].strip()
    else:
        sent = flat
    if len(sent) > MAX_SEED_LEN:
        cut = sent[:MAX_SEED_LEN]
        sp = cut.rfind(" ")
        sent = (cut[:sp] if sp > 20 else cut).rstrip(" ,;:-")
    return sent


def derive_seed(text: str) -> str:
    """Derive one meaningful query seed from a chunk's text."""
    text = text or ""
    if not text.strip():
        return ""
    line = _first_line(text)
    if _heading_like(line):
        return line
    sent = _first_sentence(text)
    if len(sent.split()) >= 3:
        return sent
    return line or sent


def build_section_queries(
    vector_store: Any,
    doc_ids: Optional[List[int]] = None,
    max_pool: int = MAX_POOL,
) -> List[str]:
    """Ordered, deduplicated, deterministic pool of corpus-derived query seeds."""
    pool: List[str] = []
    seen = set()
    wanted = set(doc_ids) if doc_ids else None
    for meta in getattr(vector_store, "metadata", None) or []:
        if wanted is not None and meta.get("doc_id") not in wanted:
            continue
        seed = derive_seed(meta.get("text") or meta.get("content") or "")
        if not seed or len(seed.split()) < 3:
            continue
        key = _norm_key(seed)
        if key in seen:
            continue
        seen.add(key)
        pool.append(seed)
    if len(pool) > max_pool:
        step = math.ceil(len(pool) / max_pool)
        pool = pool[::step][:max_pool]
    return pool


def select_query(pool: List[str], index: int) -> Optional[str]:
    """Deterministic rotation over the pool. Returns None for an empty pool."""
    if not pool:
        return None
    return pool[index % len(pool)]
