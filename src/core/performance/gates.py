from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import yaml

from core.application import VerifyRefactorCommand, execute_verify_refactor


_DEFAULT_PERF_GATES_POLICY: dict[str, Any] = {
    "version": 1,
    "profiles": {
        "ci": {
            "startup": {
                "enabled": True,
                "budget_sec": 12.0,
                "steps": {
                    "import_app": 10.0,
                    "startup": 4.0,
                },
            },
            "pipeline_smoke": {
                "enabled": True,
                "budget_sec": 12.0,
                "steps": {
                    "ingest_total": 4.0,
                    "qc": 3.0,
                    "train": 4.0,
                    "score": 3.0,
                    "report": 4.0,
                    "decision_log": 2.0,
                    "pack": 3.0,
                },
            },
            "web_smoke": {
                "enabled": True,
                "budget_sec": 35.0,
                "steps": {
                    "rbac": 3.0,
                    "ingest_all": 12.0,
                    "qc": 6.0,
                    "train": 6.0,
                    "score": 5.0,
                    "report": 6.0,
                    "decisions": 6.0,
                    "pack": 4.0,
                },
            },
            "verify_refactor": {
                "enabled": True,
                "budget_sec": 20.0,
                "scenarios": ["standard", "qc_issues"],
                "steps": {
                    "standard": 12.0,
                    "qc_issues": 12.0,
                },
            },
        }
    },
}


class PerfGateError(ValueError):
    """Human-readable performance gate configuration/runtime error."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def _patched_environment(updates: dict[str, str | None]):
    old_values = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise PerfGateError(f"{path}: ожидался YAML-объект верхнего уровня")
    return raw


def load_performance_gates_policy(
    *,
    project_root: str | Path = ".",
    config_path: str | Path | None = None,
    profile: str = "ci",
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    path = Path(config_path).resolve() if config_path is not None else (project_root_path / "configs" / "ops" / "performance_gates_v1.yaml").resolve()
    raw = _load_yaml_dict(path)
    cfg = _deep_merge(json.loads(json.dumps(_DEFAULT_PERF_GATES_POLICY)), raw)
    try:
        cfg["version"] = int(cfg.get("version", 1))
    except Exception as exc:
        raise PerfGateError(f"{path}: version должен быть целым числом") from exc

    profiles = cfg.get("profiles") or {}
    if not isinstance(profiles, dict) or not profiles:
        raise PerfGateError(f"{path}: profiles должен быть непустым объектом")
    profile_name = str(profile or "ci").strip() or "ci"
    if profile_name not in profiles:
        raise PerfGateError(f"{path}: profile '{profile_name}' не найден")
    profile_cfg = profiles[profile_name]
    if not isinstance(profile_cfg, dict):
        raise PerfGateError(f"{path}: profiles.{profile_name} должен быть объектом")

    normalized_profile: dict[str, Any] = {}
    for gate_name in ["startup", "pipeline_smoke", "web_smoke", "verify_refactor"]:
        gate_cfg = profile_cfg.get(gate_name) or {}
        if not isinstance(gate_cfg, dict):
            raise PerfGateError(f"{path}: profiles.{profile_name}.{gate_name} должен быть объектом")
        normalized = dict(gate_cfg)
        normalized["enabled"] = bool(normalized.get("enabled", True))
        try:
            normalized["budget_sec"] = float(normalized.get("budget_sec", 0.0))
        except Exception as exc:
            raise PerfGateError(f"{path}: profiles.{profile_name}.{gate_name}.budget_sec должен быть числом") from exc
        if normalized["budget_sec"] <= 0:
            raise PerfGateError(f"{path}: profiles.{profile_name}.{gate_name}.budget_sec должен быть > 0")
        steps = normalized.get("steps") or {}
        if not isinstance(steps, dict):
            raise PerfGateError(f"{path}: profiles.{profile_name}.{gate_name}.steps должен быть объектом")
        normalized_steps: dict[str, float] = {}
        for step_name, budget in steps.items():
            try:
                step_budget = float(budget)
            except Exception as exc:
                raise PerfGateError(
                    f"{path}: profiles.{profile_name}.{gate_name}.steps.{step_name} должен быть числом"
                ) from exc
            if step_budget <= 0:
                raise PerfGateError(
                    f"{path}: profiles.{profile_name}.{gate_name}.steps.{step_name} должен быть > 0"
                )
            normalized_steps[str(step_name)] = step_budget
        normalized["steps"] = normalized_steps
        scenarios = normalized.get("scenarios") or []
        if gate_name == "verify_refactor":
            if not isinstance(scenarios, list) or not scenarios:
                raise PerfGateError(f"{path}: profiles.{profile_name}.verify_refactor.scenarios должен быть непустым списком")
            normalized["scenarios"] = [str(item).strip() for item in scenarios if str(item).strip()]
            if not normalized["scenarios"]:
                raise PerfGateError(f"{path}: profiles.{profile_name}.verify_refactor.scenarios не должен быть пустым")
        normalized_profile[gate_name] = normalized

    cfg["profile_name"] = profile_name
    cfg["profile"] = normalized_profile
    cfg["path"] = str(path)
    cfg["project_root"] = str(project_root_path)
    return cfg


def _measure_step(steps: dict[str, float], name: str, fn) -> Any:
    started = perf_counter()
    result = fn()
    steps[name] = max(0.0, perf_counter() - started)
    return result


def _evaluate_gate_budget(*, gate_name: str, gate: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    total_sec = float(gate.get("duration_sec") or 0.0)
    max_sec = float(budget.get("budget_sec") or 0.0)
    step_budgets = budget.get("steps") or {}
    steps = gate.get("steps") or {}
    problems: list[str] = []
    if total_sec > max_sec:
        problems.append(
            f"{gate_name}: total {total_sec:.3f}s > budget {max_sec:.3f}s"
        )
    for step_name, step_budget in sorted(step_budgets.items()):
        step_value = steps.get(step_name)
        if step_value is None:
            continue
        step_value_f = float(step_value)
        if step_value_f > float(step_budget):
            problems.append(
                f"{gate_name}.{step_name}: {step_value_f:.3f}s > budget {float(step_budget):.3f}s"
            )
    return {
        "budget_sec": max_sec,
        "step_budgets": step_budgets,
        "ok": not problems,
        "problems": problems,
    }


def evaluate_perf_report(report: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    effective_policy = policy or report.get("policy") or {}
    profile = (effective_policy.get("profile") or {}) if isinstance(effective_policy, dict) else {}
    gates = list(report.get("gates") or [])
    diagnostics: list[str] = []
    for gate in gates:
        gate_name = str(gate.get("gate") or "")
        budget = profile.get(gate_name) or {}
        gate["budget"] = _evaluate_gate_budget(gate_name=gate_name, gate=gate, budget=budget)
        diagnostics.extend(gate["budget"].get("problems") or [])
    report["summary"] = {
        "ok": not diagnostics and all(bool(g.get("ok", True)) for g in gates),
        "gate_count": len(gates),
        "failed_gates": [g["gate"] for g in gates if not g.get("budget", {}).get("ok", True) or not g.get("ok", True)],
        "diagnostics": diagnostics,
    }
    return report


def _write_report(report: dict[str, Any], *, report_root: Path) -> dict[str, str]:
    report_root.mkdir(parents=True, exist_ok=True)
    json_path = report_root / "performance_gates_report.json"
    md_path = report_root / "performance_gates_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Performance gates report",
        "",
        f"- created_at_utc: {report.get('created_at_utc')}",
        f"- profile: {report.get('profile')}",
        f"- policy_path: {report.get('policy_path')}",
        f"- ok: {str(bool((report.get('summary') or {}).get('ok'))).lower()}",
        "",
    ]
    for gate in report.get("gates") or []:
        lines.append(f"## {gate.get('gate')}")
        lines.append("")
        lines.append(f"- ok: {str(bool(gate.get('ok', True))).lower()}")
        lines.append(f"- duration_sec: {float(gate.get('duration_sec') or 0.0):.3f}")
        budget = gate.get("budget") or {}
        lines.append(f"- budget_sec: {float(budget.get('budget_sec') or 0.0):.3f}")
        lines.append(f"- within_budget: {str(bool(budget.get('ok', True))).lower()}")
        steps = gate.get("steps") or {}
        if steps:
            lines.append("")
            lines.append("| step | duration_sec | budget_sec |")
            lines.append("|---|---:|---:|")
            step_budgets = budget.get("step_budgets") or {}
            for step_name, step_value in sorted(steps.items()):
                lines.append(f"| {step_name} | {float(step_value):.3f} | {float(step_budgets.get(step_name, 0.0)):.3f} |")
        diagnostics = (gate.get("budget") or {}).get("problems") or []
        if diagnostics:
            lines.append("")
            for item in diagnostics:
                lines.append(f"- {item}")
        lines.append("")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def render_performance_gate_cli_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        "PERF_GATES_OK" if bool((report.get("summary") or {}).get("ok")) else "PERF_GATES_FAILED",
        f"profile={report.get('profile')}",
    ]
    outputs = report.get("outputs") or {}
    if outputs.get("json"):
        lines.append(f"report_json={outputs['json']}")
    if outputs.get("md"):
        lines.append(f"report_md={outputs['md']}")
    for gate in report.get("gates") or []:
        budget = gate.get("budget") or {}
        lines.append(
            f"gate={gate.get('gate')} ok={str(bool(gate.get('ok', True))).lower()} within_budget={str(bool(budget.get('ok', True))).lower()} duration_sec={float(gate.get('duration_sec') or 0.0):.3f}"
        )
    return lines


def _measure_app_startup(*, project_root: Path) -> dict[str, Any]:
    steps: dict[str, float] = {}
    with tempfile.TemporaryDirectory(prefix="genomeai_perf_startup_") as td:
        workdir = Path(td)
        artifacts_root = workdir / "artifacts"
        web_storage = workdir / "web_storage"
        artifacts_root.mkdir(parents=True, exist_ok=True)
        web_storage.mkdir(parents=True, exist_ok=True)
        updates = {
            "GENOMEAI_PROJECT_ROOT": str(project_root),
            "GENOMEAI_ARTIFACTS_ROOT": str(artifacts_root),
            "GENOMEAI_WEB_STORAGE": str(web_storage),
            "GENOMEAI_WEB_DISABLE_WORKER": "1",
        }
        with _patched_environment(updates):
            importlib.invalidate_caches()
            started = perf_counter()
            if "web_cabinet.app" in sys.modules:
                module = _measure_step(steps, "import_app", lambda: importlib.reload(sys.modules["web_cabinet.app"]))
            else:
                module = _measure_step(steps, "import_app", lambda: importlib.import_module("web_cabinet.app"))
            try:
                _measure_step(steps, "startup", module._startup)
            finally:
                try:
                    module._shutdown()
                except Exception:
                    pass
            duration = max(0.0, perf_counter() - started)
    return {
        "gate": "startup",
        "ok": True,
        "duration_sec": duration,
        "steps": steps,
        "details": {
            "cold_root": str(workdir),
        },
    }


def _measure_pipeline_smoke(*, project_root: Path, workdir: Path | None = None, data_version: str | None = None) -> dict[str, Any]:
    from genomeai.contracts import load_contracts_dir
    from genomeai.decision_log import init_decision_log
    from genomeai.ingest import ingest_dataset
    from genomeai.pack import build_pilot_pack
    from genomeai.qc import run_qc
    from core.reporting import run_assistant_report as run_report
    from genomeai.score import run_scoring
    from genomeai.train import train_productivity_model
    from genomeai.versioning import generate_run_id

    temp_ctx = None
    if workdir is None:
        temp_ctx = tempfile.TemporaryDirectory(prefix="genomeai_perf_pipeline_")
        workdir_path = Path(temp_ctx.name)
    else:
        workdir_path = Path(workdir).resolve()
        workdir_path.mkdir(parents=True, exist_ok=True)
    artifacts_root = workdir_path / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    contracts_dir = project_root / "configs" / "contracts"
    data_dir = project_root / "data" / "examples"
    mappings_dir = project_root / "configs" / "mappings"
    dv = data_version or generate_run_id(prefix="dv_perf")
    steps: dict[str, float] = {}
    details: dict[str, Any] = {"data_version": dv, "artifacts_root": str(artifacts_root)}
    started = perf_counter()
    try:
        contracts = load_contracts_dir(contracts_dir)

        def ingest_one(dataset_key: str, contract_key: str, file_name: str, mapping_name: str) -> None:
            ingest_dataset(
                dataset_key=dataset_key,
                file_path=data_dir / file_name,
                mapping_path=mappings_dir / mapping_name,
                contract=contracts[contract_key],
                artifacts_root=artifacts_root,
                out_version=dv,
            )

        ingest_started = perf_counter()
        ingest_one("farms", "dm_farms", "dm_farms.csv", "farms_example.yaml")
        steps["ingest_farms"] = max(0.0, perf_counter() - ingest_started)
        ingest_started = perf_counter()
        ingest_one("animals", "dm_animals", "dm_animals.csv", "animals_example.yaml")
        steps["ingest_animals"] = max(0.0, perf_counter() - ingest_started)
        ingest_started = perf_counter()
        ingest_one("lactations", "dm_lactations", "dm_lactations.csv", "lactations_example.yaml")
        steps["ingest_lactations"] = max(0.0, perf_counter() - ingest_started)
        steps["ingest_total"] = steps["ingest_farms"] + steps["ingest_animals"] + steps["ingest_lactations"]

        qc = _measure_step(
            steps,
            "qc",
            lambda: run_qc(
                data_version=dv,
                artifacts_root=artifacts_root,
                contracts_dir=contracts_dir,
                qc_run=None,
            ),
        )
        if qc.get("qc_status") == "ERROR":
            return {
                "gate": "pipeline_smoke",
                "ok": False,
                "duration_sec": max(0.0, perf_counter() - started),
                "steps": steps,
                "details": {**details, "reason": "QC_ERROR", "qc": qc},
            }
        qr = qc["qc_run"]
        details["qc_run"] = qr

        train = _measure_step(
            steps,
            "train",
            lambda: train_productivity_model(
                artifacts_root=artifacts_root,
                data_version=dv,
                qc_run=qr,
                model_version=None,
            ),
        )
        if not train.get("ok"):
            return {
                "gate": "pipeline_smoke",
                "ok": False,
                "duration_sec": max(0.0, perf_counter() - started),
                "steps": steps,
                "details": {**details, "reason": "TRAIN_FAILED", "train": train},
            }
        mv = train["model_version"]
        details["model_version"] = mv

        score = _measure_step(
            steps,
            "score",
            lambda: run_scoring(
                artifacts_root=artifacts_root,
                data_version=dv,
                model_version=mv,
                scoring_run=None,
            ),
        )
        if not score.get("ok"):
            return {
                "gate": "pipeline_smoke",
                "ok": False,
                "duration_sec": max(0.0, perf_counter() - started),
                "steps": steps,
                "details": {**details, "reason": "SCORE_FAILED", "score": score},
            }
        sr = score["scoring_run"]
        details["scoring_run"] = sr

        report = _measure_step(
            steps,
            "report",
            lambda: run_report(
                artifacts_root=artifacts_root,
                data_version=dv,
                qc_run=qr,
                model_version=mv,
                scoring_run=sr,
                mode="fallback",
                report_version=None,
                make_pdf=False,
                llm_model=None,
            ),
        )
        if not report.get("ok"):
            return {
                "gate": "pipeline_smoke",
                "ok": False,
                "duration_sec": max(0.0, perf_counter() - started),
                "steps": steps,
                "details": {**details, "reason": "REPORT_FAILED", "report": report},
            }
        rv = report["report_version"]
        details["report_version"] = rv

        _measure_step(
            steps,
            "decision_log",
            lambda: init_decision_log(
                artifacts_root=artifacts_root,
                data_version=dv,
                scoring_run=sr,
                user="perf_gate",
                template_from_scoring=True,
            ),
        )

        pack = _measure_step(
            steps,
            "pack",
            lambda: build_pilot_pack(
                artifacts_root=artifacts_root,
                data_version=dv,
                qc_run=qr,
                model_version=mv,
                scoring_run=sr,
                report_version=rv,
                pack_id=None,
            ),
        )
        if not pack.get("ok"):
            return {
                "gate": "pipeline_smoke",
                "ok": False,
                "duration_sec": max(0.0, perf_counter() - started),
                "steps": steps,
                "details": {**details, "reason": "PACK_FAILED", "pack": pack},
            }
        details["pack_id"] = pack["pack_id"]
        details["pack_zip"] = pack["pack_zip"]
        return {
            "gate": "pipeline_smoke",
            "ok": True,
            "duration_sec": max(0.0, perf_counter() - started),
            "steps": steps,
            "details": details,
        }
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()


def _measure_web_smoke(*, project_root: Path, workdir: Path | None = None, data_version: str | None = None) -> dict[str, Any]:
    from web_cabinet.smoke import run_web_smoke_scenario

    temp_ctx = None
    if workdir is None:
        temp_ctx = tempfile.TemporaryDirectory(prefix="genomeai_perf_web_")
        workdir_path = Path(temp_ctx.name)
    else:
        workdir_path = Path(workdir).resolve()
        if workdir_path.exists():
            shutil.rmtree(workdir_path)
        workdir_path.mkdir(parents=True, exist_ok=True)
    try:
        result = run_web_smoke_scenario(workdir=workdir_path, data_version=data_version, clean=False)
        return {
            "gate": "web_smoke",
            "ok": bool(result.get("ok", False)),
            "duration_sec": float(result.get("duration_sec") or 0.0),
            "steps": dict(result.get("timings") or {}),
            "details": {k: v for k, v in result.items() if k not in {"ok", "duration_sec", "timings"}},
        }
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()


def _measure_verify_refactor(*, project_root: Path, golden_root: Path, report_root: Path, scenarios: Iterable[str]) -> dict[str, Any]:
    steps: dict[str, float] = {}
    reports: dict[str, str] = {}
    started = perf_counter()
    for scenario_name in scenarios:
        scenario = str(scenario_name).strip()
        if not scenario:
            continue
        scenario_report_root = report_root / scenario
        command = VerifyRefactorCommand(
            project_root=project_root,
            golden_root=golden_root,
            scenario_names=[scenario],
            report_root=scenario_report_root,
            update_golden=False,
            confirm_update_golden=False,
        )
        scenario_started = perf_counter()
        result = execute_verify_refactor(command)
        steps[scenario] = max(0.0, perf_counter() - scenario_started)
        if not result.get("ok"):
            return {
                "gate": "verify_refactor",
                "ok": False,
                "duration_sec": max(0.0, perf_counter() - started),
                "steps": steps,
                "details": {"reason": "VERIFY_REFACTOR_FAILED", "scenario": scenario, "result": result},
            }
        report_json = result.get("report_json")
        if report_json:
            reports[scenario] = str(report_json)
    return {
        "gate": "verify_refactor",
        "ok": True,
        "duration_sec": max(0.0, perf_counter() - started),
        "steps": steps,
        "details": {"reports": reports, "scenarios": list(scenarios)},
    }


def run_performance_gates(
    *,
    project_root: str | Path = ".",
    artifacts_root: str | Path = "artifacts",
    golden_root: str | Path = "golden",
    profile: str = "ci",
    config_path: str | Path | None = None,
    report_root: str | Path | None = None,
    gates: Iterable[str] | None = None,
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    artifacts_root_path = Path(artifacts_root).resolve()
    golden_root_path = Path(golden_root).resolve()
    policy = load_performance_gates_policy(project_root=project_root_path, config_path=config_path, profile=profile)
    configured_profile = policy["profile"]

    selected = [str(g).strip() for g in (gates or configured_profile.keys()) if str(g).strip()]
    unknown = [gate for gate in selected if gate not in configured_profile]
    if unknown:
        raise PerfGateError(f"unknown perf gates: {', '.join(sorted(unknown))}")

    report_dir = (
        Path(report_root).resolve()
        if report_root is not None
        else (artifacts_root_path / "_ci" / "performance_gates" / f"perf_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}").resolve()
    )

    gate_results: list[dict[str, Any]] = []
    for gate_name in selected:
        gate_cfg = configured_profile[gate_name]
        if not bool(gate_cfg.get("enabled", True)):
            continue
        if gate_name == "startup":
            gate_results.append(_measure_app_startup(project_root=project_root_path))
        elif gate_name == "pipeline_smoke":
            gate_results.append(_measure_pipeline_smoke(project_root=project_root_path))
        elif gate_name == "web_smoke":
            gate_results.append(_measure_web_smoke(project_root=project_root_path))
        elif gate_name == "verify_refactor":
            gate_results.append(
                _measure_verify_refactor(
                    project_root=project_root_path,
                    golden_root=golden_root_path,
                    report_root=report_dir / "verify_refactor",
                    scenarios=gate_cfg.get("scenarios") or ["standard", "qc_issues"],
                )
            )

    report: dict[str, Any] = {
        "schema": "genomeai.performance_gates_report.v1",
        "created_at_utc": _utc_now_iso(),
        "project_root": str(project_root_path),
        "artifacts_root": str(artifacts_root_path),
        "golden_root": str(golden_root_path),
        "profile": policy["profile_name"],
        "policy_path": policy["path"],
        "policy": {"profile": configured_profile},
        "gates": gate_results,
    }
    evaluate_perf_report(report, policy=policy)
    report["outputs"] = _write_report(report, report_root=report_dir)
    return report


__all__ = [
    "PerfGateError",
    "evaluate_perf_report",
    "load_performance_gates_policy",
    "render_performance_gate_cli_lines",
    "run_performance_gates",
]
