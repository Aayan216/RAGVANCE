import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from .sanitize import scrub_question

TASK_TIMEOUT = 150


def validate_mcq(mcq: Dict[str, Any]) -> bool:
    """Structural validation for a generated MCQ."""
    if not isinstance(mcq, dict):
        return False
    if "error" in mcq:
        return False
    question = mcq.get("question")
    if not question or not isinstance(question, str) or not question.strip():
        return False
    options = mcq.get("options")
    if not isinstance(options, dict):
        return False
    for key in ("A", "B", "C", "D"):
        value = options.get(key)
        if not value or not isinstance(value, str) or not value.strip():
            return False
    correct = str(mcq.get("correct", "")).strip().upper()
    if correct not in ("A", "B", "C", "D"):
        return False
    mcq["correct"] = correct
    if not mcq.get("explanation") or not str(mcq.get("explanation")).strip():
        return False
    return True


def validate_true_false(tf: Dict[str, Any]) -> bool:
    """Structural validation + normalization for a True/False question.

    Normalizes options to canonical {"A": "True", "B": "False"} and remaps
    `correct` if Gemini placed False under A. Rejects anything else (extra
    options, non True/False values, correct outside A/B, lists, etc.).
    """
    if not isinstance(tf, dict):
        return False
    if "error" in tf:
        return False
    if tf.get("question_type") != "true_false":
        return False
    question = tf.get("question")
    if not question or not isinstance(question, str) or not question.strip():
        return False
    options = tf.get("options")
    if not isinstance(options, dict) or set(options.keys()) != {"A", "B"}:
        return False
    a_value = str(options.get("A", "")).strip().lower()
    b_value = str(options.get("B", "")).strip().lower()
    if {a_value, b_value} != {"true", "false"}:
        return False
    correct = str(tf.get("correct", "")).strip().upper()
    if correct not in ("A", "B"):
        return False
    if a_value == "false":
        # Gemini put False under A / True under B: swap to canonical layout.
        correct = "B" if correct == "A" else "A"
    tf["options"] = {"A": "True", "B": "False"}
    tf["correct"] = correct
    if not tf.get("explanation") or not str(tf.get("explanation")).strip():
        return False
    return True


def validate_question(question: Dict[str, Any]) -> bool:
    """Type-aware validation dispatch. Missing question_type defaults to "mcq"."""
    if not isinstance(question, dict):
        return False
    question_type = question.get("question_type", "mcq")
    if question_type == "mcq":
        return validate_mcq(question)
    if question_type == "true_false":
        return validate_true_false(question)
    return False


def _normalize_question(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def is_duplicate(mcq: Dict[str, Any], seen_normalized: set, seen_tokens: List[set]) -> bool:
    """Lightweight duplicate check: exact normalized match, then token similarity.

    High token similarity is only a conservative discard signal,
    never proof that two questions are semantically identical.
    No embedding/LLM call is used.
    """
    question = str(mcq.get("question", ""))
    normalized = _normalize_question(question)
    if not normalized:
        return True
    if normalized in seen_normalized:
        return True
    tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    if tokens:
        for prev in seen_tokens:
            if not prev:
                continue
            overlap = len(tokens & prev)
            union = len(tokens | prev)
            if union and overlap / union >= 0.9:
                return True
    return False


def run_generation(
    request_one_call: Callable[[int, int], List[Dict[str, Any]]],
    *,
    requested: int,
    per_call: int,
    concurrency: int,
    log_label: str,
    shared_state: Optional[Dict[str, Any]] = None,
    extra_validate: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Generate exactly `requested` valid questions using controlled concurrent batches.

    request_one_call(call_index, count) returns a list of question dicts (possibly
    fewer than count, or empty on failure). A single failed call never fails
    the whole run; exceptions are treated as an empty result.

    Validation is type-aware (validate_question). Pass a shared_state dict to
    run multiple generations against one unified duplicate-detection set.
    extra_validate is an optional post-structural predicate (e.g. practice
    answer grounding); a False return or an exception rejects that question
    without failing the run.

    Retry cap: total question slots requested from the LLM is bounded by
    2 x requested. Results are collected in submission order (deterministic).
    """
    start_time = time.time()
    per_call = max(1, int(per_call))
    concurrency = max(1, int(concurrency))
    cap = requested * 2

    if shared_state is None:
        shared_state = {}
    seen_normalized = shared_state.setdefault("normalized", set())
    seen_tokens: List[set] = shared_state.setdefault("tokens", [])
    slots_used = 0
    llm_calls = 0
    call_index = 0
    valid: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while len(valid) < requested and slots_used < cap:
            need = requested - len(valid)
            calls_now = min(concurrency, math.ceil(need / per_call))

            futures = []
            remaining_this_round = need
            for _ in range(calls_now):
                budget = cap - slots_used
                want = min(per_call, remaining_this_round, budget)
                if want <= 0:
                    break
                slots_used += want
                remaining_this_round -= want
                llm_calls += 1
                futures.append(
                    (call_index, executor.submit(request_one_call, call_index, want))
                )
                call_index += 1

            if not futures:
                break

            # Collect in submission order for deterministic results
            for _, future in futures:
                if len(valid) >= requested:
                    break
                try:
                    results = future.result(timeout=TASK_TIMEOUT)
                except Exception:
                    results = []
                if not isinstance(results, list):
                    results = []
                for mcq in results:
                    if len(valid) >= requested:
                        break
                    mcq = scrub_question(mcq)
                    if not validate_question(mcq):
                        continue
                    if extra_validate is not None:
                        try:
                            if not extra_validate(mcq):
                                continue
                        except Exception:
                            continue
                    if is_duplicate(mcq, seen_normalized, seen_tokens):
                        continue
                    seen_normalized.add(_normalize_question(str(mcq["question"])))
                    seen_tokens.append(
                        set(re.findall(r"[a-z0-9]+", str(mcq["question"]).lower()))
                    )
                    valid.append(mcq)

    elapsed = time.time() - start_time
    initial_calls = math.ceil(requested / per_call)
    retries = max(0, llm_calls - initial_calls)

    stats = {
        "requested": requested,
        "questions_per_call": per_call,
        "concurrency": concurrency,
        "llm_calls": llm_calls,
        "valid": len(valid),
        "retries": retries,
        "time": elapsed,
    }

    if len(valid) < requested:
        print(
            f"[INFO] {log_label} generation FAILED: requested={requested} "
            f"questions_per_call={per_call} concurrency={concurrency} "
            f"llm_calls={llm_calls} valid={len(valid)} retries={retries} "
            f"time={elapsed:.1f}s"
        )
        raise ValueError(
            f"Could only generate {len(valid)} of {requested} questions. Please try again."
        )

    valid = valid[:requested]
    stats["valid"] = len(valid)

    print(
        f"[INFO] {log_label} generation: requested={requested} "
        f"questions_per_call={per_call} concurrency={concurrency} "
        f"llm_calls={llm_calls} valid={len(valid)} retries={retries} "
        f"time={elapsed:.1f}s"
    )
    return valid, stats
