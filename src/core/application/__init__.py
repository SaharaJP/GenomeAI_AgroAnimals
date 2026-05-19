from __future__ import annotations

from core.application.refactor_verify import (
    VerifyRefactorCommand,
    execute_verify_refactor,
    parse_scenarios_arg,
    render_verify_refactor_cli_lines,
)

__all__ = [
    "VerifyRefactorCommand",
    "execute_verify_refactor",
    "parse_scenarios_arg",
    "render_verify_refactor_cli_lines",
]
from core.application.job_runner import (
    PIPELINE_JOB_KEYS,
    PipelineExecutionResult,
    PipelineJobRequest,
    build_ingest_job_request,
    build_pack_job_request,
    build_qc_job_request,
    build_report_job_request,
    build_repro_job_request,
    build_score_job_request,
    build_train_job_request,
    can_execute_job_in_application,
    dispatch_pipeline_cli,
    enqueue_pipeline_job,
    infer_request_refs,
    make_job_log_path,
    parse_keyvals,
    pipeline_job_environment,
    pipeline_request_from_job,
    run_pipeline_job,
    run_pipeline_job_from_record,
    run_pipeline_job_logged,
)

__all__ += [
    "PIPELINE_JOB_KEYS",
    "PipelineExecutionResult",
    "PipelineJobRequest",
    "build_ingest_job_request",
    "build_pack_job_request",
    "build_qc_job_request",
    "build_report_job_request",
    "build_repro_job_request",
    "build_score_job_request",
    "build_train_job_request",
    "can_execute_job_in_application",
    "dispatch_pipeline_cli",
    "enqueue_pipeline_job",
    "infer_request_refs",
    "make_job_log_path",
    "parse_keyvals",
    "pipeline_job_environment",
    "pipeline_request_from_job",
    "run_pipeline_job",
    "run_pipeline_job_from_record",
    "run_pipeline_job_logged",
]

from core.application.qc_reporting import (
    alerts_to_frame,
    build_bad_rows_frames,
    build_issue_counts,
    build_row_counts,
    issues_to_frame,
    write_qc_output_bundle,
    write_qc_report_xlsx,
)
from core.application.qc_registration import register_qc_run_outputs
from core.application.qc_paths import (
    find_latest_qc2_run,
    find_latest_qc2_run_dir,
    qc2_run_roots,
    resolve_qc2_out_dir,
)
from core.application.qc_rules_engine import (
    QcConfigRef,
    evaluate_rule_based_qc,
    load_qc_config_ref,
    load_qc_rules,
    new_qc_run_id,
    run_qc_rules,
)

__all__ += [
    "alerts_to_frame",
    "build_bad_rows_frames",
    "build_issue_counts",
    "build_row_counts",
    "issues_to_frame",
    "write_qc_output_bundle",
    "write_qc_report_xlsx",
    "register_qc_run_outputs",
    "find_latest_qc2_run",
    "find_latest_qc2_run_dir",
    "qc2_run_roots",
    "resolve_qc2_out_dir",
    "QcConfigRef",
    "evaluate_rule_based_qc",
    "load_qc_config_ref",
    "load_qc_rules",
    "new_qc_run_id",
    "run_qc_rules",
]

from core.application.ml_registry import (
    MlConfigRef,
    default_ml_config_path,
    load_ml_pipeline_config,
    register_model_manifest,
    register_scoring_manifest,
    resolve_ml_config_path,
    write_best_effort_ml_audit,
)
from core.application.ml_pipeline import (
    ScoringSummary,
    TimeSplitBounds,
    TrainSummary,
    build_productivity_feature_frame,
    build_time_split_bounds,
    run_scoring,
    split_feature_frame_time_aware,
    train_productivity_model,
)

__all__ += [
    "MlConfigRef",
    "default_ml_config_path",
    "load_ml_pipeline_config",
    "register_model_manifest",
    "register_scoring_manifest",
    "resolve_ml_config_path",
    "write_best_effort_ml_audit",
    "ScoringSummary",
    "TimeSplitBounds",
    "TrainSummary",
    "build_productivity_feature_frame",
    "build_time_split_bounds",
    "run_scoring",
    "split_feature_frame_time_aware",
    "train_productivity_model",
]

from core.application.ml_artifacts import (
    build_model_surface_snapshot,
    build_scoring_surface_snapshot,
    find_latest_model_version,
    find_latest_scoring_run,
    list_model_entries,
    list_model_versions,
    list_scoring_entries,
    list_scoring_runs,
    load_model_card,
    load_model_registry,
    load_scoring_registry,
    load_scoring_summary,
    load_train_summary,
    resolve_model_dir,
    resolve_scoring_dir,
)

__all__ += [
    "build_model_surface_snapshot",
    "build_scoring_surface_snapshot",
    "find_latest_model_version",
    "find_latest_scoring_run",
    "list_model_entries",
    "list_model_versions",
    "list_scoring_entries",
    "list_scoring_runs",
    "load_model_card",
    "load_model_registry",
    "load_scoring_registry",
    "load_scoring_summary",
    "load_train_summary",
    "resolve_model_dir",
    "resolve_scoring_dir",
]

from core.application.economics_summary import build_economics_summary_v1

__all__ += [
    "build_economics_summary_v1",
]
