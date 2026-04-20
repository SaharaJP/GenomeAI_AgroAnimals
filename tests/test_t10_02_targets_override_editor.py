from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.kpi_targets import load_kpi_targets, resolve_target_spec, upsert_target_rule, save_override_yaml, reset_override


def test_targets_override_roundtrip(tmp_path, monkeypatch):
    # Create a minimal base config at the same relative path expected by the system
    cfg_rel = Path("configs/kpi/kpi_targets_v1.yaml")
    cfg_abs = tmp_path / cfg_rel
    cfg_abs.parent.mkdir(parents=True, exist_ok=True)
    cfg_abs.write_text(
        """version: '1'\n\ndefaults:\n  kpis:\n    milk_total_kg_7d:\n      target: 100000\n      direction: higher_better\n      warn_pct: 0.05\n      alert_pct: 0.10\n\ntargets: []\n""",
        encoding="utf-8",
    )

    # Work in tmp_path so relative cfg_path resolves
    monkeypatch.chdir(tmp_path)

    override_dir = tmp_path / "web_storage" / "config_overrides"

    base = load_kpi_targets(cfg_path=cfg_rel, override_dir=override_dir)
    spec0 = resolve_target_spec(base, kpi_id="milk_total_kg_7d", scope={"tenant_id": "default", "farm_id": "FARM_001"})
    assert spec0 is not None
    assert spec0.target == 100000

    new_cfg = upsert_target_rule(
        base,
        scope={"tenant_id": "default", "farm_id": "FARM_001"},
        kpi_updates={"milk_total_kg_7d": {"target": 150000, "direction": "higher_better", "warn_pct": 0.04, "alert_pct": 0.08}},
        updated_by="tester",
        comment="unit test",
    )
    out_path = save_override_yaml(new_cfg, override_dir=override_dir, cfg_path=cfg_rel)
    assert out_path.exists()

    cfg2 = load_kpi_targets(cfg_path=cfg_rel, override_dir=override_dir)
    assert str(cfg2.get("_source") or "").endswith(str(out_path))
    spec2 = resolve_target_spec(cfg2, kpi_id="milk_total_kg_7d", scope={"tenant_id": "default", "farm_id": "FARM_001"})
    assert spec2 is not None
    assert spec2.target == 150000

    # Reset override
    removed = reset_override(override_dir=override_dir, cfg_path=cfg_rel)
    assert removed is True
    cfg3 = load_kpi_targets(cfg_path=cfg_rel, override_dir=override_dir)
    spec3 = resolve_target_spec(cfg3, kpi_id="milk_total_kg_7d", scope={"tenant_id": "default", "farm_id": "FARM_001"})
    assert spec3 is not None
    assert spec3.target == 100000
