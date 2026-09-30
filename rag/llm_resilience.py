import time

import httpx
from django.conf import settings

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_RETRYABLE_GOOGLE_ERRORS = (
    "ResourceExhausted",
    "TooManyRequests",
    "ServiceUnavailable",
    "InternalServerError",
    "DeadlineExceeded",
    "Aborted",
    "Unavailable",
    "Internal",
)

_RETRYABLE_NAME_TOKENS = (
    "RateLimit",
    "ResourceExhausted",
    "TooManyRequests",
    "ServiceUnavailable",
    "InternalServerError",
    "DeadlineExceeded",
    "Aborted",
    "Unavailable",
    "Timeout",
    "Connection",
)

_TRANSIENT_BUILTINS = (ConnectionError, TimeoutError)

_TRANSIENT_HTTPX = (
    httpx.TimeoutException,
    httpx.TransportError,
)

_STATUS_ATTRS = ("status", "status_code", "code")


def _extract_status(exc):
    for attr in _STATUS_ATTRS:
        value = getattr(exc, attr, None)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and 100 <= status_code <= 599:
        return status_code
    return None


def is_transient_llm_error(exc) -> bool:
    """Classify an exception as a transient, retry-worthy LLM/network failure.

    Classification is strictly type/attribute based, never message based:
    a generic Exception (even one whose text mentions "503") is NEVER
    transient, which keeps legacy failure paths attempt counts unchanged.
    """
    if exc is None:
        return False
    if type(exc) is Exception:
        return False
    if isinstance(exc, _TRANSIENT_BUILTINS):
        return True
    if isinstance(exc, _TRANSIENT_HTTPX):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(status, int) and status in RETRYABLE_STATUS_CODES:
            return True
        return False
    status = _extract_status(exc)
    if status is not None and status in RETRYABLE_STATUS_CODES:
        return True
    module = type(exc).__module__ or ""
    name = type(exc).__name__
    if module.startswith(("google.api_core", "grpc")):
        return any(key in name for key in _RETRYABLE_GOOGLE_ERRORS)
    for cls in type(exc).__mro__:
        if any(token in cls.__name__ for token in _RETRYABLE_NAME_TOKENS):
            return True
    return False


def invoke_with_retry(llm, prompt, *, sleep=None, max_attempts=None, base_delay=None):
    """Invoke llm.invoke(prompt) with backoff on transient errors only.

    Non-transient exceptions are raised on the first attempt; transient ones
    are retried up to settings.GEMINI_MAX_RETRIES extra times with
    exponential backoff. The ORIGINAL exception object is re-raised when
    attempts are exhausted so callers/logs see the exact type and message.
    """
    sleeper = time.sleep if sleep is None else sleep
    if max_attempts is None:
        try:
            max_attempts = int(settings.GEMINI_MAX_RETRIES) + 1
        except Exception:
            max_attempts = 3
    max_attempts = max(1, max_attempts)
    if base_delay is None:
        try:
            base_delay = float(settings.GEMINI_RETRY_BASE_DELAY)
        except Exception:
            base_delay = 1.0
    delay = base_delay

    attempt = 0
    while True:
        try:
            return llm.invoke(prompt)
        except Exception as exc:
            attempt += 1
            if attempt >= max_attempts or not is_transient_llm_error(exc):
                raise
            sleeper(delay)
            delay *= 2
