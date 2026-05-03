from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd

from genomeai.economics_v2 import run_economics_v2
from genomeai.unit_economics import run_unit_economics
from genomeai.roi_attribution import run_roi_attribution, load_roi


def test_t11_03_roi_attribution_integration(tmp_path: Path) -> None:
    """Integration: economics_v2 -> unit_economics -> ROI attribution (decision_log.csv)."""

    artifacts = tmp_path / "artifacts"
    dv = "dv_t11_03_roi"
    input_dir = Path("data/fixtures/target_v2")

    # 1) economics_v2 for a day that includes vet/repro/cull events
    econ = run_economics_v2(
        artifacts_root=artifacts,
        data_version=dv,
        input_dir=input_dir,
        date_from="2025-01-10",
        date_to="2025-01-10",
        tenant_id="default",
    )
    assert econ.get("ok"), econ

    # 2) unit_economics
    ue = run_unit_economics(
        artifacts_root=artifacts,
        data_version=dv,
        input_dir=input_dir,
        economics_run=str(econ.get("economics_run")),
        tenant_id="default",
        date_from="2025-01-10",
        date_to="2025-01-10",
    )
    assert ue.get("ok"), ue

    # 3) write a minimal decision_log.csv (legacy offline)
    dec_dir = artifacts / dv / "decisions"
    dec_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "animal_id": "A1001",
                "recommendation_type": "insemination",
                "decision": "accept",
                "comment": "ok",
                "scoring_run": "scoring_dummy",
                "created_at_utc": "2025-01-10T12:00:00Z",
            }
        ]
    )
    df.to_csv(dec_dir / "decision_log.csv", index=False)

    # 3b) create a minimal web.db with done task for pen (group ROI)
    # pick any pen_id available in unit_economics_group_daily
    udir = artifacts / dv / "unit_economics" / str(ue.get("unit_econ_run"))
    gdf = pd.read_csv(udir / "unit_economics_group_daily.csv")
    pen_rows = gdf[gdf["level"].astype(str) == "pen"].copy()
    assert not pen_rows.empty
    pen_id = str(pen_rows.iloc[0]["pen_id"])

    # fixtures may contain only one pen; add a synthetic control pen in the same site/farm for group DiD test
    ctrl_pen_id = f"{pen_id}_CTRL"
    base = pen_rows.iloc[0].copy()
    base["pen_id"] = ctrl_pen_id
    # slight difference to avoid degenerate cases
    try:
        base["margin_rub"] = float(base.get("margin_rub") or 0.0) + 10.0
    except Exception:
        pass
    gdf2 = pd.concat([gdf, pd.DataFrame([base])], ignore_index=True)
    gdf2.to_csv(udir / "unit_economics_group_daily.csv", index=False)

    webdb = tmp_path / "web.db"
    conn = sqlite3.connect(str(webdb))
    try:
        conn.execute(
            """
            CREATE TABLE tasks_v1 (
                task_id TEXT,
                tenant_id TEXT,
                object_type TEXT,
                object_id TEXT,
                task_type TEXT,
                status TEXT,
                title TEXT,
                closed_at TEXT,
                updated_at TEXT,
                closed_comment TEXT,
                closed_reason TEXT,
                data_version TEXT,
                qc_run TEXT,
                model_version TEXT,
                scoring_run TEXT,
                report_version TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO tasks_v1 (
                task_id, tenant_id, object_type, object_id, task_type, status, title,
                closed_at, updated_at, closed_comment, closed_reason,
                data_version, qc_run, model_version, scoring_run, report_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "T1",
                "default",
                "pen",
                pen_id,
                "feed_adjustment",
                "done",
                "Feed adjustment",
                "2025-01-10T12:00:00Z",
                "2025-01-10T12:00:00Z",
                "ok",
                "",
                dv,
                "",
                "",
                "scoring_dummy",
                "",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # 3c) custom config to make diff-in-diff testable on 1-day fixtures
    cfg = tmp_path / "roi_cfg.yaml"
    cfg.write_text(
        """
roi:
  window_days: 1
  include_action_day: true
  min_coverage: 0.0
  eps_cost: 1.0e-9
  method: diff_in_diff
  control:
    enabled: true
    scope: pen
    min_control_animals: 1
    min_coverage: 0.0
    exclude_any_action_in_window: false
    exclude_same_action_type_in_window: false
  group_did:
    enabled: true
    pen_control_scope: site
    site_control_scope: farm
    min_control_groups: 1
    min_coverage: 0.0
    exclude_any_action_in_window: false
    exclude_same_action_type_in_window: false

  outputs:
    action_series: true
    action_components: true
    details_max_actions: 50

sources:
  decision_log_csv:
    enabled: true
    accepted_values: ["accept"]
  web_db:
    enabled: true

cost_mapping:
  rules:
    - match_any: ["insemination", "ai", "осемен", "инсем"]
      cost_param: "insemination_cost_rub"
    - match_any: ["mastitis", "treat", "леч", "вет", "antibi"]
      cost_param: "vet_cost_per_treatment_event_rub"

limitations: []
""",
        encoding="utf-8",
    )

    # 4) roi attribution
    roi = run_roi_attribution(
        artifacts_root=artifacts,
        data_version=dv,
        cfg_path=cfg,
        unit_econ_run=str(ue.get("unit_econ_run")),
        tenant_id="default",
        web_db_path=webdb,
    )
    assert roi.get("ok"), roi

    rid, dfs, _ = load_roi(artifacts_root=artifacts, data_version=dv, roi_run=str(roi.get("roi_run")))
    assert rid

    actions = dfs["actions"]
    assert not actions.empty

    # quality breakdown artifact
    qdf = dfs.get("quality")
    assert qdf is not None
    assert not qdf.empty

    # optional detail artifacts should be present with outputs.* enabled
    sdf = dfs.get("series")
    cdf = dfs.get("components")
    assert sdf is not None
    assert cdf is not None
    assert not sdf.empty
    assert not cdf.empty
    assert "treated_margin_rub" in sdf.columns
    assert "component" in cdf.columns

    # find animal row
    arow = actions[actions["object_type"].astype(str) == "animal"].iloc[0]
    assert str(arow.get("object_id")) == "A1001"

    # cost mapping should work from economics_v2 formulas_catalog
    assert float(arow.get("cost_rub")) == 800.0
    assert str(arow.get("cost_param")) == "insemination_cost_rub"

    # With 1-day unit economics, windows will be low coverage (treated and/or control)
    assert str(arow.get("quality_flag")) in {"OK", "LOW_COVERAGE"}

    # internal consistency: used columns must be consistent
    wd = int(arow.get("window_days"))
    dpd_used = float(arow.get("delta_margin_per_day_used"))
    dw_used = float(arow.get("delta_margin_window_used"))
    assert abs(dw_used - dpd_used * wd) < 1e-6

    # raw consistency preserved
    dpd = float(arow.get("delta_margin_per_day"))
    dw = float(arow.get("delta_margin_window"))
    assert abs(dw - dpd * wd) < 1e-6

    # find pen row (from web.db tasks_v1)
    prow = actions[actions["object_type"].astype(str) == "pen"].iloc[0]
    assert str(prow.get("object_id")) == pen_id
    # should use diff-in-diff when control exists and cfg allows it
    assert str(prow.get("method")) == "diff_in_diff"
