from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence


_VERSION_KEYS = ("data_version", "qc_run", "model_version", "scoring_run", "report_version")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


@dataclass(frozen=True)
class ExplainabilityBundle:
    context_kind: str
    title: str
    summary: str
    source_linkage: dict[str, str]
    because_rows: list[dict[str, str]]
    source_facts: list[dict[str, str]]
    versions: list[dict[str, str]]
    events: list[dict[str, str]]
    thresholds: list[dict[str, str]]
    model_factors: list[dict[str, str]]
    caveats: list[dict[str, str]]
    linked_objects: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _append_row(rows: list[dict[str, str]], *, label: str, value: Any, source: str, link: str = "") -> None:
    text = _clean(value)
    if not text:
        return
    row = {"label": _clean(label) or "field", "value": text, "source": _clean(source) or "derived", "source_linkage": _clean(link)}
    if row not in rows:
        rows.append(row)


def _collect_versions(*items: Mapping[str, Any] | None, extra: Mapping[str, Any] | None = None) -> tuple[dict[str, str], list[dict[str, str]]]:
    payload: dict[str, str] = {}
    for key in _VERSION_KEYS:
        for item in list(items) + [extra or {}]:
            if not isinstance(item, Mapping):
                continue
            value = _clean(item.get(key))
            if value:
                payload[key] = value
                break
    rows = [{"label": key, "value": value, "source": "version", "source_linkage": key} for key, value in payload.items()]
    return payload, rows


def _collect_linked_objects(*items: Mapping[str, Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    specs = (
        ("object_type", "object_id", "focus_object"),
        ("related_alert", "related_alert", "alert"),
        ("linked_alert_id", "linked_alert_id", "alert"),
        ("linked_worklist_id", "linked_worklist_id", "worklist"),
        ("worklist_id", "worklist_id", "worklist"),
        ("linked_task_id", "linked_task_id", "task"),
        ("task_id", "task_id", "task"),
        ("linked_decision_id", "linked_decision_id", "decision"),
        ("decision_id", "decision_id", "decision"),
        ("farm_id", "farm_id", "farm"),
        ("site_id", "site_id", "site"),
        ("group_id", "group_id", "group"),
        ("pen_id", "pen_id", "pen"),
        ("report_version", "report_version", "report"),
    )
    for item in items:
        if not isinstance(item, Mapping):
            continue
        for type_key, id_key, fallback_kind in specs:
            if type_key == "object_type":
                obj_type = _clean(item.get(type_key)) or fallback_kind
                obj_id = _clean(item.get(id_key))
                if obj_id:
                    rec = {"kind": obj_type, "id": obj_id, "source": "object", "source_linkage": f"{obj_type}:{obj_id}"}
                    if rec not in rows:
                        rows.append(rec)
                continue
            obj_id = _clean(item.get(id_key))
            if obj_id:
                rec = {"kind": fallback_kind, "id": obj_id, "source": "linkage", "source_linkage": f"{fallback_kind}:{obj_id}"}
                if rec not in rows:
                    rows.append(rec)
    return rows


def _collect_source_facts(*payloads: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add(label: str, value: Any, source: str, link: str = "") -> None:
        _append_row(rows, label=label, value=value, source=source, link=link)

    for payload in payloads:
        if payload is None:
            continue
        if isinstance(payload, Mapping):
            for key in ("cause", "reason", "summary", "expected_effect", "why_now"):
                add(key, payload.get(key), "mapping", key)
            why = payload.get("why")
            if isinstance(why, Mapping):
                for key, value in why.items():
                    if any(tok in str(key).lower() for tok in ("factor", "threshold", "limit", "confidence")):
                        continue
                    add(str(key), value, "why", f"why.{key}")
            what_to_do = payload.get("what_to_do")
            if isinstance(what_to_do, Sequence) and not isinstance(what_to_do, (str, bytes)):
                for step in list(what_to_do)[:6]:
                    if isinstance(step, Mapping):
                        add(f"step {step.get('step') or '-'}", step.get("text") or step.get("action"), "what_to_do", "what_to_do")
            preview = payload.get("linked_facts_preview") or payload.get("facts") or payload.get("source_facts")
            if isinstance(preview, Sequence) and not isinstance(preview, (str, bytes)):
                for i, fact in enumerate(list(preview)[:12], start=1):
                    if isinstance(fact, Mapping):
                        add(_clean(fact.get("label") or fact.get("fact") or f"fact {i}"), fact.get("value") or fact.get("fact"), _clean(fact.get("source") or "source_fact"), _clean(fact.get("source_linkage") or fact.get("source") or f"fact[{i}]") )
                    else:
                        add(f"fact {i}", fact, "source_fact", f"fact[{i}]")
            for key in ("physical_location", "organizational_location", "lineage_path"):
                add(key, payload.get(key), "location", key)
        elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            for i, item in enumerate(list(payload)[:12], start=1):
                if isinstance(item, Mapping):
                    add(_clean(item.get("label") or item.get("fact") or item.get("field") or f"fact {i}"), item.get("value") or item.get("fact"), _clean(item.get("source") or "source_fact"), _clean(item.get("source_linkage") or item.get("source") or f"fact[{i}]") )
                else:
                    add(f"fact {i}", item, "source_fact", f"fact[{i}]")
        else:
            add("fact", payload, "source_fact")
    return rows


def _collect_model_factors(*payloads: Mapping[str, Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        for key in ("top_factors_text", "explain_top_factors_text", "counterfactuals_text", "explain_counterfactuals_text"):
            _append_row(rows, label=key, value=payload.get(key), source="model_factor", link=key)
        why = payload.get("why")
        if isinstance(why, Mapping):
            for key, value in why.items():
                if any(tok in str(key).lower() for tok in ("factor", "model", "driver", "explain")):
                    _append_row(rows, label=str(key), value=value, source="why_factor", link=f"why.{key}")
        factors = payload.get("factors")
        if isinstance(factors, Sequence) and not isinstance(factors, (str, bytes)):
            for i, item in enumerate(list(factors)[:12], start=1):
                if isinstance(item, Mapping):
                    value = item.get("explainability") or item.get("formula") or item.get("value") or item.get("factor")
                    label = item.get("factor") or item.get("metric") or item.get("label") or f"factor {i}"
                    _append_row(rows, label=str(label), value=value, source="model_factor", link=_clean(item.get("source_linkage") or f"factors[{i}]"))
                else:
                    _append_row(rows, label=f"factor {i}", value=item, source="model_factor", link=f"factors[{i}]")
    return rows


def _collect_thresholds(*payloads: Mapping[str, Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        for key in ("priority", "status", "stage", "severity", "due_bucket", "bucket", "queue_owner_label"):
            _append_row(rows, label=key, value=payload.get(key), source="operational_threshold", link=key)
        why = payload.get("why")
        if isinstance(why, Mapping):
            for key, value in why.items():
                low = str(key).lower()
                if any(tok in low for tok in ("threshold", "limit", "cutoff", "bucket", "priority", "sla")):
                    _append_row(rows, label=str(key), value=value, source="threshold", link=f"why.{key}")
    return rows


def _collect_events(*payloads: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add(label: str, value: Any, source: str, link: str = "") -> None:
        _append_row(rows, label=label, value=value, source=source, link=link)

    for payload in payloads:
        if payload is None:
            continue
        if isinstance(payload, Mapping):
            for key in ("last_handover_at", "last_handover_reason", "latest_event", "event_date", "updated_at", "created_at"):
                add(key, payload.get(key), "event", key)
            chain = payload.get("source_chain")
            if isinstance(chain, Sequence) and not isinstance(chain, (str, bytes)):
                for i, item in enumerate(list(chain)[:10], start=1):
                    if isinstance(item, Mapping):
                        add(_clean(item.get("kind") or item.get("label") or f"event {i}"), item.get("id") or item.get("value") or item.get("summary"), "source_chain", _clean(item.get("source_linkage") or f"source_chain[{i}]"))
                    else:
                        add(f"event {i}", item, "source_chain", f"source_chain[{i}]")
        elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            for i, item in enumerate(list(payload)[:10], start=1):
                if isinstance(item, Mapping):
                    add(_clean(item.get("label") or item.get("kind") or item.get("event_type") or f"event {i}"), item.get("value") or item.get("event_type") or item.get("summary"), _clean(item.get("source") or "event"), _clean(item.get("source_linkage") or f"event[{i}]"))
                else:
                    add(f"event {i}", item, "event", f"event[{i}]")
    return rows


def _collect_caveats(*payloads: Any, confidence: Any = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    conf = _to_float(confidence)
    if conf is not None and conf < 0.6:
        _append_row(rows, label="confidence", value=f"{conf:.2f} · low-confidence output", source="quality_caveat", link="confidence")
    for payload in payloads:
        if payload is None:
            continue
        if isinstance(payload, Mapping):
            for key in ("caveat", "note"):
                _append_row(rows, label=key, value=payload.get(key), source="quality_caveat", link=key)
            for key in ("quality_caveats", "caveats", "warnings"):
                raw = payload.get(key)
                if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                    for i, item in enumerate(list(raw)[:10], start=1):
                        _append_row(rows, label=f"{key} {i}", value=item, source="quality_caveat", link=f"{key}[{i}]")
                else:
                    _append_row(rows, label=key, value=raw, source="quality_caveat", link=key)
        elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            for i, item in enumerate(list(payload)[:10], start=1):
                _append_row(rows, label=f"caveat {i}", value=item, source="quality_caveat", link=f"caveat[{i}]")
        else:
            _append_row(rows, label="caveat", value=payload, source="quality_caveat")
    return rows


def _fallback_summary(context_kind: str, title: str, because_rows: Sequence[Mapping[str, str]], source_facts: Sequence[Mapping[str, str]]) -> str:
    for rows in (because_rows, source_facts):
        for row in rows:
            value = _clean((row or {}).get("value"))
            if value:
                return value
    prefix = {
        "animal": "Почему это животное в фокусе",
        "group": "Почему эта группа в фокусе",
        "worklist": "Почему этот worklist в очереди",
        "planner_item": "Почему этот planner item в bucket",
        "alert": "Почему этот alert сработал",
        "report": "Почему этот report требует действия",
        "economics_delta": "Почему виден economics delta",
    }.get(_clean(context_kind), "Почему объект в фокусе")
    return f"{prefix}: {title or 'объект'}"


def build_explainability_bundle(
    *,
    context_kind: str,
    title: str,
    primary: Mapping[str, Any] | None = None,
    secondary: Sequence[Mapping[str, Any] | None] | None = None,
    summary: str | None = None,
    source_facts: Sequence[Mapping[str, Any]] | None = None,
    events: Sequence[Mapping[str, Any]] | None = None,
) -> ExplainabilityBundle:
    items = [primary] + [x for x in list(secondary or []) if isinstance(x, Mapping)]
    source_linkage, versions = _collect_versions(*items)
    because_rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        for key in ("title", "alert_type", "worklist_type", "source_kind", "expected_effect", "why_now", "physical_location", "organizational_location", "lineage_path"):
            _append_row(because_rows, label=key, value=item.get(key), source="context", link=key)
    sf = _collect_source_facts(*(items), source_facts or [])
    ev = _collect_events(*(items), events or [])
    th = _collect_thresholds(*items)
    mf = _collect_model_factors(*items)
    cv = _collect_caveats(*(items), confidence=(primary or {}).get("confidence") if isinstance(primary, Mapping) else None)
    linked = _collect_linked_objects(*items)
    final_summary = _clean(summary) or _fallback_summary(_clean(context_kind), _clean(title), because_rows, sf)
    return ExplainabilityBundle(
        context_kind=_clean(context_kind),
        title=_clean(title),
        summary=final_summary,
        source_linkage=source_linkage,
        because_rows=because_rows,
        source_facts=sf,
        versions=versions,
        events=ev,
        thresholds=th,
        model_factors=mf,
        caveats=cv,
        linked_objects=linked,
    )


def build_worklist_explainability(*, worklist: Mapping[str, Any], economics_snapshot: Mapping[str, Any] | None = None, reproduction_state: Mapping[str, Any] | None = None) -> ExplainabilityBundle:
    summary = _clean(worklist.get("expected_effect") or worklist.get("title") or worklist.get("why_now"))
    return build_explainability_bundle(
        context_kind="worklist",
        title=_clean(worklist.get("title") or worklist.get("worklist_id") or "worklist"),
        primary=worklist,
        secondary=[economics_snapshot, reproduction_state],
        summary=summary,
        events=list((worklist.get("source_chain") or [])) if isinstance(worklist, Mapping) else None,
    )


def build_planner_item_explainability(*, item: Mapping[str, Any]) -> ExplainabilityBundle:
    return build_explainability_bundle(
        context_kind="planner_item",
        title=_clean(item.get("title") or item.get("planner_item_id") or "planner item"),
        primary=item,
        secondary=[],
        summary=_clean(item.get("expected_effect") or item.get("title")),
        events=list(item.get("source_chain") or []),
    )


def build_alert_explainability(*, alert: Mapping[str, Any], source_facts: Sequence[Mapping[str, Any]] | None = None, bundle: Mapping[str, Any] | None = None) -> ExplainabilityBundle:
    secondary: list[Mapping[str, Any] | None] = [bundle]
    return build_explainability_bundle(
        context_kind="alert",
        title=_clean(alert.get("title") or alert.get("alert_type") or alert.get("alert_id") or "alert"),
        primary=alert,
        secondary=secondary,
        summary=_clean(alert.get("cause") or alert.get("title") or alert.get("alert_type")),
        source_facts=source_facts,
    )


def build_animal_explainability(
    *,
    animal_id: str,
    data_version: str,
    daily_use: Mapping[str, Any] | None = None,
    prod_card: Mapping[str, Any] | None = None,
    mastitis_card: Mapping[str, Any] | None = None,
    alerts: Sequence[Mapping[str, Any]] | None = None,
    tasks: Sequence[Mapping[str, Any]] | None = None,
    decisions: Sequence[Mapping[str, Any]] | None = None,
    location_info: Mapping[str, Any] | None = None,
) -> ExplainabilityBundle:
    primary = {
        "object_type": "animal",
        "object_id": _clean(animal_id),
        "data_version": _clean(data_version),
        "physical_location": _clean((location_info or {}).get("physical_location")),
        "organizational_location": _clean((location_info or {}).get("organizational_location")),
        "lineage_path": _clean((location_info or {}).get("lineage_path")),
        "title": f"animal:{_clean(animal_id)}",
        "summary": _clean((daily_use or {}).get("current_status", {}).get("status", {}).get("hint")) or _clean((prod_card or {}).get("top_factors_text")) or _clean((mastitis_card or {}).get("top_factors_text")),
        "model_version": _clean((prod_card or {}).get("model_version")),
        "scoring_run": _clean((prod_card or {}).get("scoring_run")),
        "report_version": _clean((prod_card or {}).get("report_version")),
    }
    source_rows = _collect_source_facts(daily_use or {}, prod_card or {}, mastitis_card or {}, list(alerts or [])[:5], list(decisions or [])[:5])
    events = list((daily_use or {}).get("timeline_preview") or [])
    secondary = [daily_use, prod_card, mastitis_card, (alerts or [{}])[0] if alerts else None, (tasks or [{}])[0] if tasks else None, (decisions or [{}])[0] if decisions else None]
    return build_explainability_bundle(context_kind="animal", title=f"animal:{_clean(animal_id)}", primary=primary, secondary=secondary, source_facts=source_rows, events=events)


def build_group_explainability(
    *,
    pen_id: str,
    data_version: str,
    group_hub: Mapping[str, Any] | None = None,
    alerts: Sequence[Mapping[str, Any]] | None = None,
    tasks: Sequence[Mapping[str, Any]] | None = None,
    decisions: Sequence[Mapping[str, Any]] | None = None,
    location_info: Mapping[str, Any] | None = None,
) -> ExplainabilityBundle:
    primary = {
        "object_type": "group",
        "object_id": _clean(pen_id),
        "data_version": _clean(data_version),
        "physical_location": _clean((location_info or {}).get("physical_location")),
        "organizational_location": _clean((location_info or {}).get("organizational_location")),
        "lineage_path": _clean((location_info or {}).get("lineage_path")),
        "title": f"group:{_clean(pen_id)}",
        "summary": _clean((group_hub or {}).get("group_status", {}).get("hint")) or _clean((group_hub or {}).get("group_status", {}).get("label")),
    }
    source_rows = _collect_source_facts(group_hub or {}, list(alerts or [])[:5], list(decisions or [])[:5])
    events = list((group_hub or {}).get("recent_events") or [])
    secondary = [group_hub, (alerts or [{}])[0] if alerts else None, (tasks or [{}])[0] if tasks else None, (decisions or [{}])[0] if decisions else None]
    return build_explainability_bundle(context_kind="group", title=f"group:{_clean(pen_id)}", primary=primary, secondary=secondary, source_facts=source_rows, events=events)


def build_report_explainability(
    *,
    data_version: str,
    report_version: str,
    selected_row: Mapping[str, Any] | None = None,
    dashboard_summary: Mapping[str, Any] | None = None,
    source_facts: Sequence[Mapping[str, Any]] | None = None,
    related_objects: Sequence[Mapping[str, Any]] | None = None,
    approval_status: str | None = None,
) -> ExplainabilityBundle:
    primary = {
        "object_type": "report",
        "object_id": _clean(report_version),
        "data_version": _clean(data_version),
        "report_version": _clean(report_version),
        "title": f"report:{_clean(report_version)}",
        "status": _clean(approval_status) or _clean((selected_row or {}).get("approval_status")),
        "summary": _clean((dashboard_summary or {}).get("summary_text")) or _clean((selected_row or {}).get("kind_label")),
    }
    if isinstance(dashboard_summary, Mapping):
        lineage = dashboard_summary.get("lineage")
        if isinstance(lineage, Mapping):
            primary = {**primary, **{k: _clean(lineage.get(k)) for k in _VERSION_KEYS if _clean(lineage.get(k))}}
    return build_explainability_bundle(
        context_kind="report",
        title=f"report:{_clean(report_version)}",
        primary=primary,
        secondary=[selected_row, dashboard_summary],
        source_facts=source_facts,
        events=related_objects,
    )


def build_economics_delta_explainability(*, snapshot: Mapping[str, Any]) -> ExplainabilityBundle:
    summary = _clean(snapshot.get("why_now")) or _clean(snapshot.get("title")) or "economics per action"
    return build_explainability_bundle(
        context_kind="economics_delta",
        title=_clean(snapshot.get("title") or snapshot.get("worklist_id") or "economics per action"),
        primary=snapshot,
        secondary=[],
        summary=summary,
        source_facts=list(snapshot.get("linked_source_facts") or []),
        events=list(snapshot.get("factors") or []),
    )


__all__ = [
    "ExplainabilityBundle",
    "build_explainability_bundle",
    "build_worklist_explainability",
    "build_planner_item_explainability",
    "build_alert_explainability",
    "build_animal_explainability",
    "build_group_explainability",
    "build_report_explainability",
    "build_economics_delta_explainability",
]
