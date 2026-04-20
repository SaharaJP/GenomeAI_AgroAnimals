from __future__ import annotations

import json
from pathlib import Path

from genomeai.run_reproduce import reproduce_run
from genomeai.versioning import get_run_root, write_run_manifest


def test_reproduce_replay(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_test"
    src_run = "score_20260101_000000_aaaaaa"
    src_root = get_run_root(artifacts_root=artifacts, data_version=dv, run_id=src_run)
    (src_root / "scoring").mkdir(parents=True, exist_ok=True)
    (src_root / "scoring" / "dummy.txt").write_text("hello", encoding="utf-8")

    write_run_manifest(
        run_root=src_root,
        manifest={
            "schema": "genomeai.run_manifest.v1",
            "step": "score",
            "data_version": dv,
            "run_id": src_run,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "DONE",
            "outputs": {"run_dir": str(src_root / "scoring")},
        },
    )

    res = reproduce_run(artifacts_root=artifacts, data_version=dv, run_id=src_run, mode="replay")
    assert res["ok"] is True
    new_run = res["new_run_id"]
    dst_root = get_run_root(artifacts_root=artifacts, data_version=dv, run_id=new_run)

    assert (dst_root / "run_manifest.json").exists()
    assert (dst_root / "checksums.json").exists()
    assert (dst_root / "replay" / "scoring" / "dummy.txt").read_text(encoding="utf-8") == "hello"

    m = json.loads((dst_root / "run_manifest.json").read_text(encoding="utf-8"))
    assert m["lineage"]["source_run_id"] == src_run
