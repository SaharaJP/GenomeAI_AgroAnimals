from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd

from core.operational.multi_site import build_explainable_scope_aggregates


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _safe_rate(num: Any, den: Any) -> float:
    try:
        num_v = float(num or 0)
        den_v = float(den or 0)
    except Exception:
        return 0.0
    if den_v <= 0:
        return 0.0
    return round(num_v / den_v, 4)


def _empty_compare(level: str) -> pd.DataFrame:
    cols = {
        'farm': ['farm_id', 'farm_name'],
        'site': ['farm_id', 'farm_name', 'site_id', 'site_name'],
        'group': ['farm_id', 'farm_name', 'site_id', 'site_name', 'group_id', 'group_name'],
    }.get(str(level or 'site').strip().lower(), ['farm_id', 'farm_name', 'site_id', 'site_name'])
    extra = [
        'items_total', 'high_priority', 'overdue', 'today', 'animals_n', 'source_kinds', 'object_types', 'explainability',
        'overdue_rate', 'high_priority_rate', 'today_rate', 'benchmark_parent_scope', 'sibling_count',
        'benchmark_items_median', 'benchmark_overdue_rate_median', 'benchmark_high_priority_rate_median',
        'items_delta_vs_median', 'overdue_rate_delta_pp', 'high_priority_rate_delta_pp', 'deviation_score',
        'benchmark_basis', 'top_issue_hint',
    ]
    return pd.DataFrame(columns=cols + extra)


def _parent_scope_label(row: Mapping[str, Any], *, level_key: str) -> str:
    if level_key == 'farm':
        return 'enterprise:visible_scope'
    if level_key == 'site':
        farm_id = _clean(row.get('farm_id'))
        farm_name = _clean(row.get('farm_name'))
        return f"farm:{farm_name or farm_id or 'unassigned'}"
    site_id = _clean(row.get('site_id'))
    site_name = _clean(row.get('site_name'))
    farm_id = _clean(row.get('farm_id'))
    prefix = _clean(site_name or site_id or 'unassigned')
    farm_prefix = _clean(farm_id)
    return f"site:{prefix}" if not farm_prefix else f"farm:{farm_prefix}/site:{prefix}"


def _top_issue_hint(rows: Sequence[Mapping[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for raw in rows or []:
        row = dict(raw)
        key = _clean(row.get('worklist_type')) or _clean(row.get('source_kind')) or _clean(row.get('object_type')) or 'unknown'
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return '—'
    top_key, top_n = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return f'{top_key}: {top_n}'


def build_benchmark_compare_view(rows: Sequence[Mapping[str, Any]], *, level: str) -> pd.DataFrame:
    level_key = str(level or 'site').strip().lower()
    if level_key not in {'farm', 'site', 'group'}:
        level_key = 'site'
    base = build_explainable_scope_aggregates(rows, level=level_key)
    if base.empty:
        return _empty_compare(level_key)

    group_cols = {
        'farm': ['farm_id', 'farm_name'],
        'site': ['farm_id', 'farm_name', 'site_id', 'site_name'],
        'group': ['farm_id', 'farm_name', 'site_id', 'site_name', 'group_id', 'group_name'],
    }[level_key]
    df = base.copy()
    df['overdue_rate'] = [
        _safe_rate(row.get('overdue'), row.get('items_total')) for _, row in df.iterrows()
    ]
    df['high_priority_rate'] = [
        _safe_rate(row.get('high_priority'), row.get('items_total')) for _, row in df.iterrows()
    ]
    df['today_rate'] = [
        _safe_rate(row.get('today'), row.get('items_total')) for _, row in df.iterrows()
    ]
    df['benchmark_parent_scope'] = [
        _parent_scope_label(row, level_key=level_key) for _, row in df.iterrows()
    ]

    rows_out: list[dict[str, Any]] = []
    for parent_scope, sub in df.groupby('benchmark_parent_scope', dropna=False, sort=True):
        sibling_count = int(len(sub))
        items_median = float(sub['items_total'].median()) if sibling_count else 0.0
        overdue_median = float(sub['overdue_rate'].median()) if sibling_count else 0.0
        high_median = float(sub['high_priority_rate'].median()) if sibling_count else 0.0
        for _, row in sub.iterrows():
            record = {col: row.get(col) for col in group_cols}
            record['items_total'] = int(row.get('items_total') or 0)
            record['high_priority'] = int(row.get('high_priority') or 0)
            record['overdue'] = int(row.get('overdue') or 0)
            record['today'] = int(row.get('today') or 0)
            record['animals_n'] = int(row.get('animals_n') or 0)
            record['source_kinds'] = row.get('source_kinds') or '—'
            record['object_types'] = row.get('object_types') or '—'
            record['explainability'] = row.get('explainability') or '—'
            record['overdue_rate'] = round(float(row.get('overdue_rate') or 0.0), 4)
            record['high_priority_rate'] = round(float(row.get('high_priority_rate') or 0.0), 4)
            record['today_rate'] = round(float(row.get('today_rate') or 0.0), 4)
            record['benchmark_parent_scope'] = parent_scope
            record['sibling_count'] = sibling_count
            record['benchmark_items_median'] = round(items_median, 2)
            record['benchmark_overdue_rate_median'] = round(overdue_median, 4)
            record['benchmark_high_priority_rate_median'] = round(high_median, 4)
            record['items_delta_vs_median'] = round(float(record['items_total']) - items_median, 2)
            record['overdue_rate_delta_pp'] = round((float(record['overdue_rate']) - overdue_median) * 100.0, 2)
            record['high_priority_rate_delta_pp'] = round((float(record['high_priority_rate']) - high_median) * 100.0, 2)
            record['deviation_score'] = round(abs(float(record['overdue_rate_delta_pp'])) + abs(float(record['high_priority_rate_delta_pp'])), 2)
            record['benchmark_basis'] = (
                'Benchmark = median of visible sibling scopes under current filter. '
                'Rates use visible operational items only; this is not a hidden corporate KPI engine.'
            )
            subset = [
                dict(x) for x in (rows or [])
                if (level_key == 'farm' and _clean(x.get('farm_id')) == _clean(record.get('farm_id')))
                or (level_key == 'site' and _clean(x.get('site_id')) == _clean(record.get('site_id')))
                or (level_key == 'group' and _clean(x.get('group_id')) == _clean(record.get('group_id')))
            ]
            record['top_issue_hint'] = _top_issue_hint(subset)
            rows_out.append(record)

    out = pd.DataFrame(rows_out)
    if out.empty:
        return _empty_compare(level_key)
    return out.sort_values(
        by=['deviation_score', 'overdue', 'high_priority', 'items_total'],
        ascending=[False, False, False, False],
        kind='stable',
    ).reset_index(drop=True)


def build_top_issue_matrix(rows: Sequence[Mapping[str, Any]], *, level: str = 'site', limit: int = 20) -> pd.DataFrame:
    level_key = str(level or 'site').strip().lower()
    scope_cols = {
        'site': ['farm_id', 'farm_name', 'site_id', 'site_name'],
        'group': ['farm_id', 'farm_name', 'site_id', 'site_name', 'group_id', 'group_name'],
    }.get(level_key, ['farm_id', 'farm_name', 'site_id', 'site_name'])
    df = pd.DataFrame(list(rows or []))
    if df.empty:
        return pd.DataFrame(columns=scope_cols + ['issue_key', 'items_total', 'overdue', 'high_priority', 'top_objects', 'action_hint'])

    for col in scope_cols + ['worklist_type', 'source_kind', 'object_type', 'object_id', 'bucket', 'priority']:
        if col not in df.columns:
            df[col] = pd.NA
    df['priority_num'] = pd.to_numeric(df['priority'], errors='coerce').fillna(3)
    df['issue_key'] = [
        _clean(r.get('worklist_type')) or _clean(r.get('source_kind')) or _clean(r.get('object_type')) or 'unknown'
        for _, r in df.iterrows()
    ]
    rows_out: list[dict[str, Any]] = []
    for keys, sub in df.groupby(scope_cols + ['issue_key'], dropna=False, sort=True):
        vals = keys if isinstance(keys, tuple) else (keys,)
        record = {col: (None if pd.isna(val) else val) for col, val in zip(scope_cols + ['issue_key'], vals)}
        record['items_total'] = int(len(sub))
        record['overdue'] = int((sub['bucket'].astype(str) == 'overdue').sum())
        record['high_priority'] = int((sub['priority_num'] <= 2).sum())
        top_objects = []
        for x in sub['object_id'].astype(str).tolist():
            xv = _clean(x)
            if xv and xv not in {'nan', 'None'} and xv not in top_objects:
                top_objects.append(xv)
            if len(top_objects) >= 3:
                break
        record['top_objects'] = ', '.join(top_objects) or '—'
        record['action_hint'] = 'Open planner/worklists with current scope and issue focus.'
        rows_out.append(record)
    out = pd.DataFrame(rows_out)
    if out.empty:
        return out
    return out.sort_values(by=['overdue', 'high_priority', 'items_total', 'issue_key'], ascending=[False, False, False, True], kind='stable').head(max(1, int(limit))).reset_index(drop=True)


def build_enterprise_dashboard_snapshot(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    prepared = [dict(r) for r in (rows or [])]
    df = pd.DataFrame(prepared)
    if df.empty:
        empty_summary = {
            'items_total': 0,
            'farms_n': 0,
            'sites_n': 0,
            'groups_n': 0,
            'overdue': 0,
            'high_priority': 0,
        }
        return {
            'summary': empty_summary,
            'by_farm': [],
            'by_site': [],
            'by_group': [],
            'top_deviations': [],
            'top_issues_by_site': [],
            'benchmark_assumptions': [
                'Benchmark = median of visible sibling scopes under the current filter.',
                'Visible operational items only; no hidden corporate KPI layer is introduced.',
            ],
        }

    for col in ['farm_id', 'site_id', 'group_id', 'bucket', 'priority']:
        if col not in df.columns:
            df[col] = pd.NA
    df['priority_num'] = pd.to_numeric(df['priority'], errors='coerce').fillna(3)
    summary = {
        'items_total': int(len(df)),
        'farms_n': len(sorted({_clean(x) for x in df['farm_id'].astype(str).tolist() if _clean(x) and _clean(x) not in {'nan', 'None'}})),
        'sites_n': len(sorted({_clean(x) for x in df['site_id'].astype(str).tolist() if _clean(x) and _clean(x) not in {'nan', 'None'}})),
        'groups_n': len(sorted({_clean(x) for x in df['group_id'].astype(str).tolist() if _clean(x) and _clean(x) not in {'nan', 'None'}})),
        'overdue': int((df['bucket'].astype(str) == 'overdue').sum()),
        'high_priority': int((df['priority_num'] <= 2).sum()),
    }

    by_farm = build_benchmark_compare_view(prepared, level='farm')
    by_site = build_benchmark_compare_view(prepared, level='site')
    by_group = build_benchmark_compare_view(prepared, level='group')
    top_deviations = by_site.head(10).to_dict(orient='records') if not by_site.empty else []
    top_issues = build_top_issue_matrix(prepared, level='site', limit=15)
    return {
        'summary': summary,
        'by_farm': by_farm.to_dict(orient='records'),
        'by_site': by_site.to_dict(orient='records'),
        'by_group': by_group.to_dict(orient='records'),
        'top_deviations': top_deviations,
        'top_issues_by_site': top_issues.to_dict(orient='records') if not top_issues.empty else [],
        'benchmark_assumptions': [
            'Benchmark = median of visible sibling scopes under the current filter.',
            'Rates use visible operational items only; they are explainable counts/rates, not a hidden corporate KPI engine.',
            'Site comparison is scoped farm → site; group benchmark is scoped site → group.',
        ],
    }


__all__ = [
    'build_benchmark_compare_view',
    'build_enterprise_dashboard_snapshot',
    'build_top_issue_matrix',
]
