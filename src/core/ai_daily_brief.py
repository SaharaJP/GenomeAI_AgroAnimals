from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


def _text(value: Any) -> str:
    return str(value or "").strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class DailyBriefFact:
    label: str
    value: str
    source: str = ""
    source_linkage: str = ""


@dataclass(frozen=True)
class DailyBriefAction:
    key: str
    label: str
    page: str
    reason: str = ""
    expected_effect: str = ""
    object_type: str = ""
    object_id: str = ""


@dataclass(frozen=True)
class DailyBriefItem:
    key: str
    title: str
    summary: str
    why_now: str
    expected_effect: str
    linked_facts: tuple[DailyBriefFact, ...]
    linked_actions: tuple[DailyBriefAction, ...]
    source_linkage: dict[str, str]


@dataclass(frozen=True)
class DailyBrief:
    role: str
    data_version: str
    brief_version: str
    generated_at_utc: str
    generated_mode: str
    fallback_without_llm: bool
    source_versions: dict[str, str]
    items: tuple[DailyBriefItem, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _collect_source_versions(snapshot: Mapping[str, Any], *, data_version: str) -> dict[str, str]:
    report = dict(snapshot.get("report") or {})
    role_focus = dict(snapshot.get("role_focus") or {})
    out = {"data_version": _text(data_version) or "dv_demo"}
    for key in ("report_version", "qc_run", "model_version", "scoring_run"):
        value = _text(report.get(key) or role_focus.get(key))
        if value:
            out[key] = value
    return out


def _base_action(key: str, label: str, page: str, reason: str, expected_effect: str, *, object_type: str = "", object_id: str = "") -> DailyBriefAction:
    return DailyBriefAction(
        key=key,
        label=label,
        page=page,
        reason=reason,
        expected_effect=expected_effect,
        object_type=object_type,
        object_id=object_id,
    )


def _build_operational_items(*, role: str, snapshot: Mapping[str, Any], source_versions: Mapping[str, str]) -> list[DailyBriefItem]:
    report = dict(snapshot.get("report") or {})
    op = dict(snapshot.get("operational") or {})
    alerts = dict(op.get("alerts") or {})
    tasks = dict(op.get("tasks") or {})
    focus = dict(snapshot.get("role_focus") or {})

    active_alerts = int((alerts.get("new") or 0) + (alerts.get("acknowledged") or 0))
    open_tasks = int(tasks.get("open") or 0)
    has_report = bool(report.get("has_any"))
    report_version = _text(report.get("report_version"))

    items: list[DailyBriefItem] = []

    items.append(
        DailyBriefItem(
            key="operational_load",
            title="Что требует внимания прямо сейчас",
            summary=f"Есть {active_alerts} активных сигналов и {open_tasks} открытых задач.",
            why_now="Это ближайшая operational нагрузка текущего цикла; она already linked to alerts/tasks и не требует ручной реконструкции.",
            expected_effect="Снижение time-to-triage и переход к исполнению без потери контекста.",
            linked_facts=(
                DailyBriefFact("active_alerts", str(active_alerts), "operational_summary", "operational.alerts"),
                DailyBriefFact("open_tasks", str(open_tasks), "operational_summary", "operational.tasks"),
            ),
            linked_actions=(
                _base_action("open_worklists", "Открыть daily worklists", "pages/43_Daily_Worklists_By_Role.py", "Там лежат текущие очереди исполнения и triage.", "Переход от brief к конкретным действиям."),
                _base_action("open_planner", "Открыть operational planner", "pages/44_Operational_Planner.py", "Планировщик нужен для bucket/shift view.", "Переход к планированию исполнения по смене."),
                _base_action("open_alerts", "Открыть alert center", "pages/5_Alert_Center_v2.py", "Alert center нужен для приоритизации сигналов.", "Быстрый triage и review сигналов."),
            ),
            source_linkage=dict(source_versions),
        )
    )

    if has_report:
        items.append(
            DailyBriefItem(
                key="report_ready",
                title="Есть готовый отчёт текущего контура",
                summary=f"Доступен report_version={report_version or 'NA'}.",
                why_now="Отчёт уже собран из fact-pack и может использоваться как governed источник краткой сводки и linked actions.",
                expected_effect="Быстрый переход от статуса дня к source-linked report facts и approval/archive flows.",
                linked_facts=(
                    DailyBriefFact("report_ready", "yes", "reports_regular", "report.has_any"),
                    DailyBriefFact("report_version", report_version or "NA", "reports_regular", "report.report_version"),
                ),
                linked_actions=(
                    _base_action("open_report_view", "Открыть report view", "pages/16_Report_View.py", "Report view показывает facts, approvals, bridge-to-actions и версии.", "Переход к утверждению или детализации выводов.", object_type="report", object_id=report_version),
                    _base_action("open_approvals", "Открыть approvals center", "pages/40_Approvals_Center.py", "Если нужен governance flow, approvals делаются существующим контуром.", "Согласование/архивирование без ad hoc permission path.", object_type="report", object_id=report_version),
                ),
                source_linkage=dict(source_versions),
            )
        )
    else:
        items.append(
            DailyBriefItem(
                key="report_missing",
                title="Готового отчёта пока нет",
                summary="На текущем data_version ещё нет готового daily-ready report artifact.",
                why_now="Это ограничение governance: brief не должен изображать report summary, если reproducible report artefact отсутствует.",
                expected_effect="Прозрачный fallback без LLM и без invented report conclusions.",
                linked_facts=(
                    DailyBriefFact("report_ready", "no", "reports_regular", "report.has_any"),
                    DailyBriefFact("data_version", _text(source_versions.get("data_version")), "runtime_context", "source_versions.data_version"),
                ),
                linked_actions=(
                    _base_action("open_report_builder", "Открыть report builder", "pages/55_Operational_Report_Builder.py", "Report builder собирает governed operational reports.", "Подготовка report artefact для следующего цикла."),
                ),
                source_linkage=dict(source_versions),
            )
        )

    if role == "Director":
        items.append(
            DailyBriefItem(
                key="director_governance",
                title="Что директору утвердить или проверить",
                summary="Сначала проверьте deviations / approvals / economics links, затем переходите к actions.",
                why_now="Daily brief для Director не подменяет Home, а собирает start-of-day guidance из уже существующих governed surfaces.",
                expected_effect="Быстрый старт дня с переходом к decisions, approvals и network-level summary.",
                linked_facts=(
                    DailyBriefFact("role", role, "rbac", "user.role"),
                    DailyBriefFact("active_alerts", str(active_alerts), "operational_summary", "operational.alerts"),
                ),
                linked_actions=(
                    _base_action("open_director_summary", "Открыть director summary", "pages/1_Director_Summary.py", "Там network/enterprise summary и KPI deviations.", "Понять, где именно отклоняется исполнение."),
                    _base_action("open_decisions", "Открыть decisions", "pages/31_Decisions_Operations.py", "Decisions screen связывает report approvals, alerts и decision log.", "Утверждение действий и governance closure."),
                    _base_action("open_economics", "Открыть economics what-if", "pages/9_Economics_WhatIf.py", "What-if нужен для оценки effect/cost перед утверждением.", "Проверка expected effect в рублях."),
                ),
                source_linkage=dict(source_versions),
            )
        )
    elif role == "Zootech":
        top_candidates = int(focus.get("top_candidates") or 0)
        items.append(
            DailyBriefItem(
                key="zootech_focus",
                title="Кого пересмотреть в первую очередь",
                summary=f"В зоне внимания до {top_candidates or 0} кандидатов из scoring/операционного списка.",
                why_now="Это role-specific start point для productive triage и execution по животным/группам.",
                expected_effect="Быстрее перейти к проверке animals/groups без ручного поиска по shell.",
                linked_facts=(
                    DailyBriefFact("top_candidates", str(top_candidates), "role_focus", "role_focus.top_candidates"),
                    DailyBriefFact("role", role, "rbac", "user.role"),
                ),
                linked_actions=(
                    _base_action("open_group_profile", "Открыть group profile", "pages/14_Group_Profile.py", "Групповой профиль даёт group-level explainability.", "Понять why this list / why this group."),
                    _base_action("open_animal_profile", "Открыть animal profile", "pages/15_Animal_Profile.py", "Карточка животного нужна для object-level reasoning и действий.", "Понять why this cow и перейти к execution."),
                ),
                source_linkage=dict(source_versions),
            )
        )
    elif role == "Vet":
        high_risk = int(focus.get("high_risk_count") or 0)
        items.append(
            DailyBriefItem(
                key="vet_focus",
                title="Клинический приоритет смены",
                summary=f"High-risk animals: {high_risk}.",
                why_now="Daily brief должен помочь начать vet shift с high-risk очереди и linked alerts/tasks.",
                expected_effect="Снижение delay на triage и handover между vet shifts.",
                linked_facts=(
                    DailyBriefFact("high_risk_count", str(high_risk), "role_focus", "role_focus.high_risk_count"),
                    DailyBriefFact("role", role, "rbac", "user.role"),
                ),
                linked_actions=(
                    _base_action("open_vet_queue", "Открыть vet triage", "pages/51_Vet_Triage_Queues.py", "Vet queue содержит high-risk lists и actions.", "Немедленный triage high-risk случаев."),
                    _base_action("open_alerts", "Открыть alerts", "pages/5_Alert_Center_v2.py", "Alerts дают source-linked причины и workflow status.", "Подтвердить сигнал и назначить действия."),
                ),
                source_linkage=dict(source_versions),
            )
        )
    elif role == "Operator":
        items.append(
            DailyBriefItem(
                key="operator_pipeline",
                title="Следующий шаг operational pipeline",
                summary="Проверьте freshness контекста, затем доведите queue → report → actions до замкнутого цикла.",
                why_now="Operator brief не пишет свободный summary, а напоминает governed sequence daily execution.",
                expected_effect="Предсказуемый daily-use rollout без разрыва между pipeline и operational actions.",
                linked_facts=(
                    DailyBriefFact("role", role, "rbac", "user.role"),
                    DailyBriefFact("report_ready", "yes" if has_report else "no", "report_snapshot", "report.has_any"),
                ),
                linked_actions=(
                    _base_action("open_jobs", "Открыть jobs / observability", "pages/37_Admin_Observability_Release.py", "Нужно проверить rollout diagnostics и jobs status.", "Убедиться, что контур готов к daily execution."),
                    _base_action("open_report_builder", "Открыть report builder", "pages/55_Operational_Report_Builder.py", "Builder нужен для воспроизводимого governed output.", "Закрытие цикла до shareable brief/report."),
                ),
                source_linkage=dict(source_versions),
            )
        )
    elif role == "Admin":
        items.append(
            DailyBriefItem(
                key="admin_observability",
                title="Системный старт дня",
                summary="Проверьте operational gates, observability и access surfaces перед началом смены.",
                why_now="Admin brief — это governance/readiness reminder, а не отдельный AI shell.",
                expected_effect="Раннее выявление rollout regressions и access issues.",
                linked_facts=(
                    DailyBriefFact("role", role, "rbac", "user.role"),
                    DailyBriefFact("data_version", _text(source_versions.get("data_version")), "runtime_context", "source_versions.data_version"),
                ),
                linked_actions=(
                    _base_action("open_admin_observability", "Открыть observability", "pages/37_Admin_Observability_Release.py", "Здесь rollout diagnostics и release status.", "Проверить readiness enterprise deployment."),
                    _base_action("open_users_security", "Открыть users & security", "pages/35_Admin_Users_Security.py", "Нужно проверить role/access changes и governance.", "Снизить риск access regression."),
                ),
                source_linkage=dict(source_versions),
            )
        )
    else:
        items.append(
            DailyBriefItem(
                key="viewer_read",
                title="С чего начать чтение дня",
                summary="Откройте report view и daily worklists, если нужно понять текущие приоритеты.",
                why_now="Viewer получает governed reading path, не требующий write actions.",
                expected_effect="Быстрое чтение статуса дня и переход к source-linked surfaces.",
                linked_facts=(
                    DailyBriefFact("role", role, "rbac", "user.role"),
                    DailyBriefFact("report_ready", "yes" if has_report else "no", "report_snapshot", "report.has_any"),
                ),
                linked_actions=(
                    _base_action("open_report_view", "Открыть report view", "pages/16_Report_View.py", "Оттуда можно читать facts и approvals status.", "Понять, что происходит, без лишней навигации."),
                    _base_action("open_home", "Вернуться на home", "pages/0_Home_v3.py", "Home остаётся главным role-aware start screen.", "Не терять контекст стартового экрана."),
                ),
                source_linkage=dict(source_versions),
            )
        )
    return items


def build_role_daily_brief(*, role: str, snapshot: Mapping[str, Any], data_version: str) -> DailyBrief:
    role_norm = _text(role) or "Viewer"
    versions = _collect_source_versions(snapshot, data_version=data_version)
    report_version = _text(versions.get("report_version")) or "NA"
    brief_version = f"daily_brief::{role_norm.lower()}::{_text(data_version) or 'dv_demo'}::{report_version}"
    items = tuple(_build_operational_items(role=role_norm, snapshot=snapshot, source_versions=versions))
    return DailyBrief(
        role=role_norm,
        data_version=_text(data_version) or "dv_demo",
        brief_version=brief_version,
        generated_at_utc=_utc_now(),
        generated_mode="facts_template",
        fallback_without_llm=True,
        source_versions=dict(versions),
        items=items,
    )


def build_daily_brief_markdown(brief: DailyBrief) -> str:
    lines: list[str] = []
    lines.append(f"# Daily brief — {brief.role}")
    lines.append("")
    lines.append(f"- brief_version: {brief.brief_version}")
    lines.append(f"- data_version: {brief.data_version}")
    lines.append(f"- generated_mode: {brief.generated_mode}")
    lines.append(f"- fallback_without_llm: {'yes' if brief.fallback_without_llm else 'no'}")
    if brief.source_versions:
        joined = ", ".join(f"{k}={v}" for k, v in brief.source_versions.items())
        lines.append(f"- source_versions: {joined}")
    for item in brief.items:
        lines.append("")
        lines.append(f"## {item.title}")
        lines.append(item.summary)
        lines.append("")
        lines.append(f"Почему сейчас: {item.why_now}")
        lines.append(f"Ожидаемый эффект: {item.expected_effect}")
        if item.linked_facts:
            lines.append("")
            lines.append("Связанные факты:")
            for fact in item.linked_facts:
                lines.append(f"- {fact.label}: {fact.value} ({fact.source_linkage or fact.source})")
        if item.linked_actions:
            lines.append("")
            lines.append("Связанные действия:")
            for action in item.linked_actions:
                lines.append(f"- {action.label} -> {action.page} :: {action.expected_effect}")
    return "\n".join(lines).strip() + "\n"


def build_daily_brief_share_seed(*, brief: DailyBrief, page_key: str = "ai_daily_brief") -> dict[str, Any]:
    return {
        f"{page_key}.role": brief.role,
        f"{page_key}.data_version": brief.data_version,
        f"{page_key}.brief_version": brief.brief_version,
        f"{page_key}.source_versions": dict(brief.source_versions),
    }


__all__ = [
    "DailyBrief",
    "DailyBriefAction",
    "DailyBriefFact",
    "DailyBriefItem",
    "build_daily_brief_markdown",
    "build_daily_brief_share_seed",
    "build_role_daily_brief",
]
