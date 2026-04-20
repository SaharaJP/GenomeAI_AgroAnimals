from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    ROOT / "docs" / "deployment_full_guide.md",
    ROOT / "docs" / "operations_runbook.md",
]

REQUIRED_FILES = [
    ROOT / "deploy" / "adult" / "ops" / "post_deploy_smoke.sh",
    ROOT / "deploy" / "adult" / "ops" / "collect_support_bundle.sh",
    ROOT / "deploy" / "adult" / "compose.yaml",
    ROOT / "deploy" / "adult" / "compose.prod.yaml",
    ROOT / "deploy" / "adult" / "env" / "prod.env.example",
    ROOT / "deploy" / "adult" / "ops" / "backup_host.sh",
    ROOT / "deploy" / "adult" / "ops" / "restore_host.sh",
]

REQUIRED_GUIDE_TOKENS = [
    "backend API",
    "web frontend",
    "worker",
    "scheduler",
    "PostgreSQL",
    "Redis",
    "MinIO",
    "TLS",
    "backup",
    "restore",
    "upgrade",
    "rollback",
    "support bundle",
    "Android",
]

REQUIRED_RUNBOOK_TOKENS = [
    "post_deploy_smoke",
    "collect_support_bundle",
    "upgrade",
    "rollback",
    "incident",
    "backup",
    "restore",
]


def main() -> None:
    for path in REQUIRED_DOCS + REQUIRED_FILES:
        if not path.exists():
            raise SystemExit(f"missing required artifact: {path.relative_to(ROOT)}")

    guide = REQUIRED_DOCS[0].read_text(encoding="utf-8")
    runbook = REQUIRED_DOCS[1].read_text(encoding="utf-8")

    for token in REQUIRED_GUIDE_TOKENS:
        if token not in guide:
            raise SystemExit(f"deployment_full_guide missing token: {token}")
    for token in REQUIRED_RUNBOOK_TOKENS:
        if token not in runbook:
            raise SystemExit(f"operations_runbook missing token: {token}")

    print(json.dumps({
        "status": "ok",
        "docs": [str(p.relative_to(ROOT)) for p in REQUIRED_DOCS],
        "ops_scripts": [str(p.relative_to(ROOT)) for p in REQUIRED_FILES if p.name.endswith('.sh')],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
