from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from genomeai.target.validators_v2 import load_fixture_folder, validate_target_v2_relations
from dataclasses import dataclass

@dataclass(frozen=True)
class ShellItem:
    key: str
    label: str
    page: str | None = None
    permission: str | None = None


def flatten_shell_sections(sections):
    items = []
    for section in sections or []:
        for item in (section.get("items") or []):
            items.append(ShellItem(key=str(item.get("key") or ""), label=str(item.get("label") or item.get("key") or ""), page=str(item.get("page") or item.get("route") or ""), permission=str(item.get("permission") or "") or None))
    return items

DEFAULT_DEMO_CFG = Path('configs/ui/demo_farm_scenarios_v1.yaml')
DEMO_DATASET_ID = 'demo_farm_v1'


@dataclass(frozen=True)
class DemoScenarioStep:
    title: str
    page: str
    page_label: str
    why: str
    object_refs: dict[str, str]
    checklist: tuple[str, ...]
    diagnostics: tuple[str, ...]
    expected_effect: str


@dataclass(frozen=True)
class DemoScenario:
    scenario_id: str
    role: str
    title: str
    summary: str
    benchmark_demo: bool
    expected_outcomes: tuple[str, ...]
    linked_artifacts: tuple[str, ...]
    steps: tuple[DemoScenarioStep, ...]


@dataclass(frozen=True)
class RoleDemoKit:
    role: str
    summary: str
    dataset_dir: str
    dataset_id: str
    login_hint: str
    synthetic_note: str
    scenarios: tuple[DemoScenario, ...]
    manifest: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_demo_cfg(cfg: Mapping[str, Any]) -> None:
    if not isinstance(cfg, Mapping):
        raise ValueError('Demo config must be a mapping')
    if not isinstance(cfg.get('roles'), Mapping) or not cfg.get('roles'):
        raise ValueError("Demo config must contain non-empty 'roles'")
    dataset = cfg.get('dataset') or {}
    if not str(dataset.get('id') or '').strip():
        raise ValueError('Demo config dataset.id is required')
    if not str(dataset.get('path') or '').strip():
        raise ValueError('Demo config dataset.path is required')


def load_demo_scenarios_config(path: str | Path = DEFAULT_DEMO_CFG) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'Demo scenarios config not found: {p}')
    cfg = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    _validate_demo_cfg(cfg)
    return cfg


def _resolve_step_page(step: Mapping[str, Any], flat: Mapping[str, ShellItem]) -> tuple[str, str]:
    page_key = str(step.get('page_key') or '').strip()
    if page_key:
        item = flat.get(page_key)
        if item is None:
            return '', ''
        return str(item.page), str(item.label)
    page = str(step.get('page') or '').strip()
    if not page:
        return '', ''
    label = str(step.get('page_label') or Path(page).stem.replace('_', ' ')).strip()
    return page, label


def load_demo_farm_manifest(dataset_dir: str | Path) -> dict[str, Any]:
    p = Path(dataset_dir) / 'demo_farm_manifest.json'
    if not p.exists():
        raise FileNotFoundError(f'Demo farm manifest not found: {p}')
    payload = json.loads(p.read_text(encoding='utf-8'))
    if not payload.get('synthetic'):
        raise ValueError('Demo farm manifest must explicitly mark dataset as synthetic=true')
    return payload


def build_role_demo_kit(*, role: str, shell_sections: Sequence[Any], cfg: Mapping[str, Any] | None = None, manifest: Mapping[str, Any] | None = None) -> RoleDemoKit:
    config = dict(cfg or load_demo_scenarios_config())
    dataset_cfg = dict(config.get('dataset') or {})
    roles_cfg = dict(config.get('roles') or {})
    role_cfg = dict(roles_cfg.get(role) or {})
    flat = flatten_shell_sections(list(shell_sections))
    if manifest is None:
        manifest = load_demo_farm_manifest(dataset_cfg.get('path') or f'data/demo/{DEMO_DATASET_ID}')

    scenarios: list[DemoScenario] = []
    for raw in list(role_cfg.get('scenarios') or []):
        if not isinstance(raw, Mapping):
            continue
        steps: list[DemoScenarioStep] = []
        for raw_step in list(raw.get('steps') or []):
            if not isinstance(raw_step, Mapping):
                continue
            page, page_label = _resolve_step_page(raw_step, flat)
            if not page:
                continue
            refs = {str(k): str(v) for k, v in dict(raw_step.get('object_refs') or {}).items() if str(v).strip()}
            steps.append(
                DemoScenarioStep(
                    title=str(raw_step.get('title') or 'Step').strip(),
                    page=page,
                    page_label=page_label,
                    why=str(raw_step.get('why') or '').strip(),
                    object_refs=refs,
                    checklist=tuple(str(x).strip() for x in (raw_step.get('checklist') or []) if str(x).strip()),
                    diagnostics=tuple(str(x).strip() for x in (raw_step.get('diagnostics') or []) if str(x).strip()),
                    expected_effect=str(raw_step.get('expected_effect') or '').strip(),
                )
            )
        if not steps:
            continue
        scenarios.append(
            DemoScenario(
                scenario_id=str(raw.get('scenario_id') or '').strip(),
                role=str(role),
                title=str(raw.get('title') or 'Demo scenario').strip(),
                summary=str(raw.get('summary') or '').strip(),
                benchmark_demo=bool(raw.get('benchmark_demo', False)),
                expected_outcomes=tuple(str(x).strip() for x in (raw.get('expected_outcomes') or []) if str(x).strip()),
                linked_artifacts=tuple(str(x).strip() for x in (raw.get('linked_artifacts') or []) if str(x).strip()),
                steps=tuple(steps),
            )
        )

    return RoleDemoKit(
        role=str(role),
        summary=str(role_cfg.get('summary') or '').strip(),
        dataset_dir=str(dataset_cfg.get('path') or f'data/demo/{DEMO_DATASET_ID}'),
        dataset_id=str(dataset_cfg.get('id') or DEMO_DATASET_ID),
        login_hint=str(role_cfg.get('login_hint') or '').strip(),
        synthetic_note=str((manifest or {}).get('synthetic_note') or 'Synthetic demo dataset').strip(),
        scenarios=tuple(scenarios),
        manifest=dict(manifest or {}),
    )


def build_role_demo_markdown(kit: RoleDemoKit) -> str:
    lines = [
        f'# Demo farm & benchmark demos — {kit.role}',
        '',
        kit.summary,
        '',
        f'- Dataset: `{kit.dataset_dir}`',
        f'- Dataset id: `{kit.dataset_id}`',
        f'- Login hint: `{kit.login_hint}`',
        f'- Synthetic note: {kit.synthetic_note}',
        '',
    ]
    for scenario in kit.scenarios:
        lines.extend([
            f'## {scenario.title}',
            '',
            scenario.summary,
            '',
            f'- scenario_id: `{scenario.scenario_id}`',
            f'- benchmark_demo: `{str(scenario.benchmark_demo).lower()}`',
        ])
        if scenario.linked_artifacts:
            lines.append('- Linked artifacts:')
            for item in scenario.linked_artifacts:
                lines.append(f'  - {item}')
        if scenario.expected_outcomes:
            lines.append('- Expected outcomes:')
            for item in scenario.expected_outcomes:
                lines.append(f'  - {item}')
        lines.append('- Steps:')
        for idx, step in enumerate(scenario.steps, start=1):
            lines.append(f'  {idx}. **{step.title}** — `{step.page}`')
            if step.why:
                lines.append(f'     - Why: {step.why}')
            if step.object_refs:
                lines.append(f'     - Object refs: {json.dumps(step.object_refs, ensure_ascii=False, sort_keys=True)}')
            if step.expected_effect:
                lines.append(f'     - Expected effect: {step.expected_effect}')
            for item in step.checklist:
                lines.append(f'     - Checklist: {item}')
            for item in step.diagnostics:
                lines.append(f'     - Diagnostics: {item}')
        lines.append('')
    return '\n'.join(lines)


def build_demo_farm_dataset(output_dir: str | Path) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    farms = pd.DataFrame([
        ['default', 'DEMO_FARM_001', 'SYNTHETIC North River Demo Farm', 'DE', 'Europe/Berlin', 'EUR'],
        ['default', 'DEMO_FARM_002', 'SYNTHETIC South Creek Demo Farm', 'DE', 'Europe/Berlin', 'EUR'],
    ], columns=['tenant_id', 'farm_id', 'farm_name', 'country_code', 'timezone', 'currency'])

    sites = pd.DataFrame([
        ['default', 'DEMO_SITE_001', 'DEMO_FARM_001', 'North Site A', 'Demo Avenue 1'],
        ['default', 'DEMO_SITE_002', 'DEMO_FARM_001', 'North Site B', 'Demo Avenue 2'],
        ['default', 'DEMO_SITE_003', 'DEMO_FARM_002', 'South Site', 'Demo Road 3'],
    ], columns=['tenant_id', 'site_id', 'farm_id', 'site_name', 'address'])

    pens = pd.DataFrame([
        ['default', 'PEN_N1_LACT', 'DEMO_SITE_001', 'North A Lactating', 'lactating', 120],
        ['default', 'PEN_N1_FRESH', 'DEMO_SITE_001', 'North A Fresh', 'fresh', 40],
        ['default', 'PEN_N2_REPRO', 'DEMO_SITE_002', 'North B Repro', 'repro', 70],
        ['default', 'PEN_N2_HOSP', 'DEMO_SITE_002', 'North B Hospital', 'hospital', 25],
        ['default', 'PEN_S1_LACT', 'DEMO_SITE_003', 'South Lactating', 'lactating', 110],
        ['default', 'PEN_S1_DRY', 'DEMO_SITE_003', 'South Dry', 'dry', 55],
    ], columns=['tenant_id', 'pen_id', 'site_id', 'pen_name', 'pen_type', 'capacity_head'])

    animal_specs = [
        ('DEMO_COW_1001', 'DEMO_FARM_001', 'DEMO_SITE_001', 'PEN_N1_LACT', '2021-03-12', 'active', 10850, 'normal'),
        ('DEMO_COW_1002', 'DEMO_FARM_001', 'DEMO_SITE_001', 'PEN_N1_FRESH', '2021-05-02', 'active', 9850, 'normal'),
        ('DEMO_COW_1003', 'DEMO_FARM_001', 'DEMO_SITE_001', 'PEN_N1_LACT', '2020-11-18', 'active', 11220, 'normal'),
        ('DEMO_COW_2001', 'DEMO_FARM_001', 'DEMO_SITE_002', 'PEN_N2_REPRO', '2021-01-27', 'active', 9410, 'normal'),
        ('DEMO_COW_2002', 'DEMO_FARM_001', 'DEMO_SITE_002', 'PEN_N2_HOSP', '2020-08-15', 'active', 9050, 'normal'),
        ('DEMO_COW_2003', 'DEMO_FARM_001', 'DEMO_SITE_002', 'PEN_N2_REPRO', '2021-09-03', 'active', 9980, 'normal'),
        ('DEMO_COW_3001', 'DEMO_FARM_002', 'DEMO_SITE_003', 'PEN_S1_LACT', '2021-02-08', 'active', 10310, 'normal'),
        ('DEMO_COW_3002', 'DEMO_FARM_002', 'DEMO_SITE_003', 'PEN_S1_LACT', '2020-12-21', 'active', 9750, 'normal'),
        ('DEMO_COW_3003', 'DEMO_FARM_002', 'DEMO_SITE_003', 'PEN_S1_DRY', '2021-06-30', 'active', 8875, 'normal'),
    ]
    animals_rows = []
    lact_rows = []
    milk_rows = []
    testday_rows = []
    sensor_rows = []
    base_day = date(2025, 4, 5)
    for idx, (animal_id, farm_id, site_id, pen_id, birth_date, status, milk305, outcome) in enumerate(animal_specs, start=1):
        animals_rows.append([
            'default', animal_id, farm_id, site_id, pen_id, f'MA_{animal_id}', f'EXT_{animal_id}', 'F', birth_date, 'Holstein', status,
        ])
        lact_id = f'LAC_{animal_id}_2'
        calving_date = date(2024, 8, 1) + timedelta(days=idx * 6)
        dryoff_date = calving_date + timedelta(days=290)
        lact_rows.append(['default', lact_id, animal_id, 2, calving_date.isoformat(), dryoff_date.isoformat(), milk305, outcome])
        for j, delta in enumerate((0, 7, 14), start=1):
            d = base_day - timedelta(days=delta)
            milk = round(29.0 + (milk305 / 1000.0) / 4 + (idx % 3) * 1.3 - j * 0.4, 1)
            fat = round(3.8 + (idx % 2) * 0.2, 2)
            protein = round(3.15 + (idx % 3) * 0.05, 2)
            scc = 145000 + idx * 12000 + j * 5000
            milk_rows.append(['default', f'MD_{idx:03d}_{j}', animal_id, lact_id, d.isoformat(), milk, 2, fat, protein, scc])
            testday_rows.append(['default', f'TD_{idx:03d}_{j}', animal_id, lact_id, d.isoformat(), 120 + j * 10, milk, fat, protein, scc])
            sensor_rows.append(['default', f'SN_{idx:03d}_{j}', animal_id, d.isoformat(), 4300 + idx * 110 - j * 40, 520 - j * 15, 710 + j * 5, round(38.5 + (idx % 4) * 0.1, 2)])

    animals = pd.DataFrame(animals_rows, columns=['tenant_id', 'animal_id', 'farm_id', 'site_id', 'current_pen_id', 'master_animal_id', 'external_id', 'sex', 'birth_date', 'breed', 'status'])
    lactations = pd.DataFrame(lact_rows, columns=['tenant_id', 'lactation_id', 'animal_id', 'lactation_no', 'calving_date', 'dryoff_date', 'milk_305d_kg', 'calving_outcome'])
    milkings = pd.DataFrame(milk_rows, columns=['tenant_id', 'record_id', 'animal_id', 'lactation_id', 'date', 'milk_kg', 'milking_count', 'fat_pct', 'protein_pct', 'scc_cells_ml'])
    testday = pd.DataFrame(testday_rows, columns=['tenant_id', 'testday_id', 'animal_id', 'lactation_id', 'test_date', 'dim', 'milk_kg', 'fat_pct', 'protein_pct', 'scc_cells_ml'])
    sensors = pd.DataFrame(sensor_rows, columns=['tenant_id', 'record_id', 'animal_id', 'date', 'activity_count', 'rumination_min', 'lying_min', 'temperature_c'])

    bulls = pd.DataFrame([
        ['default', 'BULL_9001', 'North Signal', 'Holstein'],
        ['default', 'BULL_9002', 'South Index', 'Holstein'],
        ['default', 'BULL_9003', 'Balanced Merit', 'Holstein'],
    ], columns=['tenant_id', 'bull_id', 'bull_name', 'breed'])

    repro = pd.DataFrame([
        ['default', 'RE_001', 'DEMO_COW_2001', '2025-03-18', 'heat', 'BULL_9002', 'candidate', 'heat watch high'],
        ['default', 'RE_002', 'DEMO_COW_2001', '2025-03-20', 'insemination', 'BULL_9002', 'done', 'AI after heat'],
        ['default', 'RE_003', 'DEMO_COW_2003', '2025-04-01', 'preg_check_due', 'BULL_9001', 'due', 'preg check this week'],
        ['default', 'RE_004', 'DEMO_COW_1002', '2025-04-04', 'fresh', 'BULL_9003', 'event', 'fresh cow monitoring'],
        ['default', 'RE_005', 'DEMO_COW_3003', '2025-03-30', 'dry_off_due', 'BULL_9001', 'due', 'dry-off queue'],
    ], columns=['tenant_id', 'repro_event_id', 'animal_id', 'event_date', 'event_type', 'bull_id', 'result', 'notes'])

    health = pd.DataFrame([
        ['default', 'HE_001', 'DEMO_COW_1002', '2025-04-04', 'metritis', 'medium', 'fresh cow protocol'],
        ['default', 'HE_002', 'DEMO_COW_2002', '2025-04-03', 'lameness', 'high', 'locomotion drop'],
        ['default', 'HE_003', 'DEMO_COW_3002', '2025-04-02', 'mastitis', 'medium', 'SCC rise and conductivity'],
        ['default', 'HE_004', 'DEMO_COW_3003', '2025-04-01', 'ketosis_risk', 'warn', 'fresh risk flag'],
    ], columns=['tenant_id', 'event_id', 'animal_id', 'event_date', 'event_type', 'severity', 'notes'])

    treatments = pd.DataFrame([
        ['default', 'TR_001', 'DEMO_COW_1002', '2025-04-04', '2025-04-08', 'protocol_metritis', 'HE_001', '2025-04-12'],
        ['default', 'TR_002', 'DEMO_COW_2002', '2025-04-03', '2025-04-10', 'pain_relief', 'HE_002', '2025-04-05'],
        ['default', 'TR_003', 'DEMO_COW_3002', '2025-04-02', '2025-04-06', 'mastitis_protocol', 'HE_003', '2025-04-15'],
    ], columns=['tenant_id', 'treatment_id', 'animal_id', 'start_date', 'end_date', 'treatment_type', 'reason_event_id', 'withdrawal_end_date'])

    pen_moves = pd.DataFrame([
        ['default', 'PM_001', 'DEMO_COW_1002', 'PEN_N1_LACT', 'PEN_N1_FRESH', '2025-04-04', 'fresh transition'],
        ['default', 'PM_002', 'DEMO_COW_2002', 'PEN_N2_REPRO', 'PEN_N2_HOSP', '2025-04-03', 'vet treatment'],
        ['default', 'PM_003', 'DEMO_COW_3003', 'PEN_S1_LACT', 'PEN_S1_DRY', '2025-03-30', 'dry-off prep'],
    ], columns=['tenant_id', 'move_id', 'animal_id', 'from_pen_id', 'to_pen_id', 'move_date', 'reason'])

    rations = pd.DataFrame([
        ['default', 'RAT_NA_LACT', 'DEMO_SITE_001', 'North Lactating TMR', '2025-03-01', '2025-04-30', 48.0],
        ['default', 'RAT_NB_REPRO', 'DEMO_SITE_002', 'North Repro Mix', '2025-03-01', '2025-04-30', 46.5],
        ['default', 'RAT_S_LACT', 'DEMO_SITE_003', 'South Lactating TMR', '2025-03-01', '2025-04-30', 47.2],
    ], columns=['tenant_id', 'ration_id', 'site_id', 'ration_name', 'effective_from', 'effective_to', 'dm_pct'])

    deliveries = pd.DataFrame([
        ['default', 'FD_001', 'RAT_NA_LACT', 'PEN_N1_LACT', '2025-04-05', 1240.0],
        ['default', 'FD_002', 'RAT_NA_LACT', 'PEN_N1_FRESH', '2025-04-05', 360.0],
        ['default', 'FD_003', 'RAT_NB_REPRO', 'PEN_N2_REPRO', '2025-04-05', 710.0],
        ['default', 'FD_004', 'RAT_NB_REPRO', 'PEN_N2_HOSP', '2025-04-05', 180.0],
        ['default', 'FD_005', 'RAT_S_LACT', 'PEN_S1_LACT', '2025-04-05', 1185.0],
        ['default', 'FD_006', 'RAT_S_LACT', 'PEN_S1_DRY', '2025-04-05', 410.0],
    ], columns=['tenant_id', 'delivery_id', 'ration_id', 'pen_id', 'delivery_date', 'feed_kg_as_fed'])

    prices = pd.DataFrame([
        ['default', 'PR_001', 'milk', 'raw_milk', 'EUR', 'kg', '2025-04-01', '2025-04-30', 0.53],
        ['default', 'PR_002', 'feed', 'tMR', 'EUR', 'kg_dm', '2025-04-01', '2025-04-30', 0.31],
        ['default', 'PR_003', 'service', 'vet_visit', 'EUR', 'visit', '2025-04-01', '2025-04-30', 45.0],
    ], columns=['tenant_id', 'price_id', 'item_type', 'item_name', 'currency', 'unit', 'valid_from', 'valid_to', 'value'])

    econ = pd.DataFrame([
        ['default', 'EC_001', 'DEMO_FARM_001', '2025-04-04', 0.53, 'EUR', 0.31, 'EUR', 148.0],
        ['default', 'EC_002', 'DEMO_FARM_001', '2025-04-05', 0.53, 'EUR', 0.31, 'EUR', 152.0],
        ['default', 'EC_003', 'DEMO_FARM_002', '2025-04-04', 0.52, 'EUR', 0.30, 'EUR', 139.0],
        ['default', 'EC_004', 'DEMO_FARM_002', '2025-04-05', 0.52, 'EUR', 0.30, 'EUR', 141.0],
    ], columns=['tenant_id', 'record_id', 'farm_id', 'date', 'milk_price_per_kg', 'milk_price_ccy', 'feed_cost_per_kg_dm', 'feed_cost_ccy', 'other_cost_eur'])

    alerts = pd.DataFrame([
        ['default', 'AL_DEMO_001', 'DEMO_FARM_001', '2025-04-05', 'high', 'fresh_cow_risk', 'animal', 'DEMO_COW_1002', 'Fresh cow needs protocol review'],
        ['default', 'AL_DEMO_002', 'DEMO_FARM_001', '2025-04-05', 'high', 'vet_triage', 'animal', 'DEMO_COW_2002', 'Lameness triage overdue'],
        ['default', 'AL_DEMO_003', 'DEMO_FARM_001', '2025-04-05', 'warn', 'repro_due', 'animal', 'DEMO_COW_2001', 'Insemination follow-up due'],
        ['default', 'AL_DEMO_004', 'DEMO_FARM_002', '2025-04-05', 'warn', 'milk_quality', 'animal', 'DEMO_COW_3002', 'SCC needs review'],
        ['default', 'AL_DEMO_005', 'DEMO_FARM_002', '2025-04-05', 'warn', 'dry_off', 'animal', 'DEMO_COW_3003', 'Dry-off task due this week'],
        ['default', 'AL_DEMO_006', 'DEMO_FARM_002', '2025-04-05', 'info', 'benchmark_gap', 'site', 'DEMO_SITE_003', 'South site below sibling median on overdue rate'],
    ], columns=['tenant_id', 'alert_id', 'farm_id', 'alert_date', 'severity', 'alert_type', 'entity_type', 'entity_id', 'message'])

    decisions = pd.DataFrame([
        ['default', 'DEMO_DEC_001', 'DEMO_FARM_001', '2025-04-05', 'DEMO_COW_1002', 'LAC_DEMO_COW_1002_2', 'fresh_protocol', 'accept', 'Treat and monitor fresh cow', 'AL_DEMO_001'],
        ['default', 'DEMO_DEC_002', 'DEMO_FARM_001', '2025-04-05', 'DEMO_COW_2002', 'LAC_DEMO_COW_2002_2', 'vet_review', 'accept', 'Escalate to vet round', 'AL_DEMO_002'],
        ['default', 'DEMO_DEC_003', 'DEMO_FARM_002', '2025-04-05', 'DEMO_COW_3003', 'LAC_DEMO_COW_3003_2', 'dry_off', 'review', 'Check economics before dry-off move', 'AL_DEMO_005'],
    ], columns=['tenant_id', 'decision_id', 'farm_id', 'decision_date', 'animal_id', 'lactation_id', 'recommendation_type', 'decision', 'comment', 'source_alert_id'])

    reports = pd.DataFrame([
        ['default', 'RP_DEMO_001', 'DEMO_FARM_001', '2025-04-05', 'daily_ops', 'dv_demo_farm_v1', 'run_demo_daily_001', 'artifacts/dv_demo_farm_v1/reports/run_demo_daily_001/daily_brief.md'],
        ['default', 'RP_DEMO_002', 'DEMO_FARM_001', '2025-04-05', 'repro', 'dv_demo_farm_v1', 'run_demo_repro_001', 'artifacts/dv_demo_farm_v1/reports/run_demo_repro_001/report.md'],
        ['default', 'RP_DEMO_003', 'DEMO_FARM_002', '2025-04-05', 'economics', 'dv_demo_farm_v1', 'run_demo_econ_001', 'artifacts/dv_demo_farm_v1/reports/run_demo_econ_001/report.md'],
    ], columns=['tenant_id', 'report_id', 'farm_id', 'report_date', 'report_type', 'data_version', 'run_id', 'storage_path'])

    cull = pd.DataFrame([
        ['default', 'CU_DEMO_001', 'DEMO_COW_3003', '2025-03-20', 'cull', 38000.0, 9000.0, 'synthetic economics benchmark note'],
    ], columns=['tenant_id', 'cull_event_id', 'animal_id', 'event_date', 'event_type', 'revenue_rub', 'cost_rub', 'notes'])

    users = pd.DataFrame([
        ['default', 'USR_ADMIN_DEMO', 'demo_admin', 'Demo Admin', 1],
        ['default', 'USR_DIRECTOR_DEMO', 'demo_director', 'Demo Director', 1],
        ['default', 'USR_OPERATOR_DEMO', 'demo_operator', 'Demo Operator', 1],
        ['default', 'USR_ZOOTECH_DEMO', 'demo_zootech', 'Demo Zootech', 1],
        ['default', 'USR_VET_DEMO', 'demo_vet', 'Demo Vet', 1],
    ], columns=['tenant_id', 'user_id', 'username', 'display_name', 'is_active'])

    roles = pd.DataFrame([
        ['default', 'R_ADMIN', 'Admin'],
        ['default', 'R_DIRECTOR', 'Director'],
        ['default', 'R_OPERATOR', 'Operator'],
        ['default', 'R_ZOOTECH', 'Zootech'],
        ['default', 'R_VET', 'Vet'],
    ], columns=['tenant_id', 'role_id', 'role_name'])

    user_roles = pd.DataFrame([
        ['default', 'USR_ADMIN_DEMO', 'R_ADMIN'],
        ['default', 'USR_DIRECTOR_DEMO', 'R_DIRECTOR'],
        ['default', 'USR_OPERATOR_DEMO', 'R_OPERATOR'],
        ['default', 'USR_ZOOTECH_DEMO', 'R_ZOOTECH'],
        ['default', 'USR_VET_DEMO', 'R_VET'],
    ], columns=['tenant_id', 'user_id', 'role_id'])

    payloads = {
        'dm_farms.csv': farms,
        'dm_sites.csv': sites,
        'dm_pens.csv': pens,
        'dm_animals.csv': animals,
        'dm_lactations.csv': lactations,
        'dm_milkings_daily.csv': milkings,
        'dm_testday.csv': testday,
        'dm_sensors_daily.csv': sensors,
        'dm_bulls.csv': bulls,
        'dm_repro_events.csv': repro,
        'dm_health_events.csv': health,
        'dm_treatments.csv': treatments,
        'dm_pen_moves.csv': pen_moves,
        'dm_feed_rations.csv': rations,
        'dm_feed_deliveries.csv': deliveries,
        'dm_prices.csv': prices,
        'dm_economics_daily.csv': econ,
        'dm_alerts.csv': alerts,
        'dm_decisions.csv': decisions,
        'dm_reports.csv': reports,
        'dm_cull_events.csv': cull,
        'dm_users.csv': users,
        'dm_roles.csv': roles,
        'dm_user_roles.csv': user_roles,
    }
    for filename, df in payloads.items():
        df.to_csv(out / filename, index=False)

    readme = (
        '# SYNTHETIC demo farm dataset\n\n'
        'This folder is synthetic but realistic demo data for sales / pilot / UAT benchmark scenarios.\n'
        'It must never be treated as production farm data.\n'
    )
    (out / 'README_SYNTHETIC.md').write_text(readme, encoding='utf-8')

    summary = {name.replace('.csv', ''): int(len(df)) for name, df in payloads.items()}
    manifest = {
        'dataset_id': DEMO_DATASET_ID,
        'synthetic': True,
        'synthetic_note': 'Synthetic but realistic demo farm dataset for sales/pilot/UAT. Never mix with production evidence.',
        'generated_at': date.today().isoformat(),
        'generator': 'core.demo_farm.build_demo_farm_dataset',
        'dataset_dir': str(out).replace('\\', '/'),
        'default_data_version': 'dv_demo_farm_v1',
        'default_asof_date': '2025-04-05',
        'farms': ['DEMO_FARM_001', 'DEMO_FARM_002'],
        'sites': ['DEMO_SITE_001', 'DEMO_SITE_002', 'DEMO_SITE_003'],
        'role_logins': {
            'Admin': 'demo_admin',
            'Director': 'demo_director',
            'Operator': 'demo_operator',
            'Zootech': 'demo_zootech',
            'Vet': 'demo_vet',
        },
        'scenario_focus': [
            'daily_operator_flow', 'reproduction_review', 'vet_triage', 'reports_and_brief', 'economics_delta', 'admin_rollout', 'mobile_cowside', 'enterprise_benchmark_compare'
        ],
        'row_counts': summary,
        'artifacts_hint': [
            'artifacts/dv_demo_farm_v1/reports/run_demo_daily_001/daily_brief.md',
            'artifacts/_ci/demo_farm_v1/demo_farm_report.json',
        ],
    }
    (out / 'demo_farm_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    dfs = load_fixture_folder(str(out))
    issues = validate_target_v2_relations(dfs)
    errors = [asdict(i) for i in issues if str(i.severity).upper() == 'ERROR']
    if errors:
        raise ValueError(f'Demo farm dataset failed referential validation: {errors[:3]}')
    return manifest


__all__ = [
    'DEMO_DATASET_ID',
    'DemoScenarioStep',
    'DemoScenario',
    'RoleDemoKit',
    'build_demo_farm_dataset',
    'build_role_demo_kit',
    'build_role_demo_markdown',
    'load_demo_farm_manifest',
    'load_demo_scenarios_config',
]
