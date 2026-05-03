from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml


_ANOMALY_CONTEXT_MARKERS = ["аномал", "alert", "алерт", "риск", "мастит", "mastitis", "problem", "проблем"]
_STATUS_ALIASES = {
    "open": ["open", "открыт", "открытые", "открытая", "активн", "active"],
    "in_progress": ["in progress", "in_progress", "в работе", "в процессе", "processing"],
    "done": ["done", "закрыт", "закрытые", "выполн", "completed", "complete"],
    "cancelled": ["cancelled", "canceled", "отмен", "archive", "архив"],
}
_SEVERITY_ALIASES = {
    "critical": ["critical", "crit", "критич"],
    "high": ["high", "высок", "красн"],
    "medium": ["medium", "med", "средн", "warn", "warning", "предупр"],
    "low": ["low", "низк", "green", "зел"],
}
_FEEDBACK_CONTEXT_MARKERS = ["feedback", "принят", "отклон", "acceptance", "reject", "accepted", "rejected", "рекомендац", "reason code"]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_COPILOT_TOOLS_CFG: Dict[str, Any] = {
    "enabled": True,
    "default_tool": "query_kpi",
    "tools": {
        "query_kpi": {
            "label": "KPI",
            "required_permission": "kpi.view",
            "priority": 10,
            "max_rows": 5,
            "section_prefixes": ["modules.kpi"],
            "section_permissions": {"modules.kpi": "kpi.view"},
            "intent_bonuses": {"overview": 0},
            "extra_section_prefixes": [],
            "intent_section_prefixes": {},
            "keywords": ["kpi", "показат", "удо", "milk", "молок", "fat", "protein", "scc"],
        },
        "query_anomalies": {
            "label": "Аномалии и алерты",
            "required_permission": "alerts.view",
            "priority": 20,
            "max_rows": 5,
            "section_prefixes": ["modules.alerts_v2", "modules.health.mastitis_risk"],
            "extra_section_prefixes": ["assistant_knowledge.playbooks"],
            "section_permissions": {
                "modules.alerts_v2": "alerts.view",
                "modules.health.mastitis_risk": "alerts.view",
                "assistant_knowledge.playbooks": "playbooks.view",
                "assistant_knowledge.tasks_v1": "tasks.view",
            },
            "intent_bonuses": {"why": 25, "what_to_do": 15},
            "intent_section_prefixes": {
                "what_to_do": ["assistant_knowledge.tasks_v1"],
            },
            "keywords": ["аномал", "alert", "алерт", "отклон", "риск", "мастит", "mastitis", "qc", "проблем", "почему"],
        },
        "query_tasks": {
            "label": "Задачи и worklists",
            "required_permission": "tasks.view",
            "priority": 30,
            "max_rows": 5,
            "section_prefixes": ["assistant_knowledge.tasks_v1"],
            "extra_section_prefixes": ["assistant_knowledge.playbooks", "assistant_knowledge.feedback_loop"],
            "section_permissions": {
                "assistant_knowledge.tasks_v1": "tasks.view",
                "assistant_knowledge.playbooks": "playbooks.view",
                "assistant_knowledge.feedback_loop": "decisionlog.view",
                "modules.alerts_v2": "alerts.view",
                "modules.health.mastitis_risk": "alerts.view",
            },
            "intent_bonuses": {"what_to_do": 25, "why": 10},
            "intent_section_prefixes": {
                "incident_context": ["modules.alerts_v2", "modules.health.mastitis_risk"],
            },
            "keywords": ["задач", "task", "workflow", "worklist", "work list", "что делать", "сделать", "todo", "план действий", "feedback", "принят", "отклон", "acceptance", "reject", "accepted", "rejected", "рекомендац"],
        },
        "query_economics": {
            "label": "Экономика",
            "required_permission": "economics.view",
            "priority": 40,
            "max_rows": 5,
            "section_prefixes": ["modules.economics"],
            "section_permissions": {"modules.economics": "economics.view"},
            "intent_bonuses": {"cost": 40},
            "extra_section_prefixes": [],
            "intent_section_prefixes": {},
            "keywords": ["эконом", "стоит", "cost", "выруч", "прибыл", "марж", "убыт", "revenue", "roi", "окуп"],
        },
    },
}


@dataclass
class ToolRouteDecision:
    tool_name: str
    label: str
    matched_keywords: List[str] = field(default_factory=list)
    route_reason: str = "default"
    score: int = 0
    required_permission: Optional[str] = None
    section_prefixes: List[str] = field(default_factory=list)


@dataclass
class ToolQuerySpec:
    intent: str = "overview"
    top_n: int = 5
    period_hint: Optional[str] = None
    farm_id: Optional[str] = None
    object_id: Optional[str] = None
    alert_id: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    assignee_team: Optional[str] = None
    extra_section_prefixes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ToolExecutionResult:
    decision: ToolRouteDecision
    query_spec: ToolQuerySpec
    allowed: bool
    required_permission: Optional[str]
    effective_permissions: List[str]
    visible_section_prefixes: List[str]
    hidden_section_prefixes: List[str]
    filtered_fact_pack: Dict[str, Any]
    denial_message: Optional[str] = None


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_copilot_tools_config(cfg_path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(cfg_path) if cfg_path is not None else (_project_root() / "configs" / "copilot" / "tools_v1.yaml")
    raw: Dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            raw = loaded
    return _deep_merge(DEFAULT_COPILOT_TOOLS_CFG, raw)


def _iter_keywords(tool_cfg: Dict[str, Any]) -> Iterable[str]:
    for item in list(tool_cfg.get("keywords") or []):
        value = str(item or "").strip().lower()
        if value:
            yield value


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, needles: Sequence[str]) -> bool:
    q = _norm(text)
    return any(_norm(n) and _norm(n) in q for n in (needles or []))


def _detect_intent(question: str) -> str:
    q = _norm(question)
    if _contains_any(q, ["что делать", "что сделать", "рекомендуй", "план действий", "что предпринять"]):
        return "what_to_do"
    if _contains_any(q, ["почему", "why", "причин", "из-за чего"]):
        return "why"
    if _contains_any(q, ["сколько стоит", "стоимость", "cost", "выруч", "марж", "прибыл", "убыт", "roi", "окуп"]):
        return "cost"
    return "overview"


def _extract_top_n(question: str, default_value: int = 5) -> int:
    q = str(question or "")
    patterns = [
        r"\btop\s*(\d{1,2})\b",
        r"\b(\d{1,2})\s*(?:шт|штук|items|rows|строк|запис[еи])\b",
        r"\bпокажи\s+(\d{1,2})\b",
        r"\bкакие\s+(\d{1,2})\b",
        r"\bтоп\s*(\d{1,2})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, q, flags=re.IGNORECASE)
        if m:
            try:
                value = int(m.group(1))
                if value > 0:
                    return min(value, 50)
            except Exception:
                continue
    return max(1, int(default_value or 5))


def _extract_named_token(question: str, prefixes: Sequence[str]) -> Optional[str]:
    q = str(question or "")
    for prefix in prefixes:
        m = re.search(rf"\b({re.escape(prefix)}[A-Za-z0-9_\-]+)\b", q, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_field_after_word(question: str, words: Sequence[str]) -> Optional[str]:
    q = str(question or "")
    for word in words:
        m = re.search(rf"{word}\s+([A-Za-zА-Яа-я0-9_\-]+)", q, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _detect_status(question: str) -> Optional[str]:
    q = _norm(question)
    for canonical, aliases in _STATUS_ALIASES.items():
        if _contains_any(q, aliases):
            return canonical
    return None


def _detect_severity(question: str) -> Optional[str]:
    q = _norm(question)
    for canonical, aliases in _SEVERITY_ALIASES.items():
        if _contains_any(q, aliases):
            return canonical
    return None


def _detect_period_hint(question: str) -> Optional[str]:
    q = _norm(question)
    if _contains_any(q, ["7 дней", "7 day", "недел", "weekly"]):
        return "7d"
    if _contains_any(q, ["30 дней", "30 day", "месяц", "monthly"]):
        return "30d"
    if _contains_any(q, ["90 дней", "90 day", "квартал"]):
        return "90d"
    if _contains_any(q, ["today", "сегодня", "daily", "сутки"]):
        return "1d"
    return None


def route_copilot_tool(question: str, cfg: Optional[Dict[str, Any]] = None) -> ToolRouteDecision:
    config = cfg or load_copilot_tools_config()
    q = str(question or "").strip().lower()
    tools = config.get("tools") or {}
    default_tool = str(config.get("default_tool") or "query_kpi")
    intent = _detect_intent(q)

    best_name = default_tool
    best_score = -1
    best_priority = -1
    best_keywords: List[str] = []

    for tool_name, tool_cfg in tools.items():
        if not isinstance(tool_cfg, dict):
            continue
        matched = [kw for kw in _iter_keywords(tool_cfg) if kw in q]
        score = len(matched) + int((tool_cfg.get("intent_bonuses") or {}).get(intent, 0))
        if _contains_any(q, _FEEDBACK_CONTEXT_MARKERS) and str(tool_name) == "query_tasks":
            score += 20
        priority = int(tool_cfg.get("priority", 0))
        if score > best_score or (score == best_score and priority > best_priority):
            best_name = str(tool_name)
            best_score = score
            best_priority = priority
            best_keywords = matched

    selected = tools.get(best_name) or {}
    route_reason = "keyword_match" if best_keywords else (f"intent_{intent}" if best_score > 0 else "default_tool")
    return ToolRouteDecision(
        tool_name=best_name,
        label=str(selected.get("label") or best_name),
        matched_keywords=best_keywords,
        route_reason=route_reason,
        score=max(best_score, 0),
        required_permission=str(selected.get("required_permission") or "") or None,
        section_prefixes=[str(x) for x in list(selected.get("section_prefixes") or []) if str(x).strip()],
    )


def build_tool_query_spec(
    *,
    question: str,
    decision: ToolRouteDecision,
    cfg: Optional[Dict[str, Any]] = None,
) -> ToolQuerySpec:
    config = cfg or load_copilot_tools_config()
    tool_cfg = ((config.get("tools") or {}).get(decision.tool_name) or {})
    intent = _detect_intent(question)
    farm_id = _extract_named_token(question, ["farm_", "ферма_"]) or _extract_field_after_word(question, [r"ферм[аеы]?", r"farm"])
    object_id = (
        (re.search(r"\banimal_id\s*[=:]?\s*([A-Za-z0-9_-]+)", str(question or ""), flags=re.IGNORECASE).group(1) if re.search(r"\banimal_id\s*[=:]?\s*([A-Za-z0-9_-]+)", str(question or ""), flags=re.IGNORECASE) else None)
        or (re.search(r"\bcow_id\s*[=:]?\s*([A-Za-z0-9_-]+)", str(question or ""), flags=re.IGNORECASE).group(1) if re.search(r"\bcow_id\s*[=:]?\s*([A-Za-z0-9_-]+)", str(question or ""), flags=re.IGNORECASE) else None)
        or _extract_named_token(question, ["animal_", "cow_", "task_", "alert_"])
        or _extract_field_after_word(question, [r"животн(?:ое|ого|ому|ым)?", r"animal", r"cow", r"объект[ауе]?", r"task", r"alert"])
    )
    alert_id = _extract_named_token(question, ["alert_", "al-"]) or _extract_field_after_word(question, [r"alert", r"алерт"])
    assignee_team = _extract_field_after_word(question, [r"команд[аеы]", r"team"])

    extra_section_prefixes = [str(x) for x in list(tool_cfg.get("extra_section_prefixes") or []) if str(x).strip()]
    for prefix in list((tool_cfg.get("intent_section_prefixes") or {}).get(intent) or []):
        value = str(prefix).strip()
        if value and value not in extra_section_prefixes:
            extra_section_prefixes.append(value)
    if decision.tool_name == "query_tasks" and _contains_any(question, _ANOMALY_CONTEXT_MARKERS):
        for prefix in list((tool_cfg.get("intent_section_prefixes") or {}).get("incident_context") or []):
            value = str(prefix).strip()
            if value and value not in extra_section_prefixes:
                extra_section_prefixes.append(value)
    if decision.tool_name == "query_tasks" and _contains_any(question, _FEEDBACK_CONTEXT_MARKERS):
        value = "assistant_knowledge.feedback_loop"
        if value not in extra_section_prefixes:
            extra_section_prefixes.append(value)

    return ToolQuerySpec(
        intent=intent,
        top_n=_extract_top_n(question, default_value=int(tool_cfg.get("max_rows", 5) or 5)),
        period_hint=_detect_period_hint(question),
        farm_id=farm_id,
        object_id=object_id,
        alert_id=alert_id,
        severity=_detect_severity(question),
        status=_detect_status(question),
        assignee_team=assignee_team,
        extra_section_prefixes=extra_section_prefixes,
    )


def resolve_effective_permissions(
    *,
    user_role: Optional[str] = None,
    user_permissions: Optional[Sequence[str]] = None,
) -> Tuple[Optional[str], Optional[List[str]]]:
    if user_permissions is None and not str(user_role or "").strip():
        return None, None

    from core.security import DEFAULT_ROLE_PERMISSIONS, map_legacy_role

    role = map_legacy_role(str(user_role or "").strip()) if str(user_role or "").strip() else None
    perms: List[str] = []
    if role:
        perms.extend(list(DEFAULT_ROLE_PERMISSIONS.get(role, [])))
    if user_permissions is not None:
        perms.extend([str(p) for p in user_permissions if str(p).strip()])
    return role, sorted(set(perms))




def resolve_section_required_permission(section: str, cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    config = cfg or load_copilot_tools_config()
    value = str(section or '').strip()
    if not value:
        return None
    best_prefix = ''
    best_permission: Optional[str] = None
    for tool_cfg in (config.get("tools") or {}).values():
        if not isinstance(tool_cfg, dict):
            continue
        for prefix, permission in (tool_cfg.get("section_permissions") or {}).items():
            prefix_s = str(prefix or '').strip()
            perm_s = str(permission or '').strip()
            if not prefix_s or not perm_s:
                continue
            if value.startswith(prefix_s) and len(prefix_s) > len(best_prefix):
                best_prefix = prefix_s
                best_permission = perm_s
    return best_permission


def section_is_allowed_for_permissions(
    section: str,
    *,
    user_role: Optional[str] = None,
    user_permissions: Optional[Sequence[str]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> tuple[bool, Optional[str], Optional[List[str]]]:
    _, perms = resolve_effective_permissions(user_role=user_role, user_permissions=user_permissions)
    required_permission = resolve_section_required_permission(section, cfg=cfg)
    if perms is None or not required_permission:
        return True, required_permission, None if perms is None else list(perms)
    perm_set = {str(p) for p in perms}
    return required_permission in perm_set, required_permission, list(perms)

def _section_matches(section: str, prefixes: Sequence[str]) -> bool:
    value = str(section or "")
    return any(value.startswith(str(prefix)) for prefix in (prefixes or []))


def _generic_missing_request(section: str, data_version: str) -> Dict[str, Any]:
    return {
        "request_id": f"missing.tool.{section.replace('.', '_')}",
        "section": str(section),
        "why": f"В routed fact-pack нет подтверждённых фактов для раздела {section}.",
        "needed_data": [
            f"Актуальные артефакты и итоговые таблицы для раздела {section}",
            f"run_id/data_version={data_version} и summary-таблицы, которые должен читать Copilot",
        ],
        "how_to_get": [
            f"Запустить или перепроверить offline-core pipeline для раздела {section}",
            "Проверить, что артефакты появились в artifacts и попали в fact-pack",
            "Повторить вопрос после появления подтверждённых run_id/таблиц",
        ],
        "deep_link": f"genomeai://copilot/fact?data_version={data_version}&section={section}",
    }


def _filtered_empty_request(
    *,
    section: str,
    data_version: str,
    spec: ToolQuerySpec,
) -> Dict[str, Any]:
    filters: List[str] = []
    if spec.farm_id:
        filters.append(f"farm_id={spec.farm_id}")
    if spec.object_id:
        filters.append(f"object_id={spec.object_id}")
    if spec.alert_id:
        filters.append(f"alert_id={spec.alert_id}")
    if spec.severity:
        filters.append(f"severity={spec.severity}")
    if spec.status:
        filters.append(f"status={spec.status}")
    if spec.assignee_team:
        filters.append(f"assignee_team={spec.assignee_team}")
    if spec.period_hint:
        filters.append(f"period_hint={spec.period_hint}")
    why = f"В fact-pack нет записей для фильтров: {', '.join(filters) if filters else 'без дополнительных фильтров'}."
    req = _generic_missing_request(section=section, data_version=data_version)
    req["why"] = why
    return req


def _row_matches_filters(row: Dict[str, Any], spec: ToolQuerySpec) -> bool:
    if not isinstance(row, dict):
        return False

    def rowv(*keys: str) -> str:
        for key in keys:
            if key in row and str(row.get(key) or "").strip():
                return _norm(row.get(key))
        return ""

    if spec.farm_id and rowv("farm_id") and rowv("farm_id") != _norm(spec.farm_id):
        return False
    if spec.object_id:
        candidates = {
            rowv("object_id"),
            rowv("animal_id"),
            rowv("entity_id"),
            rowv("task_id"),
            rowv("alert_id"),
            rowv("related_alert"),
        }
        present_candidates = {c for c in candidates if c}
        if present_candidates and _norm(spec.object_id) not in present_candidates:
            return False
    if spec.alert_id:
        candidates = {rowv("alert_id"), rowv("related_alert")}
        present_candidates = {c for c in candidates if c}
        if present_candidates and _norm(spec.alert_id) not in present_candidates:
            return False
    if spec.severity and rowv("severity") and rowv("severity") != _norm(spec.severity):
        return False
    if spec.status and rowv("status") and rowv("status") != _norm(spec.status):
        return False
    if spec.assignee_team and rowv("assignee_team") and rowv("assignee_team") != _norm(spec.assignee_team):
        return False
    return True


def _filter_table_rows(table_block: Dict[str, Any], spec: ToolQuerySpec) -> Optional[Dict[str, Any]]:
    rows = list(table_block.get("rows") or [])
    if not rows:
        return copy.deepcopy(table_block)
    filtered_rows = [copy.deepcopy(row) for row in rows if _row_matches_filters(row, spec)]
    if not filtered_rows and any([
        spec.farm_id,
        spec.object_id,
        spec.alert_id,
        spec.severity,
        spec.status,
        spec.assignee_team,
    ]):
        return None
    limited_rows = filtered_rows[: int(spec.top_n)] if filtered_rows else rows[: int(spec.top_n)]
    out = copy.deepcopy(table_block)
    out["rows"] = limited_rows
    out["row_count"] = int(len(limited_rows))
    out["tool_filters"] = spec.as_dict()
    return out


def _fact_matches_filters(fact: Dict[str, Any], spec: ToolQuerySpec) -> bool:
    section = _norm(fact.get("section"))
    metric = _norm(fact.get("metric_name"))
    if spec.farm_id and not any(k in section or k in metric for k in ["farm", _norm(spec.farm_id)]):
        # aggregate facts stay visible when no farm-specific marker exists
        pass
    if spec.severity and spec.severity not in _norm(fact.get("value")) and spec.severity not in metric and "severity" in metric:
        return False
    if spec.status and spec.status not in _norm(fact.get("value")) and spec.status not in metric and "status" in metric:
        return False
    return True


def _resolve_visible_prefixes(
    *,
    decision: ToolRouteDecision,
    query_spec: ToolQuerySpec,
    perms: Optional[Sequence[str]],
    cfg: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    tool_cfg = ((cfg.get("tools") or {}).get(decision.tool_name) or {})
    all_prefixes: List[str] = []
    for value in list(decision.section_prefixes or []) + list(query_spec.extra_section_prefixes or []):
        prefix = str(value).strip()
        if prefix and prefix not in all_prefixes:
            all_prefixes.append(prefix)

    prefix_perms = {str(k): str(v) for k, v in ((tool_cfg.get("section_permissions") or {}).items()) if str(k).strip()}
    if perms is None:
        return all_prefixes, []

    visible: List[str] = []
    hidden: List[str] = []
    perm_set = set(str(p) for p in perms)
    for prefix in all_prefixes:
        needed = prefix_perms.get(prefix)
        if not needed or needed in perm_set:
            visible.append(prefix)
        else:
            hidden.append(prefix)
    return visible, hidden


def filter_copilot_fact_pack_by_tool(
    fact_pack: Dict[str, Any],
    *,
    section_prefixes: Sequence[str],
    tool_name: str,
    query_spec: Optional[ToolQuerySpec] = None,
) -> Dict[str, Any]:
    assistant_fp = copy.deepcopy(fact_pack or {})
    copilot = copy.deepcopy((assistant_fp.get("copilot_fact_pack") or {}))
    if not isinstance(copilot, dict) or str(copilot.get("schema") or "") != "genomeai.copilot.fact_pack.v1":
        return assistant_fp

    prefixes = [str(x) for x in section_prefixes if str(x).strip()]
    spec = query_spec or ToolQuerySpec()
    if not prefixes:
        assistant_fp["copilot_fact_pack"] = {
            **copilot,
            "tool": {"tool_name": str(tool_name), "section_prefixes": [], "query_spec": spec.as_dict()},
        }
        return assistant_fp

    facts = [
        copy.deepcopy(f)
        for f in list(copilot.get("facts") or [])
        if isinstance(f, dict) and _section_matches(str(f.get("section") or ""), prefixes) and _fact_matches_filters(f, spec)
    ]
    tables: List[Dict[str, Any]] = []
    for table in list(copilot.get("tables") or []):
        if not isinstance(table, dict) or not _section_matches(str(table.get("section") or ""), prefixes):
            continue
        filtered = _filter_table_rows(table, spec)
        if filtered is not None:
            tables.append(filtered)

    missing = [
        copy.deepcopy(m)
        for m in list(copilot.get("missing_data_requests") or [])
        if isinstance(m, dict) and _section_matches(str(m.get("section") or ""), prefixes)
    ]

    if not facts and not tables:
        dv = str(((copilot.get("versions") or {}).get("data_version") or (assistant_fp.get("versions") or {}).get("data_version") or "NA"))
        missing = [_filtered_empty_request(section=prefix, data_version=dv, spec=spec) for prefix in prefixes[:3]]

    used_source_ids = set()
    for item in facts + tables:
        used_source_ids.update([str(sid) for sid in list(item.get("source_ids") or []) if str(sid).strip()])
    sources = {sid: src for sid, src in (copilot.get("sources") or {}).items() if sid in used_source_ids}

    filtered = {
        "schema": copilot.get("schema"),
        "created_at_utc": copilot.get("created_at_utc"),
        "period": copilot.get("period"),
        "asof_date": copilot.get("asof_date"),
        "versions": copy.deepcopy(copilot.get("versions") or {}),
        "sources": sources,
        "facts": facts,
        "tables": tables,
        "missing_data_requests": missing,
        "tool": {
            "tool_name": str(tool_name),
            "section_prefixes": prefixes,
            "query_spec": spec.as_dict(),
        },
    }
    assistant_fp["copilot_fact_pack"] = filtered
    return assistant_fp


def execute_copilot_tool(
    *,
    question: str,
    fact_pack: Dict[str, Any],
    user_role: Optional[str] = None,
    user_permissions: Optional[Sequence[str]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> ToolExecutionResult:
    config = cfg or load_copilot_tools_config()
    decision = route_copilot_tool(question, cfg=config)
    query_spec = build_tool_query_spec(question=question, decision=decision, cfg=config)
    return _execute_copilot_tool_with_decision(
        question=question,
        fact_pack=fact_pack,
        decision=decision,
        query_spec=query_spec,
        user_role=user_role,
        user_permissions=user_permissions,
        cfg=config,
    )



def _question_has_intent_marker(question: str, intent: str) -> bool:
    q = _norm(question)
    if intent == "why":
        return _contains_any(q, ["почему", "why", "причин", "из-за чего"])
    if intent == "what_to_do":
        return _contains_any(q, ["что делать", "что сделать", "рекомендуй", "план действий", "что предпринять"])
    if intent == "cost":
        return _contains_any(q, ["сколько стоит", "стоимость", "cost", "выруч", "марж", "прибыл", "убыт", "roi", "окуп"])
    return False



def _forced_intent_for_tool(question: str, tool_name: str) -> Optional[str]:
    if tool_name == "query_anomalies" and _question_has_intent_marker(question, "why"):
        return "why"
    if tool_name == "query_tasks" and _question_has_intent_marker(question, "what_to_do"):
        return "what_to_do"
    if tool_name == "query_economics" and _question_has_intent_marker(question, "cost"):
        return "cost"
    if tool_name == "query_kpi":
        return "overview"
    return None



def _rebuild_query_spec_with_intent(
    *,
    question: str,
    decision: ToolRouteDecision,
    forced_intent: Optional[str],
    cfg: Dict[str, Any],
) -> ToolQuerySpec:
    spec = build_tool_query_spec(question=question, decision=decision, cfg=cfg)
    if not forced_intent or forced_intent == spec.intent:
        return spec
    tool_cfg = ((cfg.get("tools") or {}).get(decision.tool_name) or {})
    extra_section_prefixes = [str(x) for x in list(tool_cfg.get("extra_section_prefixes") or []) if str(x).strip()]
    for prefix in list((tool_cfg.get("intent_section_prefixes") or {}).get(forced_intent) or []):
        value = str(prefix).strip()
        if value and value not in extra_section_prefixes:
            extra_section_prefixes.append(value)
    if decision.tool_name == "query_tasks" and _contains_any(question, _ANOMALY_CONTEXT_MARKERS):
        for prefix in list((tool_cfg.get("intent_section_prefixes") or {}).get("incident_context") or []):
            value = str(prefix).strip()
            if value and value not in extra_section_prefixes:
                extra_section_prefixes.append(value)
    spec.intent = forced_intent
    spec.extra_section_prefixes = extra_section_prefixes
    return spec



def _score_tool_for_plan(question: str, tool_name: str, tool_cfg: Dict[str, Any]) -> Tuple[int, List[str], str]:
    q = str(question or "").strip().lower()
    matched = [kw for kw in _iter_keywords(tool_cfg) if kw in q]
    forced_intent = _forced_intent_for_tool(q, tool_name)
    intent = forced_intent or _detect_intent(q)
    score = len(matched) + int((tool_cfg.get("intent_bonuses") or {}).get(intent, 0))
    return score, matched, intent



def _execute_copilot_tool_with_decision(
    *,
    question: str,
    fact_pack: Dict[str, Any],
    decision: ToolRouteDecision,
    query_spec: ToolQuerySpec,
    user_role: Optional[str] = None,
    user_permissions: Optional[Sequence[str]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> ToolExecutionResult:
    config = cfg or load_copilot_tools_config()
    role, perms = resolve_effective_permissions(user_role=user_role, user_permissions=user_permissions)
    required_permission = decision.required_permission

    unrestricted = perms is None
    allowed = unrestricted or not required_permission or required_permission in set(perms or [])
    visible_prefixes, hidden_prefixes = _resolve_visible_prefixes(decision=decision, query_spec=query_spec, perms=perms, cfg=config)
    filtered = filter_copilot_fact_pack_by_tool(
        fact_pack,
        section_prefixes=visible_prefixes,
        tool_name=decision.tool_name,
        query_spec=query_spec,
    )
    denial_message = None
    if not allowed:
        role_part = f" для роли '{role}'" if role else ""
        denial_message = (
            f"Недостаточно прав{role_part}: Copilot не может вызвать tool '{decision.tool_name}'. "
            f"Нужен доступ '{required_permission}'."
        )
    elif hidden_prefixes:
        tool_block = ((filtered.get("copilot_fact_pack") or {}).get("tool") or {})
        tool_block["hidden_section_prefixes"] = list(hidden_prefixes)
        filtered.setdefault("copilot_fact_pack", {}).update({"tool": tool_block})

    return ToolExecutionResult(
        decision=decision,
        query_spec=query_spec,
        allowed=allowed,
        required_permission=required_permission,
        effective_permissions=list(perms or []),
        visible_section_prefixes=list(visible_prefixes),
        hidden_section_prefixes=list(hidden_prefixes),
        filtered_fact_pack=filtered,
        denial_message=denial_message,
    )



def plan_copilot_tools(
    *,
    question: str,
    fact_pack: Dict[str, Any],
    user_role: Optional[str] = None,
    user_permissions: Optional[Sequence[str]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> List[ToolExecutionResult]:
    config = cfg or load_copilot_tools_config()
    tools = config.get("tools") or {}
    q = str(question or "").strip().lower()
    explicit_intents = [name for name in ("why", "what_to_do", "cost") if _question_has_intent_marker(q, name)]
    candidates: List[Tuple[int, int, str, ToolRouteDecision, Optional[str]]] = []
    default_order = {"query_anomalies": 10, "query_tasks": 20, "query_economics": 30, "query_kpi": 40}

    for tool_name, tool_cfg in tools.items():
        if not isinstance(tool_cfg, dict):
            continue
        score, matched_keywords, intent = _score_tool_for_plan(q, str(tool_name), tool_cfg)
        forced_intent = _forced_intent_for_tool(q, str(tool_name))
        include = bool(matched_keywords)
        if forced_intent:
            include = True
        if explicit_intents and str(tool_name) == "query_kpi" and not matched_keywords:
            include = False
        if not include:
            continue
        decision = ToolRouteDecision(
            tool_name=str(tool_name),
            label=str(tool_cfg.get("label") or tool_name),
            matched_keywords=list(matched_keywords),
            route_reason="multi_tool_plan",
            score=max(int(score), 0),
            required_permission=str(tool_cfg.get("required_permission") or "") or None,
            section_prefixes=[str(x) for x in list(tool_cfg.get("section_prefixes") or []) if str(x).strip()],
        )
        candidates.append((default_order.get(str(tool_name), 999), -max(int(score), 0), str(tool_name), decision, forced_intent or intent))

    unique_tools = {item[2] for item in candidates}
    if len(explicit_intents) < 2 or len(unique_tools) < 2:
        return []

    results: List[ToolExecutionResult] = []
    for _, _, _, decision, forced_intent in sorted(candidates):
        query_spec = _rebuild_query_spec_with_intent(
            question=question,
            decision=decision,
            forced_intent=forced_intent,
            cfg=config,
        )
        results.append(
            _execute_copilot_tool_with_decision(
                question=question,
                fact_pack=fact_pack,
                decision=decision,
                query_spec=query_spec,
                user_role=user_role,
                user_permissions=user_permissions,
                cfg=config,
            )
        )
    return results
