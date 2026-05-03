from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from .migration_pack_import import import_pilot_pack
from .smoke import run_smoke


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SmokeMigrationSummary:
    schema: str
    created_at_utc: str
    ok: bool
    source_artifacts: str
    dest_artifacts: str
    data_version: str
    pack_zip: str
    import_manifest_json: str
    copied_files: int


def run_smoke_migration(
    *,
    artifacts_root: Path,
    contracts_dir: Path,
    data_dir: Path,
    mappings_dir: Path,
) -> Dict[str, object]:
    """End-to-end migration smoke:

    1) Run offline smoke (ingest->qc->train->score->report->pack) into temp artifacts.
    2) Import resulting Pilot Pack into *artifacts_root* (Target layout).

    The result is a checkable proof that Offline artifacts can be transferred into Web Cabinet storage.
    """

    artifacts_root = Path(artifacts_root).resolve()
    contracts_dir = Path(contracts_dir).resolve()
    data_dir = Path(data_dir).resolve()
    mappings_dir = Path(mappings_dir).resolve()

    with tempfile.TemporaryDirectory(prefix="genomeai_smoke_offline_") as td:
        src = Path(td)
        # Step 1: Offline smoke creates pack zip
        sm = run_smoke(
            artifacts_root=src,
            contracts_dir=contracts_dir,
            data_dir=data_dir,
            mappings_dir=mappings_dir,
            out_version=None,
        )
        if not sm.get("ok"):
            return {"ok": False, "reason": "offline_smoke_failed", "details": sm}

        summary = sm["summary"]
        pack_zip = Path(summary["outputs"]["pack_zip"]).resolve()
        dv = str(summary["data_version"])

        # Step 2: Import into destination artifacts root
        imp = import_pilot_pack(pack_zip=pack_zip, artifacts_root=artifacts_root, verify=True, force=False)
        if not imp.get("ok"):
            return {"ok": False, "reason": "import_failed", "import": imp, "offline": sm}

        out = SmokeMigrationSummary(
            schema="genomeai.smoke_migration_summary.v1",
            created_at_utc=_utc_now_iso(),
            ok=True,
            source_artifacts=str(src),
            dest_artifacts=str(artifacts_root),
            data_version=dv,
            pack_zip=str(pack_zip),
            import_manifest_json=str(imp.get("import_manifest_json")),
            copied_files=int(imp.get("copied_files") or 0),
        )
        return {"ok": True, "summary": asdict(out), "offline": sm, "import": imp}
