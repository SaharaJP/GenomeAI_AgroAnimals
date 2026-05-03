from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import ConfigValidationError, MappingSchema, coerce_bool, field_spec, load_yaml_mapping, positive_int
from core.infra import AuditRepo
from core.infra.runtime_storage import resolve_runtime_storage_settings

from core.infra.web_db import utcnow_iso
from core.observability import get_correlation_context

AUDIT_SCHEMA_VERSION = 2
_DEFAULT_SCOPE = 'active'
_ALLOWED_SCOPE = {'active', 'archived', 'all'}
_DEFAULT_RETENTION_CONFIG: dict[str, Any] = {
    'version': 1,
    'enabled': True,
    'archive_after_days': 90,
    'max_archive_batch_size': 1000,
    'facets': {
        'top_actions_limit': 8,
        'top_users_limit': 8,
    },
}


def _canonical_action_group(action: str) -> str:
    value = str(action or '').strip().lower()
    if not value:
        return 'other'
    if value.startswith('security.') or value.startswith('auth.') or value.startswith('users.'):
        return 'security'
    if value.startswith('upload.') or value.startswith('connector.upload'):
        return 'upload'
    if value.startswith('export.') or value.endswith('.export') or '.export.' in value:
        return 'export'
    if value.startswith('pipeline.') or value.startswith('job.') or value.startswith('connector.') or value.endswith('.run') or '.run.' in value:
        return 'run'
    if '.approve' in value or '.reject' in value or '.archive' in value:
        return 'approve'
    if value.startswith('config') or value.startswith('configs.') or value.startswith('playbooks_') or value.startswith('price_book.') or value.startswith('assumptions.') or value.startswith('refdata.'):
        return 'config'
    head = value.split('.', 1)[0].split('_', 1)[0]
    return head or 'other'


def _normalize_json_payload(value: Any) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {'value': value}


def _object_ref(object_type: Optional[str], object_id: Optional[str]) -> Optional[str]:
    if object_type and object_id:
        return f'{object_type}:{object_id}'
    return object_id or object_type


def _loads_json_or_none(value: Any) -> Optional[dict[str, Any]]:
    if value in (None, ''):
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else {'value': parsed}


def _canonicalize_row(row: dict[str, Any]) -> dict[str, Any]:
    schema_version = int(row.get('schema_version') or AUDIT_SCHEMA_VERSION)
    action = str(row.get('action') or '')
    object_type = row.get('object_type')
    object_id = row.get('object_id')
    before = _loads_json_or_none(row.get('before_json'))
    after = _loads_json_or_none(row.get('after_json'))
    action_group = row.get('action_group') or _canonical_action_group(action)
    object_ref = row.get('object_ref') or _object_ref(object_type, object_id)
    row['schema_version'] = schema_version
    row['action_group'] = action_group
    row['object_ref'] = object_ref
    row['before'] = before
    row['after'] = after
    row['who'] = {
        'user_id': row.get('user_id'),
        'username': row.get('username'),
        'role': row.get('role'),
        'ip': row.get('ip'),
        'user_agent': row.get('user_agent'),
    }
    row['what'] = {'action': action, 'action_group': action_group, 'status': row.get('status')}
    row['when'] = row.get('ts')
    row['object'] = {'type': object_type, 'id': object_id, 'ref': object_ref}
    return row


def validate_audit_scope(scope: Optional[str]) -> str:
    value = str(scope or _DEFAULT_SCOPE).strip().lower() or _DEFAULT_SCOPE
    if value not in _ALLOWED_SCOPE:
        allowed = ', '.join(sorted(_ALLOWED_SCOPE))
        raise ValueError(f"scope должен быть одним из: {allowed}. Получено: {scope!r}")
    return value


def load_audit_retention_config(project_root: str | Path) -> dict[str, Any]:
    path = Path(project_root) / 'configs' / 'security' / 'audit_retention_v1.yaml'
    try:
        raw = load_yaml_mapping(
            path,
            schema=MappingSchema(
                config_name='audit_retention_v1',
                fields=(
                    field_spec('version', int, default=1, validator=lambda value: None if int(value) >= 1 else 'version должна быть >= 1'),
                    field_spec('enabled', bool, default=True, coerce=coerce_bool),
                    field_spec('archive_after_days', int, default=90, validator=positive_int),
                    field_spec('max_archive_batch_size', int, default=1000, validator=positive_int),
                    field_spec('facets', dict, default={}),
                ),
            ),
            required=False,
            default={},
        )
    except ConfigValidationError as exc:
        raise ValueError(f'audit_retention_config_invalid: {exc}') from exc
    cfg = json.loads(json.dumps(_DEFAULT_RETENTION_CONFIG))
    cfg.update({k: v for k, v in raw.items() if k != 'facets'})
    facets = dict(_DEFAULT_RETENTION_CONFIG['facets'])
    raw_facets = raw.get('facets') or {}
    if raw_facets and not isinstance(raw_facets, dict):
        raise ValueError(f'{path}: facets должен быть объектом')
    for key in ('top_actions_limit', 'top_users_limit'):
        if key in raw_facets:
            err = positive_int(raw_facets[key])
            if err:
                raise ValueError(f'audit_retention_config_invalid: facets.{key}: {err} in {path}')
    facets.update(raw_facets)
    cfg['facets'] = facets

    cfg['archive_after_days'] = int(cfg.get('archive_after_days', 90))
    cfg['max_archive_batch_size'] = int(cfg.get('max_archive_batch_size', 1000))
    cfg['facets']['top_actions_limit'] = int(cfg['facets'].get('top_actions_limit', 8))
    cfg['facets']['top_users_limit'] = int(cfg['facets'].get('top_users_limit', 8))
    cfg['enabled'] = bool(cfg.get('enabled', True))
    cfg['version'] = int(cfg.get('version', 1))
    cfg['path'] = str(path)
    return cfg


def retention_cutoff_ts(*, archive_after_days: int, now: Optional[datetime] = None) -> str:
    base = now or datetime.now(timezone.utc)
    cutoff = (base - timedelta(days=int(archive_after_days))).replace(microsecond=0)
    return cutoff.isoformat()



def _write_audit_postgres_direct(*, row: dict[str, Any]) -> int:
    import os
    from psycopg import connect

    dsn = str(os.environ.get("GENOMEAI_RUNTIME_POSTGRES_DSN") or "").strip()
    if not dsn:
        raise RuntimeError("GENOMEAI_RUNTIME_POSTGRES_DSN is required for Postgres audit write")

    sql = """
        INSERT INTO audit_log(
          ts, tenant_id, user_id, username, role,
          action, action_group, object_type, object_id, object_ref,
          data_version, run_id,
          before_json, after_json,
          ip, user_agent,
          status, error, request_id,
          schema_version
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """

    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    row.get("ts"),
                    row.get("tenant_id"),
                    int(row.get("user_id") or 0),
                    row.get("username"),
                    row.get("role"),
                    row.get("action"),
                    row.get("action_group"),
                    row.get("object_type"),
                    row.get("object_id"),
                    row.get("object_ref"),
                    row.get("data_version"),
                    row.get("run_id"),
                    row.get("before_json"),
                    row.get("after_json"),
                    row.get("ip"),
                    row.get("user_agent"),
                    row.get("status"),
                    row.get("error"),
                    row.get("request_id"),
                    int(row.get("schema_version") or 2),
                ),
            )
            inserted_id = cur.fetchone()[0]
        conn.commit()
    return int(inserted_id)


def write_audit(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    action: str,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    data_version: Optional[str] = None,
    run_id: Optional[str] = None,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = 'OK',
    error: Optional[str] = None,
    request_id: Optional[str] = None,
) -> int:
    """Append-only audit log in canonical schema v2."""

    before = _normalize_json_payload(before)
    after = _normalize_json_payload(after)
    action_group = _canonical_action_group(action)
    object_ref = _object_ref(object_type, object_id)
    correlation = get_correlation_context()
    if request_id is None:
        request_id = correlation.get('request_id')
    if data_version is None:
        data_version = correlation.get('data_version')
    if run_id is None:
        run_id = correlation.get('run_id')

    row = {
        'ts': utcnow_iso(),
        'tenant_id': tenant_id,
        'user_id': int(user_id),
        'username': username,
        'role': role,
        'action': action,
        'action_group': action_group,
        'object_type': object_type,
        'object_id': object_id,
        'object_ref': object_ref,
        'data_version': data_version,
        'run_id': run_id,
        'before_json': json.dumps(before, ensure_ascii=False) if before is not None else None,
        'after_json': json.dumps(after, ensure_ascii=False) if after is not None else None,
        'ip': ip,
        'user_agent': user_agent,
        'status': status,
        'error': error,
        'request_id': request_id,
        'schema_version': AUDIT_SCHEMA_VERSION,
    }

    project_root = Path(__file__).resolve().parents[2]
    storage_dir = project_root / 'web_cabinet' / 'storage'
    runtime = resolve_runtime_storage_settings(
        project_root=project_root,
        storage_dir=storage_dir,
        sqlite_db_path=storage_dir / 'web.db',
    )

    if conn is None and str(runtime.backend or '').lower() == 'postgres':
        return _write_audit_postgres_direct(row=row)

    repo = AuditRepo(conn)
    return repo.write(row=row)


def _build_audit_where(
    *,
    tenant_id: str,
    action: Optional[str] = None,
    action_prefix: Optional[str] = None,
    action_group: Optional[str] = None,
    status: Optional[str] = None,
    username: Optional[str] = None,
    role: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    object_ref: Optional[str] = None,
    run_id: Optional[str] = None,
    data_version: Optional[str] = None,
    request_id: Optional[str] = None,
    q: Optional[str] = None,
    ts_from: Optional[str] = None,
    ts_to: Optional[str] = None,
    scope: str = _DEFAULT_SCOPE,
) -> tuple[str, list[Any]]:
    scope = validate_audit_scope(scope)
    q_sql = ' FROM audit_log WHERE tenant_id=?'
    args: list[Any] = [tenant_id]
    if scope == 'active':
        q_sql += ' AND archived_at IS NULL'
    elif scope == 'archived':
        q_sql += ' AND archived_at IS NOT NULL'
    if action:
        q_sql += ' AND action=?'
        args.append(action)
    if action_prefix:
        q_sql += ' AND action LIKE ?'
        args.append(f'{action_prefix}%')
    if action_group:
        q_sql += ' AND action_group=?'
        args.append(action_group)
    if status:
        q_sql += ' AND status=?'
        args.append(status)
    if username:
        q_sql += ' AND username=?'
        args.append(username)
    if role:
        q_sql += ' AND role=?'
        args.append(role)
    if object_type:
        q_sql += ' AND object_type=?'
        args.append(object_type)
    if object_id:
        q_sql += ' AND object_id LIKE ?'
        args.append(f'%{object_id}%')
    if object_ref:
        q_sql += ' AND object_ref LIKE ?'
        args.append(f'%{object_ref}%')
    if run_id:
        q_sql += ' AND run_id LIKE ?'
        args.append(f'%{run_id}%')
    if data_version:
        q_sql += ' AND data_version LIKE ?'
        args.append(f'%{data_version}%')
    if request_id:
        q_sql += ' AND request_id LIKE ?'
        args.append(f'%{request_id}%')
    if ts_from:
        q_sql += ' AND ts >= ?'
        args.append(ts_from)
    if ts_to:
        q_sql += ' AND ts <= ?'
        args.append(ts_to)
    if q:
        q_sql += " AND (action LIKE ? OR username LIKE ? OR COALESCE(object_type,'') LIKE ? OR COALESCE(object_id,'') LIKE ? OR COALESCE(run_id,'') LIKE ? OR COALESCE(data_version,'') LIKE ? OR COALESCE(error,'') LIKE ? OR COALESCE(before_json,'') LIKE ? OR COALESCE(after_json,'') LIKE ?)"
        needle = f'%{q}%'
        args.extend([needle] * 9)
    return q_sql, args


def list_audit(
    conn,
    *,
    tenant_id: str,
    limit: int = 200,
    offset: int = 0,
    action: Optional[str] = None,
    action_prefix: Optional[str] = None,
    action_group: Optional[str] = None,
    status: Optional[str] = None,
    username: Optional[str] = None,
    role: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    object_ref: Optional[str] = None,
    run_id: Optional[str] = None,
    data_version: Optional[str] = None,
    request_id: Optional[str] = None,
    q: Optional[str] = None,
    ts_from: Optional[str] = None,
    ts_to: Optional[str] = None,
    scope: str = _DEFAULT_SCOPE,
) -> list[dict[str, Any]]:
    where_sql, args = _build_audit_where(
        tenant_id=tenant_id,
        action=action,
        action_prefix=action_prefix,
        action_group=action_group,
        status=status,
        username=username,
        role=role,
        object_type=object_type,
        object_id=object_id,
        object_ref=object_ref,
        run_id=run_id,
        data_version=data_version,
        request_id=request_id,
        q=q,
        ts_from=ts_from,
        ts_to=ts_to,
        scope=scope,
    )
    q_sql = 'SELECT *' + where_sql + ' ORDER BY id DESC LIMIT ? OFFSET ?'
    args += [max(1, min(int(limit), 5000)), max(0, int(offset))]
    rows = AuditRepo(conn).list_rows(select_sql=q_sql, args=args)
    return [_canonicalize_row(r) for r in rows]


def aggregate_audit_facets(
    conn,
    *,
    tenant_id: str,
    action: Optional[str] = None,
    action_prefix: Optional[str] = None,
    action_group: Optional[str] = None,
    status: Optional[str] = None,
    username: Optional[str] = None,
    role: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    object_ref: Optional[str] = None,
    run_id: Optional[str] = None,
    data_version: Optional[str] = None,
    request_id: Optional[str] = None,
    q: Optional[str] = None,
    ts_from: Optional[str] = None,
    ts_to: Optional[str] = None,
    scope: str = _DEFAULT_SCOPE,
    top_actions_limit: int = 8,
    top_users_limit: int = 8,
) -> dict[str, Any]:
    where_sql, args = _build_audit_where(
        tenant_id=tenant_id,
        action=action,
        action_prefix=action_prefix,
        action_group=action_group,
        status=status,
        username=username,
        role=role,
        object_type=object_type,
        object_id=object_id,
        object_ref=object_ref,
        run_id=run_id,
        data_version=data_version,
        request_id=request_id,
        q=q,
        ts_from=ts_from,
        ts_to=ts_to,
        scope=scope,
    )
    top_actions_limit = max(1, min(int(top_actions_limit), 50))
    top_users_limit = max(1, min(int(top_users_limit), 50))
    repo = AuditRepo(conn)

    summary_row = repo.fetch_one(
        select_sql='SELECT COUNT(*) AS total, MIN(ts) AS first_ts, MAX(ts) AS last_ts' + where_sql,
        args=args,
    )
    inventory_row = repo.fetch_one(
        select_sql="""
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN archived_at IS NULL THEN 1 ELSE 0 END) AS active_rows,
          SUM(CASE WHEN archived_at IS NOT NULL THEN 1 ELSE 0 END) AS archived_rows
        FROM audit_log
        WHERE tenant_id=?
        """,
        args=[tenant_id],
    )

    def _group(sql_tail: str, limit: int) -> list[dict[str, Any]]:
        rows = repo.list_rows(
            select_sql='SELECT ' + sql_tail + where_sql + ' GROUP BY key ORDER BY count DESC, key ASC LIMIT ?',
            args=list(args) + [limit],
        )
        return [{'key': r['key'], 'count': int(r['count'])} for r in rows if r['key'] not in (None, '')]

    by_action_group = _group("COALESCE(action_group, 'other') AS key, COUNT(*) AS count ", 20)
    by_status = _group("COALESCE(status, 'UNKNOWN') AS key, COUNT(*) AS count ", 10)
    top_actions = _group("COALESCE(action, '') AS key, COUNT(*) AS count ", top_actions_limit)
    top_users = _group("COALESCE(username, '') AS key, COUNT(*) AS count ", top_users_limit)

    return {
        'summary': {
            'filtered_total': int(summary_row['total'] or 0),
            'first_ts': summary_row['first_ts'],
            'last_ts': summary_row['last_ts'],
            'scope': validate_audit_scope(scope),
            'inventory_total': int(inventory_row['total_rows'] or 0),
            'inventory_active': int(inventory_row['active_rows'] or 0),
            'inventory_archived': int(inventory_row['archived_rows'] or 0),
        },
        'by_action_group': by_action_group,
        'by_status': by_status,
        'top_actions': top_actions,
        'top_users': top_users,
    }


def count_archivable_audit(conn, *, tenant_id: str, older_than_ts: str) -> int:
    row = AuditRepo(conn).fetch_one(
        select_sql='SELECT COUNT(*) AS c FROM audit_log WHERE tenant_id=? AND archived_at IS NULL AND ts < ?',
        args=[tenant_id, older_than_ts],
    )
    return int(row['c'] or 0)


def archive_old_audit(
    conn,
    *,
    tenant_id: str,
    older_than_ts: str,
    limit: int,
    reason: str = 'retention',
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100000))
    batch_id = uuid.uuid4().hex[:12]
    archived_at = utcnow_iso()
    return AuditRepo(conn).archive_batch(
        tenant_id=tenant_id,
        older_than_ts=older_than_ts,
        limit=limit,
        reason=reason,
        archived_at=archived_at,
        batch_id=batch_id,
    )


__all__ = [
    'AUDIT_SCHEMA_VERSION',
    '_canonical_action_group',
    '_object_ref',
    'aggregate_audit_facets',
    'archive_old_audit',
    'count_archivable_audit',
    'list_audit',
    'load_audit_retention_config',
    'retention_cutoff_ts',
    'validate_audit_scope',
    'write_audit',
]
