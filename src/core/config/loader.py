from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml


class ConfigValidationError(ValueError):
    """Human-readable config validation error."""

    def __init__(self, *, config_name: str, path: Path, errors: Sequence[str]):
        self.config_name = str(config_name)
        self.path = Path(path)
        self.errors = [str(item) for item in errors if str(item).strip()]
        message = f"{self.config_name}: невалидный конфиг {self.path}"
        if self.errors:
            message += ": " + "; ".join(self.errors)
        super().__init__(message)


@dataclass(frozen=True)
class FieldSpec:
    key: str
    expected_type: type[Any] | tuple[type[Any], ...]
    required: bool = False
    default: Any = None
    has_default: bool = False
    allow_empty: bool = True
    item_type: type[Any] | tuple[type[Any], ...] | None = None
    validator: Callable[[Any], str | None] | None = None
    item_validator: Callable[[Any], str | None] | None = None
    coerce: Callable[[Any], Any] | None = None


@dataclass(frozen=True)
class MappingSchema:
    config_name: str
    fields: tuple[FieldSpec, ...]
    allow_unknown_keys: bool = True


MISSING = object()


def field_spec(
    key: str,
    expected_type: type[Any] | tuple[type[Any], ...],
    *,
    required: bool = False,
    default: Any = MISSING,
    allow_empty: bool = True,
    item_type: type[Any] | tuple[type[Any], ...] | None = None,
    validator: Callable[[Any], str | None] | None = None,
    item_validator: Callable[[Any], str | None] | None = None,
    coerce: Callable[[Any], Any] | None = None,
) -> FieldSpec:
    return FieldSpec(
        key=str(key),
        expected_type=expected_type,
        required=bool(required),
        default=None if default is MISSING else default,
        has_default=default is not MISSING,
        allow_empty=bool(allow_empty),
        item_type=item_type,
        validator=validator,
        item_validator=item_validator,
        coerce=coerce,
    )


_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _BOOL_TRUE:
            return True
        if lowered in _BOOL_FALSE:
            return False
    raise ValueError(f"ожидалось булево значение, получено {value!r}")


def _type_label(tp: type[Any] | tuple[type[Any], ...]) -> str:
    if isinstance(tp, tuple):
        return "|".join(sorted(t.__name__ for t in tp))
    return tp.__name__


def _validate_scalar(field: FieldSpec, value: Any, *, errors: list[str]) -> Any:
    if field.coerce is not None:
        try:
            value = field.coerce(value)
        except Exception as exc:
            errors.append(f"поле '{field.key}': {exc}")
            return value
    if not isinstance(value, field.expected_type):
        errors.append(
            f"поле '{field.key}' должно иметь тип {_type_label(field.expected_type)}, получено {type(value).__name__}"
        )
        return value
    if not field.allow_empty:
        if isinstance(value, str) and not value.strip():
            errors.append(f"поле '{field.key}' не должно быть пустой строкой")
        if isinstance(value, Mapping) and not value:
            errors.append(f"поле '{field.key}' не должно быть пустым объектом")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and not value:
            errors.append(f"поле '{field.key}' не должно быть пустым списком")
    if field.item_type is not None and isinstance(value, list):
        for idx, item in enumerate(value):
            if not isinstance(item, field.item_type):
                errors.append(
                    f"поле '{field.key}[{idx}]' должно иметь тип {_type_label(field.item_type)}, получено {type(item).__name__}"
                )
                continue
            if field.item_validator is not None:
                msg = field.item_validator(item)
                if msg:
                    errors.append(f"поле '{field.key}[{idx}]': {msg}")
    if field.validator is not None:
        msg = field.validator(value)
        if msg:
            errors.append(f"поле '{field.key}': {msg}")
    return value


def load_yaml_mapping(
    path: str | Path,
    *,
    schema: MappingSchema,
    required: bool = True,
    default: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        if required:
            raise ConfigValidationError(
                config_name=schema.config_name,
                path=cfg_path,
                errors=["файл не найден"],
            )
        return dict(default or {})
    try:
        payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigValidationError(
            config_name=schema.config_name,
            path=cfg_path,
            errors=[f"не удалось прочитать YAML: {exc}"],
        ) from exc
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ConfigValidationError(
            config_name=schema.config_name,
            path=cfg_path,
            errors=[f"верхний уровень должен быть YAML-объектом, получено {type(payload).__name__}"],
        )

    errors: list[str] = []
    normalized = dict(default or {})
    field_map = {field.key: field for field in schema.fields}
    for field in schema.fields:
        if field.key not in payload:
            if field.required and not field.has_default:
                errors.append(f"отсутствует обязательное поле '{field.key}'")
            elif field.has_default:
                normalized[field.key] = field.default
            continue
        normalized[field.key] = _validate_scalar(field, payload[field.key], errors=errors)

    if not schema.allow_unknown_keys:
        extras = sorted(k for k in payload.keys() if k not in field_map)
        if extras:
            errors.append(f"неподдерживаемые поля: {', '.join(extras)}")
    else:
        for key, value in payload.items():
            if key not in normalized:
                normalized[key] = value

    if errors:
        raise ConfigValidationError(config_name=schema.config_name, path=cfg_path, errors=errors)
    return normalized


def positive_int(value: Any) -> str | None:
    try:
        ivalue = int(value)
    except Exception:
        return f"ожидалось целое число > 0, получено {value!r}"
    if ivalue <= 0:
        return f"ожидалось значение > 0, получено {ivalue}"
    return None


def non_negative_float(value: Any) -> str | None:
    try:
        fvalue = float(value)
    except Exception:
        return f"ожидалось число >= 0, получено {value!r}"
    if fvalue < 0:
        return f"ожидалось значение >= 0, получено {fvalue}"
    return None


def non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "ожидалась непустая строка"
    return None


def validate_startup_config_bundle(project_root: str | Path) -> dict[str, Any]:
    from core.audit import load_audit_retention_config
    from core.security import load_permission_matrix
    from web_cabinet.jobs_v2 import load_job_runner_config

    root = Path(project_root).resolve()
    matrix = load_permission_matrix(root)
    retention = load_audit_retention_config(root)
    runner = load_job_runner_config(root)
    return {
        "project_root": str(root),
        "permission_matrix_version": int(matrix.get("version") or 1),
        "audit_retention_version": int(retention.get("version") or 1),
        "job_runner_queue": runner.queue_name_default,
        "job_runner_max_attempts": int(runner.max_attempts_default),
    }


__all__ = [
    "ConfigValidationError",
    "FieldSpec",
    "MappingSchema",
    "coerce_bool",
    "field_spec",
    "load_yaml_mapping",
    "non_empty_string",
    "non_negative_float",
    "positive_int",
    "validate_startup_config_bundle",
]
