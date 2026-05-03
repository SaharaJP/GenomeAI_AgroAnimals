from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from core.pilot_framework import build_pilot_framework_summary

DEFAULT_PILOT_ADOPTION_CFG = Path('configs/ops/pilot_adoption_and_roi_v1.yaml')


def load_pilot_adoption_config(path: str | Path = DEFAULT_PILOT_ADOPTION_CFG) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'Pilot adoption config not found: {p}')
    cfg = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    if not isinstance(cfg, Mapping):
        raise ValueError('Pilot adoption config must be a mapping')
    if not int(cfg.get('version') or 0) >= 1:
        raise ValueError('Pilot adoption config version must be >= 1')
    if int(cfg.get('window_days') or 0) <= 0:
        raise ValueError('Pilot adoption config window_days must be > 0')
    if int(cfg.get('activation_window_hours') or 0) <= 0:
        raise ValueError('Pilot adoption config activation_window_hours must be > 0')
    thresholds = dict(cfg.get('thresholds') or {})
    if not thresholds:
        raise ValueError('Pilot adoption config thresholds are required')
    role_signals = dict(cfg.get('role_activation_signals') or {})
    if not role_signals:
        raise ValueError('Pilot adoption config role_activation_signals are required')
    return dict(cfg)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ''):
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ''):
            return None
        return int(value)
    except Exception:
        return None


def _load_sql_df(conn, sql: str, params: tuple[Any, ...]) -> pd.DataFrame:
    try:
        return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def _norm_ts(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns, UTC]')
    return pd.to_datetime(df[col], utc=True, errors='coerce')


def _string_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series('', index=df.index, dtype='object')
    return df[col].fillna('').astype(str).str.strip()


def _json_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([{} for _ in range(len(df.index))], index=df.index, dtype='object')
    out = []
    for value in df[col].tolist():
        try:
            parsed = json.loads(value or '{}') if not isinstance(value, dict) else value
            out.append(parsed if isinstance(parsed, dict) else {})
        except Exception:
            out.append({})
    return pd.Series(out, index=df.index, dtype='object')


def _match_prefix(value: str, prefixes: list[str]) -> bool:
    value = str(value or '').strip().lower()
    return any(value.startswith(str(p).strip().lower()) for p in prefixes if str(p).strip())


def _usage_match(row: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    action = str(row.get('action') or '').strip().lower()
    object_type = str(row.get('object_type') or '').strip().lower()
    action_group = str(row.get('action_group') or '').strip().lower()
    action_equals = {str(x).strip().lower() for x in list(rule.get('action_equals') or []) if str(x).strip()}
    if action_equals and action in action_equals:
        if action == 'export.download':
            allowed_types = {str(x).strip().lower() for x in list(rule.get('object_types') or []) if str(x).strip()}
            return (not allowed_types) or (object_type in allowed_types)
        return True
    if rule.get('action_group') and action_group == str(rule.get('action_group')).strip().lower():
        return True
    if _match_prefix(action, list(rule.get('action_prefixes') or [])):
        return True
    allowed_types = {str(x).strip().lower() for x in list(rule.get('object_types') or []) if str(x).strip()}
    if allowed_types and object_type in allowed_types:
        return True
    return False


def _daily_weekly_activity(audit_df: pd.DataFrame, now_utc: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int], dict[str, int], int, int]:
    if audit_df.empty:
        return [], [], {}, {}, 0, 0
    df = audit_df.copy()
    df['ts_dt'] = _norm_ts(df, 'ts')
    df = df[df['ts_dt'].notna()].copy()
    if df.empty:
        return [], [], {}, {}, 0, 0
    df['date'] = df['ts_dt'].dt.strftime('%Y-%m-%d')
    week_start = (df['ts_dt'].dt.floor('D') - pd.to_timedelta(df['ts_dt'].dt.weekday, unit='D'))
    df['week_start'] = week_start.dt.strftime('%Y-%m-%d')
    user = _string_series(df, 'username')
    df = df[user != ''].copy()
    if df.empty:
        return [], [], {}, {}, 0, 0
    dau_cutoff = pd.Timestamp(now_utc - timedelta(days=1))
    wau_cutoff = pd.Timestamp(now_utc - timedelta(days=7))
    dau_df = df[df['ts_dt'] >= dau_cutoff]
    wau_df = df[df['ts_dt'] >= wau_cutoff]
    dau_total = int(dau_df['username'].nunique())
    wau_total = int(wau_df['username'].nunique())
    dau_by_role = {str(k): int(v) for k, v in dau_df.groupby(_string_series(dau_df, 'role'))['username'].nunique().items() if str(k).strip()}
    wau_by_role = {str(k): int(v) for k, v in wau_df.groupby(_string_series(wau_df, 'role'))['username'].nunique().items() if str(k).strip()}
    daily = (
        df.groupby(['date', _string_series(df, 'role')])['username']
        .nunique()
        .reset_index(name='dau')
        .rename(columns={'role': 'user_role'})
    )
    weekly = (
        df.groupby(['week_start', _string_series(df, 'role')])['username']
        .nunique()
        .reset_index(name='wau')
        .rename(columns={'role': 'user_role'})
    )
    daily_rows = [
        {'date': str(r['date']), 'role': str(r['user_role']), 'dau': int(r['dau'])}
        for _, r in daily.sort_values(['date', 'user_role']).iterrows()
        if str(r['user_role']).strip()
    ]
    weekly_rows = [
        {'week_start': str(r['week_start']), 'role': str(r['user_role']), 'wau': int(r['wau'])}
        for _, r in weekly.sort_values(['week_start', 'user_role']).iterrows()
        if str(r['user_role']).strip()
    ]
    return daily_rows, weekly_rows, dau_by_role, wau_by_role, dau_total, wau_total


def _tasks_metrics(tasks_df: pd.DataFrame, now_utc: datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if tasks_df.empty:
        return {'created_total': 0, 'done_total': 0, 'completion_rate': 0.0, 'overdue_open_tasks': 0}, []
    df = tasks_df.copy()
    df['created_at_dt'] = _norm_ts(df, 'created_at')
    df['closed_at_dt'] = _norm_ts(df, 'closed_at')
    df['due_at_dt'] = _norm_ts(df, 'due_at')
    status = _string_series(df, 'status').str.lower()
    worklist_type = _string_series(df, 'worklist_type')
    overdue = ((status.isin(['open', 'in_progress'])) & df['due_at_dt'].notna() & (df['due_at_dt'] < pd.Timestamp(now_utc)))
    done = status.eq('done')
    created_total = int(len(df.index))
    done_total = int(done.sum())
    summary = {
        'created_total': created_total,
        'done_total': done_total,
        'completion_rate': round(float(done_total / created_total), 4) if created_total else 0.0,
        'overdue_open_tasks': int(overdue.sum()),
    }
    rows = []
    df = df.assign(_status=status, _worklist_type=worklist_type, _overdue=overdue, _done=done)
    for key, grp in df.groupby('_worklist_type', dropna=False):
        created = int(len(grp.index))
        done_n = int(grp['_done'].sum())
        rows.append({
            'worklist_type': str(key or 'untyped'),
            'created_total': created,
            'done_total': done_n,
            'completion_rate': round(float(done_n / created), 4) if created else 0.0,
            'overdue_open_tasks': int(grp['_overdue'].sum()),
        })
    rows.sort(key=lambda x: (-int(x['created_total']), x['worklist_type']))
    return summary, rows


def _event_latency_metrics(events_df: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if events_df.empty:
        return {'event_count': 0, 'median_event_entry_latency_hours': None, 'p90_event_entry_latency_hours': None}, []
    df = events_df.copy()
    df['created_at_dt'] = _norm_ts(df, 'created_at')
    df['event_ts_dt'] = _norm_ts(df, 'event_ts')
    df['latency_h'] = (df['created_at_dt'] - df['event_ts_dt']).dt.total_seconds() / 3600.0
    df = df[df['latency_h'].notna()].copy()
    df = df[(df['latency_h'] >= 0) & (df['latency_h'] <= 24 * 30)]
    if df.empty:
        return {'event_count': 0, 'median_event_entry_latency_hours': None, 'p90_event_entry_latency_hours': None}, []
    summary = {
        'event_count': int(len(df.index)),
        'median_event_entry_latency_hours': round(float(df['latency_h'].median()), 3),
        'p90_event_entry_latency_hours': round(float(df['latency_h'].quantile(0.9)), 3),
    }
    rows = []
    df['_event_type'] = _string_series(df, 'event_type')
    for key, grp in df.groupby('_event_type', dropna=False):
        rows.append({
            'event_type': str(key or 'unknown'),
            'events': int(len(grp.index)),
            'median_latency_hours': round(float(grp['latency_h'].median()), 3),
            'p90_latency_hours': round(float(grp['latency_h'].quantile(0.9)), 3),
        })
    rows.sort(key=lambda x: (-int(x['events']), x['event_type']))
    return summary, rows


def _usage_tables(audit_df: pd.DataFrame, cfg: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    categories = dict(cfg.get('usage_categories') or {})
    if audit_df.empty:
        zero = {key: 0 for key in categories.keys()}
        return zero, []
    df = audit_df.copy()
    rows = []
    totals = {key: 0 for key in categories.keys()}
    roles = sorted({str(x).strip() for x in _string_series(df, 'role').tolist() if str(x).strip()})
    for role in roles:
        grp = df[_string_series(df, 'role') == role].copy()
        row = {'role': role, 'users': int(_string_series(grp, 'username').replace('', pd.NA).dropna().nunique())}
        for key, rule in categories.items():
            mask = grp.apply(lambda r: _usage_match(r.to_dict(), rule), axis=1)
            value = int(mask.sum())
            row[key] = value
            totals[key] += value
        rows.append(row)
    rows.sort(key=lambda x: x['role'])
    return totals, rows


def _assistant_feedback_counts(feedback_df: pd.DataFrame) -> dict[str, Any]:
    if feedback_df.empty:
        return {'assistant_feedback_total': 0, 'operational_feedback_total': 0, 'feedback_total': 0}
    df = feedback_df.copy()
    meta = _json_series(df, 'metadata_json')
    kinds = []
    for item in meta.tolist():
        kinds.append(str((item or {}).get('feedback_kind') or '').strip())
    df['_feedback_kind'] = kinds
    assistant_total = int((df['_feedback_kind'] == 'assistant_answer').sum())
    total = int(len(df.index))
    return {
        'assistant_feedback_total': assistant_total,
        'operational_feedback_total': int(total - assistant_total),
        'feedback_total': total,
    }


def _match_activation(row: Mapping[str, Any], role_cfg: Mapping[str, Any]) -> bool:
    action = str(row.get('action') or '').strip().lower()
    action_group = str(row.get('action_group') or '').strip().lower()
    object_type = str(row.get('object_type') or '').strip().lower()
    if action in {'auth.login.web', 'auth.logout.web', 'auth.login.streamlit', 'auth.logout.streamlit'}:
        return False
    if _match_prefix(action, list(role_cfg.get('action_prefixes') or [])):
        return True
    groups = {str(x).strip().lower() for x in list(role_cfg.get('action_groups') or []) if str(x).strip()}
    if groups and action_group in groups:
        return True
    obj_types = {str(x).strip().lower() for x in list(role_cfg.get('object_types') or []) if str(x).strip()}
    if obj_types and object_type in obj_types:
        return True
    return False


def _onboarding_friction(audit_df: pd.DataFrame, cfg: Mapping[str, Any], now_utc: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if audit_df.empty:
        return [], {'users_started': 0, 'users_activated': 0, 'activation_rate': 0.0}
    df = audit_df.copy()
    df['ts_dt'] = _norm_ts(df, 'ts')
    df = df[df['ts_dt'].notna()].copy()
    login_df = df[_string_series(df, 'action').isin(['auth.login.web', 'auth.login.streamlit'])].copy()
    if login_df.empty:
        return [], {'users_started': 0, 'users_activated': 0, 'activation_rate': 0.0}
    activation_window_h = int(cfg.get('activation_window_hours') or 24)
    role_cfgs = dict(cfg.get('role_activation_signals') or {})
    rows = []
    total_started = total_activated = 0
    for role, role_logins in login_df.groupby(_string_series(login_df, 'role')):
        role = str(role).strip()
        if not role:
            continue
        started_users = 0
        activated_users = 0
        activation_hours: list[float] = []
        last_actions: list[str] = []
        cfg_role = dict(role_cfgs.get(role) or {})
        for username, user_logins in role_logins.groupby(_string_series(role_logins, 'username')):
            username = str(username).strip()
            if not username:
                continue
            started_users += 1
            login_ts = user_logins['ts_dt'].min()
            window_end = login_ts + pd.Timedelta(hours=activation_window_h)
            user_actions = df[(_string_series(df, 'username') == username) & (_string_series(df, 'role') == role) & (df['ts_dt'] >= login_ts) & (df['ts_dt'] <= window_end)].copy()
            user_actions = user_actions.sort_values('ts_dt')
            activated = False
            for _, act in user_actions.iterrows():
                if _match_activation(act.to_dict(), cfg_role):
                    activated = True
                    activated_users += 1
                    activation_hours.append(float((act['ts_dt'] - login_ts).total_seconds() / 3600.0))
                    break
            if not activated:
                non_auth = user_actions[~_string_series(user_actions, 'action').isin(['auth.login.web','auth.login.streamlit'])]
                if non_auth.empty:
                    last_actions.append('no_post_login_action')
                else:
                    last_actions.append(str(non_auth.iloc[-1].get('action') or 'unknown_last_action'))
        total_started += started_users
        total_activated += activated_users
        counter = Counter(last_actions)
        top = [f'{k}:{v}' for k, v in counter.most_common(3)]
        rows.append({
            'role': role,
            'users_started': int(started_users),
            'users_activated': int(activated_users),
            'activation_rate': round(float(activated_users / started_users), 4) if started_users else 0.0,
            'median_hours_to_activation': round(float(pd.Series(activation_hours).median()), 3) if activation_hours else None,
            'dropoff_users': int(started_users - activated_users),
            'top_dropoff_points': top,
        })
    rows.sort(key=lambda x: x['role'])
    summary = {
        'users_started': int(total_started),
        'users_activated': int(total_activated),
        'activation_rate': round(float(total_activated / total_started), 4) if total_started else 0.0,
    }
    return rows, summary


def _roi_metrics(decisions_df: pd.DataFrame, outcomes_df: pd.DataFrame, tasks_df: pd.DataFrame, cfg: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if decisions_df.empty:
        return {
            'economics_linked_decisions': 0,
            'outcome_linked_decisions': 0,
            'evidence_ready_decisions': 0,
            'roi_evidence_rate': 0.0,
            'expected_net_value_sum_rub': 0.0,
            'median_expected_roi': None,
        }, []
    out_link = {}
    if not outcomes_df.empty and 'linked_decision_id' in outcomes_df.columns:
        for _, row in outcomes_df.iterrows():
            did = str(row.get('linked_decision_id') or '').strip()
            if did and did not in out_link:
                out_link[did] = {'outcome_status': str(row.get('outcome_status') or '').strip(), 'outcome_created_at': str(row.get('created_at') or '').strip()}
    task_link = {}
    if not tasks_df.empty and 'linked_decision_id' in tasks_df.columns:
        for _, row in tasks_df.iterrows():
            did = str(row.get('linked_decision_id') or '').strip()
            if did and did not in task_link:
                task_link[did] = {'task_status': str(row.get('status') or '').strip(), 'task_closed_at': str(row.get('closed_at') or '').strip()}
    rows = []
    expected_net_values: list[float] = []
    expected_rois: list[float] = []
    econ_total = outcome_total = ready_total = 0
    for _, row in decisions_df.iterrows():
        meta = row.get('metadata') or {}
        if not isinstance(meta, Mapping):
            meta = {}
        economics_version = str(meta.get('economics_inputs_version') or '').strip()
        expected_net = _safe_float(meta.get('expected_net_value_rub'))
        expected_roi = _safe_float(meta.get('expected_roi'))
        expected_gain = _safe_float(meta.get('expected_gain_rub'))
        has_econ = bool(economics_version or expected_net is not None or expected_roi is not None or expected_gain is not None)
        if not has_econ:
            continue
        econ_total += 1
        decision_id = str(row.get('decision_id') or '').strip()
        outcome = out_link.get(decision_id) or {}
        task = task_link.get(decision_id) or {}
        outcome_linked = bool(outcome or task)
        if outcome_linked:
            outcome_total += 1
        evidence_ready = bool(economics_version) and outcome_linked
        if evidence_ready:
            ready_total += 1
        if expected_net is not None:
            expected_net_values.append(expected_net)
        if expected_roi is not None:
            expected_rois.append(expected_roi)
        rows.append({
            'decision_id': decision_id,
            'action': str(row.get('action') or '').strip(),
            'object_type': str(row.get('object_type') or '').strip(),
            'object_id': str(row.get('object_id') or '').strip(),
            'report_version': str(row.get('report_version') or '').strip(),
            'scoring_run': str(row.get('scoring_run') or '').strip(),
            'data_version': str(row.get('data_version') or '').strip(),
            'economics_inputs_version': economics_version,
            'expected_net_value_rub': expected_net,
            'expected_roi': expected_roi,
            'recommended_action': str(meta.get('recommended_action') or '').strip(),
            'worklist_type': str(meta.get('worklist_type') or '').strip(),
            'outcome_linked': outcome_linked,
            'outcome_status': str(outcome.get('outcome_status') or task.get('task_status') or '').strip(),
            'evidence_ready': evidence_ready,
            'source_linkage': f"decision_log_v2:{decision_id}",
        })
    min_decisions = int((cfg.get('thresholds') or {}).get('min_economics_decisions_for_roi_gate') or 2)
    summary = {
        'economics_linked_decisions': econ_total,
        'outcome_linked_decisions': outcome_total,
        'evidence_ready_decisions': ready_total,
        'roi_evidence_rate': round(float(ready_total / econ_total), 4) if econ_total else 0.0,
        'expected_net_value_sum_rub': round(float(sum(expected_net_values)), 2) if expected_net_values else 0.0,
        'median_expected_roi': round(float(pd.Series(expected_rois).median()), 4) if expected_rois else None,
        'roi_gate_applicable': econ_total >= min_decisions,
    }
    rows.sort(key=lambda x: (not bool(x['evidence_ready']), -(x['expected_net_value_rub'] or 0.0), x['decision_id']))
    return summary, rows


def _hardening_priorities(*, metrics: Mapping[str, Any], tasks_summary: Mapping[str, Any], friction_summary: Mapping[str, Any], friction_rows: list[dict[str, Any]], event_summary: Mapping[str, Any], roi_summary: Mapping[str, Any], cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    thresholds = dict(cfg.get('thresholds') or {})
    priorities: list[dict[str, Any]] = []
    activation_min = _safe_float(thresholds.get('onboarding_activation_rate_min')) or 0.7
    for row in friction_rows:
        current = _safe_float(row.get('activation_rate')) or 0.0
        if current < activation_min:
            priorities.append({
                'priority_key': f'onboarding_friction_{row.get("role")}',
                'severity': 'high' if current < activation_min * 0.75 else 'medium',
                'metric': 'onboarding_activation_rate',
                'current': current,
                'target': activation_min,
                'why': f"Role {row.get('role')} does not reach first meaningful action reliably. Top drop-off points: {', '.join(row.get('top_dropoff_points') or []) or 'n/a'}.",
                'source_linkage': f"audit_log:auth.login.web::{row.get('role')}",
            })
    completion_min = _safe_float(thresholds.get('task_completion_rate_min')) or 0.6
    completion_rate = _safe_float(tasks_summary.get('completion_rate')) or 0.0
    if completion_rate < completion_min:
        priorities.append({
            'priority_key': 'worklist_completion',
            'severity': 'high',
            'metric': 'task_completion_rate',
            'current': completion_rate,
            'target': completion_min,
            'why': 'Open lists are not converting into completed work fast enough; review task closure flow, handover and queue balance.',
            'source_linkage': 'tasks_v1:status/closed_at',
        })
    overdue_max = _safe_int(thresholds.get('overdue_open_tasks_max')) or 5
    overdue = _safe_int(tasks_summary.get('overdue_open_tasks')) or 0
    if overdue > overdue_max:
        priorities.append({
            'priority_key': 'overdue_backlog',
            'severity': 'high' if overdue > overdue_max * 2 else 'medium',
            'metric': 'overdue_open_tasks',
            'current': overdue,
            'target': overdue_max,
            'why': 'Too many overdue operational items remain open; review SLA, team/shift handover and default prioritization.',
            'source_linkage': 'tasks_v1:due_at/status',
        })
    latency_max = _safe_float(thresholds.get('median_event_entry_latency_hours_max')) or 6.0
    median_latency = _safe_float(event_summary.get('median_event_entry_latency_hours'))
    if median_latency is not None and median_latency > latency_max:
        priorities.append({
            'priority_key': 'event_entry_latency',
            'severity': 'medium',
            'metric': 'median_event_entry_latency_hours',
            'current': median_latency,
            'target': latency_max,
            'why': 'Operational event entry is too slow; mobile/cowside entry and queue-to-entry transition should be hardened.',
            'source_linkage': 'animal_events_v1:event_ts/created_at',
        })
    roi_rate_min = _safe_float(thresholds.get('roi_evidence_rate_min')) or 0.5
    if bool(roi_summary.get('roi_gate_applicable')):
        roi_rate = _safe_float(roi_summary.get('roi_evidence_rate')) or 0.0
        if roi_rate < roi_rate_min:
            priorities.append({
                'priority_key': 'roi_evidence_gap',
                'severity': 'medium',
                'metric': 'roi_evidence_rate',
                'current': roi_rate,
                'target': roi_rate_min,
                'why': 'Economics-linked decisions do not yet have enough linked outcome evidence to support pilot ROI claims.',
                'source_linkage': 'decision_log_v2 + completion_outcomes_v1',
            })
    priorities.sort(key=lambda x: (0 if x['severity'] == 'high' else 1, x['priority_key']))
    return priorities


def build_pilot_adoption_metrics_summary(*, project_root: str | Path = '.', conn, tenant_id: str = 'default', cfg_path: str | Path = DEFAULT_PILOT_ADOPTION_CFG, now_utc: datetime | None = None) -> dict[str, Any]:
    root = Path(project_root)
    cfg = load_pilot_adoption_config(root / Path(cfg_path))
    now_utc = now_utc or datetime.now(timezone.utc)
    window_days = int(cfg.get('window_days') or 30)
    since_ts = (now_utc - timedelta(days=window_days)).replace(microsecond=0).isoformat()

    audit_df = _load_sql_df(conn, "SELECT ts, username, role, action, action_group, object_type, object_id, status, request_id FROM audit_log WHERE tenant_id=? AND archived_at IS NULL AND ts>=? ORDER BY ts ASC", (tenant_id, since_ts))
    tasks_df = _load_sql_df(conn, "SELECT task_id, status, worklist_type, domain, assignee_team, created_at, closed_at, due_at, linked_decision_id FROM tasks_v1 WHERE tenant_id=? AND (created_at>=? OR COALESCE(closed_at,'')>=?) ORDER BY created_at ASC", (tenant_id, since_ts, since_ts))
    events_df = _load_sql_df(conn, "SELECT event_id, event_type, source, actor_type, created_at, event_ts FROM animal_events_v1 WHERE tenant_id=? AND created_at>=? ORDER BY created_at ASC", (tenant_id, since_ts))
    decisions_df = _load_sql_df(conn, "SELECT decision_id, created_at, action, object_type, object_id, data_version, report_version, scoring_run, metadata_json FROM decision_log_v2 WHERE tenant_id=? AND created_at>=? ORDER BY created_at DESC", (tenant_id, since_ts))
    if not decisions_df.empty:
        decisions_df['metadata'] = _json_series(decisions_df, 'metadata_json')
    outcomes_df = _load_sql_df(conn, "SELECT linked_decision_id, outcome_status, created_at FROM completion_outcomes_v1 WHERE tenant_id=? AND created_at>=? ORDER BY created_at DESC", (tenant_id, since_ts))
    feedback_df = _load_sql_df(conn, "SELECT created_at, feedback_source, metadata_json FROM feedback_events_v1 WHERE tenant_id=? AND created_at>=? ORDER BY created_at DESC", (tenant_id, since_ts))
    approvals_df = _load_sql_df(conn, "SELECT status, created_at, updated_at, approved_at, archived_at, rejected_at FROM report_approvals_v1 WHERE tenant_id=?", (tenant_id,))

    daily_rows, weekly_rows, dau_by_role, wau_by_role, dau_total, wau_total = _daily_weekly_activity(audit_df, now_utc)
    usage_totals, usage_by_role = _usage_tables(audit_df, cfg)
    assistant_feedback = _assistant_feedback_counts(feedback_df)
    tasks_summary, completion_rows = _tasks_metrics(tasks_df, now_utc)
    event_summary, latency_rows = _event_latency_metrics(events_df)
    friction_rows, friction_summary = _onboarding_friction(audit_df, cfg, now_utc)
    roi_summary, roi_rows = _roi_metrics(decisions_df, outcomes_df, tasks_df, cfg)
    pilot_summary = build_pilot_framework_summary(project_root=root)

    approval_usage_total = int(usage_totals.get('approval_usage') or 0)
    if not approvals_df.empty:
        approvals_window = approvals_df.copy()
        ts_cols = [c for c in ('approved_at', 'archived_at', 'rejected_at', 'updated_at') if c in approvals_window.columns]
        counts = 0
        cutoff_ts = pd.Timestamp(now_utc - timedelta(days=window_days))
        for col in ts_cols:
            counts += int((_norm_ts(approvals_window, col) >= cutoff_ts).sum())
        approval_usage_total = max(approval_usage_total, counts)

    summary = {
        'schema': 'genomeai.pilot_adoption_and_roi_metrics.v1',
        'config_version': int(cfg.get('version') or 1),
        'title': str(cfg.get('title') or 'Pilot adoption and ROI metrics'),
        'window_days': window_days,
        'generated_at': now_utc.replace(microsecond=0).isoformat(),
        'tenant_id': str(tenant_id),
        'dau_total': dau_total,
        'wau_total': wau_total,
        'dau_by_role': dau_by_role,
        'wau_by_role': wau_by_role,
        'report_usage_total': int(usage_totals.get('report_usage') or 0),
        'approval_usage_total': approval_usage_total,
        'assistant_usage_total': int(usage_totals.get('assistant_usage') or 0),
        **assistant_feedback,
        **tasks_summary,
        **event_summary,
        **friction_summary,
        **roi_summary,
        'pilot_context': {
            'pilot_count': int(pilot_summary.get('pilot_count') or 0),
            'status_counts': dict(pilot_summary.get('status_counts') or {}),
            'referenceable_count': int(pilot_summary.get('referenceable_count') or 0),
            'record_mode': str(pilot_summary.get('record_mode') or ''),
        },
    }
    priorities = _hardening_priorities(
        metrics=summary,
        tasks_summary=tasks_summary,
        friction_summary=friction_summary,
        friction_rows=friction_rows,
        event_summary=event_summary,
        roi_summary=roi_summary,
        cfg=cfg,
    )
    summary['hardening_priorities_count'] = len(priorities)
    return {
        'summary': summary,
        'daily_active_by_role': daily_rows,
        'weekly_active_by_role': weekly_rows,
        'usage_by_role': usage_by_role,
        'list_completion_by_worklist': completion_rows,
        'event_entry_latency_by_type': latency_rows,
        'onboarding_friction_by_role': friction_rows,
        'roi_evidence_rows': roi_rows,
        'hardening_priorities': priorities,
        'pilot_framework': {
            'pilot_rows': list(pilot_summary.get('pilot_rows') or []),
            'reference_deployments': list(pilot_summary.get('reference_deployments') or []),
        },
        'thresholds': dict(cfg.get('thresholds') or {}),
        'notes': list(cfg.get('notes') or []),
        'source_paths': {
            'config': str(Path(cfg_path)),
            'pilot_framework_config': str(pilot_summary.get('source_paths', {}).get('config') or ''),
            'pilot_framework_records': str(pilot_summary.get('source_paths', {}).get('records') or ''),
        },
        'traceability_statement': 'Metrics are computed from audit_log, tasks_v1, animal_events_v1, report_approvals_v1, feedback_events_v1, decision_log_v2 and completion_outcomes_v1 within the configured window.',
    }


def _render_table_md(title: str, rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    lines = [f'## {title}']
    if not rows:
        lines.append('Нет данных.')
        return lines
    header = '| ' + ' | '.join(columns) + ' |'
    sep = '| ' + ' | '.join(['---'] * len(columns)) + ' |'
    lines.extend([header, sep])
    for row in rows:
        vals = [str(row.get(col, '')) for col in columns]
        lines.append('| ' + ' | '.join(vals) + ' |')
    return lines


def render_pilot_adoption_metrics_markdown(payload: Mapping[str, Any]) -> str:
    summary = dict(payload.get('summary') or {})
    lines = [
        '# Pilot adoption / usage / ROI metrics',
        '',
        f"Window days: {summary.get('window_days')}",
        f"DAU / WAU: {summary.get('dau_total')} / {summary.get('wau_total')}",
        f"Task completion rate: {summary.get('completion_rate')} · overdue={summary.get('overdue_open_tasks')}",
        f"Median event entry latency (h): {summary.get('median_event_entry_latency_hours')}",
        f"Assistant usage: {summary.get('assistant_usage_total')} · report usage: {summary.get('report_usage_total')} · approvals: {summary.get('approval_usage_total')}",
        f"ROI evidence rate: {summary.get('roi_evidence_rate')} · evidence-ready decisions={summary.get('evidence_ready_decisions')}",
        f"Onboarding activation rate: {summary.get('activation_rate')} · hardening priorities={summary.get('hardening_priorities_count')}",
        '',
        str(payload.get('traceability_statement') or ''),
        '',
    ]
    lines.extend(_render_table_md('Usage by role', list(payload.get('usage_by_role') or []), ['role', 'users', 'report_usage', 'approval_usage', 'assistant_usage']))
    lines.append('')
    lines.extend(_render_table_md('Onboarding friction by role', list(payload.get('onboarding_friction_by_role') or []), ['role', 'users_started', 'users_activated', 'activation_rate', 'dropoff_users', 'top_dropoff_points']))
    lines.append('')
    lines.extend(_render_table_md('ROI evidence rows', list(payload.get('roi_evidence_rows') or []), ['decision_id', 'action', 'expected_net_value_rub', 'expected_roi', 'outcome_status', 'evidence_ready']))
    lines.append('')
    lines.extend(_render_table_md('Hardening priorities', list(payload.get('hardening_priorities') or []), ['priority_key', 'severity', 'metric', 'current', 'target', 'source_linkage']))
    return '\n'.join(lines).strip() + '\n'


def render_pilot_adoption_metrics_cli_lines(payload: Mapping[str, Any]) -> list[str]:
    summary = dict(payload.get('summary') or {})
    return [
        f"window_days={summary.get('window_days')}",
        f"dau={summary.get('dau_total')} wau={summary.get('wau_total')}",
        f"task_completion_rate={summary.get('completion_rate')} overdue={summary.get('overdue_open_tasks')}",
        f"event_latency_h_median={summary.get('median_event_entry_latency_hours')}",
        f"roi_evidence_rate={summary.get('roi_evidence_rate')} evidence_ready={summary.get('evidence_ready_decisions')}",
        f"hardening_priorities={summary.get('hardening_priorities_count')}",
    ]


__all__ = [
    'DEFAULT_PILOT_ADOPTION_CFG',
    'build_pilot_adoption_metrics_summary',
    'load_pilot_adoption_config',
    'render_pilot_adoption_metrics_cli_lines',
    'render_pilot_adoption_metrics_markdown',
]
