from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List
from urllib.parse import urlencode

from .copilot_target_resolver import build_copilot_web_target

DEFAULT_COPILOT_WEB_BASE_URL = "http://127.0.0.1:8000"


def _href_required_permission(href: str) -> str:
    value = str(href or "").strip()
    if value.startswith("/reports"):
        return "reports.view"
    if value.startswith("/playbooks"):
        return "playbooks.view"
    if value.startswith("/whatif_scenarios"):
        return "whatif.scenarios.view"
    return ""


def _is_href_allowed(href: str, effective_permissions: Iterable[str] | None) -> bool:
    required = _href_required_permission(href)
    if not required or effective_permissions is None:
        return True
    return required in {str(p) for p in effective_permissions if str(p).strip()}


def normalize_web_base_url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = DEFAULT_COPILOT_WEB_BASE_URL
    if "://" not in raw:
        raw = "http://" + raw.lstrip("/")
    return raw.rstrip("/")


def absolutize_web_href(href: str | None, *, web_base_url: str | None = None) -> str:
    raw = str(href or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    base = normalize_web_base_url(web_base_url)
    if not raw.startswith("/"):
        raw = "/" + raw
    return base + raw


def _as_dict(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if is_dataclass(row):
        return asdict(row)
    data: Dict[str, Any] = {}
    for key in (
        "label",
        "source",
        "data_version",
        "period",
        "asof_date",
        "run_id",
        "model_version",
        "report_version",
        "section",
        "table",
        "metric",
        "fact_id",
        "deep_link",
    ):
        if hasattr(row, key):
            data[key] = getattr(row, key)
    return data


def build_citation_action_cards(
    citations: Iterable[Any],
    *,
    web_base_url: str | None = None,
    max_cards: int = 8,
    effective_permissions: Iterable[str] | None = None,
) -> List[Dict[str, str]]:
    cards: List[Dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for raw in citations or []:
        row = _as_dict(raw)
        fact_id = str(row.get("fact_id") or "")
        section = str(row.get("section") or "")
        table = str(row.get("table") or "")
        metric = str(row.get("metric") or "")
        run_id = str(row.get("run_id") or "")
        key = (fact_id, section, table, metric, run_id)
        if key in seen:
            continue
        seen.add(key)

        data_version = str(row.get("data_version") or "")
        report_version = str(row.get("report_version") or "")
        params = {
            "data_version": data_version,
            "section": section,
            "table": table,
            "metric": metric,
            "run_id": run_id,
            "report_version": report_version,
            "fact_id": fact_id,
        }
        target_href = build_copilot_web_target(params)
        api_href = "/api/copilot/fact?" + urlencode({k: v for k, v in params.items() if str(v or "").strip()})
        jobs_href = "/jobs?" + urlencode({"q": run_id}) if run_id else ""
        reports_href = "/reports?" + urlencode({"dv": data_version}) if data_version else ""
        preview_href = (target_href + "#table-preview") if table else (target_href + "#fact-card")
        artifacts_href = target_href + "#artifacts"

        title = " · ".join([part for part in [section or "NA", metric or table or fact_id or "source"] if part])
        caption_parts = []
        if fact_id:
            caption_parts.append(f"fact_id={fact_id}")
        if run_id:
            caption_parts.append(f"run_id={run_id}")
        if table:
            caption_parts.append(f"table={table}")
        if report_version:
            caption_parts.append(f"report_version={report_version}")
        caption = " | ".join(caption_parts) or f"source={row.get('label') or 'NA'}"

        resolver_allowed = _is_href_allowed(target_href, effective_permissions)
        api_allowed = _is_href_allowed(api_href, effective_permissions)
        preview_allowed = _is_href_allowed(preview_href, effective_permissions) if preview_href else False
        artifacts_allowed = _is_href_allowed(artifacts_href, effective_permissions)
        jobs_allowed = _is_href_allowed(jobs_href, effective_permissions) if jobs_href else False
        reports_allowed = _is_href_allowed(reports_href, effective_permissions) if reports_href else False

        cards.append(
            {
                "title": title,
                "caption": caption,
                "source": str(row.get("source") or "NA"),
                "resolver_href": target_href if resolver_allowed else "",
                "resolver_url": absolutize_web_href(target_href, web_base_url=web_base_url) if resolver_allowed else "",
                "preview_href": preview_href if preview_allowed else "",
                "preview_url": absolutize_web_href(preview_href, web_base_url=web_base_url) if preview_allowed else "",
                "artifacts_href": artifacts_href if artifacts_allowed else "",
                "artifacts_url": absolutize_web_href(artifacts_href, web_base_url=web_base_url) if artifacts_allowed else "",
                "api_href": api_href if api_allowed else "",
                "api_url": absolutize_web_href(api_href, web_base_url=web_base_url) if api_allowed else "",
                "jobs_href": jobs_href if jobs_allowed else "",
                "jobs_url": absolutize_web_href(jobs_href, web_base_url=web_base_url) if jobs_allowed and jobs_href else "",
                "reports_href": reports_href if reports_allowed else "",
                "reports_url": absolutize_web_href(reports_href, web_base_url=web_base_url) if reports_allowed and reports_href else "",
                "has_table_preview": "1" if table else "0",
            }
        )
        if len(cards) >= int(max_cards):
            break
    return cards
