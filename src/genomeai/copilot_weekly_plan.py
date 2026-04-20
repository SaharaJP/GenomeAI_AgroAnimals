from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import yaml

from core.common.time import utc_now

from .copilot_fact_pack import build_copilot_fact_pack_from_assistant_fact_pack
from .copilot_target_resolver import build_copilot_web_target


DEFAULT_WEEKLY_PLAN_CFG: Dict[str, Any] = {
    "weekly_plan_copilot_v1": {
        "enabled": True,
        "intent_keywords": [
            "сформируй план на неделю",
            "план на неделю",
            "сформируй недельный план",
            "план действий на неделю",
            "weekly plan",
        ],
        "min_items": 5,
        "max_items": 15,
        "max_candidates_per_section": 5,
        "max_table_rows_per_candidate_scan": 8,
        "include_sections": [
            "modules.alerts_v2",
            "modules.health",
            "modules.repro",
            "modules.kpi",
            "modules.economics",
            "assistant_knowledge.tasks_v1",
        ],
        "section_weights": {
            "modules.alerts_v2": 100,
            "modules.health": 95,
            "modules.repro": 90,
            "assistant_knowledge.tasks_v1": 85,
            "modules.kpi": 80,
            "modules.economics": 75,
        },
        "severity_priority": {"critical": 1, "high": 2, "medium": 3, "low": 4},
        "default_priority": 3,
        "default_domain": "data",
        "default_assignee_team_by_domain": {
            "health": "team-health",
            "repro": "team-repro",
            "econ": "team-econ",
            "data": "team-data",
        },
    }
}


@dataclass
class WeeklyPlanCandidate:
    score: int
    key: str
    item: Dict[str, Any]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_weekly_plan_copilot_config(cfg_path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(cfg_path) if cfg_path is not None else (_project_root() / "configs" / "copilot" / "weekly_plan_v1.yaml")
    raw: Dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            raw = loaded
    return _deep_merge(DEFAULT_WEEKLY_PLAN_CFG, raw)


def is_weekly_plan_request(question: str, cfg: Optional[Dict[str, Any]] = None) -> bool:
    conf = (cfg or load_weekly_plan_copilot_config()).get("weekly_plan_copilot_v1") or {}
    q = str(question or "").strip().lower()
    if not q:
        return False
    return any(str(k).strip().lower() in q for k in (conf.get("intent_keywords") or []))


def _ensure_copilot_fact_pack(fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    copilot = (fact_pack or {}).get("copilot_fact_pack") or {}
    if isinstance(copilot, dict) and copilot.get("schema") == "genomeai.copilot.fact_pack.v1":
        return copilot
    return build_copilot_fact_pack_from_assistant_fact_pack(fact_pack or {})


def _slug(value: str) -> str:
    v = re.sub(r"[^a-zA-Z0-9а-яА-Я_]+", "-", str(value or "").strip().lower())
    v = re.sub(r"-+", "-", v).strip("-")
    return v or "na"


def _build_deep_link(
    *,
    data_version: str,
    section: str,
    table: Optional[str] = None,
    metric: Optional[str] = None,
    run_id: Optional[str] = None,
    report_version: Optional[str] = None,
    fact_id: Optional[str] = None,
) -> str:
    payload = {
        "data_version": str(data_version or "NA"),
        "section": str(section or ""),
        "table": str(table or ""),
        "metric": str(metric or ""),
        "run_id": str(run_id or ""),
        "report_version": str(report_version or ""),
        "fact_id": str(fact_id or ""),
    }
    return "genomeai://copilot/fact?" + urlencode(payload)


def _section_weight(section: str, cfg: Dict[str, Any]) -> int:
    weights = (cfg.get("weekly_plan_copilot_v1") or {}).get("section_weights") or {}
    for prefix, weight in weights.items():
        if str(section or "").startswith(str(prefix)):
            try:
                return int(weight)
            except Exception:
                return 0
    return 0


def _section_allowed(section: str, cfg: Dict[str, Any]) -> bool:
    prefixes = list(((cfg.get("weekly_plan_copilot_v1") or {}).get("include_sections") or []))
    if not prefixes:
        return True
    return any(str(section or "").startswith(str(p)) for p in prefixes)


def _priority_from_severity(severity: str, cfg: Dict[str, Any], default: int) -> int:
    mapping = ((cfg.get("weekly_plan_copilot_v1") or {}).get("severity_priority") or {})
    try:
        return int(mapping.get(str(severity or "").strip().lower(), default))
    except Exception:
        return default


def _infer_domain(section: str, row: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    sec = str(section or "")
    if sec.startswith("modules.economics"):
        return "econ"
    if sec.startswith("modules.repro"):
        return "repro"
    if sec.startswith("modules.health") or "mastitis" in sec or "alert" in sec:
        return "health"
    if sec.startswith("assistant_knowledge.tasks_v1"):
        dom = str(row.get("domain") or "").strip().lower()
        if dom:
            return dom
    return str(((cfg.get("weekly_plan_copilot_v1") or {}).get("default_domain") or "data"))


def _default_team(domain: str, cfg: Dict[str, Any]) -> str:
    teams = ((cfg.get("weekly_plan_copilot_v1") or {}).get("default_assignee_team_by_domain") or {})
    return str(teams.get(str(domain or "data"), teams.get("data", "team-data")))


def _normalize_assignee_team(value: Any, domain: str, cfg: Dict[str, Any]) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "vet": "team-health",
        "health": "team-health",
        "zootech": "team-repro",
        "repro": "team-repro",
        "data": "team-data",
        "qc": "team-qc",
        "director": "team-econ",
        "economics": "team-econ",
    }
    if raw in aliases:
        return aliases[raw]
    if raw.startswith("team-"):
        return raw
    return _default_team(domain, cfg)


def _row_object_type(row: Dict[str, Any]) -> Optional[str]:
    if row.get("object_type"):
        return str(row.get("object_type"))
    if row.get("animal_id"):
        return "animal"
    if row.get("farm_id"):
        return "farm"
    if row.get("alert_id"):
        return "alert"
    return None


def _row_object_id(row: Dict[str, Any]) -> Optional[str]:
    for key in ("object_id", "animal_id", "farm_id", "alert_id", "task_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _citation_payload(
    *,
    label: str,
    source: str,
    data_version: str,
    section: str,
    run_id: Optional[str],
    report_version: Optional[str],
    table: Optional[str] = None,
    metric: Optional[str] = None,
    fact_id: Optional[str] = None,
) -> Dict[str, Any]:
    target = _build_deep_link(
        data_version=data_version,
        section=section,
        table=table,
        metric=metric,
        run_id=run_id,
        report_version=report_version,
        fact_id=fact_id,
    )
    web_target = build_copilot_web_target(
        {
            "data_version": data_version,
            "section": section,
            "table": table or "",
            "metric": metric or "",
            "run_id": run_id or "",
            "report_version": report_version or "",
            "fact_id": fact_id or "",
        }
    )
    return {
        "label": label,
        "source": source or "NA",
        "data_version": data_version,
        "section": section or "NA",
        "table": table or None,
        "metric": metric or None,
        "run_id": run_id or None,
        "report_version": report_version or None,
        "fact_id": fact_id or None,
        "target": target,
        "web_target": web_target,
    }


def _first_source_ref(source_ids: List[str], source_registry: Dict[str, Any]) -> str:
    for sid in source_ids or []:
        src = source_registry.get(sid)
        if isinstance(src, dict):
            ref = src.get("ref") or src.get("source") or src.get("path")
            if ref:
                return str(ref)
        elif src not in (None, ""):
            return str(src)
    return "NA"


def _table_citation(table_block: Dict[str, Any], copilot: Dict[str, Any]) -> Dict[str, Any]:
    source_registry = copilot.get("sources") or {}
    return _citation_payload(
        label=str(table_block.get("table_id") or table_block.get("table") or "table"),
        source=_first_source_ref(list(table_block.get("source_ids") or []), source_registry),
        data_version=str(table_block.get("data_version") or (copilot.get("versions") or {}).get("data_version") or "NA"),
        section=str(table_block.get("section") or "NA"),
        table=str(table_block.get("table") or ""),
        run_id=str(table_block.get("run_id") or "") or None,
        report_version=str(table_block.get("report_version") or "") or None,
        fact_id=str(table_block.get("table_id") or "") or None,
    )


def _fact_citation(fact: Dict[str, Any], copilot: Dict[str, Any]) -> Dict[str, Any]:
    source_registry = copilot.get("sources") or {}
    return _citation_payload(
        label=str(fact.get("fact_id") or fact.get("metric_name") or "fact"),
        source=_first_source_ref(list(fact.get("source_ids") or []), source_registry),
        data_version=str(fact.get("data_version") or (copilot.get("versions") or {}).get("data_version") or "NA"),
        section=str(fact.get("section") or "NA"),
        metric=str(fact.get("metric_name") or ""),
        run_id=str(fact.get("run_id") or "") or None,
        report_version=str(fact.get("report_version") or "") or None,
        fact_id=str(fact.get("fact_id") or "") or None,
    )


def _title_for_row(section: str, table_name: str, row: Dict[str, Any]) -> str:
    sec = str(section or "")
    if sec.startswith("assistant_knowledge.tasks_v1"):
        return f"Контролировать выполнение задачи: {str(row.get('title') or row.get('task_id') or 'без названия')}"
    if sec.startswith("modules.economics"):
        farm_id = row.get("farm_id") or row.get("group_id") or row.get("scenario_name") or "scope"
        return f"Разобрать экономику по {farm_id}"
    if sec.startswith("modules.kpi"):
        farm_id = row.get("farm_id") or "ферме"
        kpi_id = row.get("kpi_id") or row.get("metric") or row.get("alert_id") or "KPI"
        return f"Разобрать KPI-отклонение {kpi_id} по {farm_id}"
    if "mastitis" in sec or sec.startswith("modules.health") or sec.startswith("modules.alerts_v2"):
        alert_id = row.get("alert_id") or row.get("animal_id") or row.get("farm_id") or row.get("event_id") or "объекту"
        return f"Разобрать отклонение {alert_id}"
    if sec.startswith("modules.repro"):
        obj = row.get("animal_id") or row.get("farm_id") or row.get("event_id") or "объекту"
        return f"Проверить репродуктивный риск по {obj}"
    return f"Разобрать факт из {table_name}"


def _expected_effect_for_row(section: str, row: Dict[str, Any]) -> str:
    sec = str(section or "")
    if sec.startswith("assistant_knowledge.tasks_v1"):
        return "Ожидаемый эффект: перевести открытую задачу в управляемое исполнение или закрытие по подтверждённому объекту."
    if sec.startswith("modules.economics"):
        farm_id = row.get("farm_id") or row.get("group_id") or "scope"
        return f"Ожидаемый эффект: получить подтверждённый разбор экономики по {farm_id} и зафиксировать решение на неделю."
    if sec.startswith("modules.kpi"):
        return "Ожидаемый эффект: подтвердить KPI-отклонение, назначить владельца и срок корректирующего действия."
    if "mastitis" in sec or sec.startswith("modules.health") or sec.startswith("modules.alerts_v2"):
        return "Ожидаемый эффект: подтвердить или снять отклонение по объекту и перевести риск в конкретное действие."
    if sec.startswith("modules.repro"):
        return "Ожидаемый эффект: подтвердить репродуктивный риск и согласовать следующее действие по объекту."
    return "Ожидаемый эффект: зафиксировать действие по подтверждённому факту недели."


def _what_to_do_for_row(section: str, row: Dict[str, Any]) -> List[str]:
    sec = str(section or "")
    if sec.startswith("assistant_knowledge.tasks_v1"):
        return [
            "Проверить актуальный статус и владельца задачи.",
            "Подтвердить срок и следующий шаг по объекту.",
        ]
    if sec.startswith("modules.economics"):
        return [
            "Открыть подтверждённую economics-таблицу и сверить ключевые суммы/маржу.",
            "Зафиксировать управленческое решение по строке экономики на неделю.",
        ]
    return [
        "Открыть исходную таблицу/алерт по citation target.",
        "Подтвердить факт и назначить владельца следующего действия.",
    ]


def _score_row_candidate(section: str, row: Dict[str, Any], row_idx: int, cfg: Dict[str, Any]) -> int:
    score = _section_weight(section, cfg) * 100
    severity = str(row.get("severity") or "").strip().lower()
    if severity == "critical":
        score += 40
    elif severity == "high":
        score += 25
    elif severity == "medium":
        score += 10
    status = str(row.get("status") or "").strip().lower()
    if status in {"open", "in_progress", "new"}:
        score += 15
    if row.get("priority") not in (None, ""):
        try:
            score += max(0, 10 - int(row.get("priority")))
        except Exception:
            pass
    score += max(0, 8 - int(row_idx))
    return score


def _candidate_from_table_row(table_block: Dict[str, Any], row: Dict[str, Any], row_idx: int, copilot: Dict[str, Any], cfg: Dict[str, Any]) -> WeeklyPlanCandidate:
    section = str(table_block.get("section") or "")
    table_name = str(table_block.get("table") or "table")
    domain = _infer_domain(section, row, cfg)
    default_priority = int(((cfg.get("weekly_plan_copilot_v1") or {}).get("default_priority") or 3))
    priority = default_priority
    severity = str(row.get("severity") or "").strip().lower()
    if severity:
        priority = _priority_from_severity(severity, cfg, default_priority)
    elif row.get("priority") not in (None, ""):
        try:
            priority = int(row.get("priority"))
        except Exception:
            priority = default_priority
    object_type = _row_object_type(row)
    object_id = _row_object_id(row)
    citations = [_table_citation(table_block, copilot)]
    title = _title_for_row(section, table_name, row)
    item = {
        "key": f"ai-{_slug(section)}-{_slug(str(object_id or row_idx))}",
        "title": title,
        "task_type": "weekly_plan.action",
        "domain": domain,
        "priority": int(priority),
        "assignee_team": _normalize_assignee_team(row.get("assignee_team"), domain, cfg),
        "object_type": object_type,
        "object_id": object_id,
        "expected_effect": _expected_effect_for_row(section, row),
        "citations": citations,
        "source_run_ids": [cit.get("run_id") for cit in citations if cit.get("run_id")],
        "what_to_do": _what_to_do_for_row(section, row),
        "why": {
            "source": "copilot_weekly_plan_v1",
            "section": section,
            "table": table_name,
            "row_preview": {k: row.get(k) for k in list(row.keys())[:8]},
            "citations": citations,
        },
    }
    return WeeklyPlanCandidate(
        score=_score_row_candidate(section, row, row_idx, cfg),
        key=str(item["key"]),
        item=item,
    )


def _score_fact_candidate(section: str, metric_name: str, value: Any, cfg: Dict[str, Any]) -> int:
    score = _section_weight(section, cfg) * 100
    if isinstance(value, (int, float)):
        try:
            score += min(int(abs(float(value))), 50)
        except Exception:
            pass
    if "alert" in metric_name or "overdue" in metric_name:
        score += 20
    return score


def _candidate_from_fact(fact: Dict[str, Any], copilot: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[WeeklyPlanCandidate]:
    section = str(fact.get("section") or "")
    metric_name = str(fact.get("metric_name") or "")
    value = fact.get("value")
    if value in (None, "", 0, "0"):
        return None
    domain = _infer_domain(section, {}, cfg)
    citation = _fact_citation(fact, copilot)
    title = f"Разобрать показатель {metric_name} за неделю"
    if section.startswith("modules.kpi") and "alert" in metric_name:
        title = "Разобрать суммарные KPI-отклонения недели"
    elif section.startswith("assistant_knowledge.tasks_v1") and "overdue" in metric_name:
        title = "Разобрать просроченные задачи недели"
    elif section.startswith("assistant_knowledge.tasks_v1") and "open" in metric_name:
        title = "Пересмотреть открытую очередь задач недели"
    elif section.startswith("modules.economics"):
        title = f"Проверить экономический показатель {metric_name}"
    item = {
        "key": f"ai-{_slug(section)}-{_slug(metric_name)}",
        "title": title,
        "task_type": "weekly_plan.action",
        "domain": domain,
        "priority": int(((cfg.get("weekly_plan_copilot_v1") or {}).get("default_priority") or 3)),
        "assignee_team": _default_team(domain, cfg),
        "expected_effect": f"Ожидаемый эффект: согласовать действие по метрике {metric_name}={value} на подтверждённом run.",
        "citations": [citation],
        "source_run_ids": [citation.get("run_id")] if citation.get("run_id") else [],
        "what_to_do": [
            f"Открыть citation target по метрике {metric_name}.",
            "Подтвердить, нужен ли отдельный action item или задача по этой метрике.",
        ],
        "why": {
            "source": "copilot_weekly_plan_v1",
            "section": section,
            "metric": metric_name,
            "value": value,
            "citations": [citation],
        },
    }
    return WeeklyPlanCandidate(
        score=_score_fact_candidate(section, metric_name, value, cfg),
        key=str(item["key"]),
        item=item,
    )


def _dedupe_candidates(candidates: List[WeeklyPlanCandidate]) -> List[WeeklyPlanCandidate]:
    best: Dict[str, WeeklyPlanCandidate] = {}
    for cand in candidates:
        prev = best.get(cand.key)
        if prev is None or cand.score > prev.score:
            best[cand.key] = cand
    return sorted(best.values(), key=lambda x: (-x.score, x.key))


def _week_start_default(asof_date: str) -> str:
    try:
        dt = datetime.fromisoformat(str(asof_date)[:10])
    except Exception:
        dt = utc_now()
    week_start = dt.date() - timedelta(days=dt.weekday())
    return week_start.isoformat()


def build_weekly_plan_from_fact_pack(
    *,
    fact_pack: Dict[str, Any],
    question: str,
    week_start: Optional[str] = None,
    farm_id: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    full_cfg = cfg or load_weekly_plan_copilot_config()
    conf = full_cfg.get("weekly_plan_copilot_v1") or {}
    copilot = _ensure_copilot_fact_pack(fact_pack)
    versions = copilot.get("versions") or {}
    data_version = str(versions.get("data_version") or ((fact_pack.get("versions") or {}).get("data_version") or "NA"))
    wk = str(week_start or _week_start_default(str(copilot.get("asof_date") or fact_pack.get("asof_date") or "")))
    max_items = max(int(conf.get("min_items") or 5), int(conf.get("max_items") or 15))
    max_scan = int(conf.get("max_table_rows_per_candidate_scan") or 8)
    max_per_section = int(conf.get("max_candidates_per_section") or 5)

    candidates: List[WeeklyPlanCandidate] = []
    per_section_count: Dict[str, int] = {}

    for table_block in list(copilot.get("tables") or []):
        if not isinstance(table_block, dict):
            continue
        section = str(table_block.get("section") or "")
        if not _section_allowed(section, full_cfg):
            continue
        rows = list(table_block.get("rows") or [])
        if farm_id:
            rows = [r for r in rows if str(r.get("farm_id") or "") == str(farm_id)] or rows
        for idx, row in enumerate(rows[:max_scan]):
            if not isinstance(row, dict):
                continue
            if per_section_count.get(section, 0) >= max_per_section:
                break
            cand = _candidate_from_table_row(table_block, row, idx, copilot, full_cfg)
            candidates.append(cand)
            per_section_count[section] = per_section_count.get(section, 0) + 1

    for fact in list(copilot.get("facts") or []):
        if not isinstance(fact, dict):
            continue
        section = str(fact.get("section") or "")
        if not _section_allowed(section, full_cfg):
            continue
        if per_section_count.get(section, 0) >= max_per_section:
            continue
        cand = _candidate_from_fact(fact, copilot, full_cfg)
        if cand is None:
            continue
        candidates.append(cand)
        per_section_count[section] = per_section_count.get(section, 0) + 1

    deduped = _dedupe_candidates(candidates)
    selected = deduped[:max_items]
    action_items = [cand.item for cand in selected]

    source_run_ids = sorted({str(run_id) for it in action_items for run_id in (it.get("source_run_ids") or []) if str(run_id).strip()})
    source_sections = sorted({str((it.get("why") or {}).get("section") or "") for it in action_items if (it.get("why") or {}).get("section")})
    citations: List[Dict[str, Any]] = []
    seen_targets: set[str] = set()
    for item in action_items:
        for cit in list(item.get("citations") or []):
            tgt = str(cit.get("target") or "")
            if tgt and tgt not in seen_targets:
                citations.append(cit)
                seen_targets.add(tgt)

    missing_data_requests = list(copilot.get("missing_data_requests") or [])
    summary_parts = [
        "План сформирован только из подтверждённых фактов copilot_fact_pack.",
        f"Пунктов: {len(action_items)}.",
        f"data_version={data_version}.",
        f"week_start={wk}.",
    ]
    if farm_id:
        summary_parts.append(f"farm_id={farm_id}.")
    if source_run_ids:
        summary_parts.append(f"source_run_ids={', '.join(source_run_ids[:8])}.")
    if source_sections:
        summary_parts.append(f"sections={', '.join(source_sections[:6])}.")
    if not action_items:
        summary_parts.append("Недостаточно подтверждённых данных для генерации weekly plan.")

    return {
        "schema": "genomeai.copilot.weekly_plan.v1",
        "generator": "copilot_weekly_plan_v1",
        "question": str(question or ""),
        "name": f"AI-план на неделю {wk}",
        "week_start": wk,
        "data_version": data_version,
        "farm_id": str(farm_id or "") or None,
        "summary": " ".join(summary_parts).strip(),
        "action_items": action_items,
        "citations": citations,
        "source_run_ids": source_run_ids,
        "source_sections": source_sections,
        "missing_data_requests": missing_data_requests,
        "versions": versions,
    }


def render_weekly_plan_answer(plan: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("Сформирован weekly plan только по подтверждённым данным fact-pack.")
    lines.append(f"Неделя: {plan.get('week_start')}; data_version={plan.get('data_version')}; пунктов={len(plan.get('action_items') or [])}.")
    if plan.get("farm_id"):
        lines.append(f"farm_id={plan.get('farm_id')}")
    lines.append("")
    for idx, item in enumerate(list(plan.get("action_items") or []), start=1):
        title = str(item.get("title") or "без названия")
        priority = item.get("priority")
        effect = str(item.get("expected_effect") or "")
        citations = list(item.get("citations") or [])
        cit = citations[0] if citations else {}
        lines.append(f"{idx}. {title} (priority={priority})")
        if effect:
            lines.append(f"   - {effect}")
        if item.get("what_to_do"):
            for step in list(item.get("what_to_do") or [])[:2]:
                lines.append(f"   - {step}")
        if cit:
            lines.append(
                "   [Источник: fact_id={fact_id}; section={section}; table={table}; metric={metric}; run_id={run_id}; report_version={report_version}; target={target}]".format(
                    fact_id=cit.get("fact_id") or "NA",
                    section=cit.get("section") or "NA",
                    table=cit.get("table") or "NA",
                    metric=cit.get("metric") or "NA",
                    run_id=cit.get("run_id") or "NA",
                    report_version=cit.get("report_version") or "NA",
                    target=cit.get("target") or "NA",
                )
            )
    if not list(plan.get("action_items") or []):
        lines.append("Подтверждённых действий не найдено.")
    missing = list(plan.get("missing_data_requests") or [])
    if missing:
        lines.append("")
        lines.append("Нехватка данных:")
        for req in missing[:3]:
            lines.append(f"- {req.get('section')}: {req.get('why')}")
            for need in list(req.get("needed_data") or [])[:2]:
                lines.append(f"  • Нужны данные: {need}")
            for how in list(req.get("how_to_get") or [])[:2]:
                lines.append(f"  • Как получить: {how}")
    return "\n".join(lines).strip()
