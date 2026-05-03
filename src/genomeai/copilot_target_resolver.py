from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from .copilot_fact_pack import build_copilot_fact_pack_from_assistant_fact_pack

_ALLOWED_KEYS = {
    "data_version",
    "section",
    "table",
    "metric",
    "run_id",
    "report_version",
    "fact_id",
    "source_id",
    "request_id",
}


def parse_copilot_target(*, target: Optional[str] = None, **params: Any) -> Dict[str, str]:
    raw: Dict[str, str] = {k: "" for k in sorted(_ALLOWED_KEYS)}
    if target:
        parsed = urlparse(str(target))
        if parsed.scheme != "genomeai" or parsed.netloc != "copilot" or parsed.path != "/fact":
            raise ValueError(
                "copilot_target_invalid: ожидается ссылка вида genomeai://copilot/fact?..."
            )
        query = parse_qs(parsed.query, keep_blank_values=True)
        for key in _ALLOWED_KEYS:
            if key in query and query[key]:
                raw[key] = str(query[key][0] or "")
    for key, value in params.items():
        if key in _ALLOWED_KEYS and value is not None:
            raw[key] = str(value or "")
    return raw


def build_copilot_web_target(params: Dict[str, Any]) -> str:
    payload = {k: str(v or "") for k, v in (params or {}).items() if k in _ALLOWED_KEYS and str(v or "").strip()}
    return "/copilot/fact?" + urlencode(payload)


def build_copilot_api_target(params: Dict[str, Any]) -> str:
    payload = {k: str(v or "") for k, v in (params or {}).items() if k in _ALLOWED_KEYS and str(v or "").strip()}
    return "/api/copilot/fact?" + urlencode(payload)


def _same_run(expected: str, actual: str) -> bool:
    if not expected:
        return True
    return str(expected) == str(actual or "")


def _same_report(expected: str, actual: str) -> bool:
    if not expected:
        return True
    return str(expected) == str(actual or "")


def _ensure_copilot_fact_pack(fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    copilot = (fact_pack or {}).get("copilot_fact_pack") or {}
    if isinstance(copilot, dict) and copilot.get("schema") == "genomeai.copilot.fact_pack.v1":
        return copilot
    return build_copilot_fact_pack_from_assistant_fact_pack(fact_pack or {})


def _match_fact(facts: List[Dict[str, Any]], target: Dict[str, str]) -> Optional[Dict[str, Any]]:
    fact_id = str(target.get("fact_id") or "")
    if fact_id:
        for fact in facts:
            if str(fact.get("fact_id") or "") == fact_id:
                return fact
    section = str(target.get("section") or "")
    metric = str(target.get("metric") or "")
    if section and metric:
        for fact in facts:
            if str(fact.get("section") or "") != section:
                continue
            if str(fact.get("metric_name") or "") != metric:
                continue
            if not _same_run(str(target.get("run_id") or ""), str(fact.get("run_id") or "")):
                continue
            if not _same_report(str(target.get("report_version") or ""), str(fact.get("report_version") or "")):
                continue
            return fact
    return None


def _match_table(tables: List[Dict[str, Any]], target: Dict[str, str]) -> Optional[Dict[str, Any]]:
    source_id = str(target.get("source_id") or "")
    if source_id.startswith("table."):
        for table in tables:
            if str(table.get("table_id") or "") == source_id:
                return table
    section = str(target.get("section") or "")
    table_name = str(target.get("table") or "")
    if section and table_name:
        for table in tables:
            if str(table.get("section") or "") != section:
                continue
            if str(table.get("table") or "") != table_name:
                continue
            if not _same_run(str(target.get("run_id") or ""), str(table.get("run_id") or "")):
                continue
            if not _same_report(str(target.get("report_version") or ""), str(table.get("report_version") or "")):
                continue
            return table
    return None


def _match_missing(requests: List[Dict[str, Any]], target: Dict[str, str]) -> Optional[Dict[str, Any]]:
    request_id = str(target.get("request_id") or target.get("source_id") or "")
    if request_id.startswith("missing."):
        for req in requests:
            if str(req.get("request_id") or "") == request_id:
                return req
    section = str(target.get("section") or "")
    if section:
        for req in requests:
            if str(req.get("section") or "") == section:
                return req
    return None


def _collect_sources(copilot: Dict[str, Any], ids: List[str]) -> List[Dict[str, Any]]:
    registry = copilot.get("sources") or {}
    out: List[Dict[str, Any]] = []
    for sid in ids:
        row = registry.get(sid)
        if isinstance(row, dict):
            out.append(dict(row))
    return out


def _first_same_section_tables(copilot: Dict[str, Any], section: str, limit: int = 3) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for table in (copilot.get("tables") or []):
        if str(table.get("section") or "") == str(section or ""):
            out.append(dict(table))
        if len(out) >= int(limit):
            break
    return out


def _first_same_section_facts(copilot: Dict[str, Any], section: str, limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fact in (copilot.get("facts") or []):
        if str(fact.get("section") or "") == str(section or ""):
            out.append(dict(fact))
        if len(out) >= int(limit):
            break
    return out


def resolve_copilot_target_from_fact_pack(*, fact_pack: Dict[str, Any], target: Dict[str, str]) -> Dict[str, Any]:
    copilot = _ensure_copilot_fact_pack(fact_pack or {})
    versions = (copilot.get("versions") or {}) if isinstance(copilot, dict) else {}
    normalized = {
        "data_version": str(target.get("data_version") or versions.get("data_version") or "NA"),
        "section": str(target.get("section") or ""),
        "table": str(target.get("table") or ""),
        "metric": str(target.get("metric") or ""),
        "run_id": str(target.get("run_id") or ""),
        "report_version": str(target.get("report_version") or ""),
        "fact_id": str(target.get("fact_id") or ""),
        "source_id": str(target.get("source_id") or ""),
        "request_id": str(target.get("request_id") or ""),
    }

    facts = [dict(x) for x in (copilot.get("facts") or []) if isinstance(x, dict)]
    tables = [dict(x) for x in (copilot.get("tables") or []) if isinstance(x, dict)]
    missing_requests = [dict(x) for x in (copilot.get("missing_data_requests") or []) if isinstance(x, dict)]

    matched_fact = _match_fact(facts, normalized)
    matched_table = _match_table(tables, normalized)
    matched_missing = _match_missing(missing_requests, normalized)

    if matched_fact:
        source_ids = list(matched_fact.get("source_ids") or [])
        source_ids.extend([sid for sid in [normalized.get("source_id")] if sid])
        sources = _collect_sources(copilot, source_ids)
        related_tables = _first_same_section_tables(copilot, str(matched_fact.get("section") or ""), limit=3)
        return {
            "ok": True,
            "matched_kind": "fact",
            "target": normalized,
            "fact": matched_fact,
            "table": matched_table,
            "missing_data_request": None,
            "sources": sources,
            "related_tables": related_tables,
            "same_section_facts": _first_same_section_facts(copilot, str(matched_fact.get("section") or ""), limit=5),
        }

    if matched_table:
        source_ids = list(matched_table.get("source_ids") or [])
        source_ids.extend([sid for sid in [normalized.get("source_id")] if sid])
        sources = _collect_sources(copilot, source_ids)
        return {
            "ok": True,
            "matched_kind": "table",
            "target": normalized,
            "fact": None,
            "table": matched_table,
            "missing_data_request": None,
            "sources": sources,
            "related_tables": [matched_table],
            "same_section_facts": _first_same_section_facts(copilot, str(matched_table.get("section") or ""), limit=5),
        }

    if matched_missing:
        return {
            "ok": False,
            "matched_kind": "missing_data_request",
            "target": normalized,
            "fact": None,
            "table": None,
            "missing_data_request": matched_missing,
            "sources": [],
            "related_tables": [],
            "same_section_facts": [],
        }

    return {
        "ok": False,
        "matched_kind": "not_found",
        "target": normalized,
        "fact": None,
        "table": None,
        "missing_data_request": None,
        "sources": [],
        "related_tables": _first_same_section_tables(copilot, normalized.get("section") or "", limit=3),
        "same_section_facts": _first_same_section_facts(copilot, normalized.get("section") or "", limit=5),
        "error": (
            "copilot_target_not_found: факт или таблица не найдены в текущем fact-pack. "
            "Проверьте data_version/run_id/section/table/metric и пересоберите fact-pack."
        ),
    }


def build_copilot_detail_actions(*, target: Dict[str, str], resolution: Dict[str, Any]) -> List[Dict[str, str]]:
    dv = str(target.get("data_version") or "")
    run_id = str(target.get("run_id") or "")
    resolver_href = build_copilot_web_target(target)
    api_href = build_copilot_api_target(target)
    actions: List[Dict[str, str]] = []

    def add(label: str, href: str, reason: str) -> None:
        payload = {"label": label, "href": href, "reason": reason}
        if href and payload not in actions:
            actions.append(payload)

    add("Открыть факт", resolver_href, "Карточка факта/таблицы/источников по citation target")
    add("JSON API", api_href, "Машинно-читаемое разрешение citation target")

    if resolution.get("fact"):
        add("Карточка факта", resolver_href + "#fact-card", "Переход к подтверждённому факту и его ссылкам")
    if resolution.get("table") or str(target.get("table") or "").strip() or list(resolution.get("related_tables") or []):
        add("Preview таблицы", resolver_href + "#table-preview", "Переход к preview таблицы в resolver-экране")
    if resolution.get("missing_data_request"):
        add("Что догрузить", resolver_href + "#missing-data", "Что нужно догрузить, если фактов недостаточно")
    if resolution.get("sources"):
        add("Артефакты/источники", resolver_href + "#artifacts", "Скачать/открыть файл-источник или preview")
    if run_id:
        add("Jobs по run_id", "/jobs?" + urlencode({"q": run_id}), "Фильтр очереди работ и логов по конкретному run_id")
    if dv:
        add("Reports по data_version", "/reports?" + urlencode({"dv": dv}), "Регулярные и итоговые отчёты по выбранной версии данных")
    return actions


def build_copilot_navigation_hints(*, target: Dict[str, str], resolution: Dict[str, Any]) -> List[Dict[str, str]]:
    dv = str(target.get("data_version") or "")
    section = str(target.get("section") or "")
    hints: List[Dict[str, str]] = []

    def add(label: str, href: str, reason: str) -> None:
        payload = {"label": label, "href": href, "reason": reason}
        if payload not in hints:
            hints.append(payload)

    if dv:
        add("Resolver", build_copilot_web_target(target), "Точное разрешение citation target в web-cabinet")

    if section.startswith("modules.kpi"):
        add("Reports", f"/reports?dv={dv}", "Связанный report_version и итоговые KPI/отчёты")
        add("Score", f"/score?dv={dv}", "Переход к скорингам и связанным артефактам")
    elif section.startswith("modules.repro"):
        add("Repro", f"/repro?dv={dv}", "KPI и worklists по воспроизводству")
    elif section.startswith("modules.alerts_v2") or section.startswith("modules.health.mastitis_risk"):
        add("Workflow", "/workflow", "Связанные алерты и задачи для действий персонала")
        add("Score", f"/score?dv={dv}", "ML/score-артефакты по выбранной версии данных")
    elif section.startswith("assistant_knowledge.decision_log"):
        add("Decision Log", f"/decisions?dv={dv}", "Переход к журналу решений")
    elif section.startswith("assistant_knowledge.regular_reports_latest"):
        add("Reports", f"/reports?dv={dv}", "Регулярные отчёты и exports")
    elif section.startswith("modules.economics"):
        add("What-If", "/whatif_scenarios", "Экономические сценарии и отчёты")
        add("Reports", f"/reports?dv={dv}", "Итоговые отчёты по версии данных")
    elif section.startswith("modules.mating"):
        add("Reports", f"/reports?dv={dv}", "Итоговые отчёты и артефакты по скрещиванию")
    elif section.startswith("modules.playbooks") or section.startswith("assistant_knowledge.playbooks"):
        add("Playbooks", "/playbooks", "Чек-листы и рекомендуемые шаги")

    if not hints and dv:
        add("Reports", f"/reports?dv={dv}", "Базовый экран для артефактов версии данных")
    return hints


def summarize_target_resolution(resolution: Dict[str, Any]) -> str:
    kind = str(resolution.get("matched_kind") or "")
    if kind == "fact":
        fact = resolution.get("fact") or {}
        return f"fact: {fact.get('section','NA')}.{fact.get('metric_name','NA')}={fact.get('value','NA')}"
    if kind == "table":
        table = resolution.get("table") or {}
        return f"table: {table.get('section','NA')}.{table.get('table','NA')} row_count={table.get('row_count','NA')}"
    if kind == "missing_data_request":
        req = resolution.get("missing_data_request") or {}
        return f"missing_data_request: {req.get('section','NA')}"
    if resolution.get("error"):
        return str(resolution.get("error"))
    return json.dumps(resolution, ensure_ascii=False)[:500]
