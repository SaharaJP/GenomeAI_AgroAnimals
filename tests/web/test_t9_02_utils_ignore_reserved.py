from __future__ import annotations

from pathlib import Path

from web_cabinet.utils import list_data_versions


def test_list_data_versions_ignores_reserved_dirs(tmp_path: Path) -> None:
    # create a valid dv folder and a legacy operational folder
    (tmp_path / "dv1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "backups").mkdir(parents=True, exist_ok=True)

    dvs = list_data_versions(tmp_path)
    assert "dv1" in dvs
    assert "runs" not in dvs
    assert "backups" not in dvs
