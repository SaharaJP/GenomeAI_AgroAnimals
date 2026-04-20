from __future__ import annotations

import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
ADULT = ROOT / "deploy" / "adult"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> None:
    compose = load_yaml(ADULT / "compose.yaml")
    services = compose.get("services") or {}
    networks = compose.get("networks") or {}
    required_networks = {"edge_net", "app_net", "data_net", "ops_net"}
    missing_networks = required_networks - set(networks)
    if missing_networks:
        raise SystemExit(f"missing networks: {sorted(missing_networks)}")

    if not (networks.get("app_net") or {}).get("internal", False):
        raise SystemExit("app_net must be internal")
    if not (networks.get("data_net") or {}).get("internal", False):
        raise SystemExit("data_net must be internal")
    if not (networks.get("ops_net") or {}).get("internal", False):
        raise SystemExit("ops_net must be internal")

    reverse_proxy = services.get("reverse-proxy") or {}
    reverse_proxy_networks = set(reverse_proxy.get("networks") or [])
    if "edge_net" not in reverse_proxy_networks:
        raise SystemExit("reverse-proxy must sit in edge_net")

    backend_api = services.get("backend-api") or {}
    backend_networks = set(backend_api.get("networks") or [])
    if not {"app_net", "data_net", "ops_net"}.issubset(backend_networks):
        raise SystemExit("backend-api must sit in app_net,data_net,ops_net")

    web_frontend = services.get("web-frontend") or {}
    web_networks = set(web_frontend.get("networks") or [])
    if "data_net" in web_networks:
        raise SystemExit("web-frontend must not sit in data_net")

    worker_networks = set((services.get("worker") or {}).get("networks") or [])
    scheduler_networks = set((services.get("scheduler") or {}).get("networks") or [])
    if "edge_net" in worker_networks or "edge_net" in scheduler_networks:
        raise SystemExit("worker/scheduler must not sit in edge_net")

    prod_env = (ADULT / "env" / "prod.env.example").read_text(encoding="utf-8")
    stage_env = (ADULT / "env" / "stage.env.example").read_text(encoding="utf-8")
    for required in [
        "GENOMEAI_WEB_SECRET_FILE=",
        "GENOMEAI_INTERNAL_SERVICE_TOKEN_FILE=",
        "GENOMEAI_AUTH_SIGNING_KEY_FILE=",
        "GENOMEAI_AUTH_REFRESH_HMAC_KEY_FILE=",
        "POSTGRES_PASSWORD_FILE=",
        "REDIS_PASSWORD_FILE=",
        "MINIO_ROOT_PASSWORD_FILE=",
    ]:
        if required not in prod_env:
            raise SystemExit(f"prod env missing {required}")
        if required not in stage_env:
            raise SystemExit(f"stage env missing {required}")

    prod_overlay = load_yaml(ADULT / "compose.prod.yaml")
    overlay_services = prod_overlay.get("services") or {}
    for name in ["reverse-proxy", "web-frontend", "backend-api", "worker", "scheduler"]:
        svc = overlay_services.get(name) or {}
        security_opt = svc.get("security_opt") or []
        if "no-new-privileges:true" not in security_opt:
            raise SystemExit(f"{name} missing no-new-privileges in prod overlay")

    required_files = [
        ROOT / "docs" / "production_security_and_iam_baseline.md",
        ROOT / "configs" / "security" / "production_iam_token_policy_v1.json",
        ROOT / "configs" / "security" / "service_trust_policy_v1.json",
        ROOT / "configs" / "security" / "onprem_security_checklist_v1.json",
        ADULT / "security" / "security_headers.conf",
        ADULT / "security" / "tls_server.conf.example",
        ADULT / "secrets" / "README.md",
        ADULT / "ops" / "run_with_runtime_secrets.sh",
        ADULT / "k8s" / "secret.example.yaml",
        ADULT / "k8s" / "networkpolicy.example.yaml",
    ]
    for path in required_files:
        if not path.exists():
            raise SystemExit(f"missing security baseline artifact: {path}")

    token_policy = json.loads((ROOT / "configs" / "security" / "production_iam_token_policy_v1.json").read_text(encoding="utf-8"))
    if int(token_policy.get("access_token_ttl_sec") or 0) != 900:
        raise SystemExit("unexpected access token ttl")
    if int(token_policy.get("refresh_token_ttl_sec") or 0) != 2592000:
        raise SystemExit("unexpected refresh token ttl")
    if not bool(token_policy.get("refresh_rotation_required")):
        raise SystemExit("refresh rotation must be required")

    print(json.dumps({
        "status": "ok",
        "networks": sorted(required_networks),
        "prod_file_secrets": True,
        "token_policy": {
            "access_ttl_sec": token_policy["access_token_ttl_sec"],
            "refresh_ttl_sec": token_policy["refresh_token_ttl_sec"],
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
