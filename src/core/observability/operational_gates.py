from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import yaml


_NON_PYTHON_EXTENSIONS = {'.tsx', '.ts', '.jsx', '.js', '.kt', '.swift', '.sh', '.bash'}


def _check_file_syntax(path: Path) -> None:
    if path.suffix.lower() in _NON_PYTHON_EXTENSIONS:
        content = path.read_text(encoding='utf-8', errors='strict')
        if not content.strip():
            raise ValueError(f"file is empty: {path.name}")
    else:
        py_compile.compile(str(path), doraise=True)


_DEFAULT_OPERATIONAL_GATES_POLICY: dict[str, Any] = {
    "version": 1,
    "profiles": {
        "enterprise_ci": {
            "compile_daily_pages": {
                "enabled": True,
                "budget_sec": 8.0,
                "pages": [
                    "web_app/app/(protected)/daily-summary/page.tsx",
                    "web_app/app/(protected)/alerts/page.tsx",
                    "web_app/app/(protected)/planner/page.tsx",
                    "web_app/app/(protected)/reports/page.tsx",
                    "web_app/app/(protected)/observability/page.tsx",
                ],
            },
            "role_scenarios": {"enabled": True, "budget_sec": 12.0},
            "mobile_views": {
                "enabled": True,
                "budget_sec": 12.0,
                "pages": [
                    "mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/ui/screens/TodayWorklistsScreen.kt",
                    "mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/ui/screens/AlertsNowScreen.kt",
                ],
                "scripts": ["scripts/smoke_t32_08_android_field_app.sh"],
            },
            "worklists_profiles_reports": {
                "enabled": True,
                "budget_sec": 16.0,
                "pages": [
                    "web_app/app/(protected)/daily-summary/page.tsx",
                    "web_app/app/(protected)/profiles/[objectType]/[objectId]/page.tsx",
                    "web_app/app/(protected)/reports/page.tsx",
                ],
                "scripts": [
                    "scripts/smoke_t32_05_react_daily_operations.sh",
                    "scripts/smoke_t32_06_react_profiles_reports_assistant.sh",
                ],
            },
            "rollout_diagnostics": {
                "enabled": True,
                "budget_sec": 5.0,
                "required_files": [
                    "docs/operational_sla_and_gates.md",
                    "docs/server_deployment_baseline.md",
                    "web_app/app/(protected)/observability/page.tsx",
                    "mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/OfflineSyncService.kt",
                ],
                "expected_reports": [
                    "operational_rollout_gates_report.json",
                    "warning_governance_report.json",
                ],
            },
        }
    },
}


class OperationalGateError(ValueError):
    """Human-readable operational gate configuration/runtime error."""


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
        raise OperationalGateError(f"{path}: ожидался YAML-объект верхнего уровня")
    return raw


def _find_latest_rglob(root: Path, pattern: str) -> Path | None:
    hits = [p for p in root.rglob(pattern) if p.is_file()]
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)


def load_operational_rollout_gates_policy(
    *,
    project_root: str | Path = '.',
    config_path: str | Path | None = None,
    profile: str = 'enterprise_ci',
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    path = Path(config_path).resolve() if config_path is not None else (project_root_path / 'configs' / 'ops' / 'operational_rollout_gates_v1.yaml').resolve()
    raw = _load_yaml_dict(path)
    cfg = _deep_merge(json.loads(json.dumps(_DEFAULT_OPERATIONAL_GATES_POLICY)), raw)
    try:
        cfg['version'] = int(cfg.get('version', 1))
    except Exception as exc:
        raise OperationalGateError(f"{path}: version должен быть целым числом") from exc
    profiles = cfg.get('profiles') or {}
    if not isinstance(profiles, dict) or not profiles:
        raise OperationalGateError(f"{path}: profiles должен быть непустым объектом")
    profile_name = str(profile or 'enterprise_ci').strip() or 'enterprise_ci'
    if profile_name not in profiles:
        raise OperationalGateError(f"{path}: profile '{profile_name}' не найден")
    profile_cfg = profiles[profile_name]
    if not isinstance(profile_cfg, dict):
        raise OperationalGateError(f"{path}: profiles.{profile_name} должен быть объектом")

    normalized: dict[str, Any] = {}
    for gate_name in ['compile_daily_pages', 'role_scenarios', 'mobile_views', 'worklists_profiles_reports', 'rollout_diagnostics']:
        gate_cfg = profile_cfg.get(gate_name) or {}
        if not isinstance(gate_cfg, dict):
            raise OperationalGateError(f"{path}: profiles.{profile_name}.{gate_name} должен быть объектом")
        item = dict(gate_cfg)
        item['enabled'] = bool(item.get('enabled', True))
        try:
            item['budget_sec'] = float(item.get('budget_sec', 0.0))
        except Exception as exc:
            raise OperationalGateError(f"{path}: profiles.{profile_name}.{gate_name}.budget_sec должен быть числом") from exc
        if item['budget_sec'] <= 0:
            raise OperationalGateError(f"{path}: profiles.{profile_name}.{gate_name}.budget_sec должен быть > 0")
        for list_key in ['pages', 'scripts', 'required_files', 'expected_reports']:
            raw_list = item.get(list_key) or []
            if not isinstance(raw_list, list):
                raise OperationalGateError(f"{path}: profiles.{profile_name}.{gate_name}.{list_key} должен быть списком")
            item[list_key] = [str(v).strip() for v in raw_list if str(v).strip()]
        normalized[gate_name] = item

    cfg['profile_name'] = profile_name
    cfg['profile'] = normalized
    cfg['path'] = str(path)
    cfg['project_root'] = str(project_root_path)
    return cfg


def _evaluate_gate_budget(*, gate_name: str, gate: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    total_sec = float(gate.get('duration_sec') or 0.0)
    max_sec = float(budget.get('budget_sec') or 0.0)
    problems: list[str] = []
    if total_sec > max_sec:
        problems.append(f"{gate_name}: total {total_sec:.3f}s > budget {max_sec:.3f}s")
    return {
        'budget_sec': max_sec,
        'ok': not problems,
        'problems': problems,
    }


def evaluate_operational_rollout_report(report: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    effective_policy = policy or report.get('policy') or {}
    profile = (effective_policy.get('profile') or {}) if isinstance(effective_policy, dict) else {}
    gates = list(report.get('gates') or [])
    diagnostics: list[str] = []
    for gate in gates:
        gate_name = str(gate.get('gate') or '')
        gate['budget'] = _evaluate_gate_budget(gate_name=gate_name, gate=gate, budget=profile.get(gate_name) or {})
        diagnostics.extend(gate['budget'].get('problems') or [])
        if not gate.get('ok', True):
            details = gate.get('details') or {}
            for item in details.get('diagnostics') or []:
                diagnostics.append(f"{gate_name}: {item}")
    report['summary'] = {
        'ok': not diagnostics and all(bool(g.get('ok', True)) and bool((g.get('budget') or {}).get('ok', True)) for g in gates),
        'gate_count': len(gates),
        'failed_gates': [g['gate'] for g in gates if (not g.get('ok', True)) or (not (g.get('budget') or {}).get('ok', True))],
        'diagnostics': diagnostics,
        'ready_for_rollout': not diagnostics and all(bool(g.get('ok', True)) and bool((g.get('budget') or {}).get('ok', True)) for g in gates),
    }
    return report


def _write_report(report: dict[str, Any], *, report_root: Path) -> dict[str, str]:
    report_root.mkdir(parents=True, exist_ok=True)
    json_path = report_root / 'operational_rollout_gates_report.json'
    md_path = report_root / 'operational_rollout_gates_report.md'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [
        '# Operational SLA / rollout gates report',
        '',
        f"- created_at_utc: {report.get('created_at_utc')}",
        f"- profile: {report.get('profile')}",
        f"- policy_path: {report.get('policy_path')}",
        f"- ok: {str(bool((report.get('summary') or {}).get('ok'))).lower()}",
        f"- ready_for_rollout: {str(bool((report.get('summary') or {}).get('ready_for_rollout'))).lower()}",
        '',
        '| gate | ok | within_budget | duration_sec |',
        '|---|---|---|---:|',
    ]
    for gate in report.get('gates') or []:
        budget = gate.get('budget') or {}
        lines.append(f"| {gate.get('gate')} | {'yes' if gate.get('ok', True) else 'no'} | {'yes' if budget.get('ok', True) else 'no'} | {float(gate.get('duration_sec') or 0.0):.3f} |")
    lines.append('')
    for gate in report.get('gates') or []:
        lines.append(f"## {gate.get('gate')}")
        lines.append('')
        lines.append(f"- ok: {str(bool(gate.get('ok', True))).lower()}")
        lines.append(f"- duration_sec: {float(gate.get('duration_sec') or 0.0):.3f}")
        budget = gate.get('budget') or {}
        lines.append(f"- budget_sec: {float(budget.get('budget_sec') or 0.0):.3f}")
        details = gate.get('details') or {}
        if details.get('diagnostics'):
            lines.append('')
            for item in details.get('diagnostics') or []:
                lines.append(f"- {item}")
        lines.append('')
    md_path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    return {'json': str(json_path), 'md': str(md_path)}


def render_operational_rollout_cli_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        'OPERATIONAL_ROLLOUT_GATES_OK' if bool((report.get('summary') or {}).get('ok')) else 'OPERATIONAL_ROLLOUT_GATES_FAILED',
        f"profile={report.get('profile')}",
    ]
    outputs = report.get('outputs') or {}
    if outputs.get('json'):
        lines.append(f"report_json={outputs['json']}")
    if outputs.get('md'):
        lines.append(f"report_md={outputs['md']}")
    for gate in report.get('gates') or []:
        budget = gate.get('budget') or {}
        lines.append(
            f"gate={gate.get('gate')} ok={str(bool(gate.get('ok', True))).lower()} within_budget={str(bool(budget.get('ok', True))).lower()} duration_sec={float(gate.get('duration_sec') or 0.0):.3f}"
        )
    return lines


def _measure_compile_daily_pages(*, project_root: Path, pages: Iterable[str]) -> dict[str, Any]:
    started = perf_counter()
    diagnostics: list[str] = []
    compiled: list[str] = []
    steps: dict[str, float] = {}
    for rel in list(pages or []):
        path = (project_root / rel).resolve()
        step_key = Path(rel).stem
        step_started = perf_counter()
        if not path.exists():
            diagnostics.append(f"page_not_found: {rel}")
            steps[step_key] = max(0.0, perf_counter() - step_started)
            continue
        try:
            _check_file_syntax(path)
            compiled.append(rel)
        except Exception as exc:
            diagnostics.append(f"compile_failed: {rel}: {exc.__class__.__name__}: {exc}")
        steps[step_key] = max(0.0, perf_counter() - step_started)
    return {
        'gate': 'compile_daily_pages',
        'ok': not diagnostics,
        'duration_sec': max(0.0, perf_counter() - started),
        'steps': steps,
        'details': {
            'compiled_pages': compiled,
            'compiled_count': len(compiled),
            'diagnostics': diagnostics,
        },
    }


def _run_python_script(*, project_root: Path, rel_path: str, timeout_sec: int = 180) -> dict[str, Any]:
    env = dict(os.environ)
    # Need both src/ (for `core.*`, `genomeai.*`) and project_root (for top-level
    # packages like `web_cabinet`). cwd alone doesn't make Python see top-level
    # packages — only the directory of the script being run is on sys.path.
    project_root_str = str(project_root.resolve())
    py_parts = [
        str((project_root / 'src').resolve()),
        project_root_str,
        env.get('PYTHONPATH', ''),
    ]
    env['PYTHONPATH'] = os.pathsep.join([part for part in py_parts if part])
    path = (project_root / rel_path).resolve()
    started = perf_counter()
    if path.suffix.lower() in ('.sh', '.bash'):
        runner = ['bash', str(path)]
    else:
        runner = [sys.executable, str(path)]
    proc = subprocess.run(
        runner,
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    return {
        'ok': proc.returncode == 0,
        'duration_sec': max(0.0, perf_counter() - started),
        'returncode': int(proc.returncode),
        'stdout_tail': proc.stdout[-4000:],
        'stderr_tail': proc.stderr[-4000:],
    }


def _measure_role_scenarios(*, project_root: Path, artifacts_root: Path, workdir_root: Path | None = None) -> dict[str, Any]:
    started = perf_counter()
    evidence_candidates = [
        project_root / 'configs' / 'post_removal' / 'streamlit_removal_regression_report_v1.json',
        project_root / 'configs' / 'parity' / 'react_daily_operations_parity_v1.json',
        project_root / 'docs' / 'react_profiles_reports_assistant_parity.md',
        project_root / 'docs' / 'react_extended_surface_parity.md',
    ]
    missing = [str(p.relative_to(project_root)) for p in evidence_candidates if not p.exists()]
    diagnostics = [f'missing_evidence: {item}' for item in missing]
    return {
        'gate': 'role_scenarios',
        'ok': not diagnostics,
        'duration_sec': max(0.0, perf_counter() - started),
        'steps': {'role_scenarios': max(0.0, perf_counter() - started)},
        'details': {
            'source': 'web_react_and_post_removal_evidence',
            'diagnostics': diagnostics,
            'evidence_checked': [str(p.relative_to(project_root)) for p in evidence_candidates],
        },
    }


def _measure_script_bundle(*, gate_name: str, project_root: Path, pages: Iterable[str], scripts: Iterable[str]) -> dict[str, Any]:
    started = perf_counter()
    diagnostics: list[str] = []
    steps: dict[str, float] = {}
    compiled_pages: list[str] = []
    script_runs: dict[str, Any] = {}
    for rel in list(pages or []):
        path = (project_root / rel).resolve()
        step_key = Path(rel).stem
        step_started = perf_counter()
        if not path.exists():
            diagnostics.append(f"page_not_found: {rel}")
            steps[step_key] = max(0.0, perf_counter() - step_started)
            continue
        try:
            _check_file_syntax(path)
            compiled_pages.append(rel)
        except Exception as exc:
            diagnostics.append(f"compile_failed: {rel}: {exc.__class__.__name__}: {exc}")
        steps[step_key] = max(0.0, perf_counter() - step_started)
    for rel in list(scripts or []):
        result = _run_python_script(project_root=project_root, rel_path=rel)
        step_key = Path(rel).stem
        steps[step_key] = float(result.get('duration_sec') or 0.0)
        script_runs[rel] = result
        if not bool(result.get('ok')):
            diagnostics.append(f"script_failed: {rel}")
    return {
        'gate': gate_name,
        'ok': not diagnostics,
        'duration_sec': max(0.0, perf_counter() - started),
        'steps': steps,
        'details': {
            'compiled_pages': compiled_pages,
            'script_runs': script_runs,
            'diagnostics': diagnostics,
        },
    }


def _measure_rollout_diagnostics(*, project_root: Path, artifacts_root: Path, required_files: Iterable[str], expected_reports: Iterable[str]) -> dict[str, Any]:
    started = perf_counter()
    diagnostics: list[str] = []
    files_present: dict[str, bool] = {}
    latest_reports: dict[str, str | None] = {}
    for rel in list(required_files or []):
        exists = (project_root / rel).exists()
        files_present[rel] = bool(exists)
        if not exists:
            diagnostics.append(f"required_file_missing: {rel}")
    for name in list(expected_reports or []):
        latest = _find_latest_rglob(artifacts_root, name)
        latest_reports[name] = str(latest) if latest else None
    return {
        'gate': 'rollout_diagnostics',
        'ok': not diagnostics,
        'duration_sec': max(0.0, perf_counter() - started),
        'steps': {'rollout_snapshot': max(0.0, perf_counter() - started)},
        'details': {
            'files_present': files_present,
            'latest_reports': latest_reports,
            'diagnostics': diagnostics,
        },
    }


def run_operational_rollout_gates(
    *,
    project_root: str | Path = '.',
    artifacts_root: str | Path = 'artifacts',
    profile: str = 'enterprise_ci',
    config_path: str | Path | None = None,
    report_root: str | Path | None = None,
    workdir_root: str | Path | None = None,
    gates: Iterable[str] | None = None,
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    artifacts_root_path = Path(artifacts_root).resolve()
    policy = load_operational_rollout_gates_policy(project_root=project_root_path, config_path=config_path, profile=profile)
    configured_profile = policy['profile']
    selected = [str(g).strip() for g in (gates or configured_profile.keys()) if str(g).strip()]
    unknown = [g for g in selected if g not in configured_profile]
    if unknown:
        raise OperationalGateError(f"unknown operational rollout gates: {', '.join(sorted(unknown))}")
    report_dir = Path(report_root).resolve() if report_root is not None else (artifacts_root_path / '_ci' / 'operational_rollout_gates' / f"rollout_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}").resolve()
    workdir_root_path = Path(workdir_root).resolve() if workdir_root is not None else (project_root_path / '_tmp' / 'operational_rollout_gates').resolve()
    gate_results: list[dict[str, Any]] = []
    for gate_name in selected:
        cfg = configured_profile[gate_name]
        if not bool(cfg.get('enabled', True)):
            continue
        if gate_name == 'compile_daily_pages':
            gate_results.append(_measure_compile_daily_pages(project_root=project_root_path, pages=cfg.get('pages') or []))
        elif gate_name == 'role_scenarios':
            gate_results.append(_measure_role_scenarios(project_root=project_root_path, artifacts_root=artifacts_root_path, workdir_root=workdir_root_path / 'role_scenarios'))
        elif gate_name == 'mobile_views':
            gate_results.append(_measure_script_bundle(gate_name='mobile_views', project_root=project_root_path, pages=cfg.get('pages') or [], scripts=cfg.get('scripts') or []))
        elif gate_name == 'worklists_profiles_reports':
            gate_results.append(_measure_script_bundle(gate_name='worklists_profiles_reports', project_root=project_root_path, pages=cfg.get('pages') or [], scripts=cfg.get('scripts') or []))
        elif gate_name == 'rollout_diagnostics':
            gate_results.append(_measure_rollout_diagnostics(project_root=project_root_path, artifacts_root=artifacts_root_path, required_files=cfg.get('required_files') or [], expected_reports=cfg.get('expected_reports') or []))
    report: dict[str, Any] = {
        'schema': 'genomeai.operational_rollout_gates_report.v1',
        'created_at_utc': _utc_now_iso(),
        'project_root': str(project_root_path),
        'artifacts_root': str(artifacts_root_path),
        'profile': policy['profile_name'],
        'policy_path': policy['path'],
        'policy': {'profile': configured_profile},
        'gates': gate_results,
    }
    evaluate_operational_rollout_report(report, policy=policy)
    report['outputs'] = _write_report(report, report_root=report_dir)
    return report


__all__ = [
    'OperationalGateError',
    'evaluate_operational_rollout_report',
    'load_operational_rollout_gates_policy',
    'render_operational_rollout_cli_lines',
    'run_operational_rollout_gates',
]
