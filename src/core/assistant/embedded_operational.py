from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

import core.security as rbac


@dataclass(frozen=True)
class EmbeddedAssistantAction:
    key: str
    label: str
    kind: str
    reason: str
    page: str | None = None
    requires_permission: str | None = None
    decision_action: str | None = None
    session_updates: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AssistantAnswerLinkage:
    context_kind: str
    object_type: str
    object_id: str
    farm_id: str
    group_id: str
    related_alert: str
    worklist_id: str
    task_id: str
    data_version: str
    qc_run: str
    model_version: str
    scoring_run: str
    report_version: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _clean(value: Any) -> str:
    return str(value or "").strip()


_ALLOWED_KINDS = {"home", "alert", "animal_profile", "group_profile", "report_view", "worklist", "planner_item"}


def build_assistant_answer_linkage(
    *,
    context_kind: str,
    object_type: str | None = None,
    object_id: str | None = None,
    farm_id: str | None = None,
    group_id: str | None = None,
    related_alert: str | None = None,
    worklist_id: str | None = None,
    task_id: str | None = None,
    data_version: str | None = None,
    qc_run: str | None = None,
    model_version: str | None = None,
    scoring_run: str | None = None,
    report_version: str | None = None,
) -> AssistantAnswerLinkage:
    kind = _clean(context_kind).lower() or "home"
    if kind not in _ALLOWED_KINDS:
        kind = "home"
    return AssistantAnswerLinkage(
        context_kind=kind,
        object_type=_clean(object_type),
        object_id=_clean(object_id),
        farm_id=_clean(farm_id),
        group_id=_clean(group_id),
        related_alert=_clean(related_alert),
        worklist_id=_clean(worklist_id),
        task_id=_clean(task_id),
        data_version=_clean(data_version),
        qc_run=_clean(qc_run),
        model_version=_clean(model_version),
        scoring_run=_clean(scoring_run),
        report_version=_clean(report_version),
    )


def build_embedded_assistant_actions(
    *,
    context_kind: str,
    object_type: str | None = None,
    object_id: str | None = None,
    farm_id: str | None = None,
    group_id: str | None = None,
    related_alert: str | None = None,
    worklist_id: str | None = None,
    report_version: str | None = None,
    worklist_type: str | None = None,
) -> list[EmbeddedAssistantAction]:
    kind = _clean(context_kind).lower() or "home"
    object_type_v = _clean(object_type).lower()
    object_id_v = _clean(object_id)
    farm_id_v = _clean(farm_id)
    group_id_v = _clean(group_id)
    alert_id_v = _clean(related_alert)
    worklist_id_v = _clean(worklist_id)
    report_version_v = _clean(report_version)
    worklist_type_v = _clean(worklist_type).lower()

    actions: list[EmbeddedAssistantAction] = []
    seen: set[tuple[str, str, str]] = set()

    def add(action: EmbeddedAssistantAction) -> None:
        key = (action.key, action.kind, action.page or action.decision_action or "")
        if key in seen:
            return
        seen.add(key)
        actions.append(action)

    def nav(*, key: str, label: str, reason: str, page: str, requires_permission: str | None = None, updates: Mapping[str, Any] | None = None) -> None:
        payload = {str(k): _clean(v) for k, v in dict(updates or {}).items() if _clean(v)}
        add(
            EmbeddedAssistantAction(
                key=key,
                label=label,
                kind="navigate",
                reason=reason,
                page=page,
                requires_permission=requires_permission,
                session_updates=payload or None,
            )
        )

    def decision(*, key: str, label: str, reason: str, decision_action: str = "assistant.triage.note") -> None:
        add(
            EmbeddedAssistantAction(
                key=key,
                label=label,
                kind="decision_note",
                reason=reason,
                decision_action=decision_action,
                requires_permission=rbac.PERM_DECISIONLOG_WRITE,
            )
        )

    if kind == "home":
        nav(key="open_daily_worklists", label="Открыть daily worklists", reason="Перейти из summary к очереди ежедневного исполнения по ролям.", page="pages/43_Daily_Worklists_By_Role.py", requires_permission=rbac.PERM_TASKS_VIEW)
        nav(key="open_alert_center", label="Открыть alert center", reason="Перейти к triage сигналов и связанным действиям.", page="pages/5_Alert_Center_v2.py", requires_permission=rbac.PERM_ALERTS_VIEW)
        nav(key="open_reports", label="Открыть reports", reason="Перейти к регулярным отчётам и приложениям по версиям данных.", page="pages/16_Report_View.py", requires_permission=rbac.PERM_REPORTS_VIEW)
        decision(key="home_note", label="Зафиксировать weekly triage note", reason="Сохранить вывод помощника как append-only note в Decision Log.")

    if kind == "alert":
        nav(key="open_alert_center", label="Открыть alert detail", reason="Открыть alert surface и продолжить triage по объекту/сигналу.", page="pages/5_Alert_Center_v2.py", requires_permission=rbac.PERM_ALERTS_VIEW, updates={"alert_center.selected_alert_id": alert_id_v})
        if object_type_v == "animal" and object_id_v:
            nav(key="open_animal_profile", label="Открыть animal profile", reason="Провалиться от сигнала к карточке животного и связанным worklists.", page="pages/15_Animal_Profile.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_animal_id": object_id_v})
        if object_type_v == "group" and object_id_v:
            nav(key="open_group_profile", label="Открыть group profile", reason="Открыть группу/pen и проверить peer-context, roster и recent events.", page="pages/14_Group_Profile.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_pen_id": object_id_v})
        nav(key="open_daily_worklists", label="Открыть daily worklists", reason="Перейти к очереди исполнения и handoff по роли/команде.", page="pages/43_Daily_Worklists_By_Role.py", requires_permission=rbac.PERM_TASKS_VIEW)
        decision(key="alert_note", label="Зафиксировать triage note", reason="Сохранить вывод по сигналу как traceable note в Decision Log.")

    if kind == "animal_profile":
        nav(key="open_operational_planner", label="Открыть operational planner", reason="Перейти к time-bucket plan и связанным worklists по объекту.", page="pages/44_Operational_Planner.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_animal_id": object_id_v})
        nav(key="open_daily_worklists", label="Открыть daily worklists", reason="Открыть ежедневную очередь действий по животному и связанным алертам.", page="pages/43_Daily_Worklists_By_Role.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_animal_id": object_id_v})
        nav(key="open_report_builder", label="Открыть report builder", reason="Подготовить operational report по объекту без потери контекста.", page="pages/55_Operational_Report_Builder.py", requires_permission=rbac.PERM_REPORTS_VIEW, updates={"nav_animal_id": object_id_v})
        decision(key="animal_note", label="Зафиксировать action note", reason="Сохранить next-step по животному как append-only note в Decision Log.")

    if kind == "group_profile":
        nav(key="open_operational_planner", label="Открыть operational planner", reason="Перейти к очереди группы, bottleneck-ам и time buckets.", page="pages/44_Operational_Planner.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_pen_id": object_id_v or group_id_v})
        nav(key="open_daily_worklists", label="Открыть daily worklists", reason="Открыть ежедневную очередь по группе/pen и связанным объектам.", page="pages/43_Daily_Worklists_By_Role.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_pen_id": object_id_v or group_id_v})
        nav(key="open_report_builder", label="Открыть report builder", reason="Подготовить operational report по группе и связанным deviations.", page="pages/55_Operational_Report_Builder.py", requires_permission=rbac.PERM_REPORTS_VIEW, updates={"nav_pen_id": object_id_v or group_id_v})
        decision(key="group_note", label="Зафиксировать group triage note", reason="Сохранить note по группе как append-only запись с link на объект и версии.")

    if kind == "report_view":
        nav(key="open_report_bridge", label="Открыть bridge к action surfaces", reason="Перейти к actionable rows/sections и связанным объектам без копирования текста.", page="pages/16_Report_View.py", requires_permission=rbac.PERM_REPORTS_VIEW, updates={"report_view.report_version": report_version_v})
        nav(key="open_operational_planner", label="Открыть operational planner", reason="Перейти от summary к исполнению по buckets и ролям.", page="pages/44_Operational_Planner.py", requires_permission=rbac.PERM_TASKS_VIEW)
        nav(key="open_daily_worklists", label="Открыть daily worklists", reason="Провалиться в очереди выполнения по итогам отчёта.", page="pages/43_Daily_Worklists_By_Role.py", requires_permission=rbac.PERM_TASKS_VIEW)
        decision(key="report_note", label="Зафиксировать report action note", reason="Сохранить вывод отчёта как traceable decision note с привязкой к report_version.")

    if kind == "worklist":
        if object_type_v == "animal" and object_id_v:
            nav(key="open_animal_profile", label="Открыть animal profile", reason="Перейти к карточке животного и связанным событиям/рекомендациям.", page="pages/15_Animal_Profile.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_animal_id": object_id_v})
        if object_type_v == "group" and object_id_v:
            nav(key="open_group_profile", label="Открыть group profile", reason="Открыть группу/pen и проверить roster, status и recent events.", page="pages/14_Group_Profile.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_pen_id": object_id_v})
        if alert_id_v:
            nav(key="open_alert_center", label="Открыть linked alert", reason="Провалиться к сигналу, который поднял worklist.", page="pages/5_Alert_Center_v2.py", requires_permission=rbac.PERM_ALERTS_VIEW, updates={"alert_center.selected_alert_id": alert_id_v})
        nav(key="open_economics_per_action", label="Открыть economics per action", reason="Проверить ожидаемый эффект действия и альтернативы исполнения.", page="pages/65_Economics_Per_Action.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_worklist_id": worklist_id_v})
        if worklist_type_v in {"reproduction", "vet", "health_follow_up", "movement", "culling_review", "manager_review", "milk_quality"}:
            nav(key="open_operational_what_if", label="Открыть operational what-if", reason="Сравнить explainable next-step сценарии прямо от worklist.", page="pages/67_Operational_What_If.py", requires_permission=rbac.PERM_WHATIF_SCENARIOS_VIEW, updates={"nav_worklist_id": worklist_id_v})
        decision(key="worklist_note", label="Зафиксировать worklist execution note", reason="Сохранить next-step/handover note по очереди исполнения в Decision Log.")

    if kind == "planner_item":
        if object_type_v == "animal" and object_id_v:
            nav(key="open_animal_profile", label="Открыть animal profile", reason="Провалиться к operational объекту из planner item.", page="pages/15_Animal_Profile.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_animal_id": object_id_v})
        if object_type_v == "group" and object_id_v:
            nav(key="open_group_profile", label="Открыть group profile", reason="Провалиться к group/pen из planner item.", page="pages/14_Group_Profile.py", requires_permission=rbac.PERM_TASKS_VIEW, updates={"nav_pen_id": object_id_v})
        nav(key="open_daily_worklists", label="Открыть daily worklists", reason="Перейти из planner к executor queue по роли/команде.", page="pages/43_Daily_Worklists_By_Role.py", requires_permission=rbac.PERM_TASKS_VIEW)
        nav(key="open_tasks_workflow", label="Открыть tasks workflow", reason="Провалиться к task-level execution и overdue control.", page="pages/32_Tasks_Workflow_Operations.py", requires_permission=rbac.PERM_TASKS_VIEW)
        decision(key="planner_note", label="Зафиксировать planner triage note", reason="Сохранить решение/комментарий по planner item как append-only note.")

    if farm_id_v:
        nav(key="open_home", label="Вернуться к home summary", reason="Быстрый возврат к role-aware home page с тем же operational контекстом.", page="pages/0_Home_v3.py")

    return actions


def filter_embedded_assistant_actions(
    actions: Iterable[EmbeddedAssistantAction],
    *,
    effective_permissions: Iterable[str] | None,
) -> list[EmbeddedAssistantAction]:
    perms = {str(p) for p in (effective_permissions or []) if _clean(p)}
    visible: list[EmbeddedAssistantAction] = []
    for item in actions or []:
        required = _clean(item.requires_permission)
        if required and required not in perms:
            continue
        visible.append(item)
    return visible


__all__ = [
    'EmbeddedAssistantAction',
    'AssistantAnswerLinkage',
    'build_assistant_answer_linkage',
    'build_embedded_assistant_actions',
    'filter_embedded_assistant_actions',
]
