from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, TextIO

from core.observability.correlation import get_correlation_context, merge_correlation_fields

_LOGGER_NAME = "genomeai.structured"
_DEFAULT_LEVEL = "INFO"
_SCHEMA_VERSION = 1
_CONFIGURED_STREAM_ID: int | None = None


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "structured_payload", None)
        if not isinstance(payload, dict):
            payload = {"message": record.getMessage()}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)



def _coerce_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _coerce_json_value(v) for k, v in value.items()}
    return str(value)



def _level_from_env() -> int:
    raw = str(os.environ.get("GENOMEAI_LOG_LEVEL") or _DEFAULT_LEVEL).strip().upper() or _DEFAULT_LEVEL
    return int(getattr(logging, raw, logging.INFO))



def structured_logging_enabled() -> bool:
    raw = str(os.environ.get("GENOMEAI_STRUCTURED_LOGS", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}



def configure_structured_logging(*, force: bool = False, stream: TextIO | None = None) -> logging.Logger:
    global _CONFIGURED_STREAM_ID
    logger = logging.getLogger(_LOGGER_NAME)
    target_stream = stream or sys.stderr
    stream_id = id(target_stream)
    if force or not logger.handlers or _CONFIGURED_STREAM_ID != stream_id:
        logger.handlers[:] = []
        handler = logging.StreamHandler(target_stream)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
        _CONFIGURED_STREAM_ID = stream_id
    logger.setLevel(_level_from_env())
    return logger



def build_log_payload(event: str, *, level: str = "INFO", message: str | None = None, **fields: Any) -> dict[str, Any]:
    payload = {
        "schema": f"genomeai.observability.log.v{_SCHEMA_VERSION}",
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "level": str(level or "INFO").upper(),
        "event": str(event or "event"),
    }
    if message:
        payload["message"] = str(message)
    merged = merge_correlation_fields(**fields)
    for key, value in merged.items():
        normalized = _coerce_json_value(value)
        if normalized is not None:
            payload[key] = normalized
    return payload



def log_event(event: str, *, level: str = "INFO", message: str | None = None, logger: logging.Logger | None = None, **fields: Any) -> dict[str, Any]:
    payload = build_log_payload(event, level=level, message=message, **fields)
    if structured_logging_enabled():
        target = logger or configure_structured_logging()
        log_fn = getattr(target, str(level or "info").lower(), target.info)
        log_fn(message or event, extra={"structured_payload": payload})
    return payload



class StructuredLogger:
    def __init__(self, component: str) -> None:
        self.component = str(component or "core")

    def log(self, event: str, *, level: str = "INFO", message: str | None = None, **fields: Any) -> dict[str, Any]:
        return log_event(event, level=level, message=message, component=self.component, **fields)

    def info(self, event: str, **fields: Any) -> dict[str, Any]:
        return self.log(event, level="INFO", **fields)

    def warning(self, event: str, **fields: Any) -> dict[str, Any]:
        return self.log(event, level="WARNING", **fields)

    def error(self, event: str, **fields: Any) -> dict[str, Any]:
        return self.log(event, level="ERROR", **fields)



def get_structured_logger(component: str) -> StructuredLogger:
    configure_structured_logging()
    return StructuredLogger(component=component)


__all__ = [
    "StructuredLogger",
    "build_log_payload",
    "configure_structured_logging",
    "get_structured_logger",
    "log_event",
    "structured_logging_enabled",
]
