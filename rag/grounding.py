"""Practice answer-grounding validation (B9 / roadmap item 7 / plan item J).

Mirrors the deterministic criterion used by audit/grade_p4.py: the content
words (len > 2 after lowercasing and stripping non-alphanumerics) of the
correct option must appear in the concatenated text of the question's cited
chunks with at least GROUNDING_THRESHOLD coverage. Questions failing the check
are rejected by run_generation(extra_validate=...) and regenerated within the
existing 2x retry cap — never sent to the user ungrounded.
"""
import re
from typing import Any, Callable, Dict, List, Optional

GROUNDING_THRESHOLD = 0.6
SOURCE_SUPPORT_THRESHOLD = 0.4


def normalize_text(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())


def content_words(text: Optional[str], minlen: int = 2) -> set:
    return set(w for w in normalize_text(text).split() if len(w) > minlen)


def grounding_score(
    answer_text: Optional[str], cited_texts: List[Optional[str]]
) -> float:
    """Fraction of the answer's content words present in the cited chunk texts."""
    words = content_words(answer_text, minlen=2)
    if not words:
        return 0.0
    joined = normalize_text(" ".join(t or "" for t in cited_texts))
    if not joined.strip():
        return 0.0
    hits = sum(1 for w in words if w in joined)
    return hits / len(words)


def is_grounded(
    mcq: Dict[str, Any],
    cited_texts: List[Optional[str]],
    threshold: float = GROUNDING_THRESHOLD,
) -> bool:
    if not isinstance(mcq, dict):
        return False
    options = mcq.get("options")
    if not isinstance(options, dict):
        return False
    letter = str(mcq.get("correct", "")).strip().upper()
    answer_text = options.get(letter)
    if not answer_text or not isinstance(answer_text, str):
        return False
    return grounding_score(answer_text, cited_texts) >= threshold


def make_grounding_validator(
    vector_store: Any, threshold: float = GROUNDING_THRESHOLD
) -> Callable[[Dict[str, Any]], bool]:
    """Build the extra_validate predicate for run_generation.

    Resolves the question's own `source_chunks` through the vector store
    (in-memory metadata lookup; no embedding or LLM cost) and applies the
    is_grounded criterion to the correct option's text.
    """

    def validator(mcq: Dict[str, Any]) -> bool:
        if not isinstance(mcq, dict):
            return False
        fids = mcq.get("source_chunks")
        if not isinstance(fids, list) or not fids:
            return False
        texts: List[str] = []
        for fid in fids:
            if isinstance(fid, bool):
                continue
            try:
                faiss_id = int(fid)
            except (TypeError, ValueError):
                continue
            meta = vector_store.get_by_id(faiss_id)
            if meta:
                texts.append(meta.get("text") or "")
        if not texts:
            return False
        return is_grounded(mcq, texts, threshold)

    return validator


def filter_supporting_results(
    answer_text: Optional[str],
    results: List[Dict[str, Any]],
    threshold: float = SOURCE_SUPPORT_THRESHOLD,
    max_sources: int = 3,
) -> List[Dict[str, Any]]:
    """B8: keep only retrieval results whose text actually supports the answer.

    A result qualifies when its text covers >= `threshold` of the answer's
    content words; qualifying results are ranked by coverage (retrieval order
    kept for ties) and capped at `max_sources`. If nothing qualifies (e.g. a
    refusal, or an answer no single chunk covers), fall back to the top
    `max_sources` results in retrieval order. Never returns more than
    `max_sources` entries.
    """
    if not results:
        return []
    scored = [
        (grounding_score(answer_text, [r.get("text", r.get("content", ""))]), r)
        for r in results
    ]
    supporting = [pair for pair in scored if pair[0] >= threshold]
    if not supporting:
        return list(results[:max_sources])
    supporting.sort(key=lambda pair: -pair[0])
    return [r for _, r in supporting[:max_sources]]
