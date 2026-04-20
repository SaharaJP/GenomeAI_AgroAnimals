from __future__ import annotations

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
ADULT = ROOT / "deploy" / "adult"


def test_docs_and_scripts_exist() -> None:
    assert (ROOT / "docs" / "server_deployment_baseline.md").exists()
    assert (ROOT / "scripts" / "smoke_t32_10_server_deployment.sh").exists()
    assert (ROOT / "scripts" / "validate_t32_10_server_deployment.py").exists()


def test_compose_contains_required_services() -> None:
    data = yaml.safe_load((ADULT / "compose.yaml").read_text(encoding="utf-8"))
    services = set((data.get("services") or {}).keys())
    required = {
        "reverse-proxy",
        "web-frontend",
        "backend-api",
        "worker",
        "scheduler",
        "postgres",
        "redis",
        "artifact-storage",
        "prometheus",
    }
    assert required.issubset(services)


def test_environment_profiles_exist() -> None:
    for name in ["dev", "test", "stage", "prod"]:
        assert (ADULT / f"compose.{name}.yaml").exists()
        assert (ADULT / "env" / f"{name}.env.example").exists()


def test_reverse_proxy_routes_backend_and_frontend() -> None:
    conf = (ADULT / "nginx" / "conf.d" / "genomeai.conf").read_text(encoding="utf-8")
    assert "genomeai_backend_api" in conf
    assert "genomeai_web_frontend" in conf
    assert "location /api/" in conf
    assert "location / {" in conf


def test_backup_restore_and_k8s_baseline_exist() -> None:
    assert (ADULT / "ops" / "backup_host.sh").exists()
    assert (ADULT / "ops" / "restore_host.sh").exists()
    assert (ADULT / "k8s" / "kustomization.yaml").exists()
