from __future__ import annotations

from pathlib import Path

from genomeai.smoke import run_smoke


def test_smoke_runs_end_to_end(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    res = run_smoke(
        artifacts_root=tmp_path,
        contracts_dir=repo_root / "configs" / "contracts",
        data_dir=repo_root / "data" / "examples",
        mappings_dir=repo_root / "configs" / "mappings",
        out_version="dv_smoke_test",
    )
    assert res["ok"] is True
    summ = res["summary"]
    assert (tmp_path / summ["data_version"] / "pilot_packs" / summ["pack_id"]).exists()