"""Text cleaning and near-duplicate chunk detection for the ingest pipeline.

Applied in process_document_view between parse and embed:
  1. clean_pages  - per-page text normalization + cross-page header/footer removal
  2. near_duplicate_mask - drop chunks that are near-identical to an already
     kept chunk of the same document (computed on the generated embeddings).

Deliberately conservative: only near-exact duplicates are dropped (similarity
>= NEAR_DUP_SIMILARITY with a similar length ratio, or identical normalized
text). Legitimate repeated content (low similarity) is never removed.
"""
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List

import numpy as np

NEAR_DUP_SIMILARITY = 0.97
MIN_LENGTH_RATIO = 0.8
MIN_PAGES_FOR_HEADER_DETECTION = 3
MAX_HEADER_LINE_LEN = 120


def clean_text(text: str) -> str:
    """Normalize whitespace and repair PDF line-break hyphenation."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _line_key(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().lower())


def clean_pages(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean each page's text, then strip repeated running headers/footers.

    A line is treated as a header/footer when it appears as the first or last
    non-empty line of at least max(3, 40% of pages) pages and is short.
    Only first/last occurrences are removed (mid-page occurrences kept).
    Docs with fewer than 3 pages are left without header/footer removal.
    """
    cleaned = []
    for p in pages:
        cleaned.append({**p, "content": clean_text(p.get("content", ""))})

    if len(cleaned) >= MIN_PAGES_FOR_HEADER_DETECTION:
        first_counts: Counter = Counter()
        last_counts: Counter = Counter()
        for p in cleaned:
            lines = [ln for ln in p["content"].splitlines() if ln.strip()]
            if lines:
                first_counts[_line_key(lines[0])] += 1
                last_counts[_line_key(lines[-1])] += 1
        threshold = max(MIN_PAGES_FOR_HEADER_DETECTION, int(0.4 * len(cleaned)))
        drop_first = {
            k for k, n in first_counts.items()
            if n >= threshold and len(k) <= MAX_HEADER_LINE_LEN
        }
        drop_last = {
            k for k, n in last_counts.items()
            if n >= threshold and len(k) <= MAX_HEADER_LINE_LEN
        }
        for p in cleaned:
            lines = p["content"].splitlines()
            idx = 0
            while idx < len(lines) and not lines[idx].strip():
                idx += 1
            if idx < len(lines) and _line_key(lines[idx]) in drop_first:
                del lines[idx]
            idx = len(lines) - 1
            while idx >= 0 and not lines[idx].strip():
                idx -= 1
            if idx >= 0 and _line_key(lines[idx]) in drop_last:
                del lines[idx]
            p["content"] = clean_text("\n".join(lines))
    return cleaned


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def near_duplicate_mask(embeddings: np.ndarray, texts: List[str]) -> List[bool]:
    """Return keep-mask: False where a chunk duplicates an earlier kept one.

    Pairwise cosine on (unit) embeddings; drops when similarity >= 0.97 and
    lengths are similar (ratio >= 0.8), or when normalized texts are equal.
    O(n^2) over one document's chunks - fine for document-scale n.
    """
    keep: List[bool] = []
    kept_indices: List[int] = []
    norms = np.linalg.norm(embeddings, axis=1)
    normalized_texts = [_normalized(t) for t in texts]

    for i in range(len(texts)):
        drop = False
        if normalized_texts[i] and any(
            normalized_texts[i] == normalized_texts[j] for j in kept_indices
        ):
            drop = True
        if not drop:
            for j in kept_indices:
                na, nb = norms[i], norms[j]
                if na <= 0 or nb <= 0:
                    continue
                sim = float(np.dot(embeddings[i], embeddings[j]) / (na * nb))
                la, lb = len(texts[i]), len(texts[j])
                ratio = min(la, lb) / max(la, lb) if max(la, lb) else 1.0
                if sim >= NEAR_DUP_SIMILARITY and ratio >= MIN_LENGTH_RATIO:
                    drop = True
                    break
        keep.append(not drop)
        if not drop:
            kept_indices.append(i)
    return keep
