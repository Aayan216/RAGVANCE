import re
from typing import Any, Dict

_MARKER_RE = re.compile(r"\[?\bdoc_\d+:chunk_\d+\]?", re.IGNORECASE)
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +([,.;:!?])")

_TEXT_FIELDS = ("question", "explanation", "topic")


def scrub_citation_markers(text: Any) -> Any:
    """Remove [doc_N:chunk_M]-style context labels from LLM output text.

    Non-string input passes through unchanged; text without markers is
    returned byte-identical.
    """
    if not isinstance(text, str):
        return text
    cleaned = _MARKER_RE.sub("", text)
    if cleaned == text:
        return text
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    return cleaned.strip()


def scrub_question(question: Dict[str, Any]) -> Dict[str, Any]:
    """Scrub markers from user-facing text fields of a question dict.

    Only question/explanation/topic and string option values are touched;
    source_chunks, correct, question_type and other keys are preserved.
    """
    if not isinstance(question, dict):
        return question
    for key in _TEXT_FIELDS:
        value = question.get(key)
        if isinstance(value, str):
            question[key] = scrub_citation_markers(value)
    options = question.get("options")
    if isinstance(options, dict):
        for opt_key, opt_value in list(options.items()):
            if isinstance(opt_value, str):
                options[opt_key] = scrub_citation_markers(opt_value)
    return question
