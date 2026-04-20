from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence


def _clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_report_bridge_team(team: str | None) -> str | None:
    raw = _clean(team).lower()
    if not raw:
        return None
    alias_map = {
        'zootech': 'team-repro',
        'repro': 'team-repro',
        'reproduction': 'team-repro',
        'vet': 'team-health',
        'health': 'team-health',
        'operator': 'team-data',
        'data': 'team-data',
        'qc': 'team-qc',
        'director': 'team-econ',
        'manager': 'team-econ',
        'econ': 'team-econ',
    }
    return alias_map.get(raw, raw)


def _context_id(kind: str, section: str, object_type: str, object_id: str, index: int) -> str:
    base = "|".join([_clean(kind), _clean(section), _clean(object_type), _clean(object_id), str(index)])
    return hashlib.sha1(base.encode('utf-8')).hexdigest()[:16]


_VERSION_KEYS: tuple[tuple[str, str], ...] = (
    ('data_version', 'data_version'),
    ('qc_run', 'qc_run'),
    ('model_version', 'model_version'),
    ('scoring_run', 'scoring_run'),
    ('report_version', 'report_version'),
)


def _version_linked_objects(report_ref: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for object_type, key in _VERSION_KEYS:
        value = _clean(report_ref.get(key))
        if value:
            rows.append({'object_type': object_type, 'object_id': value, 'label': object_type})
    return rows


def _base_source_facts(report_ref: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for _, key in _VERSION_KEYS:
        value = _clean(report_ref.get(key))
        if value:
            rows.append({'fact': key, 'value': value})
    return rows


def _infer_primary_object(item: Mapping[str, Any]) -> tuple[str, str]:
    for key, object_type in (
        ('animal_id', 'animal'),
        ('cow_id', 'animal'),
        ('group_id', 'group'),
        ('pen_id', 'group'),
        ('site_id', 'group'),
        ('event_id', 'event'),
    ):
        value = _clean(item.get(key))
        if value:
            return object_type, value
    object_type = _clean(item.get('object_type'))
    object_id = _clean(item.get('object_id'))
    return object_type, object_id


def _linked_objects_from_item(item: Mapping[str, Any], *, report_ref: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    primary_type, primary_id = _infer_primary_object(item)
    if primary_type and primary_id:
        rows.append({'object_type': primary_type, 'object_id': primary_id, 'label': primary_type})
        seen.add((primary_type, primary_id))
    for key, object_type in (
        ('farm_id', 'farm'),
        ('site_id', 'site'),
        ('group_id', 'group'),
        ('pen_id', 'group'),
        ('event_id', 'event'),
        ('alert_id', 'alert'),
        ('task_id', 'task'),
        ('worklist_id', 'worklist'),
        ('decision_id', 'decision'),
        ('linked_alert_id', 'alert'),
        ('linked_task_id', 'task'),
        ('linked_worklist_id', 'worklist'),
        ('linked_decision_id', 'decision'),
    ):
        value = _clean(item.get(key))
        if value and (object_type, value) not in seen:
            rows.append({'object_type': object_type, 'object_id': value, 'label': key})
            seen.add((object_type, value))
    for row in _version_linked_objects(report_ref):
        pair = (row['object_type'], row['object_id'])
        if pair not in seen:
            rows.append(row)
            seen.add(pair)
    return rows


def _source_facts_from_item(item: Mapping[str, Any], *, report_ref: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = list(_base_source_facts(report_ref))
    seen = {(r['fact'], r['value']) for r in rows}
    wanted = (
        'action', 'action_reasons', 'confidence', 'severity', 'status', 'prediction', 'residual', 'index', 'rank_in_group',
        'rank_in_farm', 'calving_date', 'event_date', 'event_type', 'condition_code', 'milk_305_kg', 'scc_cells_ml',
        'services_count', 'days_open', 'explain_top_factors_text', 'explain_counterfactuals_text', 'title', 'reason',
        'summary', 'protocol_reference', 'expected_effect',
    )
    for key in wanted:
        value = _clean(item.get(key))
        if value and (key, value) not in seen:
            rows.append({'fact': key, 'value': value})
            seen.add((key, value))
    why = item.get('why')
    if isinstance(why, Mapping):
        for key, value_raw in why.items():
            value = _clean(value_raw)
            fact = f'why.{key}'
            if value and (fact, value) not in seen:
                rows.append({'fact': fact, 'value': value})
                seen.add((fact, value))
    return rows[:20]


def _actionable_rows_from_top_lists(*, top_lists: Mapping[str, Any], report_ref: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section, items in dict(top_lists or {}).items():
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
            continue
        for index, item in enumerate(list(items)):
            if not isinstance(item, Mapping):
                continue
            object_type, object_id = _infer_primary_object(item)
            context_id = _context_id('row', str(section), object_type, object_id, index)
            rows.append(
                {
                    'context_id': context_id,
                    'context_kind': 'row',
                    'section': str(section),
                    'title': _clean(item.get('title') or item.get('summary') or item.get('action') or object_id or section),
                    'object_type': object_type,
                    'object_id': object_id,
                    'linked_alert_id': _clean(item.get('linked_alert_id') or item.get('alert_id')),
                    'linked_task_id': _clean(item.get('linked_task_id') or item.get('task_id')),
                    'linked_worklist_id': _clean(item.get('linked_worklist_id') or item.get('worklist_id')),
                    'linked_decision_id': _clean(item.get('linked_decision_id') or item.get('decision_id')),
                    'source_path': f'top_lists.{section}[{index}]',
                    'source_facts': _source_facts_from_item(dict(item), report_ref=report_ref),
                    'linked_objects': _linked_objects_from_item(dict(item), report_ref=report_ref),
                }
            )
    return rows


def _actionable_rows_from_explainability(*, explainability: Sequence[Mapping[str, Any]] | None, report_ref: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(list(explainability or [])):
        if not isinstance(item, Mapping):
            continue
        object_type, object_id = _infer_primary_object(item)
        context_id = _context_id('row', 'animal_explainability', object_type, object_id, index)
        rows.append(
            {
                'context_id': context_id,
                'context_kind': 'row',
                'section': 'animal_explainability',
                'title': _clean(item.get('animal_id') or item.get('title') or object_id or 'explainability'),
                'object_type': object_type,
                'object_id': object_id,
                'linked_alert_id': _clean(item.get('linked_alert_id') or item.get('alert_id')),
                'linked_task_id': _clean(item.get('linked_task_id') or item.get('task_id')),
                'linked_worklist_id': _clean(item.get('linked_worklist_id') or item.get('worklist_id')),
                'linked_decision_id': _clean(item.get('linked_decision_id') or item.get('decision_id')),
                'source_path': f'productivity_explainability.animal_explainability[{index}]',
                'source_facts': _source_facts_from_item(dict(item), report_ref=report_ref),
                'linked_objects': _linked_objects_from_item(dict(item), report_ref=report_ref),
            }
        )
    return rows


def _section_source_facts(title: str, *, report_ref: Mapping[str, Any], fact_pack: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = list(_base_source_facts(report_ref))
    low = _clean(title).lower()
    if 'qc' in low:
        qc = dict(fact_pack.get('qc') or {})
        status = _clean(qc.get('qc_status'))
        if status:
            rows.append({'fact': 'qc.qc_status', 'value': status})
    if 'model' in low or 'ml' in low:
        ml = dict(fact_pack.get('ml') or {})
        metrics = dict(ml.get('metrics') or {})
        for key in ('mae', 'rmse', 'n_train', 'n_test'):
            value = _clean(metrics.get(key))
            if value:
                rows.append({'fact': f'ml.metrics.{key}', 'value': value})
    if 'recommend' in low or 'action' in low or 'яд' in low:
        scoring = dict(fact_pack.get('scoring') or {})
        counts = dict(scoring.get('row_counts') or {})
        for key in ('n_animals_ranked', 'n_priority', 'n_observe', 'n_cull_candidates'):
            value = _clean(counts.get(key))
            if value:
                rows.append({'fact': f'scoring.row_counts.{key}', 'value': value})
    return rows[:20]


def _section_contexts(*, toc: Sequence[Mapping[str, Any]], report_ref: Mapping[str, Any], fact_pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(list(toc or [])):
        if not isinstance(item, Mapping):
            continue
        title = _clean(item.get('title'))
        anchor = _clean(item.get('anchor'))
        if not title:
            continue
        context_id = _context_id('section', title, 'report', _clean(report_ref.get('report_version')), index)
        rows.append(
            {
                'context_id': context_id,
                'context_kind': 'section',
                'section': title,
                'title': title,
                'anchor': anchor,
                'object_type': 'report',
                'object_id': _clean(report_ref.get('report_version')),
                'linked_alert_id': '',
                'linked_task_id': '',
                'linked_worklist_id': '',
                'linked_decision_id': '',
                'source_path': f'toc[{index}]',
                'source_facts': _section_source_facts(title, report_ref=report_ref, fact_pack=fact_pack),
                'linked_objects': _version_linked_objects(report_ref),
            }
        )
    return rows


def build_report_bridge_snapshot(
    *,
    report_ref: Mapping[str, Any],
    toc: Sequence[Mapping[str, Any]] | None = None,
    fact_pack: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    report_ref_dict = {str(k): v for k, v in dict(report_ref or {}).items()}
    fp = dict(fact_pack or {})
    rows: list[dict[str, Any]] = []
    rows.extend(_actionable_rows_from_top_lists(top_lists=dict(fp.get('top_lists') or {}), report_ref=report_ref_dict))
    explainability = (fp.get('productivity_explainability') or {}).get('animal_explainability') if isinstance(fp.get('productivity_explainability'), Mapping) else None
    rows.extend(_actionable_rows_from_explainability(explainability=explainability, report_ref=report_ref_dict))

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        cid = _clean(row.get('context_id'))
        if not cid or cid in seen:
            continue
        deduped.append(row)
        seen.add(cid)

    sections = _section_contexts(toc=list(toc or []), report_ref=report_ref_dict, fact_pack=fp)
    return {
        'report_ref': report_ref_dict,
        'actionable_rows': deduped,
        'sections': sections,
        'summary': {
            'row_contexts_n': len(deduped),
            'section_contexts_n': len(sections),
            'linked_object_rows_n': sum(1 for row in deduped if list(row.get('linked_objects') or [])),
        },
    }


def find_report_bridge_context(snapshot: Mapping[str, Any], context_id: str) -> dict[str, Any] | None:
    cid = _clean(context_id)
    if not cid:
        return None
    for row in list(snapshot.get('actionable_rows') or []) + list(snapshot.get('sections') or []):
        if _clean(row.get('context_id')) == cid:
            return dict(row)
    return None


__all__ = [
    'build_report_bridge_snapshot',
    'find_report_bridge_context',
    'normalize_report_bridge_team',
]
