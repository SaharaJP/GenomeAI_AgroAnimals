from __future__ import annotations

import argparse
import json
import os
import time
import warnings
from datetime import datetime, timedelta, timezone
from time import perf_counter
from pathlib import Path

from .contracts import load_contracts_dir
from .contracts_catalog import write_contract_catalog
from .ingest import ingest_dataset
from .qc import run_qc
from .qc_v2 import run_qc_v2
from core.reporting import run_assistant_report as run_report
from .kpi_v2 import run_kpi
from .score import run_scoring
from .train import train_productivity_model
from .decision_log import add_decision, init_decision_log
from .pack import build_pilot_pack
from .smoke import run_smoke
from .backup_restore import apply_backup_retention, make_backup, restore_backup
from .versioning import bootstrap_run, compute_data_version
from .migration_pack_import import import_pilot_pack
from .smoke_migration import run_smoke_migration
from .target.master_id import MasterIdService, TrustRules, identity_run_dir, new_identity_run_id
from .target.master_id_store import MasterIdStore
from .validation import validate_input_dir
from .run_reproduce import reproduce_run
from .marts_timeseries import build_time_series_marts
from .mastitis_risk import train_mastitis_risk_model, score_mastitis_risk
from .repro_kpi_worklist import run_repro_kpi_worklists
from .pedigree_qc import run_pedigree_qc
from .mating_plan_v1 import run_mating_plan
from .connectors_v1 import ConnectorConfigError, cleanup_connector_temp_files, connector_retry_policy, failed_dataset_keys_from_results, list_connector_temp_files, load_connector_spec, run_connector_config, new_connector_run_id
from core.application import (
    VerifyRefactorCommand,
    execute_verify_refactor,
    parse_scenarios_arg,
    render_verify_refactor_cli_lines,
)
from core.artifacts import (
    ArtifactLifecycleError,
    archive_runtime_outputs,
    build_support_bundle,
    cleanup_runtime_outputs,
    load_artifact_lifecycle_policy,
)
from core.observability import (
    context_from_environment,
    correlation_scope,
    ensure_request_id,
    log_event,
    record_command_finish,
    record_command_start,
)
from core.performance import (
    PerfGateError,
    render_performance_gate_cli_lines,
    run_performance_gates,
)
from core.release import (
    ReleaseMetadataError,
    ReleasePackagingError,
    build_release_package,
    load_release_metadata,
    render_release_cli_lines,
    render_release_smoke_cli_lines,
    run_release_package_smoke,
)
from core.recovery import (
    RestoreDrillError,
    render_restore_drill_cli_lines,
    run_restore_drill,
)


def _cli_parse_argv(argv: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not argv:
        return out
    out['command'] = str(argv[0]).strip()
    i = 1
    while i < len(argv):
        token = str(argv[i])
        if token.startswith('--'):
            key = token[2:].replace('-', '_')
            if i + 1 < len(argv) and not str(argv[i + 1]).startswith('--'):
                out[key] = str(argv[i + 1])
                i += 2
                continue
            out[key] = 'true'
        i += 1
    return out


def _cli_correlation_fields(argv: list[str]) -> dict[str, object]:
    parsed = _cli_parse_argv([str(x) for x in (argv or [])])
    env_ctx = context_from_environment()
    data_version = str(env_ctx.get('data_version') or parsed.get('data_version') or parsed.get('out_version') or '').strip() or None
    run_id = str(env_ctx.get('run_id') or parsed.get('run_id') or parsed.get('report_version') or parsed.get('scoring_run') or parsed.get('model_version') or parsed.get('qc_run') or parsed.get('pack_id') or '').strip() or None
    config_version = str(env_ctx.get('config_version') or parsed.get('config') or parsed.get('cfg') or parsed.get('mapping') or parsed.get('rules') or '').strip() or None
    return {
        'request_id': ensure_request_id(str(env_ctx.get('request_id') or ''), prefix='cli'),
        'job_id': env_ctx.get('job_id'),
        'user_id': env_ctx.get('user_id'),
        'tenant_id': env_ctx.get('tenant_id'),
        'data_version': data_version,
        'run_id': run_id,
        'config_version': config_version,
        'command': str(parsed.get('command') or 'cli') or 'cli',
        'component': 'cli',
    }


def cmd_init_run(args: argparse.Namespace) -> int:
    artifacts_root = Path(args.artifacts).resolve()
    run_id, run_dir = bootstrap_run(artifacts_root=artifacts_root, run_id=args.run_id)
    print(run_id)
    print(str(run_dir))
    return 0


def cmd_contracts_catalog(args: argparse.Namespace) -> int:
    contracts_dir = Path(args.contracts).resolve()
    catalog_path = Path(args.catalog).resolve()
    output_path = Path(args.output).resolve()
    markdown_output = Path(args.markdown_output).resolve() if getattr(args, 'markdown_output', '') else None
    manifest = write_contract_catalog(
        output_path=output_path,
        contracts_dir=contracts_dir,
        catalog_path=catalog_path,
        markdown_output_path=markdown_output,
    )
    print("CONTRACTS_CATALOG_OK")
    print(f"dataset_count={manifest['dataset_count']}")
    print(f"output={output_path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    input_path = Path(args.input).resolve()
    contracts_dir = Path(args.contracts).resolve()
    contracts = load_contracts_dir(contracts_dir)

    errs, _found = validate_input_dir(input_path, contracts)

    if errs:
        print("VALIDATION_FAILED")
        for e in errs:
            print(str(e))
    else:
        print("VALIDATION_OK")

    if input_path.exists():
        dv = compute_data_version(input_path)
        print(f"data_version={dv}")
    else:
        print("data_version=NA (input path not found)")
        return 2

    return 1 if errs else 0


def cmd_ingest(args: argparse.Namespace) -> int:
    dataset_key = str(args.dataset).lower()
    dataset_map = {
        "farms": "dm_farms",
        "animals": "dm_animals",
        "lactations": "dm_lactations",
        "testday": "dm_testday",
        # Health (T4)
        "health_events": "dm_health_events",
        "treatments": "dm_treatments",
    }
    if dataset_key not in dataset_map:
        print(f"UNKNOWN_DATASET_KEY: {dataset_key}. expected one of {sorted(dataset_map)}")
        return 2

    contracts_dir = Path(args.contracts).resolve()
    contracts = load_contracts_dir(contracts_dir)
    ds = dataset_map[dataset_key]
    if ds not in contracts:
        print(f"MISSING_CONTRACT: {ds} not found in {contracts_dir}")
        return 2

    summary = ingest_dataset(
        dataset_key=dataset_key,
        file_path=Path(args.file),
        mapping_path=Path(args.mapping),
        contract=contracts[ds],
        artifacts_root=Path(args.artifacts),
        out_version=str(args.out_version),
    )

    status = "INGEST_WARN" if int(summary.get("error_count", 0)) > 0 else "INGEST_OK"
    print(status)
    print(f"dataset={summary['dataset']}")
    print(f"out_version={summary['out_version']}")
    print(f"rows_out={summary['rows_out']}")
    print(f"error_count={summary['error_count']}")
    print(f"canonical_csv={summary['canonical_csv']}")
    if summary.get("canonical_parquet"):
        print(f"canonical_parquet={summary['canonical_parquet']}")
    else:
        print("canonical_parquet=NA")

    # Non-fatal parsing issues are logged; we still return 0 so that multiple ingests
    # can be chained into the same out_version.
    return 0


def cmd_qc(args: argparse.Namespace) -> int:
    summary = run_qc(
        data_version=str(args.data_version),
        artifacts_root=Path(args.artifacts),
        contracts_dir=Path(args.contracts),
        qc_run=args.qc_run,
    )

    print(f"QC_{summary['qc_status']}")
    print(f"data_version={summary['data_version']}")
    print(f"qc_run={summary['qc_run']}")
    print(f"qc_report_xlsx={summary['outputs']['qc_report_xlsx']}")
    print(f"bad_rows_csv={summary['outputs']['bad_rows_csv']}")
    print(f"qc_issues_csv={summary['outputs']['qc_issues_csv']}")
    return 2 if summary["qc_status"] == "ERROR" else 0


def cmd_qc2(args: argparse.Namespace) -> int:
    summary = run_qc_v2(
        data_version=str(args.data_version),
        artifacts_root=Path(args.artifacts),
        rules_path=Path(args.rules),
        qc_run=args.qc_run,
    )

    print(f"QC2_{summary['qc_status']}")
    print(f"data_version={summary['data_version']}")
    print(f"qc_run={summary['qc_run']}")
    print(f"qc_issues_csv={summary['outputs']['qc_issues_csv']}")
    print(f"bad_rows_csv={summary['outputs']['bad_rows_csv']}")
    print(f"qc_report_xlsx={summary['outputs']['qc_report_xlsx']}")
    print(f"alerts_auto_csv={summary['outputs']['alerts_auto_csv']}")
    print(f"qc_summary_json={summary['outputs']['qc_summary_json']}")
    return 2 if summary["qc_status"] == "ERROR" else 0


def cmd_train(args: argparse.Namespace) -> int:
    res = train_productivity_model(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        qc_run=str(args.qc_run),
        model_version=args.model_version,
        config_path=getattr(args, "config", None),
    )

    if not res.get("ok"):
        print("TRAIN_FAILED")
        print(f"reason={res.get('reason')}")
        print(f"qc_status={res.get('qc_status')}")
        return 2

    print("TRAIN_OK")
    print(f"data_version={res['data_version']}")
    print(f"qc_run={res['qc_run']}")
    print(f"model_version={res['model_version']}")
    print(f"mae={res['metrics']['mae']}")
    print(f"rmse={res['metrics']['rmse']}")
    print(f"model_dir={res['model_dir']}")
    return 0



def cmd_train_mastitis(args: argparse.Namespace) -> int:
    res = train_mastitis_risk_model(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        qc_run=str(args.qc_run) if args.qc_run else None,
        model_version=args.model_version,
        horizon_days=int(args.horizon_days),
        cfg_path=Path(args.cfg),
    )
    if not res.get("ok"):
        print("TRAIN_MASTITIS_FAILED")
        print(f"reason={res.get('reason')}")
        if res.get("limitations"):
            print(json.dumps(res.get("limitations"), ensure_ascii=False))
        return 2
    print("TRAIN_MASTITIS_OK")
    print(f"data_version={res['data_version']}")
    print(f"model_version={res['model_version']}")
    print(f"pr_auc={res['metrics'].get('pr_auc')}")
    print(f"model_dir={res['model_dir']}")
    return 0


def cmd_score_mastitis(args: argparse.Namespace) -> int:
    res = score_mastitis_risk(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        model_version=str(args.model_version),
        scoring_run=args.scoring_run,
        asof_date=args.asof_date,
        cfg_path=Path(args.cfg),
    )
    if not res.get("ok"):
        print("SCORE_MASTITIS_FAILED")
        print(f"reason={res.get('reason')}")
        return 2
    print("SCORE_MASTITIS_OK")
    print(f"data_version={res['data_version']}")
    print(f"model_version={res['model_version']}")
    print(f"scoring_run={res['scoring_run']}")
    print(f"asof_date={res['asof_date']}")
    print(f"risk_scores_csv={res['outputs']['risk_scores_csv']}")
    return 0


def cmd_repro(args: argparse.Namespace) -> int:
    res = run_repro_kpi_worklists(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        asof_date=str(args.asof_date),
        cfg_path=Path(args.cfg),
        repro_run=args.repro_run,
        input_dir=Path(args.input_dir) if args.input_dir else None,
    )
    if not res.get("ok"):
        print("REPRO_FAILED")
        return 2
    print("REPRO_OK")
    print(f"data_version={res['data_version']}")
    print(f"repro_run={res['repro_run']}")
    print(f"asof_date={res['asof_date']}")
    print(f"kpis_csv={res['outputs']['kpis_csv']}")
    print(f"worklists_csv={res['outputs']['worklists_csv']}")
    print(f"xlsx={res['outputs']['xlsx']}")
    return 0

def cmd_pedigree(args: argparse.Namespace) -> int:
    res = run_pedigree_qc(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        cfg_path=Path(args.cfg),
        pedigree_run=args.pedigree_run,
        generations=int(args.generations),
    )
    if not res.get("ok"):
        print("PEDIGREE_QC_FAILED")
        print(f"reason={res.get('reason')}")
        return 2
    print("PEDIGREE_QC_OK")
    print(f"data_version={res['data_version']}")
    print(f"pedigree_run={res['pedigree_run']}")
    print(f"qc_issues_csv={res['outputs']['qc_issues_csv']}")
    print(f"alerts_auto_csv={res['outputs']['alerts_auto_csv']}")
    print(f"constraints_csv={res['outputs']['constraints_csv']}")
    return 0


def cmd_mating_plan(args: argparse.Namespace) -> int:
    res = run_mating_plan(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        cfg_path=Path(args.cfg),
        mating_plan_run=args.mating_plan_run,
        pedigree_run=args.pedigree_run,
    )
    if not res.get("ok"):
        print("MATING_PLAN_FAILED")
        print(f"reason={res.get('reason')}")
        if res.get("hint"):
            print(f"hint={res.get('hint')}")
        return 2
    print("MATING_PLAN_OK")
    print(f"data_version={res['data_version']}")
    print(f"mating_plan_run={res['mating_plan_run']}")
    print(f"pedigree_run={res['pedigree_run']}")
    print(f"mating_plan_csv={res['outputs']['mating_plan_csv']}")
    print(f"mating_plan_xlsx={res['outputs']['mating_plan_xlsx']}")
    return 0


def cmd_economics(args: argparse.Namespace) -> int:
    """T7-01: economics marts + what-if."""
    from pathlib import Path

    from .economics_whatif import run_economics_whatif

    res = run_economics_whatif(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        date_from=str(args.date_from),
        date_to=str(args.date_to),
        milk_price_multiplier=float(args.milk_price_multiplier),
        feed_cost_multiplier=float(args.feed_cost_multiplier),
        other_cost_multiplier=float(args.other_cost_multiplier),
        cfg_path=Path(args.cfg),
        economics_run=(str(args.economics_run).strip() or None),
        input_dir=(Path(args.input_dir) if str(args.input_dir).strip() else None),
        tenant_id=str(args.tenant_id or "default"),
    )
    print(json.dumps(res, ensure_ascii=False))
    return 0


def cmd_economics_v2(args: argparse.Namespace) -> int:
    """T11-01: Economics 2.0 (RUB) marts with transparent formulas."""
    from pathlib import Path

    from .economics_v2 import run_economics_v2

    res = run_economics_v2(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        date_from=str(args.date_from),
        date_to=str(args.date_to),
        cfg_path=Path(args.cfg),
        economics_run=(str(args.economics_run).strip() or None),
        input_dir=(Path(args.input_dir) if str(args.input_dir).strip() else None),
        tenant_id=str(args.tenant_id or "default"),
        refdata_db_path=(Path(args.refdata_db) if str(getattr(args, "refdata_db", "")).strip() else None),
        price_version=(str(getattr(args, "price_version", "")).strip() or None),
        assumptions_version=(str(getattr(args, "assumptions_version", "")).strip() or None),
    )

    # human-friendly key=value for logs
    if isinstance(res, dict):
        if res.get("ok"):
            print("ECONOMICS_V2_OK")
            print(f"data_version={res.get('data_version')}")
            print(f"economics_run={res.get('economics_run')}")
            outs = res.get("outputs") or {}
            if outs.get("economics_daily"):
                print(f"economics_daily={outs.get('economics_daily')}")
            if outs.get("economics_monthly"):
                print(f"economics_monthly={outs.get('economics_monthly')}")
        else:
            print("ECONOMICS_V2_FAILED")
            if res.get('reason'):
                print(f"reason={res.get('reason')}")

    print(json.dumps(res, ensure_ascii=False))
    return 0


def cmd_unit_economics(args: argparse.Namespace) -> int:
    """T11-03: unit economics marts (animal/group) based on economics_v2."""
    from pathlib import Path

    from .unit_economics import run_unit_economics

    res = run_unit_economics(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        cfg_path=Path(args.cfg),
        unit_econ_run=(str(args.unit_econ_run).strip() or None),
        economics_run=(str(args.economics_run).strip() or None),
        input_dir=(Path(args.input_dir) if str(args.input_dir).strip() else None),
        tenant_id=str(args.tenant_id or "default"),
        date_from=(str(args.date_from).strip() or None),
        date_to=(str(args.date_to).strip() or None),
    )

    if isinstance(res, dict):
        if res.get("ok"): 
            print("UNIT_ECONOMICS_OK")
            print(f"data_version={args.data_version}")
            print(f"unit_econ_run={res.get('unit_econ_run')}")
            print(f"economics_run={res.get('economics_run')}")
        else:
            print("UNIT_ECONOMICS_FAILED")
            if res.get('reason'): 
                print(f"reason={res.get('reason')}")

    print(json.dumps(res, ensure_ascii=False))
    return 0


def cmd_roi_attribution(args: argparse.Namespace) -> int:
    """T11-03: ROI attribution (before/after) for decisions/tasks."""
    from pathlib import Path

    from .roi_attribution import run_roi_attribution

    res = run_roi_attribution(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        cfg_path=Path(args.cfg),
        roi_run=(str(args.roi_run).strip() or None),
        unit_econ_run=(str(args.unit_econ_run).strip() or None),
        economics_run=(str(args.economics_run).strip() or None),
        tenant_id=str(args.tenant_id or "default"),
        web_db_path=(Path(args.web_db) if str(args.web_db).strip() else None),
        date_from=(str(args.date_from).strip() or None),
        date_to=(str(args.date_to).strip() or None),
    )

    if isinstance(res, dict):
        if res.get("ok"):
            print("ROI_ATTRIBUTION_OK")
            print(f"data_version={args.data_version}")
            print(f"roi_run={res.get('roi_run')}")
            print(f"unit_econ_run={res.get('unit_econ_run')}")
            print(f"economics_run={res.get('economics_run')}")
            print(f"rows={res.get('rows')}")
        else:
            print("ROI_ATTRIBUTION_FAILED")
            if res.get("reason"):
                print(f"reason={res.get('reason')}")

    print(json.dumps(res, ensure_ascii=False))
    return 0


def cmd_regular_report(args: argparse.Namespace) -> int:
    """T8-01: регулярные отчёты (daily/weekly) по модульному шаблону."""
    from pathlib import Path

    from core.reporting import run_regular_report

    res = run_regular_report(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        asof_date=str(args.asof_date),
        period=str(args.period),
        mode=str(args.mode),
        llm_model=(str(args.llm_model).strip() or None),
        report_version=(str(args.report_version).strip() or None),
    )
    print(json.dumps(res, ensure_ascii=False))
    return 0




def cmd_score(args: argparse.Namespace) -> int:
    res = run_scoring(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        model_version=str(args.model_version),
        scoring_run=args.scoring_run,
        config_path=getattr(args, "config", None),
    )

    if not res.get("ok"):
        print("SCORE_FAILED")
        return 2

    print("SCORE_OK")
    print(f"data_version={res['data_version']}")
    print(f"model_version={res['model_version']}")
    print(f"scoring_run={res['scoring_run']}")
    print(f"scoring_dir={res['scoring_dir']}")
    print(f"animal_ranking_xlsx={res['outputs']['animal_ranking_xlsx']}")
    print(f"group_summary_xlsx={res['outputs']['group_summary_xlsx']}")
    print(f"recommendations_xlsx={res['outputs']['recommendations_xlsx']}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    res = run_report(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        qc_run=str(args.qc_run),
        model_version=str(args.model_version),
        scoring_run=str(args.scoring_run),
        mode=str(args.mode),
        report_version=args.report_version,
        make_pdf=not bool(args.no_pdf),
        llm_model=args.llm_model,
    )

    if not res.get("ok"):
        print("REPORT_FAILED")
        return 2

    print("REPORT_OK")
    print(f"data_version={res['data_version']}")
    print(f"qc_run={res['qc_run']}")
    print(f"model_version={res['model_version']}")
    print(f"scoring_run={res['scoring_run']}")
    print(f"report_version={res['report_version']}")
    print(f"llm_used={res['llm_used']}")
    print(f"report_dir={res['report_dir']}")
    print(f"fact_pack={res['fact_pack']}")
    print(f"report_docx={res['outputs']['report_docx']}")
    print(f"report_pdf={res['outputs']['report_pdf']}")
    return 0


def cmd_decision_init(args: argparse.Namespace) -> int:
    paths = init_decision_log(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        scoring_run=args.scoring_run,
        user=str(args.user),
        template_from_scoring=not bool(getattr(args, "no_template", False)),
    )
    print("DECISION_LOG_OK")
    for k, v in paths.items():
        print(f"{k}={v}")
    return 0


def cmd_decision_add(args: argparse.Namespace) -> int:
    ok, msg = add_decision(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        animal_id=str(args.animal_id),
        lactation_id=str(args.lactation_id),
        recommendation_type=str(args.recommendation_type),
        decision=str(args.decision),
        comment=str(args.comment or ""),
        user=str(args.user),
        lactation_no=int(args.lactation_no) if args.lactation_no is not None else None,
        farm_id=str(args.farm_id) if args.farm_id is not None else None,
        scoring_run=str(args.scoring_run) if args.scoring_run is not None else None,
    )
    print("DECISION_ADD_OK" if ok else "DECISION_ADD_FAILED")
    print(f"msg={msg}")
    return 0 if ok else 2



def cmd_kpi(args: argparse.Namespace) -> int:
    res = run_kpi(
        data_version=args.data_version,
        asof_date=args.asof_date,
        artifacts_root=Path(args.artifacts),
        input_dir=Path(args.input_dir) if args.input_dir else (Path(args.artifacts) / args.data_version / "canonical"),
        run_id=args.run_id,
        config_kpi=Path(args.config_kpi),
        config_thresholds=Path(args.config_thresholds),
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_dashboard_export(args: argparse.Namespace) -> int:
    from datetime import datetime
    from pathlib import Path
    from .dashboard_director import DirectorSummaryInputs, export_director_summary

    artifacts = Path(args.artifacts)
    input_dir = Path(args.input_dir) if args.input_dir else None
    asof = datetime.strptime(args.asof_date, "%Y-%m-%d").date()
    inputs = DirectorSummaryInputs(
        data_version=args.data_version,
        artifacts_dir=artifacts,
        input_dir=input_dir,
        kpi_run_id=args.kpi_run_id,
        asof_date=asof,
    )
    export_director_summary(inputs=inputs, run_id=args.run_id)
    print(f"DASHBOARD_EXPORT_OK data_version={args.data_version} run_id={args.run_id or 'auto'}")
    return 0


def cmd_dashboard_save_report(args: argparse.Namespace) -> int:
    from pathlib import Path
    from .dashboard_reports import save_dashboard_snapshot_as_report

    res = save_dashboard_snapshot_as_report(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        dashboard_run_id=str(args.dashboard_run_id),
        dashboard_kind=str(args.dashboard_kind),
        report_version=(str(args.report_version) if args.report_version else None),
        notes=(str(args.notes) if args.notes else None),
    )
    if not res.get("ok"):
        print("DASHBOARD_REPORT_FAILED")
        print(f"reason={res.get('reason')}")
        return 2
    print("DASHBOARD_REPORT_OK")
    print(f"data_version={res['data_version']}")
    print(f"dashboard_run_id={res['dashboard_run_id']}")
    print(f"report_version={res['report_version']}")
    print(f"report_dir={res['report_dir']}")
    return 0

def cmd_pack(args: argparse.Namespace) -> int:
    res = build_pilot_pack(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        qc_run=str(args.qc_run),
        model_version=str(args.model_version),
        scoring_run=str(args.scoring_run),
        report_version=str(args.report_version),
        pack_id=args.pack_id,
    )
    if not res.get("ok"):
        print("PACK_FAILED")
        print(f"reason={res.get('reason')}")
        if res.get("missing"):
            print(f"missing={res['missing']}")
        return 2

    print("PACK_OK")
    print(f"data_version={res['versions']['data_version']}")
    print(f"pack_id={res['pack_id']}")
    print(f"pack_dir={res['pack_dir']}")
    print(f"pack_zip={res['pack_zip']}")
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    res = run_smoke(
        artifacts_root=Path(args.artifacts),
        contracts_dir=Path(args.contracts),
        data_dir=Path(args.data),
        mappings_dir=Path(args.mappings),
        out_version=args.out_version,
    )
    if not res.get("ok"):
        print("SMOKE_FAILED")
        print(f"reason={res.get('reason')}")
        return 2
    s = res["summary"]
    print("SMOKE_OK")
    print(f"data_version={s['data_version']}")
    print(f"qc_run={s['qc_run']}")
    print(f"model_version={s['model_version']}")
    print(f"scoring_run={s['scoring_run']}")
    print(f"report_version={s['report_version']}")
    print(f"pack_id={s['pack_id']}")
    print(f"pack_zip={s['outputs']['pack_zip']}")
    return 0


def cmd_sleep(args: argparse.Namespace) -> int:
    """Ops/test helper: sleep N seconds.

    Used for NFR timeout smoke tests (T9-01).
    """
    sec = float(args.seconds)
    if sec < 0:
        sec = 0.0
    time.sleep(sec)
    print("SLEEP_OK")
    print(f"slept_sec={sec}")
    return 0


def cmd_import_pack(args: argparse.Namespace) -> int:
    res = import_pilot_pack(
        pack_zip=Path(args.pack_zip),
        artifacts_root=Path(args.artifacts),
        verify=not bool(args.no_verify),
        force=bool(args.force),
    )
    if res.get("ok"):
        print("IMPORT_PACK_OK")
    else:
        print("IMPORT_PACK_FAIL")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 2


def cmd_smoke_migration(args: argparse.Namespace) -> int:
    res = run_smoke_migration(
        artifacts_root=Path(args.artifacts),
        contracts_dir=Path(args.contracts),
        data_dir=Path(args.data),
        mappings_dir=Path(args.mappings),
    )
    if res.get("ok"):
        print("SMOKE_MIGRATION_OK")
    else:
        print("SMOKE_MIGRATION_FAIL")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 2


def cmd_backup(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve() if args.out else None
    res = make_backup(
        artifacts_root=Path(args.artifacts),
        web_storage=Path(args.web_storage),
        db_path=Path(args.db_path) if getattr(args, 'db_path', None) else None,
        out_zip=out,
        project_root=Path(args.project_root) if getattr(args, 'project_root', None) else None,
        retention_config_path=Path(args.config) if getattr(args, 'config', None) else None,
    )
    print("BACKUP_OK")
    print(f"backup_zip={res.backup_zip}")
    print(f"backup_id={res.backup_id}")
    print(f"file_count={res.file_count}")
    return 0


def cmd_backup_cleanup(args: argparse.Namespace) -> int:
    try:
        res = apply_backup_retention(
            artifacts_root=Path(args.artifacts),
            web_storage=Path(args.web_storage),
            db_path=Path(args.db_path) if getattr(args, 'db_path', None) else None,
            project_root=Path(args.project_root) if getattr(args, 'project_root', None) else None,
            config_path=Path(args.config) if getattr(args, 'config', None) else None,
            dry_run=not bool(getattr(args, 'apply', False)),
            include_data_versions=bool(getattr(args, 'include_data_versions', False)),
        )
    except Exception as exc:
        print("BACKUP_CLEANUP_FAILED")
        print(f"reason={exc}")
        return 2
    print("BACKUP_CLEANUP_OK")
    print(f"batch_id={res.get('batch_id')}")
    print(f"dry_run={str(bool(res.get('dry_run'))).lower()}")
    print(f"backups_delete_candidates={len((res.get('backups') or {}).get('delete_candidates') or [])}")
    print(f"backups_deleted={len((res.get('backups') or {}).get('deleted_paths') or [])}")
    snapshots = (res.get('restore_snapshots') or {}).get('families') or {}
    snapshot_candidates = sum(len((fam or {}).get('delete_candidates') or []) for fam in snapshots.values())
    snapshot_deleted = sum(len((fam or {}).get('deleted_paths') or []) for fam in snapshots.values())
    print(f"restore_snapshot_delete_candidates={snapshot_candidates}")
    print(f"restore_snapshot_deleted={snapshot_deleted}")
    print(f"data_versions_delete_candidates={len((res.get('data_versions') or {}).get('delete_candidates') or [])}")
    print(f"data_versions_deleted={len((res.get('data_versions') or {}).get('deleted_paths') or [])}")
    return 0




def cmd_artifact_cleanup(args: argparse.Namespace) -> int:
    try:
        policy = load_artifact_lifecycle_policy(project_root=Path(args.project_root), config_path=getattr(args, "config", None))
        res = cleanup_runtime_outputs(
            project_root=Path(args.project_root),
            artifacts_root=Path(args.artifacts),
            web_storage=Path(args.web_storage),
            db_path=Path(args.db_path) if getattr(args, "db_path", None) else None,
            tmp_root=Path(args.tmp_root),
            config_path=getattr(args, "config", None),
            dry_run=not bool(getattr(args, "apply", False)),
            include_data_versions=(True if getattr(args, "include_data_versions", False) else None),
        )
    except ArtifactLifecycleError as exc:
        print("ARTIFACT_CLEANUP_FAILED")
        print(f"reason={exc}")
        return 2
    print("ARTIFACT_CLEANUP_OK")
    print(f"policy_path={policy['path']}")
    print(f"dry_run={str(bool(res.get('dry_run'))).lower()}")
    for family_name, family in sorted((res.get('runtime_families') or {}).items()):
        print(f"{family_name}_delete_candidates={len((family or {}).get('delete_candidates') or [])}")
        print(f"{family_name}_deleted={len((family or {}).get('deleted_paths') or [])}")
    backup_summary = res.get('backup_retention') or {}
    print(f"backups_delete_candidates={len((backup_summary.get('backups') or {}).get('delete_candidates') or [])}")
    print(f"backups_deleted={len((backup_summary.get('backups') or {}).get('deleted_paths') or [])}")
    print(f"data_versions_deleted={len((backup_summary.get('data_versions') or {}).get('deleted_paths') or [])}")
    return 0


def cmd_artifact_archive(args: argparse.Namespace) -> int:
    try:
        policy = load_artifact_lifecycle_policy(project_root=Path(args.project_root), config_path=getattr(args, "config", None))
        out = Path(args.out).resolve() if getattr(args, "out", None) else (Path(args.project_root).resolve() / str(policy['archive_dir']) / 'runtime_archive.zip')
        res = archive_runtime_outputs(
            output_zip=out,
            project_root=Path(args.project_root),
            artifacts_root=Path(args.artifacts),
            web_storage=Path(args.web_storage),
            db_path=Path(args.db_path) if getattr(args, "db_path", None) else None,
            tmp_root=Path(args.tmp_root),
            config_path=getattr(args, "config", None),
            families=(getattr(args, "families", None) or None),
            scope=str(getattr(args, "scope", "all")),
        )
    except ArtifactLifecycleError as exc:
        print("ARTIFACT_ARCHIVE_FAILED")
        print(f"reason={exc}")
        return 2
    print("ARTIFACT_ARCHIVE_OK")
    print(f"archive_zip={res['archive_zip']}")
    print(f"entry_count={res['entry_count']}")
    print(f"scope={res['scope']}")
    return 0


def cmd_support_bundle(args: argparse.Namespace) -> int:
    try:
        policy = load_artifact_lifecycle_policy(project_root=Path(args.project_root), config_path=getattr(args, "config", None))
        out = Path(args.out).resolve() if getattr(args, "out", None) else (Path(args.project_root).resolve() / str(policy['support_bundle_dir']) / 'support_bundle.zip')
        res = build_support_bundle(
            output_zip=out,
            project_root=Path(args.project_root),
            artifacts_root=Path(args.artifacts),
            web_storage=Path(args.web_storage),
            db_path=Path(args.db_path) if getattr(args, "db_path", None) else None,
            tmp_root=Path(args.tmp_root),
            config_path=getattr(args, "config", None),
        )
    except ArtifactLifecycleError as exc:
        print("SUPPORT_BUNDLE_FAILED")
        print(f"reason={exc}")
        return 2
    print("SUPPORT_BUNDLE_OK")
    print(f"bundle_zip={res['bundle_zip']}")
    print(f"entry_count={res['entry_count']}")
    return 0


def cmd_perf_gates(args: argparse.Namespace) -> int:
    try:
        res = run_performance_gates(
            project_root=Path(args.project_root),
            artifacts_root=Path(args.artifacts),
            golden_root=Path(args.golden),
            profile=str(getattr(args, "profile", "ci")),
            config_path=getattr(args, "config", None),
            report_root=(Path(args.report_root) if getattr(args, "report_root", None) else None),
            gates=(getattr(args, "gates", None) or None),
        )
    except PerfGateError as exc:
        print("PERF_GATES_FAILED")
        print(f"reason={exc}")
        return 2
    for line in render_performance_gate_cli_lines(res):
        print(line)
    return 0 if bool((res.get("summary") or {}).get("ok")) else 2


def cmd_version(args: argparse.Namespace) -> int:
    metadata = load_release_metadata(project_root=Path(args.project_root).resolve())
    if str(getattr(args, "format", "text") or "text") == "json":
        print(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("GENOMEAI_VERSION")
        print(f"version={metadata.get('version')}")
        print(f"build_stamp={metadata.get('build_stamp')}")
        print(f"release_channel={metadata.get('release_channel')}")
        print(f"build_time_utc={metadata.get('build_time_utc')}")
        if metadata.get("git_commit"):
            print(f"git_commit={metadata.get('git_commit')}")
        if metadata.get("metadata_path"):
            print(f"metadata_path={metadata.get('metadata_path')}")
    return 0


def cmd_release_build(args: argparse.Namespace) -> int:
    result = build_release_package(
        project_root=Path(args.project_root).resolve(),
        out_path=(Path(args.out).resolve() if getattr(args, "out", None) else None),
        config_path=getattr(args, "config", None),
        build_stamp=(str(args.build_stamp).strip() or None),
        release_channel=(str(args.release_channel).strip() or None),
        source_date_epoch=(int(args.source_date_epoch) if getattr(args, "source_date_epoch", None) is not None else None),
    )
    for line in render_release_cli_lines(result):
        print(line)
    return 0


def cmd_release_smoke(args: argparse.Namespace) -> int:
    result = run_release_package_smoke(
        archive_path=Path(args.archive).resolve(),
        python_executable=(str(args.python).strip() or None),
    )
    for line in render_release_smoke_cli_lines(result):
        print(line)
    if str(getattr(args, "report_json", "") or "").strip():
        report_path = Path(args.report_json).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"report_json={report_path}")
    return 0


def cmd_restore_drill(args: argparse.Namespace) -> int:
    try:
        result = run_restore_drill(
            project_root=Path(args.project_root).resolve(),
            artifacts_root=Path(args.artifacts).resolve(),
            web_storage=Path(args.web_storage).resolve(),
            db_path=(Path(args.db_path).resolve() if getattr(args, 'db_path', None) else None),
            report_root=(Path(args.report_root).resolve() if getattr(args, 'report_root', None) else None),
            config_path=getattr(args, 'config', None),
        )
    except RestoreDrillError as exc:
        print("RESTORE_DRILL_FAILED")
        print(f"reason={exc}")
        return 2
    for line in render_restore_drill_cli_lines(result):
        print(line)
    return 0 if bool((result.get('summary') or {}).get('ok')) else 2


def cmd_restore(args: argparse.Namespace) -> int:
    res = restore_backup(
        backup_zip=Path(args.backup),
        artifacts_root=Path(args.artifacts),
        web_storage=Path(args.web_storage),
        db_path=Path(args.db_path) if getattr(args, 'db_path', None) else None,
        force=bool(args.force),
        smoke_check=bool(getattr(args, 'smoke_check', False)),
    )
    if not res.get("ok"):
        print("RESTORE_FAILED")
        print(f"reason={res.get('reason')}")
        return 2
    print("RESTORE_OK")
    print(f"verified_files={res.get('verified_files')}")
    print(f"total_files={res.get('total_files')}")
    print(f"moved_artifacts={res.get('moved_artifacts') or ''}")
    print(f"moved_web_storage={res.get('moved_web_storage') or ''}")
    print(f"db_path={res.get('db_path') or ''}")
    if res.get('smoke'):
        print(f"restore_smoke_ok={bool(res['smoke'].get('ok'))}")
    return 0


def cmd_marts_ts(args: argparse.Namespace) -> int:
    res = build_time_series_marts(
        artifacts_root=Path(args.artifacts),
        data_version=str(args.data_version),
        input_dir=Path(args.input_dir),
        marts_run=args.marts_run,
    )
    if not res.get("ok"):
        print("MARTS_TS_FAILED")
        return 2
    print("MARTS_TS_OK")
    print(f"data_version={res['data_version']}")
    print(f"marts_run={res['marts_run']}")
    for k, v in res.get("outputs", {}).items():
        print(f"{k}={v}")
    return 0


def _identity_store_from_args(args: argparse.Namespace):
    artifacts_dir = Path(args.artifacts).resolve()
    dv = args.data_version
    run_id = args.run_id or new_identity_run_id()
    run_dir = identity_run_dir(artifacts_dir, dv, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    store = MasterIdStore(run_dir)
    rules = TrustRules.load(Path(args.rules).resolve())
    svc = MasterIdService(store, rules)
    return svc, run_id, run_dir

def cmd_master_id_resolve(args: argparse.Namespace) -> int:
    svc, run_id, run_dir = _identity_store_from_args(args)
    attrs = {}
    for k in ["sex","birth_date","breed","ear_tag_id","farm_id","dam_animal_id","status","calving_date","required_by_source"]:
        v = getattr(args, k, None)
        if v:
            attrs[k] = str(v)
    res = svc.resolve(
        tenant_id=args.tenant,
        source_system=args.source_system,
        source_animal_id=args.source_id,
        attrs=attrs,
        actor=args.actor,
        run_id=run_id,
    )
    print("MASTER_ID_RESOLVE_OK")
    print(f"run_id={run_id}")
    print(f"store_dir={run_dir}")
    print(f"master_animal_id={res['master_animal_id']}")
    if res.get("conflicts"):
        print(f"conflicts={len(res['conflicts'])}")
    return 0

def cmd_master_id_merge(args: argparse.Namespace) -> int:
    svc, run_id, run_dir = _identity_store_from_args(args)
    res = svc.merge(
        tenant_id=args.tenant,
        from_master=args.from_master,
        into_master=args.into_master,
        actor=args.actor,
        reason=args.reason,
        run_id=run_id,
    )
    print("MASTER_ID_MERGE_OK")
    print(f"run_id={run_id}")
    print(f"store_dir={run_dir}")
    print(f"moved_aliases={res.get('moved_aliases')}")
    return 0

def cmd_master_id_split(args: argparse.Namespace) -> int:
    svc, run_id, run_dir = _identity_store_from_args(args)
    move_aliases = []
    for a in args.move_alias:
        if ":" not in a:
            raise SystemExit(f"Bad --move-alias '{a}', expected source_system:source_animal_id")
        src, sid = a.split(":", 1)
        move_aliases.append((src, sid))
    res = svc.split(
        tenant_id=args.tenant,
        master_id=args.master,
        move_aliases=move_aliases,
        actor=args.actor,
        reason=args.reason,
        new_master_id=args.new_master,
        run_id=run_id,
    )
    print("MASTER_ID_SPLIT_OK")
    print(f"run_id={run_id}")
    print(f"store_dir={run_dir}")
    print(f"new_master_animal_id={res.get('new_master_animal_id')}")
    print(f"moved_aliases={res.get('moved_aliases')}")
    return 0



def _connectors_db():
    try:
        from core.infra.web_db import connect as wc_connect, get_settings as wc_get_settings, init_db as wc_init_db

        settings = wc_get_settings()
        conn = wc_connect(settings.db_path)
        wc_init_db(conn)
        return conn
    except Exception:
        return None



def cmd_connectors_validate(args: argparse.Namespace) -> int:
    try:
        spec = load_connector_spec(Path(args.config).resolve(), project_root=Path(args.project_root).resolve())
    except ConnectorConfigError as e:
        print('CONNECTOR_INVALID')
        print(f'reason={e}')
        return 2
    print('CONNECTOR_VALID')
    print(f'connector_id={spec.connector_id}')
    print(f'kind={spec.kind}')
    print(f'enabled={str(spec.enabled).lower()}')
    print(f'config_path={spec.config_path}')
    return 0



def cmd_connectors_run(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    artifacts_root = Path(args.artifacts).resolve()
    connector_run_id = str(args.connector_run_id or new_connector_run_id())
    status_code = 0
    conn = _connectors_db()
    tenant_id = str(args.tenant_id or 'default')
    current_retry_attempt_no = max(0, int(args.retry_attempt_no or 0))
    current_retry_parent_run_id = str(args.retry_parent_run_id or '').strip() or None
    try:
        spec = load_connector_spec(Path(args.config).resolve(), project_root=project_root)
        if conn is not None:
            from web_cabinet.connectors_v1 import start_connector_run

            start_connector_run(
                conn,
                tenant_id=tenant_id,
                connector_run_id=connector_run_id,
                connector_id=spec.connector_id,
                kind=spec.kind,
                trigger_type=str(args.trigger or 'manual'),
                schedule_slot=str(args.scheduled_slot or '').strip() or None,
                config_path=str(Path(args.config).resolve()),
            )
        dataset_keys = [str(x).strip().lower() for x in str(args.datasets or '').split(',') if str(x).strip()]
        result = run_connector_config(
            Path(args.config).resolve(),
            project_root=project_root,
            artifacts_root=artifacts_root,
            connector_run_id=connector_run_id,
            trigger_type=str(args.trigger or 'manual'),
            scheduled_slot=str(args.scheduled_slot or '').strip() or None,
            force=bool(args.force),
            dataset_keys=dataset_keys,
        )
        print('CONNECTOR_RUN_OK')
        print(f'connector_id={result.connector_id}')
        print(f'kind={result.kind}')
        print(f'status={result.status}')
        print(f'trigger_type={result.trigger_type}')
        print(f'connector_run_id={result.connector_run_id}')
        print(f'run_id={result.connector_run_id}')
        print(f'data_version={result.data_version or ""}')
        if result.outputs.get('requested_dataset_keys'):
            print(f"requested_dataset_keys={','.join(result.outputs.get('requested_dataset_keys') or [])}")
        print(f'message={result.message}')

        auto_retry_context: dict[str, object] | None = None
        failed_dataset_keys = failed_dataset_keys_from_results(result.dataset_results)
        retry_policy = connector_retry_policy(spec)
        retry_on_statuses = set(retry_policy.get('retry_on_statuses') or [])

        if failed_dataset_keys:
            if result.status not in retry_on_statuses:
                auto_retry_context = {
                    'status': 'skipped',
                    'reason': f'status_not_retryable:{result.status}',
                    'failed_dataset_keys': failed_dataset_keys,
                    'policy': retry_policy,
                    'retry_attempt_no': current_retry_attempt_no,
                }
            elif not retry_policy.get('enabled'):
                auto_retry_context = {
                    'status': 'skipped',
                    'reason': 'auto_retry_disabled',
                    'failed_dataset_keys': failed_dataset_keys,
                    'policy': retry_policy,
                    'retry_attempt_no': current_retry_attempt_no,
                }
            elif current_retry_attempt_no >= int(retry_policy.get('max_attempts') or 0):
                auto_retry_context = {
                    'status': 'skipped',
                    'reason': 'max_attempts_reached',
                    'failed_dataset_keys': failed_dataset_keys,
                    'policy': retry_policy,
                    'retry_attempt_no': current_retry_attempt_no,
                    'max_attempts': int(retry_policy.get('max_attempts') or 0),
                }
            elif conn is not None:
                from web_cabinet.connectors_v1 import enqueue_connector_job

                next_retry_attempt_no = current_retry_attempt_no + 1
                next_attempt_at = (datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=int(retry_policy.get('backoff_sec') or 0))).isoformat()
                retry_parent_run_id = current_retry_parent_run_id or result.connector_run_id
                try:
                    retry_job_id, retry_meta = enqueue_connector_job(
                        conn,
                        tenant_id=tenant_id,
                        user_id=int(args.user_id or 0),
                        username=str(args.username or 'system'),
                        config_path=str(Path(args.config).resolve()),
                        trigger_type='auto_retry_failed',
                        force=True,
                        dataset_keys=failed_dataset_keys,
                        next_attempt_at=next_attempt_at,
                        retry_source='connector_auto_failed_datasets',
                        retry_parent_run_id=retry_parent_run_id,
                        retry_attempt_no=next_retry_attempt_no,
                    )
                    auto_retry_context = {
                        'status': 'scheduled',
                        'reason': 'failed_dataset_subset',
                        'failed_dataset_keys': failed_dataset_keys,
                        'policy': retry_policy,
                        'retry_job_id': retry_job_id,
                        'retry_connector_run_id': retry_meta.get('connector_run_id'),
                        'next_attempt_at': next_attempt_at,
                        'retry_parent_run_id': retry_parent_run_id,
                        'retry_attempt_no': next_retry_attempt_no,
                    }
                    print(f'auto_retry_job_id={retry_job_id}')
                    print(f'auto_retry_next_attempt_at={next_attempt_at}')
                    print(f"auto_retry_dataset_keys={','.join(failed_dataset_keys)}")
                except Exception as auto_retry_error:
                    auto_retry_context = {
                        'status': 'skipped',
                        'reason': f'queue_guardrail:{type(auto_retry_error).__name__}',
                        'error': str(auto_retry_error),
                        'failed_dataset_keys': failed_dataset_keys,
                        'policy': retry_policy,
                        'retry_parent_run_id': retry_parent_run_id,
                        'retry_attempt_no': next_retry_attempt_no,
                    }

        outputs_payload = {
            **(result.outputs or {}),
            'dataset_results': result.dataset_results,
            'retry_parent_run_id': current_retry_parent_run_id,
            'retry_attempt_no': current_retry_attempt_no,
        }
        if auto_retry_context is not None:
            outputs_payload['connector_auto_retry'] = auto_retry_context

        for k, v in sorted(outputs_payload.items()):
            if v is not None and str(v) != '':
                print(f'{k}={v}')
        if conn is not None:
            from web_cabinet.connectors_v1 import finish_connector_run
            from core.audit.events import write_audit

            finish_connector_run(
                conn,
                tenant_id=tenant_id,
                connector_run_id=result.connector_run_id,
                status=result.status,
                data_version=result.data_version,
                message=result.message,
                outputs=outputs_payload,
                selected_files=result.selected_files,
                ingest_summaries=result.ingest_summaries,
                error_text=None,
            )
            write_audit(
                conn,
                tenant_id=tenant_id,
                user_id=int(args.user_id or 0),
                username=str(args.username or 'system'),
                role='system' if int(args.user_id or 0) == 0 else 'Operator',
                action='connector.run',
                object_type='connector',
                object_id=result.connector_id,
                data_version=result.data_version,
                run_id=result.connector_run_id,
                after={
                    'status': result.status,
                    'trigger_type': result.trigger_type,
                    'message': result.message,
                    'requested_dataset_keys': dataset_keys,
                    'retry_attempt_no': current_retry_attempt_no,
                },
                status='OK',
            )
            if auto_retry_context and auto_retry_context.get('status') == 'scheduled':
                write_audit(
                    conn,
                    tenant_id=tenant_id,
                    user_id=int(args.user_id or 0),
                    username=str(args.username or 'system'),
                    role='system' if int(args.user_id or 0) == 0 else 'Operator',
                    action='connector.auto_retry_scheduled',
                    object_type='connector',
                    object_id=result.connector_id,
                    data_version=result.data_version,
                    run_id=result.connector_run_id,
                    after=auto_retry_context,
                    status='OK',
                )
        return 0 if result.ok else 2
    except Exception as e:
        status_code = 2
        print('CONNECTOR_RUN_FAILED')
        print(f'reason={type(e).__name__}: {e}')
        if conn is not None:
            try:
                from web_cabinet.connectors_v1 import finish_connector_run
                from core.audit.events import write_audit
                spec = None
                try:
                    spec = load_connector_spec(Path(args.config).resolve(), project_root=project_root)
                except Exception:
                    pass
                finish_connector_run(
                    conn,
                    tenant_id=tenant_id,
                    connector_run_id=connector_run_id,
                    status='failed',
                    data_version=None,
                    message=str(e),
                    outputs={
                        'retry_parent_run_id': current_retry_parent_run_id,
                        'retry_attempt_no': current_retry_attempt_no,
                    },
                    selected_files=[],
                    ingest_summaries=[],
                    error_text=str(e),
                )
                write_audit(
                    conn,
                    tenant_id=tenant_id,
                    user_id=int(args.user_id or 0),
                    username=str(args.username or 'system'),
                    role='system' if int(args.user_id or 0) == 0 else 'Operator',
                    action='connector.run',
                    object_type='connector',
                    object_id=spec.connector_id if spec else str(Path(args.config).resolve()),
                    run_id=connector_run_id,
                    after={
                        'status': 'failed',
                        'trigger_type': str(args.trigger or 'manual'),
                        'retry_attempt_no': current_retry_attempt_no,
                    },
                    status='FAIL',
                    error=str(e),
                )
            except Exception:
                pass
        return status_code
    finally:
        if conn is not None:
            conn.close()


def cmd_connectors_schedule(args: argparse.Namespace) -> int:
    from web_cabinet.connectors_v1 import schedule_due_connector_jobs

    conn = _connectors_db()
    if conn is None:
        print('CONNECTOR_SCHEDULE_FAILED')
        print('reason=web db is not available; set GENOMEAI_WEB_STORAGE/PROJECT_ROOT or run inside web cabinet environment')
        return 2
    try:
        when = datetime.fromisoformat(args.at) if args.at else datetime.now(timezone.utc)
        res = schedule_due_connector_jobs(
            conn,
            tenant_id=str(args.tenant_id or 'default'),
            user_id=int(args.user_id or 0),
            username=str(args.username or 'system'),
            configs_dir=Path(args.configs_dir).resolve(),
            when=when,
        )
        print('CONNECTOR_SCHEDULE_OK')
        print(f'slot={res.get("slot") or ""}')
        print(f'enqueued_count={len(res.get("enqueued") or [])}')
        print(json.dumps(res, ensure_ascii=False))
        return 0
    finally:
        conn.close()


def cmd_connectors_cleanup(args: argparse.Namespace) -> int:
    configs_dir = Path(args.configs_dir).resolve()
    stale_before = list_connector_temp_files(configs_dir)
    stale = cleanup_connector_temp_files(configs_dir, remove=not bool(args.dry_run))
    if args.dry_run:
        print('CONNECTOR_CLEANUP_DRY_RUN')
    else:
        print('CONNECTOR_CLEANUP_OK')
    print(f'configs_dir={configs_dir}')
    print(f'stale_count={len(stale_before)}')
    if not args.dry_run:
        print(f'removed_count={len(stale)}')
    if stale_before:
        print('stale_files=')
        for path in stale_before:
            print(str(path))
    return 0



def cmd_verify_refactor(args: argparse.Namespace) -> int:
    if str(getattr(args, 'cmd', '') or '') == 'verify-refactor':
        warnings.warn(
            "CLI alias 'verify-refactor' is deprecated; use 'verify_refactor' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    command = VerifyRefactorCommand(
        project_root=Path(args.project_root).resolve(),
        golden_root=Path(args.golden).resolve(),
        scenario_names=parse_scenarios_arg(args.scenarios),
        report_root=Path(args.report_root).resolve() if args.report_root else None,
        update_golden=bool(args.update_golden),
        confirm_update_golden=bool(args.i_understand_update_golden),
    )
    result = execute_verify_refactor(command)
    for line in render_verify_refactor_cli_lines(result):
        print(line)
    return int(result["exit_code"])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="genomeai")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-run", help="Create artifacts run structure and emit run_id")
    p_init.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_init.add_argument("--run-id", default=None, help="Optional fixed run_id")
    p_init.set_defaults(func=cmd_init_run)

    p_cat = sub.add_parser("contracts-catalog", help="Export contract catalog manifest for UI/docs (T13-03 step1)")
    p_cat.add_argument("--contracts", default="configs/contracts", help="Path to contracts directory")
    p_cat.add_argument("--catalog", default="configs/contracts/catalog.json", help="Path to contract catalog metadata")
    p_cat.add_argument("--output", default="artifacts/system/data_contract_catalog.json", help="Output JSON manifest path")
    p_cat.add_argument("--markdown-output", default="", help="Optional output path for markdown catalog")
    p_cat.set_defaults(func=cmd_contracts_catalog)

    p_val = sub.add_parser("validate", help="Validate input CSVs against data contracts")
    p_val.add_argument("--input", required=True, help="Path to directory containing CSVs")
    p_val.add_argument("--contracts", default="configs/contracts", help="Path to contracts directory")
    p_val.set_defaults(func=cmd_validate)

    p_con = sub.add_parser("connectors", help="Connector framework v1: validate/run/schedule")
    con_sub = p_con.add_subparsers(dest="connectors_cmd", required=True)

    p_con_val = con_sub.add_parser("validate", help="Validate connector config")
    p_con_val.add_argument("--config", required=True, help="Path to connector YAML")
    p_con_val.add_argument("--project-root", default=".", help="Project root for resolving relative paths")
    p_con_val.set_defaults(func=cmd_connectors_validate)

    p_con_run = con_sub.add_parser("run", help="Execute a connector pull")
    p_con_run.add_argument("--config", required=True, help="Path to connector YAML")
    p_con_run.add_argument("--project-root", default=".", help="Project root for resolving relative paths")
    p_con_run.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_con_run.add_argument("--trigger", default="manual", choices=["manual", "manual_force", "schedule", "schedule_manual", "api", "retry_failed", "retry_last_failed", "auto_retry_failed"], help="Trigger type")
    p_con_run.add_argument("--connector-run-id", default=None, help="Optional fixed connector_run_id")
    p_con_run.add_argument("--scheduled-slot", default=None, help="Optional schedule slot ISO timestamp for cron tick")
    p_con_run.add_argument("--datasets", default="", help="Optional comma-separated dataset_key subset for partial retry/run")
    p_con_run.add_argument("--tenant-id", default="default")
    p_con_run.add_argument("--user-id", default=0, type=int)
    p_con_run.add_argument("--username", default="system")
    p_con_run.add_argument("--retry-parent-run-id", default=None, help="Original connector_run_id for retry lineage")
    p_con_run.add_argument("--retry-attempt-no", default=0, type=int, help="Connector auto-retry attempt number for failed dataset subset recovery")
    p_con_run.add_argument("--force", action="store_true", help="Ignore increment state and pull anyway")
    p_con_run.set_defaults(func=cmd_connectors_run)

    p_con_sched = con_sub.add_parser("schedule", help="Cron-like schedule tick: enqueue due connectors")
    p_con_sched.add_argument("--configs-dir", default="configs/connectors", help="Directory with connector YAML files")
    p_con_sched.add_argument("--at", default=None, help="Optional ISO datetime for schedule evaluation (UTC if omitted)")
    p_con_sched.add_argument("--tenant-id", default="default")
    p_con_sched.add_argument("--user-id", default=0, type=int)
    p_con_sched.add_argument("--username", default="system")
    p_con_sched.set_defaults(func=cmd_connectors_schedule)

    p_con_clean = con_sub.add_parser("cleanup", help="Remove stale connector preview/tmp configs from configs/connectors")
    p_con_clean.add_argument("--configs-dir", default="configs/connectors", help="Directory with connector YAML files")
    p_con_clean.add_argument("--dry-run", action="store_true", help="Only list stale connector temp files without deleting them")
    p_con_clean.set_defaults(func=cmd_connectors_cleanup)

    p_ing = sub.add_parser("ingest", help="Ingest external CSV/XLSX into canonical layer")
    p_ing.add_argument("--dataset", required=True, help="Dataset key: farms|animals|lactations|testday")
    p_ing.add_argument("--file", required=True, help="Path to external CSV/XLSX")
    p_ing.add_argument("--mapping", required=True, help="Path to YAML mapping: source -> canonical")
    p_ing.add_argument("--out-version", required=True, help="Target data_version for canonical output")
    p_ing.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_ing.add_argument("--contracts", default="configs/contracts", help="Path to contracts directory")
    p_ing.set_defaults(func=cmd_ingest)

    p_qc = sub.add_parser("qc", help="Run P0 QC checks on canonical layer for a data_version")
    p_qc.add_argument("--data-version", required=True, help="Existing data_version under artifacts/")
    p_qc.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_qc.add_argument("--contracts", default="configs/contracts", help="Path to contracts directory")
    p_qc.add_argument("--qc-run", default=None, help="Optional fixed qc_run id")
    p_qc.set_defaults(func=cmd_qc)

    p_qc2 = sub.add_parser("qc2", help="Run QC Rules Engine v2 (YAML-driven, with severity + auto alerts)")
    p_qc2.add_argument("--data-version", required=True, help="Existing data_version under artifacts/")
    p_qc2.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_qc2.add_argument(
        "--rules",
        default="configs/qc_rules_v2.yaml",
        help="Path to qc_rules_v2.yaml",
    )
    p_qc2.add_argument("--qc-run", default=None, help="Optional fixed qc_run id")
    p_qc2.set_defaults(func=cmd_qc2)

    p_tr = sub.add_parser("train", help="Train baseline ML model (productivity) on P0 canonical data")
    p_tr.add_argument("--data-version", required=True, help="Existing data_version under artifacts/")
    p_tr.add_argument("--qc-run", required=True, help="qc_run id under artifacts/<dv>/qc/")
    p_tr.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_tr.add_argument("--model-version", default=None, help="Optional fixed model_version")
    p_tr.add_argument("--config", default=None, help="Optional ML pipeline config path")
    p_tr.set_defaults(func=cmd_train)

    p_sc = sub.add_parser("score", help="Run inference using trained ML model and export results")
    p_sc.add_argument("--data-version", required=True, help="Existing data_version under artifacts/")
    p_sc.add_argument("--model-version", required=True, help="Existing model_version under artifacts/**/models/")
    p_sc.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_sc.add_argument("--scoring-run", default=None, help="Optional fixed scoring_run id")
    p_sc.add_argument("--config", default=None, help="Optional ML pipeline config path")
    p_sc.set_defaults(func=cmd_score)

    p_marts = sub.add_parser("marts-ts", help="Build time-series marts cow_day/group_day (T3-02)")
    p_marts.add_argument("--data-version", required=True, help="Target data_version label (used for artifacts layout)")
    p_marts.add_argument(
        "--input-dir",
        required=True,
        help="Directory with canonical dm_*.csv (e.g. data/fixtures/target_v2)",
    )
    p_marts.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_marts.add_argument("--marts-run", default=None, help="Optional fixed marts_run id")
    p_marts.set_defaults(func=cmd_marts_ts)

    p_rep = sub.add_parser("report", help="Build AI report (LLM or fallback) strictly from fact pack")
    p_rep.add_argument("--data-version", required=True, help="Existing data_version under artifacts/")
    p_rep.add_argument("--qc-run", required=True, help="qc_run id under artifacts/<dv>/qc/")
    p_rep.add_argument("--model-version", required=True, help="model_version under artifacts/<dv>/models/")
    p_rep.add_argument("--scoring-run", required=True, help="scoring_run under artifacts/<dv>/scoring/")
    p_rep.add_argument("--mode", default="fallback", choices=["fallback", "llm"], help="Report generation mode")
    p_rep.add_argument("--llm-model", default=None, help="Optional LLM model name (OpenAI).")
    p_rep.add_argument("--report-version", default=None, help="Optional fixed report_version")
    p_rep.add_argument("--no-pdf", action="store_true", help="Do not generate PDF")
    p_rep.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_rep.set_defaults(func=cmd_report)

    p_dec = sub.add_parser("decision", help="Create or append decision_log for user decisions")
    dec_sub = p_dec.add_subparsers(dest="decision_cmd", required=True)

    p_di = dec_sub.add_parser("init", help="Create decision_log (optionally prefilled from scoring)")
    p_di.add_argument("--data-version", required=True, help="Existing data_version under artifacts/")
    p_di.add_argument("--scoring-run", default=None, help="Optional scoring_run to prefill template")
    p_di.add_argument("--user", default="unknown", help="User name")
    p_di.add_argument("--no-template", action="store_true", help="Do not prefill from scoring")
    p_di.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_di.set_defaults(func=cmd_decision_init)

    p_da = dec_sub.add_parser("add", help="Append a decision record")
    p_da.add_argument("--data-version", required=True, help="Existing data_version under artifacts/")
    p_da.add_argument("--animal-id", required=True)
    p_da.add_argument("--lactation-id", required=True)
    p_da.add_argument("--recommendation-type", required=True, help="e.g. PRIORITY/OBSERVE/CULL_CANDIDATE")
    p_da.add_argument("--decision", required=True, help="User decision: e.g. ACCEPT/REJECT/DEFER")
    p_da.add_argument("--comment", default="")
    p_da.add_argument("--user", default="unknown")
    p_da.add_argument("--lactation-no", default=None, type=int)
    p_da.add_argument("--farm-id", default=None)
    p_da.add_argument("--scoring-run", default=None)
    p_da.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_da.set_defaults(func=cmd_decision_add)

    p_pack = sub.add_parser("pack", help="Build Pilot Pack (folder + zip) for delivery")
    p_pack.add_argument("--data-version", required=True)
    p_pack.add_argument("--qc-run", required=True)
    p_pack.add_argument("--model-version", required=True)
    p_pack.add_argument("--scoring-run", required=True)
    p_pack.add_argument("--report-version", required=True)
    p_pack.add_argument("--pack-id", default=None, help="Optional fixed pack id")
    p_pack.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_pack.set_defaults(func=cmd_pack)

    p_kpi = sub.add_parser("kpi", help="Compute director KPI v2 and generate KPI alerts (non-blocking)")
    p_kpi.add_argument("--data-version", required=True, help="Data version")
    p_kpi.add_argument("--asof-date", required=True, help="As-of date YYYY-MM-DD")
    p_kpi.add_argument(
        "--input-dir",
        default=None,
        help="Directory with Target v2 CSVs (fixtures or canonical exports)",
    )
    p_kpi.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_kpi.add_argument("--run-id", default=None, help="Optional fixed run_id")
    p_kpi.add_argument("--config-kpi", default="configs/kpi/kpi_v2.yaml", help="KPI dictionary config")
    p_kpi.add_argument(
        "--config-thresholds",
        default="configs/kpi/kpi_thresholds_v2.yaml",
        help="Thresholds + FX config",
    )
    p_kpi.set_defaults(func=cmd_kpi)

    

    p_ped = sub.add_parser("pedigree", help="Pedigree QC + инбридинг-ограничения (T6-01)")
    p_ped.add_argument("--data-version", required=True, help="Data version")
    p_ped.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_ped.add_argument("--pedigree-run", default=None, help="Optional fixed pedigree_run id")
    p_ped.add_argument("--generations", default=3, type=int, help="Depth N generations for common-ancestor ban")
    p_ped.add_argument(
        "--cfg",
        default="configs/pedigree/pedigree_rules_v1.yaml",
        help="Path to pedigree rules YAML",
    )
    p_ped.set_defaults(func=cmd_pedigree)

    p_mp = sub.add_parser("mating-plan", help="Mating plan v1: cow -> top bulls (T6-02)")
    p_mp.add_argument("--data-version", required=True, help="Data version")
    p_mp.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_mp.add_argument("--mating-plan-run", default=None, help="Optional fixed mating_plan_run id")
    p_mp.add_argument("--pedigree-run", default=None, help="Optional pedigree_run to use for constraints")
    p_mp.add_argument(
        "--cfg",
        default="configs/mating_plan/mating_plan_v1.yaml",
        help="Path to mating plan config YAML",
    )
    p_mp.set_defaults(func=cmd_mating_plan)

    # --- T7-01: economics what-if
    p_ec = sub.add_parser("economics", help="Economics marts + what-if scenarios (T7-01)")
    p_ec.add_argument("--artifacts", default="artifacts", help="Artifacts root")
    p_ec.add_argument("--data-version", required=True, help="data_version")
    p_ec.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    p_ec.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    p_ec.add_argument("--milk-price-multiplier", type=float, default=1.0)
    p_ec.add_argument("--feed-cost-multiplier", type=float, default=1.0)
    p_ec.add_argument("--other-cost-multiplier", type=float, default=1.0)
    p_ec.add_argument("--cfg", default="configs/economics/economics_v1.yaml")
    p_ec.add_argument("--economics-run", default="", help="Optional run id")
    p_ec.add_argument("--input-dir", default="", help="Optional canonical dir (csv/parquet)")
    p_ec.add_argument("--tenant-id", default="default")
    p_ec.set_defaults(func=cmd_economics)

    # --- T11-01: economics v2 (RUB)
    p_ec2 = sub.add_parser("economics-v2", help="Economics 2.0 marts in RUB + transparent formulas (T11-01)")
    p_ec2.add_argument("--artifacts", default="artifacts", help="Artifacts root")
    p_ec2.add_argument("--data-version", required=True, help="data_version")
    p_ec2.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    p_ec2.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    p_ec2.add_argument("--cfg", default="configs/economics/economics_v2.yaml")
    p_ec2.add_argument("--economics-run", default="", help="Optional run id")
    p_ec2.add_argument("--input-dir", default="", help="Optional canonical dir (csv/parquet)")
    p_ec2.add_argument("--tenant-id", default="default")
    p_ec2.add_argument(
        "--refdata-db",
        default="",
        help="Path to sqlite DB with price books/assumptions (T11-02)",
    )
    p_ec2.add_argument("--price-version", default="", help="Optional price_book version_id (T11-02)")
    p_ec2.add_argument("--assumptions-version", default="", help="Optional assumptions version_id (T11-02)")
    p_ec2.set_defaults(func=cmd_economics_v2)

    # --- T11-03: unit economics (animal/group)
    p_uec = sub.add_parser("unit-economics", help="Unit economics: вклад животного/группы в прибыль (T11-03)")
    p_uec.add_argument("--artifacts", default="artifacts", help="Artifacts root")
    p_uec.add_argument("--data-version", required=True, help="data_version")
    p_uec.add_argument("--cfg", default="configs/economics/unit_economics_v1.yaml")
    p_uec.add_argument("--unit-econ-run", default="", help="Optional run id")
    p_uec.add_argument("--economics-run", default="", help="Optional economics_v2 run id (если пусто — latest)")
    p_uec.add_argument("--date-from", default="", help="Optional YYYY-MM-DD (по умолчанию — диапазон economics_v2)")
    p_uec.add_argument("--date-to", default="", help="Optional YYYY-MM-DD (по умолчанию — диапазон economics_v2)")
    p_uec.add_argument("--input-dir", default="", help="Optional canonical dir (csv/parquet)")
    p_uec.add_argument("--tenant-id", default="default")
    p_uec.set_defaults(func=cmd_unit_economics)

    # --- T11-03: ROI attribution (decisions/tasks)
    p_roi = sub.add_parser("roi", help="ROI attribution: эффект от решений/задач (before/after, diff-in-diff) (T11-03)")
    p_roi.add_argument("--artifacts", default="artifacts", help="Artifacts root")
    p_roi.add_argument("--data-version", required=True, help="data_version")
    p_roi.add_argument("--cfg", default="configs/economics/roi_attribution_v1.yaml")
    p_roi.add_argument("--roi-run", default="", help="Optional run id")
    p_roi.add_argument("--unit-econ-run", default="", help="Optional unit_economics run id (если пусто — latest)")
    p_roi.add_argument("--economics-run", default="", help="Optional economics_v2 run id (если пусто — из unit_economics manifest)")
    p_roi.add_argument("--web-db", default="", help="Optional path to web.db (to include tasks_v1 and decision_log_v2)")
    p_roi.add_argument("--date-from", default="", help="Optional YYYY-MM-DD for actions")
    p_roi.add_argument("--date-to", default="", help="Optional YYYY-MM-DD for actions")
    p_roi.add_argument("--tenant-id", default="default")
    p_roi.set_defaults(func=cmd_roi_attribution)

    # --- T8-01: regular reports
    p_rr = sub.add_parser("regular-report", help="Regular director/ops reports (T8-01)")
    p_rr.add_argument("--artifacts", default="artifacts", help="Artifacts root")
    p_rr.add_argument("--data-version", required=True, help="data_version")
    p_rr.add_argument("--asof-date", required=True, help="YYYY-MM-DD")
    p_rr.add_argument("--period", default="daily", choices=["daily", "weekly"], help="report period")
    p_rr.add_argument("--mode", default="fallback", choices=["fallback", "llm"], help="text generation mode")
    p_rr.add_argument("--llm-model", default="", help="optional LLM model")
    p_rr.add_argument("--report-version", default="", help="optional fixed report_version")
    p_rr.set_defaults(func=cmd_regular_report)

    p_repro_step = sub.add_parser("repro", help="Compute reproduction KPIs and generate worklists (T5-01)")
    p_repro_step.add_argument("--data-version", required=True, help="Data version")
    p_repro_step.add_argument("--asof-date", required=True, help="As-of date YYYY-MM-DD")
    p_repro_step.add_argument(
        "--input-dir",
        default=None,
        help="Directory with Target v2 CSVs (fixtures or canonical exports)",
    )
    p_repro_step.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_repro_step.add_argument("--repro-run", default=None, help="Optional fixed repro_run id")
    p_repro_step.add_argument(
        "--cfg",
        default="configs/repro/repro_rules_v1.yaml",
        help="Path to reproduction rules YAML",
    )
    p_repro_step.set_defaults(func=cmd_repro)

    p_dash = sub.add_parser("dashboard", help="Director dashboard exports (summary snapshot)")
    p_dash.add_argument("--data-version", required=True, help="Data version")
    p_dash.add_argument("--asof-date", required=True, help="As-of date YYYY-MM-DD")
    p_dash.add_argument(
        "--input-dir",
        default=None,
        help="Directory with Target v2 CSVs (fixtures or canonical exports)",
    )
    p_dash.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_dash.add_argument("--run-id", default=None, help="Optional fixed run_id for dashboard export")
    p_dash.add_argument(
        "--kpi-run-id",
        default=None,
        help="Optional KPI run_id to use (auto-detect latest if omitted)",
    )
    p_dash.set_defaults(func=cmd_dashboard_export)

    p_drep = sub.add_parser("dashboard-report", help="Save a dashboard snapshot as report_version (T10-02)")
    p_drep.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_drep.add_argument("--data-version", required=True, help="data_version")
    p_drep.add_argument("--dashboard-run-id", required=True, help="Source dashboard run_id (artifacts/<dv>/runs/<run_id>/dashboards/...)")
    p_drep.add_argument("--dashboard-kind", default="director_summary", help="Dashboard kind (default: director_summary)")
    p_drep.add_argument("--report-version", default="", help="Optional fixed report_version")
    p_drep.add_argument("--notes", default="", help="Optional notes")
    p_drep.set_defaults(func=cmd_dashboard_save_report)

    # run: reproduce a past run on the same data_version (T0-03)
    p_run = sub.add_parser("run", help="Run utilities (Target): reproduce/replay runs")
    run_sub = p_run.add_subparsers(dest="run_cmd", required=True)

    p_repro = run_sub.add_parser("reproduce", help="Reproduce a past run by run_id")
    p_repro.add_argument("--data-version", required=True)
    p_repro.add_argument("--run-id", required=True, help="Source run_id to reproduce (e.g. report_...)")
    p_repro.add_argument("--mode", choices=["rerun", "replay"], default="rerun")
    p_repro.add_argument("--out-run-id", default=None, help="Optional new run_id for reproduction result")
    p_repro.add_argument("--artifacts", default="artifacts", help="Artifacts root")
    p_repro.set_defaults(func=_cmd_run_reproduce)

    p_vr = sub.add_parser("verify_refactor", help="Run Golden-set verification for refactor safety (T15-01)")
    p_vr.add_argument("--project-root", default=".", help="Project root")
    p_vr.add_argument("--golden", default="golden", help="Golden-set root")
    p_vr.add_argument("--scenarios", default="standard,qc_issues", help="Comma-separated scenarios or empty for all")
    p_vr.add_argument("--report-root", default="", help="Optional directory for verification reports")
    p_vr.add_argument("--update-golden", action="store_true", help="Rebuild golden snapshots (manual only)")
    p_vr.add_argument("--i-understand-update-golden", action="store_true", help="Required manual confirmation for --update-golden")
    p_vr.set_defaults(func=cmd_verify_refactor)

    p_vr_alias = sub.add_parser("verify-refactor", help="Alias for verify_refactor")
    p_vr_alias.add_argument("--project-root", default=".", help="Project root")
    p_vr_alias.add_argument("--golden", default="golden", help="Golden-set root")
    p_vr_alias.add_argument("--scenarios", default="standard,qc_issues", help="Comma-separated scenarios or empty for all")
    p_vr_alias.add_argument("--report-root", default="", help="Optional directory for verification reports")
    p_vr_alias.add_argument("--update-golden", action="store_true", help="Rebuild golden snapshots (manual only)")
    p_vr_alias.add_argument("--i-understand-update-golden", action="store_true", help="Required manual confirmation for --update-golden")
    p_vr_alias.set_defaults(func=cmd_verify_refactor)

    p_sm = sub.add_parser("smoke", help="Run A1..A6 on synthetic data in one command")
    p_sm.add_argument("--out-version", default=None, help="Optional fixed data_version")
    p_sm.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_sm.add_argument("--contracts", default="configs/contracts", help="Contracts directory")
    p_sm.add_argument("--mappings", default="configs/mappings", help="Mappings directory")
    p_sm.add_argument("--data", default="data/examples", help="Examples data root (expects external/)")
    p_sm.set_defaults(func=cmd_smoke)

    p_smig = sub.add_parser(
        "smoke-migration",
        help="Offline->Web smoke: build Pilot Pack offline and import into artifacts root",
    )
    p_smig.add_argument("--artifacts", default="artifacts", help="Destination artifacts root directory")
    p_smig.add_argument("--contracts", default="configs/contracts", help="Contracts directory")
    p_smig.add_argument("--mappings", default="configs/mappings", help="Mappings directory")
    p_smig.add_argument("--data", default="data/examples", help="Examples data root (expects external/)")
    p_smig.set_defaults(func=cmd_smoke_migration)

    p_ip = sub.add_parser("import-pack", help="Import Offline Pilot Pack zip into Target artifacts layout")
    p_ip.add_argument("--pack-zip", required=True, help="Path to Pilot Pack zip")
    p_ip.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_ip.add_argument("--no-verify", action="store_true", help="Skip pack_manifest.json verification")
    p_ip.add_argument("--force", action="store_true", help="Allow overwriting existing data_version")
    p_ip.set_defaults(func=cmd_import_pack)

    # ops: sleep (for timeout smoke tests)
    p_sl = sub.add_parser("sleep", help="Ops/test helper: sleep N seconds")
    p_sl.add_argument("--seconds", default="1", help="Seconds to sleep")
    p_sl.set_defaults(func=cmd_sleep)

    p_bk = sub.add_parser("backup", help="Backup artifacts and web storage to a zip")
    p_bk.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_bk.add_argument(
        "--web-storage",
        default="web_cabinet/storage",
        help="Web storage directory (sqlite + uploads + logs)",
    )
    p_bk.add_argument("--out", default=None, help="Optional explicit output zip path")
    p_bk.add_argument("--db-path", default=None, help="Optional explicit sqlite DB path (default: <web-storage>/web.db)")
    p_bk.add_argument("--project-root", default=".", help="Project root for default retention config lookup")
    p_bk.add_argument("--config", default=None, help="Optional path to backup retention YAML")
    p_bk.set_defaults(func=cmd_backup)

    p_bkc = sub.add_parser("backup-cleanup", help="Apply retention policy to backups / restore snapshots / optional data_versions")
    p_bkc.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_bkc.add_argument(
        "--web-storage",
        default="web_cabinet/storage",
        help="Web storage directory (sqlite + uploads + logs)",
    )
    p_bkc.add_argument("--db-path", default=None, help="Optional explicit sqlite DB path (default: <web-storage>/web.db)")
    p_bkc.add_argument("--project-root", default=".", help="Project root for default retention config lookup")
    p_bkc.add_argument("--config", default=None, help="Optional path to backup retention YAML")
    p_bkc.add_argument("--apply", action="store_true", help="Actually delete old files/directories (default: dry-run)")
    p_bkc.add_argument("--include-data-versions", action="store_true", help="Allow cleanup of old dv_* directories when enabled in config")
    p_bkc.set_defaults(func=cmd_backup_cleanup)

    p_acl = sub.add_parser("artifact-cleanup", help="Safe cleanup for runtime/verify/tmp/log outputs with retention policy")
    p_acl.add_argument("--project-root", default=".", help="Project root for lifecycle policy lookup")
    p_acl.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_acl.add_argument("--web-storage", default="web_cabinet/storage", help="Web storage directory")
    p_acl.add_argument("--db-path", default=None, help="Optional explicit sqlite DB path")
    p_acl.add_argument("--tmp-root", default="_tmp", help="Temporary runtime root to prune")
    p_acl.add_argument("--config", default=None, help="Optional path to artifact lifecycle YAML")
    p_acl.add_argument("--apply", action="store_true", help="Actually delete files/directories (default: dry-run)")
    p_acl.add_argument("--include-data-versions", action="store_true", help="Allow backup-retention cleanup for old dv_* directories")
    p_acl.set_defaults(func=cmd_artifact_cleanup)

    p_aar = sub.add_parser("artifact-archive", help="Archive selected runtime outputs into a deterministic zip")
    p_aar.add_argument("--project-root", default=".", help="Project root for lifecycle policy lookup")
    p_aar.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_aar.add_argument("--web-storage", default="web_cabinet/storage", help="Web storage directory")
    p_aar.add_argument("--db-path", default=None, help="Optional explicit sqlite DB path")
    p_aar.add_argument("--tmp-root", default="_tmp", help="Temporary runtime root to archive")
    p_aar.add_argument("--config", default=None, help="Optional path to artifact lifecycle YAML")
    p_aar.add_argument("--out", default=None, help="Output zip path (default: policy archive_dir/runtime_archive.zip)")
    p_aar.add_argument("--family", dest="families", action="append", default=[], help="Lifecycle family to include (repeatable)")
    p_aar.add_argument("--scope", default="all", choices=["all", "delete_candidates"], help="Archive all current entries or only cleanup delete candidates")
    p_aar.set_defaults(func=cmd_artifact_archive)

    p_sb = sub.add_parser("support-bundle", help="Collect deterministic diagnostics bundle for incidents/support")
    p_sb.add_argument("--project-root", default=".", help="Project root for lifecycle policy lookup")
    p_sb.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_sb.add_argument("--web-storage", default="web_cabinet/storage", help="Web storage directory")
    p_sb.add_argument("--db-path", default=None, help="Optional explicit sqlite DB path")
    p_sb.add_argument("--tmp-root", default="_tmp", help="Temporary runtime root for inventory")
    p_sb.add_argument("--config", default=None, help="Optional path to artifact lifecycle YAML")
    p_sb.add_argument("--out", default=None, help="Output zip path (default: policy support_bundle_dir/support_bundle.zip)")
    p_sb.set_defaults(func=cmd_support_bundle)

    p_pg = sub.add_parser("perf-gates", help="Run coarse performance/NFR budgets on startup, smoke, jobs and verify paths")
    p_pg.add_argument("--project-root", default=".", help="Project root for configs/examples/golden lookup")
    p_pg.add_argument("--artifacts", default="artifacts", help="Artifacts root for generated perf reports")
    p_pg.add_argument("--golden", default="golden", help="Golden root for verify_refactor perf gate")
    p_pg.add_argument("--profile", default="ci", help="Budget profile from performance_gates_v1.yaml")
    p_pg.add_argument("--config", default=None, help="Optional path to performance gates YAML")
    p_pg.add_argument("--report-root", default=None, help="Optional explicit output directory for perf gate reports")
    p_pg.add_argument("--gate", dest="gates", action="append", default=[], choices=["startup", "pipeline_smoke", "web_smoke", "verify_refactor"], help="Restrict run to selected gate(s); repeatable")
    p_pg.set_defaults(func=cmd_perf_gates)

    p_ver = sub.add_parser("version", help="Print package version/build stamp/runtime release metadata")
    p_ver.add_argument("--project-root", default=".", help="Project root for pyproject/release metadata lookup")
    p_ver.add_argument("--format", default="text", choices=["text", "json"], help="Output format")
    p_ver.set_defaults(func=cmd_version)

    p_rb = sub.add_parser("release-build", help="Build reproducible release archive with manifest and checksums")
    p_rb.add_argument("--project-root", default=".", help="Project root for packaging")
    p_rb.add_argument("--out", default=None, help="Optional explicit output zip path")
    p_rb.add_argument("--config", default=None, help="Optional path to release packaging YAML")
    p_rb.add_argument("--build-stamp", default="", help="Stable build stamp for release metadata")
    p_rb.add_argument("--release-channel", default="", help="Release channel label, e.g. dev|ci|release")
    p_rb.add_argument("--source-date-epoch", default=None, type=int, help="Reproducible build epoch (SOURCE_DATE_EPOCH)")
    p_rb.set_defaults(func=cmd_release_build)

    p_rsm = sub.add_parser("release-smoke", help="Unpack a release archive and verify key packaged interfaces")
    p_rsm.add_argument("--archive", required=True, help="Path to release archive zip")
    p_rsm.add_argument("--python", default="", help="Optional python executable for packaged smoke")
    p_rsm.add_argument("--report-json", default="", help="Optional JSON report path")
    p_rsm.set_defaults(func=cmd_release_smoke)

    p_rd = sub.add_parser("restore-drill", help="Run automated backup→restore drill with verification report")
    p_rd.add_argument("--project-root", default=".", help="Project root for config/report lookup")
    p_rd.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_rd.add_argument("--web-storage", default="web_cabinet/storage", help="Web storage directory")
    p_rd.add_argument("--db-path", default=None, help="Optional explicit sqlite DB path (default: <web-storage>/web.db)")
    p_rd.add_argument("--config", default=None, help="Optional path to backup restore drill YAML")
    p_rd.add_argument("--report-root", default=None, help="Optional explicit output directory for drill reports")
    p_rd.set_defaults(func=cmd_restore_drill)

    p_rs = sub.add_parser("restore", help="Restore artifacts and web storage from a backup zip")
    p_rs.add_argument("--backup", required=True, help="Path to backup zip")
    p_rs.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_rs.add_argument(
        "--web-storage",
        default="web_cabinet/storage",
        help="Web storage directory (sqlite + uploads + logs)",
    )
    p_rs.add_argument("--db-path", default=None, help="Optional explicit sqlite DB path (default: <web-storage>/web.db)")
    p_rs.add_argument("--force", action="store_true", help="Allow restore into non-empty destinations")
    p_rs.add_argument("--smoke-check", action="store_true", help="Run lightweight smoke validation after restore")
    p_rs.set_defaults(func=cmd_restore)


    p_mid = sub.add_parser("master-id", help="Target: master_animal_id resolution + merge/split with audit")
    mid_sub = p_mid.add_subparsers(dest="master_cmd", required=True)

    p_mr = mid_sub.add_parser("resolve", help="Resolve (or create) master_animal_id for a source animal id")
    p_mr.add_argument("--data-version", required=True, help="data_version for storing identity artifacts")
    p_mr.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_mr.add_argument("--run-id", default=None, help="Optional run_id for identity operation")
    p_mr.add_argument("--rules", default="configs/target/trust_rules.yaml", help="Trust rules YAML")
    p_mr.add_argument("--tenant", default="default", help="Tenant id")
    p_mr.add_argument("--actor", default="operator", help="User performing action (audit)")
    p_mr.add_argument("--source-system", required=True, help="Source system key, e.g. registry|sensor|lab|manual")
    p_mr.add_argument("--source-id", required=True, help="Animal id in source system")
    p_mr.add_argument("--sex", default=None, help="F|M|U")
    p_mr.add_argument("--birth-date", dest="birth_date", default=None, help="YYYY-MM-DD")
    p_mr.add_argument("--breed", default=None)
    p_mr.add_argument("--ear-tag-id", dest="ear_tag_id", default=None)
    p_mr.add_argument("--farm-id", dest="farm_id", default=None)
    p_mr.add_argument("--dam-animal-id", dest="dam_animal_id", default=None)
    p_mr.add_argument("--status", default=None, help="active|culled|merged")
    p_mr.add_argument("--calving-date", dest="calving_date", default=None, help="Optional (for conflict checks)")
    p_mr.add_argument("--required-by-source", dest="required_by_source", default=None, help="Optional: lab|sensor|...")
    p_mr.set_defaults(func=cmd_master_id_resolve)

    p_mm = mid_sub.add_parser("merge", help="Merge two master_animal_id (from -> into)")
    p_mm.add_argument("--data-version", required=True)
    p_mm.add_argument("--artifacts", default="artifacts")
    p_mm.add_argument("--run-id", default=None)
    p_mm.add_argument("--rules", default="configs/target/trust_rules.yaml")
    p_mm.add_argument("--tenant", default="default")
    p_mm.add_argument("--actor", default="operator")
    p_mm.add_argument("--reason", required=True)
    p_mm.add_argument("--from-master", dest="from_master", required=True)
    p_mm.add_argument("--into-master", dest="into_master", required=True)
    p_mm.set_defaults(func=cmd_master_id_merge)

    p_ms = mid_sub.add_parser("split", help="Split aliases from an existing master into a new master")
    p_ms.add_argument("--data-version", required=True)
    p_ms.add_argument("--artifacts", default="artifacts")
    p_ms.add_argument("--run-id", default=None)
    p_ms.add_argument("--rules", default="configs/target/trust_rules.yaml")
    p_ms.add_argument("--tenant", default="default")
    p_ms.add_argument("--actor", default="operator")
    p_ms.add_argument("--reason", required=True)
    p_ms.add_argument("--master", required=True, help="Existing master_animal_id to split from")
    p_ms.add_argument("--new-master", dest="new_master", default=None, help="Optional fixed new master_animal_id")
    p_ms.add_argument("--move-alias", action="append", default=[], help="Alias to move: source_system:source_animal_id (repeatable)")
    p_ms.set_defaults(func=cmd_master_id_split)

    return p


def _cmd_run_reproduce(args: argparse.Namespace) -> int:
    res = reproduce_run(
        artifacts_root=Path(args.artifacts),
        data_version=args.data_version,
        run_id=args.run_id,
        mode=args.mode,
        out_run_id=args.out_run_id,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    parsed_argv = [str(x) for x in (argv or [])]
    args = parser.parse_args(argv)
    obs = _cli_correlation_fields(parsed_argv)
    command = str(obs.get('command') or 'cli')
    record_command_start(command)
    started = perf_counter()
    status = 'ok'
    with correlation_scope(**obs):
        log_event('cli.command.started', component='cli')
        try:
            exit_code = int(args.func(args))
        except Exception:
            status = 'failed'
            log_event('cli.command.failed', level='ERROR', component='cli')
            raise
        else:
            if exit_code != 0:
                status = 'failed'
            return exit_code
        finally:
            duration = max(0.0, perf_counter() - started)
            record_command_finish(command, status=status, duration_sec=duration)
            log_event('cli.command.finished', component='cli', status=status, exit_code=locals().get('exit_code'))


if __name__ == "__main__":
    raise SystemExit(main())
    p_tm = sub.add_parser("train-mastitis", help="Train mastitis risk model (T4-02)")
    p_tm.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_tm.add_argument("--data-version", required=True)
    p_tm.add_argument("--qc-run", default=None)
    p_tm.add_argument("--model-version", default=None)
    p_tm.add_argument("--horizon-days", default=7, type=int)
    p_tm.add_argument("--cfg", default="configs/mastitis_risk.yaml")
    p_tm.set_defaults(func=cmd_train_mastitis)

    p_sm = sub.add_parser("score-mastitis", help="Score mastitis risk model (T4-02)")
    p_sm.add_argument("--artifacts", default="artifacts", help="Artifacts root directory")
    p_sm.add_argument("--data-version", required=True)
    p_sm.add_argument("--model-version", required=True)
    p_sm.add_argument("--scoring-run", default=None)
    p_sm.add_argument("--asof-date", default=None, help="ISO date YYYY-MM-DD; default=max date in cow_day")
    p_sm.add_argument("--cfg", default="configs/mastitis_risk.yaml")
    p_sm.set_defaults(func=cmd_score_mastitis)


