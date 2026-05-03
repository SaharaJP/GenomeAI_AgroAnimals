from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.audit.events import write_audit
from core.list_builder import build_universal_list_snapshot
from core.operational.quick_entry import (
    AnimalEventQuickEntryError,
    animal_event_quick_entry_catalog,
    create_animal_event_use_case,
)
from core.workflow.worklists import create_worklist_use_case, get_worklist


@dataclass(slots=True)
class CowsideEventEntryError(ValueError):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details or {})}


TEAM_ALIASES: dict[str, str] = {
    "vet": "team-health",
    "health": "team-health",
    "zootech": "team-repro",
    "repro": "team-repro",
    "reproduction": "team-repro",
    "operator": "team-repro",
    "data": "team-data",
    "qc": "team-qc",
    "econ": "team-econ",
}


COWSIDE_EVENT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "key": "heat_observed",
        "label": "🐄 Heat",
        "hint": "Зафиксировать охоту и при необходимости поставить repro follow-up.",
        "event_type": "heat",
        "reason_code": "HEAT_OBSERVED",
        "roles": ("Zootech", "Operator", "Admin"),
        "default_comment_placeholder": "Например: замечена охота / sensor flag / номер группы",
        "default_follow_up": {
            "enabled": True,
            "worklist_type": "reproduction",
            "assignee_team": "team-repro",
            "due_days": 1,
            "title": "Repro follow-up after heat",
        },
    },
    {
        "key": "insemination_done",
        "label": "💉 Insemination",
        "hint": "Осеменение у животного без перехода в desktop flow.",
        "event_type": "insemination",
        "reason_code": "INSEMINATION_PERFORMED",
        "roles": ("Zootech", "Operator", "Admin"),
        "default_comment_placeholder": "Например: bull / technician / batch",
        "default_follow_up": {
            "enabled": True,
            "worklist_type": "reproduction",
            "assignee_team": "team-repro",
            "due_days": 28,
            "title": "Preg-check follow-up",
        },
    },
    {
        "key": "preg_check_positive",
        "label": "✅ Preg +",
        "hint": "Подтверждение стельности по текущему осмотру.",
        "event_type": "preg_check",
        "reason_code": "PREGNANCY_CONFIRMED",
        "roles": ("Zootech", "Vet", "Operator", "Admin"),
        "default_comment_placeholder": "Например: confirmed by ultrasound",
        "default_follow_up": {"enabled": False},
    },
    {
        "key": "preg_check_open",
        "label": "↩️ Preg open",
        "hint": "Фиксация open/negative preg check с быстрым repro follow-up.",
        "event_type": "preg_check",
        "reason_code": "PREGNANCY_OPEN",
        "roles": ("Zootech", "Vet", "Operator", "Admin"),
        "default_comment_placeholder": "Например: open / recheck needed",
        "default_follow_up": {
            "enabled": True,
            "worklist_type": "reproduction",
            "assignee_team": "team-repro",
            "due_days": 1,
            "title": "Repro follow-up after open preg check",
        },
    },
    {
        "key": "treatment_started",
        "label": "💊 Treatment",
        "hint": "Старт treatment/protocol у животного с опциональным health follow-up.",
        "event_type": "treatment",
        "reason_code": "TREATMENT_PROTOCOL",
        "roles": ("Vet", "Admin"),
        "default_comment_placeholder": "Например: drug / dose / protocol ref",
        "default_follow_up": {
            "enabled": True,
            "worklist_type": "health_follow_up",
            "assignee_team": "team-health",
            "due_days": 1,
            "title": "Health follow-up after treatment",
        },
    },
    {
        "key": "pen_move",
        "label": "↔️ Pen move",
        "hint": "Быстрая фиксация перевода/перемещения.",
        "event_type": "pen_move",
        "reason_code": "PEN_REBALANCE",
        "roles": ("Zootech", "Operator", "Admin"),
        "default_comment_placeholder": "Например: new pen / reason",
        "default_follow_up": {"enabled": False},
    },
    {
        "key": "dry_off",
        "label": "🌙 Dry-off",
        "hint": "Фиксация dry-off в полевом контексте.",
        "event_type": "dry_off",
        "reason_code": "DRY_PERIOD_START",
        "roles": ("Zootech", "Operator", "Admin"),
        "default_comment_placeholder": "Например: planned dry period start",
        "default_follow_up": {"enabled": False},
    },
    {
        "key": "manual_note",
        "label": "📝 Note",
        "hint": "Bounded manual note только в taxonomy system event semantics.",
        "event_type": "manual_note",
        "reason_code": "MANUAL_NOTE_ADDED",
        "roles": ("Vet", "Zootech", "Operator", "Admin"),
        "default_comment_placeholder": "Короткая операционная заметка обязательна",
        "default_follow_up": {
            "enabled": False,
        },
    },
)


def _raise(code: str, message: str, **details: Any) -> None:
    raise CowsideEventEntryError(code=code, message=message, details={k: v for k, v in details.items() if v is not None})


def _clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_cowside_team(team: str | None) -> str | None:
    raw = _clean(team)
    if not raw:
        return None
    return TEAM_ALIASES.get(raw.lower(), raw)


def list_cowside_event_templates(*, role: str | None = None) -> list[dict[str, Any]]:
    role_raw = _clean(role)
    rows: list[dict[str, Any]] = []
    for item in COWSIDE_EVENT_TEMPLATES:
        allowed = tuple(str(x) for x in (item.get("roles") or ()))
        if role_raw and allowed and role_raw not in allowed:
            continue
        rows.append({
            "key": _clean(item.get("key")),
            "label": _clean(item.get("label")),
            "hint": _clean(item.get("hint")),
            "event_type": _clean(item.get("event_type")),
            "reason_code": _clean(item.get("reason_code")),
            "roles": allowed,
            "default_comment_placeholder": _clean(item.get("default_comment_placeholder")),
            "default_follow_up": dict(item.get("default_follow_up") or {}),
        })
    return rows


def get_cowside_event_template(*, template_key: str, role: str | None = None) -> dict[str, Any]:
    wanted = _clean(template_key)
    if not wanted:
        _raise("template_required", "Нужно выбрать quick template.")
    for item in list_cowside_event_templates(role=role):
        if _clean(item.get("key")) == wanted:
            return item
    _raise("template_not_found", "Quick template не найден или недоступен для роли.", template_key=wanted, role=role)


def search_cowside_animals(
    *,
    input_dir: Path,
    asof_date: date,
    role: str,
    q: str | None = None,
    site_id: str | None = None,
    pen_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {}
    if _clean(site_id):
        filters["site_id"] = _clean(site_id)
    if _clean(pen_id):
        filters["pen_id"] = _clean(pen_id)
    if _clean(status):
        filters["status"] = _clean(status)
    snap = build_universal_list_snapshot(
        input_dir=Path(input_dir),
        asof_date=asof_date,
        role=role,
        object_type="animals",
        filters=filters,
        selected_columns=("animal_id", "pen_name", "status", "breed", "parity", "site_id", "pen_id"),
        sort_by="animal_id",
        sort_dir="asc",
        limit=max(50, int(limit or 20) * 5),
    )
    work = pd.DataFrame(list(snap.get("rows") or []))
    if work.empty:
        return []
    extras_path = Path(input_dir) / 'dm_animals.csv'
    try:
        extras = pd.read_csv(extras_path) if extras_path.exists() else pd.DataFrame()
    except Exception:
        extras = pd.DataFrame()
    if not extras.empty and 'animal_id' in extras.columns:
        merge_cols = [c for c in ('animal_id', 'ear_tag', 'external_id', 'current_pen_name', 'current_pen_id') if c in extras.columns]
        work = work.merge(extras[merge_cols].drop_duplicates('animal_id'), on='animal_id', how='left')
    query = _clean(q).lower()
    if query:
        blob_cols = [c for c in ('animal_id', 'breed', 'status', 'pen_name', 'pen_id', 'ear_tag', 'external_id') if c in work.columns]
        mask = pd.Series([False] * len(work), index=work.index)
        for col in blob_cols:
            mask = mask | work[col].astype(str).str.lower().str.contains(query, na=False)
        work = work[mask].copy()
    work = work.head(max(1, int(limit or 20)))
    rows: list[dict[str, Any]] = []
    for row in work.to_dict(orient='records'):
        animal_id = _clean(row.get("animal_id"))
        if not animal_id:
            continue
        pen_name = _clean(row.get('pen_name')) or _clean(row.get('current_pen_name'))
        pen_id = _clean(row.get('pen_id')) or _clean(row.get('current_pen_id'))
        label_bits = [animal_id, _clean(row.get('ear_tag')) or pen_name or '—', _clean(row.get('status')) or '—']
        rows.append({
            "animal_id": animal_id,
            "label": ' · '.join(label_bits),
            "pen_name": pen_name,
            "pen_id": pen_id,
            "status": _clean(row.get("status")),
            "breed": _clean(row.get("breed")),
            "parity": row.get("parity"),
            "site_id": _clean(row.get("site_id")),
            "ear_tag": _clean(row.get('ear_tag')),
            "external_id": _clean(row.get('external_id')),
        })
    return rows


def _parse_due_date(value: str | date | None) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    raw = _clean(value)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        try:
            return date.fromisoformat(raw).isoformat()
        except Exception:
            _raise("follow_up_due_invalid", "Дата follow-up заполнена некорректно.", value=raw)
    return None


def _default_follow_up_due(*, event_ts: str, due_days: int | None) -> str:
    try:
        base = datetime.fromisoformat(str(event_ts).replace("Z", "+00:00")).date()
    except Exception:
        base = date.today()
    return (base + timedelta(days=max(0, int(due_days or 1)))).isoformat()


def create_cowside_event_entry_use_case(
    *,
    conn,
    tenant_id: str,
    animal_id: str,
    template_key: str,
    event_ts: str,
    user_id: int,
    username: str,
    role: str,
    comment: str | None = None,
    create_follow_up: bool = False,
    follow_up_due_at: str | date | None = None,
    follow_up_title: str | None = None,
    follow_up_team: str | None = None,
    follow_up_type: str | None = None,
    priority: int = 2,
    farm_id: str | None = None,
    site_id: str | None = None,
    lactation_id: str | None = None,
    linked_task_id: str | None = None,
    linked_decision_id: str | None = None,
    linked_object_type: str | None = None,
    linked_object_id: str | None = None,
    data_version: str | None = None,
    qc_run: str | None = None,
    model_version: str | None = None,
    scoring_run: str | None = None,
    report_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    if not _clean(animal_id):
        _raise("animal_id_required", "Нужно выбрать животное.")
    template = get_cowside_event_template(template_key=template_key, role=role)
    follow_cfg = dict(template.get("default_follow_up") or {})
    versions = {
        "data_version": _clean(data_version) or None,
        "qc_run": _clean(qc_run) or None,
        "model_version": _clean(model_version) or None,
        "scoring_run": _clean(scoring_run) or None,
        "report_version": _clean(report_version) or None,
    }
    extra_payload = {
        "entry_mode": "cowside_entry",
        "template_key": _clean(template.get("key")),
        "template_label": _clean(template.get("label")),
        "source_versions": {k: v for k, v in versions.items() if v},
    }
    try:
        event_res = create_animal_event_use_case(
            conn=conn,
            tenant_id=tenant_id,
            animal_id=_clean(animal_id),
            event_type=_clean(template.get("event_type")),
            event_ts=event_ts,
            user_id=int(user_id or 0),
            username=_clean(username),
            role=_clean(role),
            comment=comment,
            reason_code=_clean(template.get("reason_code")) or None,
            farm_id=_clean(farm_id) or None,
            site_id=_clean(site_id) or None,
            lactation_id=_clean(lactation_id) or None,
            linked_task_id=_clean(linked_task_id) or None,
            linked_decision_id=_clean(linked_decision_id) or None,
            linked_object_type=_clean(linked_object_type) or None,
            linked_object_id=_clean(linked_object_id) or None,
            data_version=versions["data_version"],
            request_id=_clean(request_id) or None,
            extra_payload=extra_payload,
        )
    except AnimalEventQuickEntryError as exc:
        _raise(exc.code, exc.message, **dict(exc.details or {}))
    worklist_after: dict[str, Any] | None = None
    worklist_id: str | None = None
    if create_follow_up:
        wl_type = _clean(follow_up_type) or _clean(follow_cfg.get("worklist_type")) or "health_follow_up"
        due_at = _parse_due_date(follow_up_due_at) or _default_follow_up_due(event_ts=event_ts, due_days=int(follow_cfg.get("due_days") or 1))
        team = normalize_cowside_team(follow_up_team) or normalize_cowside_team(str(follow_cfg.get("assignee_team") or "")) or "team-health"
        title = _clean(follow_up_title) or _clean(follow_cfg.get("title")) or f"Follow-up for {_clean(animal_id)}"
        event_after = dict(event_res.get("after") or {})
        worklist_res = create_worklist_use_case(
            conn=conn,
            tenant_id=tenant_id,
            worklist_type=wl_type,
            user_id=int(user_id or 0),
            username=_clean(username),
            role=_clean(role),
            title=title,
            task_type=f"cowside.follow_up.{wl_type}",
            priority=int(priority or 2),
            due_at=due_at,
            assignee_team=team,
            object_type="animal",
            object_id=_clean(animal_id),
            linked_task_id=_clean(linked_task_id) or None,
            linked_decision_id=_clean(linked_decision_id) or None,
            linked_source_facts=[
                {"label": "template", "text": _clean(template.get("label"))},
                {"label": "event_type", "text": _clean(template.get("event_type"))},
                {"label": "reason_code", "text": _clean(template.get("reason_code"))},
                {"label": "event_id", "text": _clean(event_res.get("event_id"))},
            ] + ([{"label": "comment", "text": _clean(comment)}] if _clean(comment) else []),
            attachments=[
                {
                    "kind": "cowside_event_link",
                    "event_id": _clean(event_res.get("event_id")),
                    "template_key": _clean(template.get("key")),
                    "source": "cowside_event_entry",
                }
            ],
            why={
                "source": "cowside_event_entry",
                "event_id": _clean(event_res.get("event_id")),
                "event_type": _clean(template.get("event_type")),
                "reason_code": _clean(template.get("reason_code")),
                "template_key": _clean(template.get("key")),
            },
            what_to_do=[
                {"action": "review_animal", "text": "Открыть животное и выполнить follow-up в полевом контексте."},
            ],
            data_version=versions["data_version"],
            qc_run=versions["qc_run"],
            model_version=versions["model_version"],
            scoring_run=versions["scoring_run"],
            report_version=versions["report_version"],
            dedupe_key=f"cowside_follow_up:{_clean(animal_id)}:{_clean(event_res.get('event_id'))}:{wl_type}",
            request_id=_clean(request_id) or None,
        )
        worklist_id = _clean(worklist_res.get("worklist_id"))
        worklist_after = dict(worklist_res.get("after") or get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id) or {})

    write_audit(
        conn,
        tenant_id=_clean(tenant_id) or "default",
        user_id=int(user_id or 0),
        username=_clean(username),
        role=_clean(role),
        action="animal_event.cowside_entry.submit",
        object_type="animal",
        object_id=_clean(animal_id),
        data_version=versions["data_version"],
        run_id=None,
        before=None,
        after={
            "template_key": _clean(template.get("key")),
            "event_id": _clean(event_res.get("event_id")),
            "worklist_id": worklist_id,
            "create_follow_up": bool(create_follow_up),
            "source_versions": {k: v for k, v in versions.items() if v},
        },
        status="OK",
        request_id=_clean(request_id) or None,
    )
    notice = "Событие зафиксировано в истории животного."
    if worklist_id:
        notice += " Follow-up создан и связан с полевым вводом."
    return {
        "ok": True,
        "template": template,
        "event": dict(event_res.get("after") or {}),
        "event_id": _clean(event_res.get("event_id")),
        "worklist": worklist_after,
        "worklist_id": worklist_id,
        "notice": notice,
        "source_versions": {k: v for k, v in versions.items() if v},
    }


__all__ = [
    "COWSIDE_EVENT_TEMPLATES",
    "CowsideEventEntryError",
    "create_cowside_event_entry_use_case",
    "get_cowside_event_template",
    "list_cowside_event_templates",
    "normalize_cowside_team",
    "search_cowside_animals",
]
