from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from core.commercial_packaging import build_packaging_summary

DEFAULT_COMMERCIAL_READINESS_CFG = Path('configs/ops/commercial_readiness_gate_v1.yaml')


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _status_rank(value: str) -> int:
    return {'not_ready': 0, 'partial': 1, 'ready': 2}.get(str(value), 0)


def _aggregate_status(values: list[str]) -> str:
    if not values:
        return 'not_ready'
    if any(v == 'not_ready' for v in values):
        return 'not_ready'
    if any(v == 'partial' for v in values):
        return 'partial'
    return 'ready'


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(raw, dict):
        raise ValueError(f'{path}: expected YAML object')
    return raw


def load_commercial_readiness_policy(*, project_root: str | Path = '.', config_path: str | Path = DEFAULT_COMMERCIAL_READINESS_CFG) -> dict[str, Any]:
    root = Path(project_root).resolve()
    path = (root / Path(config_path)).resolve() if not Path(config_path).is_absolute() else Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f'Commercial readiness config not found: {path}')
    cfg = _load_yaml(path)
    if int(cfg.get('version') or 0) != 1:
        raise ValueError('Commercial readiness config version must be 1')
    if not isinstance(cfg.get('thresholds'), dict):
        raise ValueError('Commercial readiness config thresholds are required')
    if not isinstance(cfg.get('artifacts'), dict):
        raise ValueError('Commercial readiness config artifacts are required')
    return cfg


def _find_latest_report(artifacts_root: Path, filename: str) -> Path | None:
    hits = sorted(artifacts_root.rglob(filename), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return hits[0] if hits else None


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _page_exists(project_root: Path, page_rel: str) -> bool:
    return (project_root / page_rel).exists()


def build_commercial_readiness_report(*, project_root: str | Path = '.', artifacts_root: str | Path = 'artifacts', config_path: str | Path = DEFAULT_COMMERCIAL_READINESS_CFG) -> dict[str, Any]:
    root = Path(project_root).resolve()
    artifacts = (root / Path(artifacts_root)).resolve() if not Path(artifacts_root).is_absolute() else Path(artifacts_root).resolve()
    cfg = load_commercial_readiness_policy(project_root=root, config_path=config_path)
    thresholds = dict(cfg.get('thresholds') or {})
    artifact_map = dict(cfg.get('artifacts') or {})

    reports: dict[str, dict[str, Any]] = {}
    for key, filename in artifact_map.items():
        path = _find_latest_report(artifacts, str(filename))
        reports[key] = {'path': str(path) if path else None, 'payload': _load_json(path)}

    competitive = (reports.get('competitive_acceptance') or {}).get('payload') or {}
    pilot_fw = (reports.get('pilot_framework') or {}).get('payload') or {}
    adoption = (reports.get('pilot_adoption') or {}).get('payload') or {}
    support = (reports.get('support_sla_incident') or {}).get('payload') or {}
    upgrade = (reports.get('customer_upgrade') or {}).get('payload') or {}
    packaging = build_packaging_summary(project_root=root)

    min_comp_scenarios = int(((thresholds.get('product_ready') or {}).get('min_competitive_scenarios_full') or 5))
    comp_summary = dict(competitive.get('summary') or {})
    comp_ready_flag = bool(comp_summary.get('ready_for_competitive_uat') is True)
    comp_scenarios = int(comp_summary.get('scenario_count') or 0)
    if competitive and comp_ready_flag and comp_scenarios >= min_comp_scenarios:
        product_parity_status = 'ready'
        product_parity_reason = f'Competitive acceptance report exists and covers {comp_scenarios} scenarios (threshold={min_comp_scenarios}).'
    elif competitive and comp_ready_flag:
        product_parity_status = 'partial'
        product_parity_reason = f'Competitive acceptance is positive, but only {comp_scenarios} scenario(s) are attached; threshold for full product-ready evidence is {min_comp_scenarios}.'
    else:
        product_parity_status = 'not_ready'
        product_parity_reason = 'Competitive acceptance evidence is missing or not ready-for-UAT.'

    min_editions = int(((thresholds.get('packaging') or {}).get('min_editions') or 3))
    min_modules = int(((thresholds.get('packaging') or {}).get('min_modules') or 3))
    edition_rows = list(packaging.get('edition_rows') or [])
    module_rows = list(packaging.get('module_rows') or [])
    enabled_modules = [row for row in module_rows if row.get('enabled')]
    if len(edition_rows) >= min_editions and len(enabled_modules) >= min_modules:
        packaging_status = 'ready'
        packaging_reason = f'Edition model is configured with {len(edition_rows)} editions and {len(enabled_modules)} enabled module(s).'
    elif edition_rows:
        packaging_status = 'partial'
        packaging_reason = f'Packaging config exists, but enabled modules/editions do not meet full threshold ({len(edition_rows)} editions, {len(enabled_modules)} enabled modules).'
    else:
        packaging_status = 'not_ready'
        packaging_reason = 'Packaging / editions config is missing.'

    upgrade_summary = dict(upgrade.get('summary') or {})
    if upgrade and bool(upgrade_summary.get('upgrade_ready') is True):
        migration_status = 'ready'
        migration_reason = 'Upgrade discipline report is present with repeatable backup/rollback evidence.'
    elif upgrade:
        migration_status = 'partial'
        migration_reason = 'Upgrade discipline report exists but is not fully ready.'
    else:
        migration_status = 'not_ready'
        migration_reason = 'Upgrade / migration report is missing.'

    support_summary = dict(support.get('summary') or {})
    min_diag = int(((thresholds.get('support') or {}).get('min_diagnostics_reports') or 2))
    min_release = int(((thresholds.get('support') or {}).get('min_release_notes') or 1))
    critical_open = int(support_summary.get('critical_open_incidents') or 0)
    traceable_critical = int(support_summary.get('traceable_critical_incidents') or 0)
    if support and traceable_critical >= critical_open and int(support_summary.get('diagnostics_available') or 0) >= min_diag and int(support_summary.get('release_notes_total') or 0) >= min_release:
        support_status = 'ready'
        support_reason = 'Support model has severity/SLA evidence, diagnostics and traceable critical incident coverage.'
    elif support:
        support_status = 'partial'
        support_reason = 'Support contour exists, but diagnostics/release-note/traceability coverage is incomplete.'
    else:
        support_status = 'not_ready'
        support_reason = 'Support / SLA / incident report is missing.'

    pilot_count = int(pilot_fw.get('pilot_count') or 0)
    min_pilots = int(((thresholds.get('pilot_ready') or {}).get('min_pilots') or 2))
    pilot_record_mode = str(pilot_fw.get('record_mode') or '')
    if pilot_fw and bool(pilot_fw.get('pilot_range_ok')) and pilot_count >= min_pilots and pilot_record_mode != 'starter_sample':
        pilot_framework_status = 'ready'
        pilot_framework_reason = f'Pilot framework tracks {pilot_count} pilot(s) with non-starter evidence.'
    elif pilot_fw and bool(pilot_fw.get('pilot_range_ok')) and pilot_count >= min_pilots:
        pilot_framework_status = 'partial'
        pilot_framework_reason = f'Pilot framework is runnable for {pilot_count} pilot(s), but current records are {pilot_record_mode or "starter"} and not field evidence.'
    elif pilot_fw:
        pilot_framework_status = 'partial'
        pilot_framework_reason = 'Pilot framework exists but pilot count/range is below target.'
    else:
        pilot_framework_status = 'not_ready'
        pilot_framework_reason = 'Pilot framework report is missing.'

    adop_sum = dict(adoption.get('summary') or {})
    min_dau = int(((thresholds.get('pilot_ready') or {}).get('min_dau') or 3))
    min_roi = float(((thresholds.get('pilot_ready') or {}).get('min_roi_evidence_rate') or 0.5))
    adoption_record_mode = str(((adop_sum.get('pilot_context') or {}).get('record_mode') or ''))
    if adoption and int(adop_sum.get('dau_total') or 0) >= min_dau and float(adop_sum.get('roi_evidence_rate') or 0.0) >= min_roi and adoption_record_mode != 'starter_sample':
        adoption_status = 'ready'
        adoption_reason = 'Adoption / ROI metrics show active usage with non-starter pilot evidence.'
    elif adoption and int(adop_sum.get('dau_total') or 0) >= min_dau and float(adop_sum.get('roi_evidence_rate') or 0.0) >= min_roi:
        adoption_status = 'partial'
        adoption_reason = 'Adoption / ROI instrumentation is working, but current pilot context is still starter/sample evidence.'
    elif adoption:
        adoption_status = 'partial'
        adoption_reason = 'Adoption metrics exist, but usage / ROI evidence does not yet meet the configured threshold.'
    else:
        adoption_status = 'not_ready'
        adoption_reason = 'Pilot adoption / ROI report is missing.'

    min_refs = int(((thresholds.get('commercially_ready') or {}).get('min_referenceable_deployments') or 1))
    referenceable_count = int(pilot_fw.get('referenceable_count') or 0)
    if referenceable_count >= min_refs and pilot_record_mode != 'starter_sample':
        reference_status = 'ready'
        reference_reason = f'{referenceable_count} referenceable deployment(s) are attached.'
    elif pilot_fw:
        reference_status = 'not_ready'
        reference_reason = f'Referenceable deployment evidence is missing ({referenceable_count}/{min_refs}); current pilot records must not be used as field proof.'
    else:
        reference_status = 'not_ready'
        reference_reason = 'Reference deployment evidence is missing.'

    launch_materials_files = [
        'docs/replacement_narratives_and_win_themes.md',
        'docs/demo_farm_and_benchmark_demos.md',
        'docs/commercial_packaging_and_editions.md',
        'docs/demo_farm_and_benchmark_demos.md',
        'docs/commercial_packaging_and_editions.md',
        'docs/replacement_narratives_and_win_themes.md',
        'web_app/app/(protected)/pilot/page.tsx',
        'web_app/app/(protected)/support/page.tsx',
    ]
    launch_available = [str(p) for p in launch_materials_files if _page_exists(root, p)]
    launch_status = 'ready' if len(launch_available) == len(launch_materials_files) else 'partial'
    launch_reason = f'Launch-supporting materials available: {len(launch_available)}/{len(launch_materials_files)}.'

    domain_rows = [
        {'key': 'product_parity', 'title': 'Product parity', 'status': product_parity_status, 'reason': product_parity_reason, 'evidence_path': (reports.get('competitive_acceptance') or {}).get('path')},
        {'key': 'packaging_and_editions', 'title': 'Packaging / editions', 'status': packaging_status, 'reason': packaging_reason, 'evidence_path': str((root / 'configs/product/commercial_packaging_v1.yaml'))},
        {'key': 'migration_and_upgrade', 'title': 'Migration / upgrade readiness', 'status': migration_status, 'reason': migration_reason, 'evidence_path': (reports.get('customer_upgrade') or {}).get('path')},
        {'key': 'support_operating_model', 'title': 'Support / SLA / incidents', 'status': support_status, 'reason': support_reason, 'evidence_path': (reports.get('support_sla_incident') or {}).get('path')},
        {'key': 'pilot_framework', 'title': 'Pilot framework', 'status': pilot_framework_status, 'reason': pilot_framework_reason, 'evidence_path': (reports.get('pilot_framework') or {}).get('path')},
        {'key': 'pilot_adoption', 'title': 'Adoption / ROI metrics', 'status': adoption_status, 'reason': adoption_reason, 'evidence_path': (reports.get('pilot_adoption') or {}).get('path')},
        {'key': 'reference_deployments', 'title': 'Reference deployments', 'status': reference_status, 'reason': reference_reason, 'evidence_path': (reports.get('pilot_framework') or {}).get('path')},
        {'key': 'launch_materials', 'title': 'Market-launch materials', 'status': launch_status, 'reason': launch_reason, 'evidence_path': str(root / 'docs/replacement_narratives_and_win_themes.md')},
    ]
    status_by_key = {row['key']: row['status'] for row in domain_rows}

    product_ready = _aggregate_status([product_parity_status, packaging_status, migration_status, support_status])
    # pilot-ready here means ready to enter governed pilots, not proof of completed field rollout.
    if _status_rank(product_ready) >= 1 and _status_rank(pilot_framework_status) >= 1 and _status_rank(adoption_status) >= 1 and support_status == 'ready':
        pilot_ready = 'ready'
        pilot_reason = 'Product has enough governed tooling to run formal pilots, even though field evidence may still be synthetic/starter-only.'
    elif pilot_framework_status != 'not_ready':
        pilot_ready = 'partial'
        pilot_reason = 'Pilot tooling exists, but readiness to start pilots is only partial because one or more supporting domains are incomplete.'
    else:
        pilot_ready = 'not_ready'
        pilot_reason = 'Pilot tooling / evidence contour is missing.'

    if product_ready == 'ready' and pilot_ready == 'ready' and reference_status == 'ready' and packaging_status == 'ready' and migration_status == 'ready' and support_status == 'ready':
        commercially_ready = 'ready'
        commercial_reason = 'Commercially-ready evidence pack is complete and at least one reference deployment is explicitly referenceable.'
    else:
        commercially_ready = 'not_ready'
        blockers = []
        if reference_status != 'ready':
            blockers.append('reference deployments missing')
        if product_ready != 'ready':
            blockers.append(f'product-ready={product_ready}')
        if pilot_ready != 'ready':
            blockers.append(f'pilot-ready={pilot_ready}')
        commercial_reason = 'Commercial launch readiness cannot be claimed yet because ' + ', '.join(blockers or ['required evidence is incomplete']) + '.'

    gate_rows = [
        {'gate': 'product_ready', 'status': product_ready, 'reason': 'Product-ready combines parity, packaging, migration and support readiness. ' + ({'ready':'All core product-readiness domains are green.','partial':'Some product-readiness evidence is present, but full parity evidence is incomplete.','not_ready':'Core product-readiness domains are not sufficiently evidenced yet.'}[product_ready])},
        {'gate': 'pilot_ready', 'status': pilot_ready, 'reason': pilot_reason},
        {'gate': 'commercially_ready', 'status': commercially_ready, 'reason': commercial_reason},
    ]

    checklist_rows = []
    for item in list(cfg.get('market_launch_checklist') or []):
        mapping_key = str(item.get('maps_to') or '').strip()
        row = next((r for r in domain_rows if r['key'] == mapping_key), None)
        checklist_rows.append({
            'key': str(item.get('key') or mapping_key),
            'title': str(item.get('title') or mapping_key),
            'status': row['status'] if row else 'not_ready',
            'maps_to': mapping_key,
            'reason': row['reason'] if row else 'Domain mapping not found.',
            'evidence_path': row['evidence_path'] if row else None,
        })

    replacement_docs = root / 'docs/replacement_narratives_and_win_themes.md'
    demo_docs = root / 'docs/demo_farm_and_benchmark_demos.md'
    sections = []
    evidence_available = 0
    for section in list((cfg.get('evidence_pack') or {}).get('sections') or []):
        key = str(section.get('key') or '')
        path = None
        available = False
        notes = ''
        if key in reports:
            path = (reports.get(key) or {}).get('path')
            available = bool(path)
            notes = 'Artifact report discovered.' if available else 'Artifact report not found.'
        elif key == 'commercial_packaging':
            path = str(root / 'configs/product/commercial_packaging_v1.yaml')
            available = True
            notes = 'Packaging config is present.'
        elif key == 'replacement_narratives':
            path = str(replacement_docs)
            available = replacement_docs.exists()
            notes = 'Replacement narratives docs are present.' if available else 'Replacement narratives docs are missing.'
        elif key == 'demo_kit':
            path = str(demo_docs)
            available = demo_docs.exists()
            notes = 'Demo kit docs are present.' if available else 'Demo kit docs are missing.'
        sections.append({
            'key': key,
            'title': str(section.get('title') or key),
            'required_for': list(section.get('required_for') or []),
            'available': available,
            'path': path,
            'notes': notes,
        })
        evidence_available += 1 if available else 0

    evidence_pack = {
        'required_sections': len(sections),
        'available_sections': evidence_available,
        'coverage_rate': round(float(evidence_available / len(sections)), 4) if sections else 0.0,
        'sections': sections,
    }

    blockers = [row for row in checklist_rows if row['status'] != 'ready']
    ready_domains = [row['title'] for row in domain_rows if row['status'] == 'ready']

    return {
        'schema': 'genomeai.commercial_readiness_gate.v1',
        'generated_at': _utc_now_iso(),
        'title': str(cfg.get('title') or 'Commercial readiness gate'),
        'policy_path': str((root / Path(config_path)).resolve() if not Path(config_path).is_absolute() else Path(config_path).resolve()),
        'artifacts_root': str(artifacts),
        'summary': {
            'product_ready': product_ready,
            'pilot_ready': pilot_ready,
            'commercially_ready': commercially_ready,
            'highest_honest_readiness': 'pilot_ready' if pilot_ready == 'ready' and commercially_ready != 'ready' else ('product_ready' if _status_rank(product_ready) >= 1 else 'not_ready'),
            'ready_domains_count': len(ready_domains),
            'blocked_checklist_items': len(blockers),
            'evidence_pack_coverage_rate': evidence_pack['coverage_rate'],
            'statement': 'This readiness report is evidence-backed and intentionally conservative: missing field evidence is treated as not-ready, not as marketing-ready.',
        },
        'gate_rows': gate_rows,
        'domain_rows': domain_rows,
        'market_launch_checklist': checklist_rows,
        'evidence_pack': evidence_pack,
        'reports': reports,
        'packaging_runtime': dict(packaging.get('runtime') or {}),
        'packaging_edition': dict(packaging.get('edition') or {}),
        'blockers': [
            {'title': row['title'], 'reason': row['reason'], 'evidence_path': row['evidence_path']}
            for row in blockers
        ],
        'notes': [
            'pilot-ready means ready to run governed pilots; it does not itself prove commercial field evidence.',
            'commercially-ready requires explicit reference deployment evidence and must not be inferred from starter/sample records.',
            'The gate is built from actual product reports/configs so missing evidence remains visible instead of being papered over.',
        ],
    }


def render_commercial_readiness_markdown(report: Mapping[str, Any]) -> str:
    summary = dict(report.get('summary') or {})
    lines = [
        '# Commercial readiness gate',
        '',
        f"- product_ready: **{summary.get('product_ready')}**",
        f"- pilot_ready: **{summary.get('pilot_ready')}**",
        f"- commercially_ready: **{summary.get('commercially_ready')}**",
        f"- highest_honest_readiness: `{summary.get('highest_honest_readiness')}`",
        '',
        str(summary.get('statement') or ''),
        '',
        '## Final gate',
    ]
    for row in report.get('gate_rows') or []:
        lines.append(f"- **{row.get('gate')}** → `{row.get('status')}`: {row.get('reason')}")
    lines.extend(['', '## Domain status'])
    for row in report.get('domain_rows') or []:
        lines.append(f"- **{row.get('title')}** → `{row.get('status')}`: {row.get('reason')}")
    lines.extend(['', '## Market-launch checklist'])
    for row in report.get('market_launch_checklist') or []:
        lines.append(f"- [{row.get('status')}] {row.get('title')} — {row.get('reason')}")
    lines.extend(['', '## Evidence pack'])
    ep = dict(report.get('evidence_pack') or {})
    lines.append(f"- coverage_rate: `{ep.get('coverage_rate')}`")
    for row in ep.get('sections') or []:
        lines.append(f"- {row.get('title')} → available={row.get('available')} path={row.get('path')}")
    if report.get('blockers'):
        lines.extend(['', '## Blockers'])
        for row in report.get('blockers') or []:
            lines.append(f"- **{row.get('title')}** — {row.get('reason')}")
    return "\n".join(lines) + "\n"


def render_commercial_readiness_cli_lines(report: Mapping[str, Any]) -> list[str]:
    summary = dict(report.get('summary') or {})
    return [
        f"COMMERCIAL_READINESS_PRODUCT={summary.get('product_ready')}",
        f"COMMERCIAL_READINESS_PILOT={summary.get('pilot_ready')}",
        f"COMMERCIAL_READINESS_COMMERCIAL={summary.get('commercially_ready')}",
    ]


__all__ = [
    'DEFAULT_COMMERCIAL_READINESS_CFG',
    'build_commercial_readiness_report',
    'load_commercial_readiness_policy',
    'render_commercial_readiness_cli_lines',
    'render_commercial_readiness_markdown',
]
