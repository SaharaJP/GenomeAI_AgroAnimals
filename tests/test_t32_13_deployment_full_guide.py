from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deployment_docs_exist() -> None:
    assert (ROOT / "docs" / "deployment_full_guide.md").exists()
    assert (ROOT / "docs" / "operations_runbook.md").exists()


def test_deployment_guide_mentions_required_sections() -> None:
    text = (ROOT / "docs" / "deployment_full_guide.md").read_text(encoding="utf-8")
    for token in [
        "backend API",
        "web frontend",
        "worker",
        "scheduler",
        "PostgreSQL",
        "Redis",
        "MinIO",
        "upgrade",
        "rollback",
        "support bundle",
        "Android",
    ]:
        assert token in text


def test_ops_scripts_exist_and_are_referenced() -> None:
    guide = (ROOT / "docs" / "deployment_full_guide.md").read_text(encoding="utf-8")
    for rel in [
        "deploy/adult/ops/post_deploy_smoke.sh",
        "deploy/adult/ops/collect_support_bundle.sh",
        "deploy/adult/ops/backup_host.sh",
        "deploy/adult/ops/restore_host.sh",
    ]:
        assert (ROOT / rel).exists()
        assert Path(rel).name in guide


def test_validator_outputs_ok() -> None:
    import subprocess
    result = subprocess.run([
        "python",
        str(ROOT / "scripts" / "validate_t32_13_deployment_full_guide.py"),
    ], capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
