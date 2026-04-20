from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SCALAR_TYPES = (str, int, float, bool)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s.lower() or "na"


def _is_scalar(value: Any) -> bool:
    return isinstance(value, SCALAR_TYPES) and not isinstance(value, bool) or isinstance(value, bool)


def _safe_json_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in (row or {}).items():
        if isinstance(value, (dict, list)):
            out[str(key)] = json.dumps(value, ensure_ascii=False)
        elif value is None:
            out[str(key)] = ""
        else:
            out[str(key)] = value
    return out


def _table_title_from_key(key: str) -> str:
    return str(key).replace("_", " ")


def _build_deep_link(
    *,
    data_version: str,
    section: str,
    table: Optional[str] = None,
    metric: Optional[str] = None,
    run_id: Optional[str] = None,
    report_version: Optional[str] = None,
    source_id: Optional[str] = None,
) -> str:
    query = {
        "data_version": str(data_version or "NA"),
        "section": str(section or "NA"),
        "table": str(table or ""),
        "metric": str(metric or ""),
        "run_id": str(run_id or ""),
        "report_version": str(report_version or ""),
        "source_id": str(source_id or ""),
    }
    return "genomeai://copilot/fact?" + urlencode(query)


def _add_source(
    sources: Dict[str, Dict[str, Any]],
    *,
    section: str,
    key: str,
    value: Any,
    run_id: Optional[str],
    report_version: Optional[str],
    model_version: Optional[str],
    data_version: str,
) -> Optional[str]:
    if value in (None, "", "NA"):
        return None
    src_id = f"src.{_slug(section)}.{_slug(key)}"
    if src_id not in sources:
        sources[src_id] = {
            "source_id": src_id,
            "kind": "reference",
            "ref": str(value),
            "section": section,
            "table": key,
            "run_id": run_id,
            "report_version": report_version,
            "model_version": model_version,
            "data_version": data_version,
            "deep_link": _build_deep_link(
                data_version=data_version,
                section=section,
                table=key,
                run_id=run_id,
                report_version=report_version,
                source_id=src_id,
            ),
        }
    return src_id


def _append_fact(
    facts: List[Dict[str, Any]],
    *,
    section: str,
    metric_name: str,
    value: Any,
    source_ids: List[str],
    run_id: Optional[str],
    report_version: Optional[str],
    model_version: Optional[str],
    data_version: str,
) -> None:
    fact_id = f"fact.{_slug(section)}.{_slug(metric_name)}"
    facts.append(
        {
            "fact_id": fact_id,
            "kind": "metric",
            "section": section,
            "metric_name": metric_name,
            "value": value,
            "run_id": run_id,
            "report_version": report_version,
            "model_version": model_version,
            "data_version": data_version,
            "source_ids": [s for s in source_ids if s],
            "deep_link": _build_deep_link(
                data_version=data_version,
                section=section,
                metric=metric_name,
                run_id=run_id,
                report_version=report_version,
                source_id=fact_id,
            ),
            "render": f"{metric_name}={value}",
        }
    )


def _append_table(
    tables: List[Dict[str, Any]],
    *,
    section: str,
    key: str,
    rows: List[Dict[str, Any]],
    source_ids: List[str],
    run_id: Optional[str],
    report_version: Optional[str],
    model_version: Optional[str],
    data_version: str,
) -> None:
    table_id = f"table.{_slug(section)}.{_slug(key)}"
    tables.append(
        {
            "table_id": table_id,
            "title": _table_title_from_key(key),
            "section": section,
            "table": key,
            "rows": [_safe_json_row(r) for r in (rows or [])],
            "row_count": int(len(rows or [])),
            "run_id": run_id,
            "report_version": report_version,
            "model_version": model_version,
            "data_version": data_version,
            "source_ids": [s for s in source_ids if s],
            "deep_link": _build_deep_link(
                data_version=data_version,
                section=section,
                table=key,
                run_id=run_id,
                report_version=report_version,
                source_id=table_id,
            ),
        }
    )


def _append_missing_data_request(
    missing: List[Dict[str, Any]],
    *,
    section: str,
    needed_data: List[str],
    how_to_get: List[str],
    why: str,
) -> None:
    missing.append(
        {
            "request_id": f"missing.{_slug(section)}",
            "section": section,
            "why": why,
            "needed_data": [str(x) for x in needed_data if str(x).strip()],
            "how_to_get": [str(x) for x in how_to_get if str(x).strip()],
            "deep_link": _build_deep_link(
                data_version="NA",
                section=section,
                source_id=f"missing.{_slug(section)}",
            ),
        }
    )


def _generic_missing_request(section: str, data_version: str) -> Dict[str, Any]:
    leaf = section.split(".")[-1]
    pretty = leaf.replace("_", " ")
    artifacts_hint = f"artifacts/{data_version}/.../{leaf}"
    return {
        "request_id": f"missing.{_slug(section)}",
        "section": section,
        "why": f"В fact-pack нет подтверждённых фактов для раздела {section}.",
        "needed_data": [
            f"Актуальные артефакты модуля '{pretty}' ({artifacts_hint})",
            f"run_id и итоговые таблицы/summary для раздела {section}",
        ],
        "how_to_get": [
            f"Запустить соответствующий offline-core pipeline для раздела {section}",
            "Проверить, что upload → qc → score/train → report завершены без ошибок",
            "Повторить вопрос после появления run_id и итоговых таблиц в artifacts",
        ],
        "deep_link": _build_deep_link(
            data_version=data_version,
            section=section,
            source_id=f"missing.{_slug(section)}",
        ),
    }


def _extract_module_block(
    *,
    section: str,
    block: Dict[str, Any],
    sources: Dict[str, Dict[str, Any]],
    facts: List[Dict[str, Any]],
    tables: List[Dict[str, Any]],
    missing: List[Dict[str, Any]],
    data_version: str,
    inherited_model_version: Optional[str],
) -> None:
    if not isinstance(block, dict):
        return

    available = block.get("available")
    run_id = (
        block.get("run_id")
        or block.get("scoring_run")
        or block.get("economics_run")
        or block.get("report_version")
    )
    report_version = block.get("report_version")
    model_version = block.get("model_version") or inherited_model_version
    source_map = block.get("sources") or {}
    source_ids = [
        sid
        for sid in [
            _add_source(
                sources,
                section=section,
                key=str(k),
                value=v,
                run_id=str(run_id) if run_id else None,
                report_version=str(report_version) if report_version else None,
                model_version=str(model_version) if model_version else None,
                data_version=data_version,
            )
            for k, v in source_map.items()
        ]
        if sid
    ]

    if available is False:
        req = _generic_missing_request(section=section, data_version=data_version)
        if source_ids:
            req["needed_data"].append("Источники/пути уже зарегистрированы, но сам раздел пуст")
        missing.append(req)
        return

    for key, value in block.items():
        if key in {"available", "sources", "top", "top_pairs", "top_risk", "kpi_wide_top", "kpi_alerts_top", "kpis_top", "worklists_top", "summary_farm_top", "director_md", "ops_md"}:
            continue
        if isinstance(value, dict):
            if key in {"counts", "worklists_counts", "params"}:
                for sub_key, sub_value in value.items():
                    if _is_scalar(sub_value):
                        _append_fact(
                            facts,
                            section=section,
                            metric_name=f"{key}.{sub_key}",
                            value=sub_value,
                            source_ids=source_ids,
                            run_id=str(run_id) if run_id else None,
                            report_version=str(report_version) if report_version else None,
                            model_version=str(model_version) if model_version else None,
                            data_version=data_version,
                        )
            elif key not in {"assistant_knowledge"}:
                _extract_module_block(
                    section=f"{section}.{key}",
                    block=value,
                    sources=sources,
                    facts=facts,
                    tables=tables,
                    missing=missing,
                    data_version=data_version,
                    inherited_model_version=str(model_version) if model_version else None,
                )
            continue
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                _append_table(
                    tables,
                    section=section,
                    key=key,
                    rows=value,
                    source_ids=source_ids,
                    run_id=str(run_id) if run_id else None,
                    report_version=str(report_version) if report_version else None,
                    model_version=str(model_version) if model_version else None,
                    data_version=data_version,
                )
            continue
        if _is_scalar(value):
            _append_fact(
                facts,
                section=section,
                metric_name=key,
                value=value,
                source_ids=source_ids,
                run_id=str(run_id) if run_id else None,
                report_version=str(report_version) if report_version else None,
                model_version=str(model_version) if model_version else None,
                data_version=data_version,
            )

    for table_key in ["top", "top_pairs", "top_risk", "kpi_wide_top", "kpi_alerts_top", "kpis_top", "worklists_top", "summary_farm_top"]:
        rows = block.get(table_key)
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            _append_table(
                tables,
                section=section,
                key=table_key,
                rows=rows,
                source_ids=source_ids,
                run_id=str(run_id) if run_id else None,
                report_version=str(report_version) if report_version else None,
                model_version=str(model_version) if model_version else None,
                data_version=data_version,
            )


def build_copilot_fact_pack_from_assistant_fact_pack(assistant_fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    payload = deepcopy(assistant_fact_pack or {})
    versions = payload.get("versions") or {}
    data_version = str(versions.get("data_version") or "NA")
    model_version = str(versions.get("model_version") or "NA")

    sources: Dict[str, Dict[str, Any]] = {}
    facts: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []

    modules = payload.get("modules") or {}
    for mod_name, block in modules.items():
        _extract_module_block(
            section=f"modules.{mod_name}",
            block=block if isinstance(block, dict) else {},
            sources=sources,
            facts=facts,
            tables=tables,
            missing=missing,
            data_version=data_version,
            inherited_model_version=model_version,
        )

    assistant_knowledge = payload.get("assistant_knowledge") or {}
    if isinstance(assistant_knowledge, dict):
        for key in ["decision_log_legacy", "decision_log_v2", "regular_reports_latest", "playbooks", "tasks_v1", "feedback_loop"]:
            block = assistant_knowledge.get(key)
            if isinstance(block, dict):
                _extract_module_block(
                    section=f"assistant_knowledge.{key}",
                    block=block,
                    sources=sources,
                    facts=facts,
                    tables=tables,
                    missing=missing,
                    data_version=data_version,
                    inherited_model_version=model_version,
                )

    if not facts and not tables:
        for default_section in [
            "modules.kpi",
            "modules.alerts_v2",
            "modules.repro",
            "modules.health.mastitis_risk",
        ]:
            missing.append(_generic_missing_request(section=default_section, data_version=data_version))

    return {
        "schema": "genomeai.copilot.fact_pack.v1",
        "created_at_utc": _utc_now_iso(),
        "period": str(payload.get("period") or "NA"),
        "asof_date": str(payload.get("asof_date") or "NA"),
        "versions": {
            "data_version": data_version,
            "model_version": model_version,
            "report_version": str(((assistant_knowledge.get("regular_reports_latest") or {}).get("report_version") or "NA")),
        },
        "sources": sources,
        "facts": facts,
        "tables": tables,
        "missing_data_requests": missing,
    }
