from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator
from uuid import uuid4

_Context = dict[str, Any]

_CORRELATION_CONTEXT: ContextVar[_Context] = ContextVar("genomeai_correlation_context", default={})

_ALLOWED_KEYS = {
    "request_id",
    "run_id",
    "data_version",
    "config_version",
    "user_id",
    "job_id",
    "command",
    "component",
    "public_job_id",
    "tenant_id",
    "role",
    "path",
    "method",
    "storage_backend",
    "queue_backend",
    "auth_backend",
    "auth_mode",
    "release_version",
}

_ENV_TO_KEY = {
    "GENOMEAI_REQUEST_ID": "request_id",
    "GENOMEAI_RUN_ID": "run_id",
    "GENOMEAI_DATA_VERSION": "data_version",
    "GENOMEAI_CONFIG_VERSION": "config_version",
    "GENOMEAI_USER_ID": "user_id",
    "GENOMEAI_JOB_ID": "job_id",
    "GENOMEAI_PUBLIC_JOB_ID": "public_job_id",
    "GENOMEAI_TENANT_ID": "tenant_id",
}


def new_correlation_id(prefix: str = "req") -> str:
    slug = "".join(ch for ch in str(prefix or "req") if ch.isalnum() or ch in {"_", "-"}).strip("_-") or "req"
    return f"{slug}_{uuid4().hex[:16]}"



def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value).strip()
    return text or None



def _normalized_updates(values: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, raw in values.items():
        if key not in _ALLOWED_KEYS:
            continue
        value = _normalize_value(raw)
        if value is not None:
            out[key] = value
    return out



def get_correlation_context() -> dict[str, Any]:
    return dict(_CORRELATION_CONTEXT.get() or {})



def bind_correlation_context(**values: Any) -> Token:
    merged = get_correlation_context()
    merged.update(_normalized_updates(values))
    return _CORRELATION_CONTEXT.set(merged)



def reset_correlation_context(token: Token) -> None:
    _CORRELATION_CONTEXT.reset(token)



def clear_correlation_context() -> None:
    _CORRELATION_CONTEXT.set({})



@contextmanager
def correlation_scope(**values: Any) -> Iterator[dict[str, Any]]:
    token = bind_correlation_context(**values)
    try:
        yield get_correlation_context()
    finally:
        reset_correlation_context(token)



def merge_correlation_fields(**values: Any) -> dict[str, Any]:
    merged = get_correlation_context()
    merged.update(_normalized_updates(values))
    return merged



def context_from_environment() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for env_name, key in _ENV_TO_KEY.items():
        value = os.environ.get(env_name)
        if value:
            out[key] = value
    return out



def ensure_request_id(value: str | None = None, *, prefix: str = "req") -> str:
    raw = str(value or "").strip()
    return raw or new_correlation_id(prefix=prefix)


__all__ = [
    "bind_correlation_context",
    "clear_correlation_context",
    "context_from_environment",
    "correlation_scope",
    "ensure_request_id",
    "get_correlation_context",
    "merge_correlation_fields",
    "new_correlation_id",
    "reset_correlation_context",
]
