from __future__ import annotations

import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
ADULT = ROOT / "deploy" / "adult"

REQUIRED_SERVICES = {
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


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> None:
    base = load_yaml(ADULT / "compose.yaml")
    services = set((base.get("services") or {}).keys())
    missing = REQUIRED_SERVICES - services
    if missing:
        raise SystemExit(f"missing services: {sorted(missing)}")
    for name in ["backend-api", "worker", "scheduler", "postgres", "redis", "artifact-storage", "web-frontend", "reverse-proxy"]:
        svc = (base.get("services") or {}).get(name) or {}
        if name != "artifact-storage-bootstrap" and "healthcheck" not in svc:
            raise SystemExit(f"service {name} missing healthcheck")
    for env_name in ["dev", "test", "stage", "prod"]:
        env_path = ADULT / "env" / f"{env_name}.env.example"
        if not env_path.exists():
            raise SystemExit(f"missing env profile: {env_path}")
        compose_path = ADULT / f"compose.{env_name}.yaml"
        if not compose_path.exists():
            raise SystemExit(f"missing compose overlay: {compose_path}")
    for rel in [
        "nginx/nginx.conf",
        "nginx/conf.d/genomeai.conf",
        "docker/python-service.Dockerfile",
        "docker/web-app.Dockerfile",
        "ops/backup_host.sh",
        "ops/restore_host.sh",
        "k8s/kustomization.yaml",
        "prometheus/prometheus.yml",
    ]:
        if not (ADULT / rel).exists():
            raise SystemExit(f"missing deployment artifact: {rel}")
    print(json.dumps({"status": "ok", "services": sorted(services), "profiles": ["dev", "test", "stage", "prod"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
