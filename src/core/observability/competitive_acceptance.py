from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml


_DEFAULT_COMPETITIVE_ACCEPTANCE_POLICY: dict[str, Any] = {
    "version": 1,
    "manual_signoff": {
        "path": "artifacts/_qa/competitive_acceptance/manual_signoff.json",
    },
    "artifact_aliases": {
        "web_cutover": "configs/post_removal/streamlit_removal_regression_report_v1.json",
        "operational_rollout": "artifacts/_ci/operational_rollout_gates/operational_rollout_gates_report.json",
    },
    "profiles": {
        "legacy_replacement_ci": {
            "daily_operations": {
                "enabled": True,
                "title": "Daily operations parity",
                "budget_sec": 45.0,
                "artifact_checks": ["web_cutover", "operational_rollout"],
                "pytest": [
                    "tests/test_t21_02_daily_worklists_by_role.py",
                    "tests/test_t21_03_operational_planner.py",
                    "tests/test_t20_04_animal_profile_daily_use.py",
                    "tests/test_t20_05_group_profile_operational_hub.py",
                ],
                "scripts": [
                    "scripts/smoke_t28_05_worklists_daily_use.py",
                ],
                "required_files": [
                    "docs/daily_worklists_by_role.md",
                    "docs/animal_profile_daily_use.md",
                    "docs/group_profile_operational_hub.md",
                ],
                "pass_fail_criteria": [
                    "Worklists, planner and profiles compile and pass deterministic smoke.",
                    "Operator can move from daily queue to profile without missing core object context.",
                ],
                "manual_checks": [
                    {"id": "CAS-01", "actor": "Herd Manager", "area": "Daily operations", "step": "Open Home -> Worklists -> Animal Profile", "expected": "Переход к объекту и next-step actions доступны без ручного поиска."},
                    {"id": "CAS-02", "actor": "Operator", "area": "Daily operations", "step": "Отработать 3 объекта из daily queue", "expected": "Статусы, linked facts и actions читаемы и воспроизводимы."},
                ],
            },
            "reproduction": {
                "enabled": True,
                "title": "Reproduction parity",
                "budget_sec": 30.0,
                "pytest": [
                    "tests/test_t22_02_repro_worklists.py",
                    "tests/test_t22_03_reproduction_cockpit.py",
                    "tests/test_t22_05_repro_mating_integration.py",
                ],
                "required_files": [
                    "docs/repro_worklists.md",
                    "docs/reproduction_cockpit.md",
                    "docs/repro_mating_integration.md",
                ],
                "pass_fail_criteria": [
                    "Repro worklists and cockpit must pass deterministic regression set.",
                    "Mating integration must remain explainable and linked to operational flow.",
                ],
                "manual_checks": [
                    {"id": "CAS-03", "actor": "Reproduction Specialist", "area": "Reproduction", "step": "Открыть reproduction cockpit и список задач", "expected": "Проблемные животные и next actions видны без ручной реконструкции."},
                ],
            },
            "vet": {
                "enabled": True,
                "title": "Vet operations parity",
                "budget_sec": 25.0,
                "pytest": [
                    "tests/test_t23_01_vet_protocol_engine.py",
                    "tests/test_t23_03_vet_triage_queues.py",
                ],
                "required_files": [
                    "docs/vet_protocol_engine.md",
                    "docs/vet_triage_queues.md",
                ],
                "pass_fail_criteria": [
                    "Protocol engine and triage queues must stay green under regression tests.",
                    "No diagnosis automation: only explainable risk and workflow guidance.",
                ],
                "manual_checks": [
                    {"id": "CAS-04", "actor": "Veterinarian", "area": "Vet", "step": "Открыть triage queue и протокол", "expected": "Queue, protocol and follow-up path сохраняют linkage и traceability."},
                ],
            },
            "reports_worklists": {
                "enabled": True,
                "title": "Reports and worklists parity",
                "budget_sec": 35.0,
                "pytest": [
                    "tests/test_t24_02_operational_report_builder.py",
                    "tests/test_t24_04_trend_reports_compare_periods.py",
                    "tests/test_t24_05_report_to_action_bridge.py",
                ],
                "scripts": [
                    "scripts/smoke_t32_06_react_profiles_reports_assistant.sh",
                    "scripts/smoke_t24_05_report_to_action_bridge.py",
                ],
                "required_files": [
                    "docs/operational_report_builder.md",
                    "docs/trend_reports_compare_periods.md",
                    "docs/report_to_action_bridge.md",
                ],
                "pass_fail_criteria": [
                    "Report surfaces must preserve drilldown and action bridge.",
                    "A generated report must remain version-linked and exportable.",
                ],
                "manual_checks": [
                    {"id": "CAS-05", "actor": "Director", "area": "Reports", "step": "Открыть report -> перейти в action surface", "expected": "Переход в worklists/planner доступен из отчёта без потери контекста."},
                ],
            },
            "mobile": {
                "enabled": True,
                "title": "Mobile and cowside parity",
                "budget_sec": 25.0,
                "artifact_checks": ["operational_rollout"],
                "pytest": [
                    "tests/test_t32_08_android_field_app_foundation.py",
                    "tests/test_t32_08a_android_offline_sync_contract.py",
                    "tests/test_t32_09_android_offline_sync_model.py",
                ],
                "scripts": [
                    "scripts/smoke_t32_08_android_field_app.sh",
                    "scripts/smoke_t32_08a_android_offline_sync_contract.sh",
                    "scripts/smoke_t32_09_android_offline_sync_model.sh",
                ],
                "required_files": [
                    "docs/mobile_shell_pwa_foundation.md",
                    "docs/mobile_worklists.md",
                    "docs/android_offline_sync_contract.md",
                ],
                "pass_fail_criteria": [
                    "Mobile shell, worklists and cowside entry must pass stable smoke without browser-heavy automation.",
                    "Offline/mobile conflict audit path must remain reproducible.",
                ],
                "manual_checks": [
                    {"id": "CAS-06", "actor": "Field Operator", "area": "Mobile", "step": "Открыть mobile worklists и cowside entry", "expected": "Daily-use mobile flow выполним за bounded число действий."},
                ],
            },
            "migration": {
                "enabled": True,
                "title": "Migration and replacement readiness",
                "budget_sec": 35.0,
                "pytest": [
                    "tests/test_t26_02_migration_verification_toolkit.py",
                    "tests/test_t26_05_migration_playbook_and_cutover.py",
                ],
                "scripts": [
                    "scripts/smoke_t26_02_migration_verification_toolkit.py",
                    "scripts/smoke_t26_05_migration_playbook_and_cutover.py",
                ],
                "required_files": [
                    "docs/migration_verification_toolkit.md",
                    "docs/migration_playbook_and_cutover.md",
                ],
                "pass_fail_criteria": [
                    "Migration toolkit must produce versioned compare evidence.",
                    "Cutover preview must remain bounded and rollback-ready, not ad hoc.",
                ],
                "manual_checks": [
                    {"id": "CAS-07", "actor": "Project Manager", "area": "Migration", "step": "Просмотреть verification + playbook evidence", "expected": "Команда видит formal pass/fail gaps для замены legacy HMS."},
                ],
            },
        }
    },
}


class CompetitiveAcceptanceError(ValueError):
    """Human-readable competitive acceptance configuration/runtime error."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise CompetitiveAcceptanceError(f"{path}: ожидался YAML-объект верхнего уровня")
    return raw


def load_competitive_acceptance_policy(
    *,
    project_root: str | Path = '.',
    config_path: str | Path | None = None,
    profile: str = 'legacy_replacement_ci',
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    path = Path(config_path).resolve() if config_path is not None else (project_root_path / 'configs' / 'ops' / 'competitive_acceptance_set_v1.yaml').resolve()
    raw = _load_yaml_dict(path)
    cfg = _deep_merge(json.loads(json.dumps(_DEFAULT_COMPETITIVE_ACCEPTANCE_POLICY)), raw)
    try:
        cfg['version'] = int(cfg.get('version', 1))
    except Exception as exc:
        raise CompetitiveAcceptanceError(f"{path}: version должен быть целым числом") from exc

    profiles = cfg.get('profiles') or {}
    if not isinstance(profiles, dict) or not profiles:
        raise CompetitiveAcceptanceError(f"{path}: profiles должен быть непустым объектом")
    profile_name = str(profile or 'legacy_replacement_ci').strip() or 'legacy_replacement_ci'
    if profile_name not in profiles:
        raise CompetitiveAcceptanceError(f"{path}: profile '{profile_name}' не найден")
    profile_cfg = profiles[profile_name]
    if not isinstance(profile_cfg, dict) or not profile_cfg:
        raise CompetitiveAcceptanceError(f"{path}: profiles.{profile_name} должен быть непустым объектом")

    aliases = cfg.get('artifact_aliases') or {}
    if not isinstance(aliases, dict):
        raise CompetitiveAcceptanceError(f"{path}: artifact_aliases должен быть объектом")

    norm_profile: dict[str, Any] = {}
    for scenario_name, scenario_cfg in profile_cfg.items():
        if not isinstance(scenario_cfg, dict):
            raise CompetitiveAcceptanceError(f"{path}: profiles.{profile_name}.{scenario_name} должен быть объектом")
        item = dict(scenario_cfg)
        item['enabled'] = bool(item.get('enabled', True))
        item['title'] = str(item.get('title') or scenario_name.replace('_', ' ').title())
        try:
            item['budget_sec'] = float(item.get('budget_sec', 0.0))
        except Exception as exc:
            raise CompetitiveAcceptanceError(f"{path}: profiles.{profile_name}.{scenario_name}.budget_sec должен быть числом") from exc
        if item['budget_sec'] <= 0:
            raise CompetitiveAcceptanceError(f"{path}: profiles.{profile_name}.{scenario_name}.budget_sec должен быть > 0")
        for list_key in ['artifact_checks', 'pytest', 'scripts', 'required_files', 'pass_fail_criteria', 'manual_checks']:
            raw_list = item.get(list_key) or []
            if not isinstance(raw_list, list):
                raise CompetitiveAcceptanceError(f"{path}: profiles.{profile_name}.{scenario_name}.{list_key} должен быть списком")
            item[list_key] = raw_list
        for alias in item['artifact_checks']:
            if str(alias) not in aliases:
                raise CompetitiveAcceptanceError(f"{path}: profiles.{profile_name}.{scenario_name}.artifact_checks -> неизвестный alias '{alias}'")
        norm_profile[str(scenario_name)] = item

    cfg['profile_name'] = profile_name
    cfg['profile'] = norm_profile
    cfg['path'] = str(path)
    cfg['project_root'] = str(project_root_path)
    return cfg


def _run_pytest_bundle(*, project_root: Path, tests: list[str]) -> dict[str, Any]:
    if not tests:
        return {'ok': True, 'duration_sec': 0.0, 'diagnostics': [], 'checks': []}
    started = perf_counter()
    cmd = [sys.executable, '-m', 'pytest', '-q', *tests]
    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True)
    duration = perf_counter() - started
    diagnostics: list[str] = []
    if proc.returncode != 0:
        tail = '\n'.join((proc.stdout or '').splitlines()[-10:] + (proc.stderr or '').splitlines()[-10:]).strip()
        diagnostics.append(f"pytest bundle failed ({proc.returncode})")
        if tail:
            diagnostics.append(tail)
    return {
        'ok': proc.returncode == 0,
        'duration_sec': duration,
        'diagnostics': diagnostics,
        'checks': [{'kind': 'pytest', 'target': t, 'ok': proc.returncode == 0} for t in tests],
        'stdout_tail': (proc.stdout or '').splitlines()[-10:],
        'stderr_tail': (proc.stderr or '').splitlines()[-10:],
    }


def _run_script_bundle(*, project_root: Path, scripts: list[str]) -> dict[str, Any]:
    started = perf_counter()
    diagnostics: list[str] = []
    checks: list[dict[str, Any]] = []
    overall_ok = True
    for rel in scripts:
        script_path = project_root / rel
        if not script_path.exists():
            diagnostics.append(f"missing script: {rel}")
            checks.append({'kind': 'script', 'target': rel, 'ok': False})
            overall_ok = False
            continue
        proc = subprocess.run([sys.executable, str(script_path)], cwd=str(project_root), capture_output=True, text=True)
        ok = proc.returncode == 0
        checks.append({'kind': 'script', 'target': rel, 'ok': ok})
        if not ok:
            overall_ok = False
            tail = '\n'.join((proc.stdout or '').splitlines()[-8:] + (proc.stderr or '').splitlines()[-8:]).strip()
            diagnostics.append(f"script failed: {rel}")
            if tail:
                diagnostics.append(tail)
    return {
        'ok': overall_ok,
        'duration_sec': perf_counter() - started,
        'diagnostics': diagnostics,
        'checks': checks,
    }


def _evaluate_required_files(*, project_root: Path, required_files: list[str]) -> dict[str, Any]:
    diagnostics: list[str] = []
    checks: list[dict[str, Any]] = []
    for rel in required_files:
        ok = (project_root / rel).exists()
        checks.append({'kind': 'required_file', 'target': rel, 'ok': ok})
        if not ok:
            diagnostics.append(f"missing required file: {rel}")
    return {'ok': not diagnostics, 'duration_sec': 0.0, 'diagnostics': diagnostics, 'checks': checks}


def _load_artifact_report(*, project_root: Path, artifacts_root: Path, relative_path: str) -> dict[str, Any]:
    path = (project_root / relative_path) if not Path(relative_path).is_absolute() else Path(relative_path)
    if not path.exists():
        alt = artifacts_root / relative_path.replace('artifacts/', '', 1)
        path = alt
    if not path.exists():
        return {'ok': False, 'path': str(path), 'diagnostics': [f'missing artifact report: {relative_path}']}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        return {'ok': False, 'path': str(path), 'diagnostics': [f'invalid json report: {relative_path}: {exc}']}
    summary = payload.get('summary') or {}
    ok = bool(summary.get('ok', False))
    diagnostics = [str(x) for x in (summary.get('diagnostics') or [])]
    return {'ok': ok, 'path': str(path), 'payload': payload, 'diagnostics': diagnostics}


def _evaluate_artifact_checks(*, project_root: Path, artifacts_root: Path, aliases: dict[str, str], names: list[str]) -> dict[str, Any]:
    diagnostics: list[str] = []
    checks: list[dict[str, Any]] = []
    overall_ok = True
    for alias in names:
        rel = aliases[str(alias)]
        report = _load_artifact_report(project_root=project_root, artifacts_root=artifacts_root, relative_path=rel)
        checks.append({'kind': 'artifact_report', 'target': alias, 'path': report.get('path'), 'ok': bool(report.get('ok'))})
        if not report.get('ok'):
            overall_ok = False
            diagnostics.extend([f"{alias}: {item}" for item in report.get('diagnostics') or []] or [f"{alias}: report not ready"])
    return {'ok': overall_ok, 'duration_sec': 0.0, 'diagnostics': diagnostics, 'checks': checks}


def _load_manual_signoff(*, project_root: Path, path_value: str) -> dict[str, Any]:
    path = (project_root / path_value).resolve() if not Path(path_value).is_absolute() else Path(path_value)
    if not path.exists():
        return {'present': False, 'path': str(path), 'payload': {}, 'diagnostics': []}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        return {'present': True, 'path': str(path), 'payload': {}, 'diagnostics': [f'invalid manual signoff json: {exc}']}
    if not isinstance(payload, dict):
        return {'present': True, 'path': str(path), 'payload': {}, 'diagnostics': ['manual signoff must be JSON object']}
    return {'present': True, 'path': str(path), 'payload': payload, 'diagnostics': []}


def _scenario_manual_status(*, signoff_payload: dict[str, Any], scenario_name: str, automated_ok: bool) -> dict[str, Any]:
    scenarios = signoff_payload.get('scenarios') or {}
    item = scenarios.get(scenario_name) or {}
    signed = bool(item.get('signed_off', False))
    if automated_ok and signed:
        status = 'product_ready'
    elif automated_ok:
        status = 'ready_for_manual_signoff'
    else:
        status = 'not_ready'
    return {
        'signed_off': signed,
        'status': status,
        'signoff_by': item.get('signoff_by'),
        'signoff_at': item.get('signoff_at'),
        'notes': item.get('notes'),
    }


def _evaluate_budget(*, name: str, duration_sec: float, budget_sec: float) -> dict[str, Any]:
    problems: list[str] = []
    if duration_sec > budget_sec:
        problems.append(f"{name}: total {duration_sec:.3f}s > budget {budget_sec:.3f}s")
    return {'budget_sec': float(budget_sec), 'ok': not problems, 'problems': problems}


def render_competitive_acceptance_markdown(report: dict[str, Any]) -> str:
    lines = [
        '# Competitive acceptance set',
        '',
        f"- created_at_utc: {report.get('created_at_utc')}",
        f"- profile: {report.get('profile')}",
        f"- ready_for_competitive_uat: {str(bool((report.get('summary') or {}).get('ready_for_competitive_uat'))).lower()}",
        f"- product_ready_count: {int((report.get('summary') or {}).get('product_ready_count', 0))}",
        '',
        '| scenario | automated_ok | manual_status | overall_status | duration_sec |',
        '|---|---|---|---|---:|',
    ]
    for row in report.get('scenarios') or []:
        lines.append(
            f"| {row.get('scenario')} | {'yes' if row.get('automated_ok') else 'no'} | {row.get('manual', {}).get('status')} | {row.get('overall_status')} | {float(row.get('duration_sec') or 0.0):.3f} |"
        )
    lines.extend(['', '## Manual checklist'])
    for row in report.get('scenarios') or []:
        lines.extend(['', f"### {row.get('title')}"])
        for check in row.get('manual_checks') or []:
            lines.append(
                f"- {check.get('id')} | {check.get('actor')} | {check.get('area')} | {check.get('step')} | expected: {check.get('expected')}"
            )
    return '\n'.join(lines) + '\n'


def _write_report(report: dict[str, Any], *, report_root: Path) -> dict[str, str]:
    report_root.mkdir(parents=True, exist_ok=True)
    json_path = report_root / 'competitive_acceptance_report.json'
    md_path = report_root / 'competitive_acceptance_report.md'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    md_path.write_text(render_competitive_acceptance_markdown(report), encoding='utf-8')
    return {'json': str(json_path), 'md': str(md_path)}


def run_competitive_acceptance_set(
    *,
    project_root: str | Path = '.',
    artifacts_root: str | Path = 'artifacts',
    profile: str = 'legacy_replacement_ci',
    config_path: str | Path | None = None,
    report_root: str | Path | None = None,
    scenarios: list[str] | None = None,
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    artifacts_root_path = Path(artifacts_root).resolve()
    policy = load_competitive_acceptance_policy(project_root=project_root_path, config_path=config_path, profile=profile)
    aliases = policy.get('artifact_aliases') or {}
    requested = set(str(x) for x in (scenarios or []))
    signoff = _load_manual_signoff(project_root=project_root_path, path_value=str(((policy.get('manual_signoff') or {}).get('path') or 'artifacts/_qa/competitive_acceptance/manual_signoff.json')))

    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for name, cfg in (policy.get('profile') or {}).items():
        if not cfg.get('enabled', True):
            continue
        if requested and name not in requested:
            continue
        started = perf_counter()
        artifact_eval = _evaluate_artifact_checks(project_root=project_root_path, artifacts_root=artifacts_root_path, aliases=aliases, names=[str(x) for x in cfg.get('artifact_checks') or []])
        pytest_eval = _run_pytest_bundle(project_root=project_root_path, tests=[str(x) for x in cfg.get('pytest') or []])
        script_eval = _run_script_bundle(project_root=project_root_path, scripts=[str(x) for x in cfg.get('scripts') or []])
        files_eval = _evaluate_required_files(project_root=project_root_path, required_files=[str(x) for x in cfg.get('required_files') or []])
        duration_sec = perf_counter() - started
        automated_ok = all([
            artifact_eval.get('ok', True),
            pytest_eval.get('ok', True),
            script_eval.get('ok', True),
            files_eval.get('ok', True),
        ])
        manual = _scenario_manual_status(signoff_payload=signoff.get('payload') or {}, scenario_name=name, automated_ok=automated_ok)
        budget = _evaluate_budget(name=name, duration_sec=duration_sec, budget_sec=float(cfg.get('budget_sec') or 0.0))
        scenario_diag = []
        scenario_diag.extend(artifact_eval.get('diagnostics') or [])
        scenario_diag.extend(pytest_eval.get('diagnostics') or [])
        scenario_diag.extend(script_eval.get('diagnostics') or [])
        scenario_diag.extend(files_eval.get('diagnostics') or [])
        scenario_diag.extend(budget.get('problems') or [])
        overall_status = manual['status'] if budget.get('ok', True) else 'not_ready'
        row = {
            'scenario': name,
            'title': cfg.get('title'),
            'automated_ok': automated_ok and bool(budget.get('ok', True)),
            'manual': manual,
            'overall_status': overall_status,
            'duration_sec': duration_sec,
            'budget': budget,
            'pass_fail_criteria': [str(x) for x in cfg.get('pass_fail_criteria') or []],
            'manual_checks': cfg.get('manual_checks') or [],
            'details': {
                'artifact_checks': artifact_eval,
                'pytest': pytest_eval,
                'scripts': script_eval,
                'required_files': files_eval,
            },
            'diagnostics': scenario_diag,
        }
        rows.append(row)
        diagnostics.extend([f"{name}: {item}" for item in scenario_diag])

    summary = {
        'ok': not diagnostics,
        'scenario_count': len(rows),
        'failed_scenarios': [r['scenario'] for r in rows if not r['automated_ok']],
        'ready_for_competitive_uat': all(r['overall_status'] in {'ready_for_manual_signoff', 'product_ready'} for r in rows) if rows else False,
        'product_ready_count': sum(1 for r in rows if r['overall_status'] == 'product_ready'),
        'diagnostics': diagnostics,
    }
    report = {
        'schema': 'genomeai.competitive_acceptance_report.v1',
        'created_at_utc': _utc_now_iso(),
        'profile': policy.get('profile_name'),
        'policy_path': policy.get('path'),
        'manual_signoff': signoff,
        'scenarios': rows,
        'summary': summary,
    }
    outputs = _write_report(report, report_root=Path(report_root).resolve() if report_root else (artifacts_root_path / '_ci' / 'competitive_acceptance'))
    report['outputs'] = outputs
    return report


def render_competitive_acceptance_cli_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"COMPETITIVE_ACCEPTANCE_PROFILE={report.get('profile')}",
        f"COMPETITIVE_ACCEPTANCE_OK={str(bool((report.get('summary') or {}).get('ok'))).lower()}",
        f"COMPETITIVE_ACCEPTANCE_READY_FOR_UAT={str(bool((report.get('summary') or {}).get('ready_for_competitive_uat'))).lower()}",
    ]
    for row in report.get('scenarios') or []:
        lines.append(
            f"SCENARIO {row.get('scenario')}: automated_ok={str(bool(row.get('automated_ok'))).lower()} manual_status={row.get('manual',{}).get('status')} overall={row.get('overall_status')}"
        )
    outputs = report.get('outputs') or {}
    if outputs.get('json'):
        lines.append(f"competitive_acceptance_json={outputs['json']}")
    if outputs.get('md'):
        lines.append(f"competitive_acceptance_md={outputs['md']}")
    lines.append('COMPETITIVE_ACCEPTANCE_SET_READY' if bool((report.get('summary') or {}).get('ready_for_competitive_uat')) else 'COMPETITIVE_ACCEPTANCE_SET_FAILED')
    return lines
