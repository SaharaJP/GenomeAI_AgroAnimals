from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
import re
import shlex

from core.list_builder import build_universal_list_snapshot, build_universal_list_table
from core.operational_report_builder import build_operational_report_snapshot, build_operational_report_table, REPORT_TYPES

MAX_QUERY_LENGTH = 280
MAX_TOKENS = 24
SAFE_FORBIDDEN_MARKERS = (';', '--', '/*', '*/', '`')
FAST_QUERY_PAGE_KEY = 'fast_query_mode'
FAVORITE_OBJECT_TYPE = 'fast_query'
PINNED_OBJECT_TYPE = 'pinned_fast_query'

REPORT_ALIAS_MAP: dict[str, str] = {
    'animals': 'animals_overview',
    'animals_overview': 'animals_overview',
    'groups': 'groups_overview',
    'groups_overview': 'groups_overview',
    'events': 'events_recent',
    'events_recent': 'events_recent',
    'repro': 'repro_attention',
    'reproduction': 'repro_attention',
    'repro_attention': 'repro_attention',
    'health': 'health_attention',
    'health_attention': 'health_attention',
    'milk': 'milk_quality_watchlist',
    'milk_quality': 'milk_quality_watchlist',
    'milk_quality_watchlist': 'milk_quality_watchlist',
}

FILTER_ALIAS_MAP: dict[str, str] = {
    'q': 'q',
    'farm': 'farm_id',
    'farm_id': 'farm_id',
    'site': 'site_id',
    'site_id': 'site_id',
    'pen': 'pen_id',
    'group': 'pen_id',
    'pen_id': 'pen_id',
    'animal': 'animal_id',
    'animal_id': 'animal_id',
    'status': 'status',
    'sex': 'sex',
    'breed': 'breed',
    'family': 'event_family',
    'event_family': 'event_family',
    'type': 'event_type',
    'event_type': 'event_type',
    'severity': 'severity',
    'after': 'date_from',
    'from': 'date_from',
    'date_from': 'date_from',
    'before': 'date_to',
    'to': 'date_to',
    'date_to': 'date_to',
}

LIST_TARGETS = {'animals', 'groups', 'events'}
_PROFILE_OPEN_RE = re.compile(r'^open:(animal|group|pen):(.+)$', re.IGNORECASE)
_KV_RE = re.compile(r'^(?P<key>[A-Za-z_][A-Za-z0-9_]*)[:=](?P<value>.+)$')
_SORT_SPLIT_RE = re.compile(r'[:,]')
_SAFE_TEXT_RE = re.compile(r'^[\w\-.:,/]+$')


@dataclass(frozen=True)
class ParsedFastQuery:
    query_text: str
    canonical_query: str
    target_kind: str
    object_type: str | None
    report_type: str | None
    open_target: dict[str, str] | None
    filters: dict[str, Any]
    selected_columns: tuple[str, ...]
    sort_by: str | None
    sort_dir: str
    limit: int
    scc_threshold: int | None
    warnings: tuple[str, ...]
    explain_rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class FastQueryResult:
    mode: str
    parsed: ParsedFastQuery
    payload: dict[str, Any]


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _guard_query_text(query_text: str) -> None:
    raw = _clean(query_text)
    if not raw:
        return
    if len(raw) > MAX_QUERY_LENGTH:
        raise ValueError(f'fast_query_too_long: максимум {MAX_QUERY_LENGTH} символов')
    lowered = raw.lower()
    for marker in SAFE_FORBIDDEN_MARKERS:
        if marker in raw:
            raise ValueError(f'fast_query_unsafe: запрещённый фрагмент {marker!r}')
    if any(word in lowered for word in (' drop ', ' delete ', ' update ', ' insert ', ' truncate ')):
        raise ValueError('fast_query_unsafe: raw query execution не поддерживается')


def _tokenize(query_text: str) -> list[str]:
    raw = _clean(query_text)
    if not raw:
        return []
    try:
        tokens = shlex.split(raw)
    except Exception as exc:
        raise ValueError(f'fast_query_invalid_quotes: {exc}') from exc
    if len(tokens) > MAX_TOKENS:
        raise ValueError(f'fast_query_too_many_tokens: максимум {MAX_TOKENS} токенов')
    return tokens


def _normalize_report_type(value: str | None) -> str:
    key = _clean(value).lower().replace('-', '_')
    return REPORT_ALIAS_MAP.get(key) or ('animals_overview' if key not in REPORT_TYPES else key)


def _normalize_sort(value: str | None, *, default_dir: str) -> tuple[str | None, str]:
    raw = _clean(value)
    if not raw:
        return None, default_dir
    parts = [p for p in _SORT_SPLIT_RE.split(raw) if _clean(p)]
    if not parts:
        return None, default_dir
    field = _clean(parts[0]) or None
    direction = default_dir
    if len(parts) >= 2 and _clean(parts[1]).lower() in {'asc', 'desc'}:
        direction = _clean(parts[1]).lower()
    return field, direction


def parse_fast_query(*, query_text: str) -> ParsedFastQuery:
    raw = _clean(query_text)
    _guard_query_text(raw)
    tokens = _tokenize(raw)

    target_kind = 'list'
    object_type = 'animals'
    report_type: str | None = None
    open_target: dict[str, str] | None = None
    filters: dict[str, Any] = {}
    selected_columns: list[str] = []
    sort_by: str | None = None
    sort_dir = 'asc'
    limit = 120
    scc_threshold: int | None = None
    warnings: list[str] = []
    free_terms: list[str] = []

    if tokens:
        first_raw = _clean(tokens[0])
        first = first_raw.lower()
        profile_match = _PROFILE_OPEN_RE.match(first_raw)
        if profile_match:
            target_kind = 'profile'
            object_type = None
            open_kind = 'group' if profile_match.group(1).lower() in {'group', 'pen'} else 'animal'
            open_target = {'kind': open_kind, 'object_id': _clean(profile_match.group(2))}
            tokens = tokens[1:]
        elif first in LIST_TARGETS:
            object_type = first
            tokens = tokens[1:]
        elif first.startswith('report:'):
            target_kind = 'report'
            object_type = None
            report_type = _normalize_report_type(first.split(':', 1)[1])
            sort_dir = 'desc'
            tokens = tokens[1:]

    for token in tokens:
        tok = _clean(token)
        if not tok:
            continue
        lowered = tok.lower()
        if lowered in {'asc', 'desc'}:
            sort_dir = lowered
            continue
        match = _KV_RE.match(tok)
        if not match:
            if _SAFE_TEXT_RE.match(tok):
                free_terms.append(tok)
            else:
                warnings.append(f'Игнорирован неподдерживаемый токен: {tok}')
            continue
        key = _clean(match.group('key')).lower()
        value = _clean(match.group('value'))

        if key == 'report':
            target_kind = 'report'
            object_type = None
            report_type = _normalize_report_type(value)
            if sort_dir not in {'asc', 'desc'}:
                sort_dir = 'desc'
            continue
        if key == 'open':
            profile_match = _PROFILE_OPEN_RE.match(f'open:{value}')
            if not profile_match:
                warnings.append(f'Игнорирован open token: {tok}')
                continue
            target_kind = 'profile'
            object_type = None
            report_type = None
            open_kind = 'group' if profile_match.group(1).lower() in {'group', 'pen'} else 'animal'
            open_target = {'kind': open_kind, 'object_id': _clean(profile_match.group(2))}
            continue
        if key in {'target', 'list'} and value.lower() in LIST_TARGETS:
            target_kind = 'list'
            object_type = value.lower()
            report_type = None
            continue
        if key in {'cols', 'columns'}:
            selected_columns = [part.strip() for part in value.split(',') if part.strip()]
            continue
        if key == 'sort':
            sort_by, sort_dir = _normalize_sort(value, default_dir=sort_dir)
            continue
        if key == 'limit':
            try:
                limit = max(1, min(int(value), 500))
            except Exception:
                warnings.append(f'Игнорирован invalid limit: {value}')
            continue
        if key in {'scc', 'scc_threshold'}:
            try:
                scc_threshold = max(100000, min(int(value), 1000000))
            except Exception:
                warnings.append(f'Игнорирован invalid scc threshold: {value}')
            continue
        alias = FILTER_ALIAS_MAP.get(key)
        if alias:
            filters[alias] = value
            continue
        warnings.append(f'Игнорирован неизвестный фильтр: {key}')

    if free_terms:
        filters['q'] = ' '.join(free_terms) if not filters.get('q') else f"{filters['q']} {' '.join(free_terms)}".strip()

    if target_kind == 'report':
        report_type = _normalize_report_type(report_type)
        if sort_dir not in {'asc', 'desc'}:
            sort_dir = 'desc'
    if target_kind == 'profile' and open_target and not open_target.get('object_id'):
        raise ValueError('fast_query_invalid_open_target: object_id обязателен')

    target_label = 'profile'
    if target_kind == 'list':
        target_label = f'list:{object_type}'
    elif target_kind == 'report':
        target_label = f'report:{report_type}'
    elif target_kind == 'profile' and open_target:
        target_label = f"profile:{open_target.get('kind')}:{open_target.get('object_id')}"

    canonical_parts = [target_label]
    for key in sorted(filters):
        if _clean(filters.get(key)):
            canonical_parts.append(f'{key}:{filters[key]}')
    if sort_by:
        canonical_parts.append(f'sort:{sort_by}:{sort_dir}')
    if selected_columns:
        canonical_parts.append('cols:' + ','.join(selected_columns))
    if limit:
        canonical_parts.append(f'limit:{int(limit)}')
    if scc_threshold is not None:
        canonical_parts.append(f'scc:{int(scc_threshold)}')

    explain_rows = [
        {'step': 'target', 'value': target_label},
        {'step': 'filters', 'value': ', '.join(f'{k}={v}' for k, v in sorted(filters.items()) if _clean(v)) or '—'},
        {'step': 'sort', 'value': f'{sort_by or "default"} {sort_dir}'},
        {'step': 'columns', 'value': ', '.join(selected_columns) or 'default'},
        {'step': 'limit', 'value': str(int(limit))},
    ]
    if warnings:
        explain_rows.append({'step': 'warnings', 'value': ' | '.join(warnings)})

    return ParsedFastQuery(
        query_text=raw,
        canonical_query=' '.join(canonical_parts),
        target_kind=target_kind,
        object_type=object_type,
        report_type=report_type,
        open_target=open_target,
        filters=filters,
        selected_columns=tuple(selected_columns),
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=int(limit),
        scc_threshold=scc_threshold,
        warnings=tuple(warnings),
        explain_rows=tuple(explain_rows),
    )


def execute_fast_query(
    *,
    input_dir: Path,
    asof_date: date,
    role: str,
    query_text: str,
) -> FastQueryResult:
    parsed = parse_fast_query(query_text=query_text)
    if parsed.target_kind == 'profile':
        payload = {
            'open_target': parsed.open_target or {},
            'filters': dict(parsed.filters),
            'canonical_query': parsed.canonical_query,
        }
        return FastQueryResult(mode='profile', parsed=parsed, payload=payload)
    if parsed.target_kind == 'report':
        snapshot = build_operational_report_snapshot(
            input_dir=Path(input_dir),
            asof_date=asof_date,
            role=role,
            report_type=str(parsed.report_type or 'animals_overview'),
            filters=dict(parsed.filters),
            selected_columns=list(parsed.selected_columns) or None,
            sort_by=parsed.sort_by,
            sort_dir=parsed.sort_dir,
            limit=parsed.limit,
            scc_threshold=int(parsed.scc_threshold or 200000),
        )
        return FastQueryResult(mode='report', parsed=parsed, payload=snapshot)
    snapshot = build_universal_list_snapshot(
        input_dir=Path(input_dir),
        asof_date=asof_date,
        role=role,
        object_type=str(parsed.object_type or 'animals'),
        filters=dict(parsed.filters),
        sort_by=parsed.sort_by,
        sort_dir=parsed.sort_dir,
        selected_columns=list(parsed.selected_columns) or None,
        limit=parsed.limit,
    )
    return FastQueryResult(mode='list', parsed=parsed, payload=snapshot)


def build_fast_query_table(result: FastQueryResult):
    if result.mode == 'report':
        return build_operational_report_table(result.payload)
    if result.mode == 'list':
        return build_universal_list_table(result.payload)
    return None


__all__ = [
    'FAST_QUERY_PAGE_KEY',
    'FAVORITE_OBJECT_TYPE',
    'MAX_QUERY_LENGTH',
    'MAX_TOKENS',
    'PINNED_OBJECT_TYPE',
    'ParsedFastQuery',
    'FastQueryResult',
    'REPORT_ALIAS_MAP',
    'build_fast_query_table',
    'execute_fast_query',
    'parse_fast_query',
]
