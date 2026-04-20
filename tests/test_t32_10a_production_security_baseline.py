from __future__ import annotations

from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]
ADULT = ROOT / "deploy" / "adult"


def test_docs_and_scripts_exist() -> None:
    assert (ROOT / "docs" / "production_security_and_iam_baseline.md").exists()
    assert (ROOT / "scripts" / "validate_t32_10a_production_security.py").exists()
    assert (ROOT / "scripts" / "smoke_t32_10a_production_security.sh").exists()


def test_compose_network_boundaries_present() -> None:
    data = yaml.safe_load((ADULT / "compose.yaml").read_text(encoding="utf-8"))
    networks = data.get("networks") or {}
    assert {"edge_net", "app_net", "data_net", "ops_net"}.issubset(set(networks))
    assert networks["app_net"]["internal"] is True
    assert networks["data_net"]["internal"] is True
    assert networks["ops_net"]["internal"] is True
    services = data.get("services") or {}
    assert "edge_net" in set((services["reverse-proxy"].get("networks") or []))
    assert "data_net" not in set((services["web-frontend"].get("networks") or []))


def test_stage_and_prod_use_file_secrets() -> None:
    for profile in ["stage", "prod"]:
        content = (ADULT / "env" / f"{profile}.env.example").read_text(encoding="utf-8")
        for key in [
            "GENOMEAI_WEB_SECRET_FILE=",
            "GENOMEAI_INTERNAL_SERVICE_TOKEN_FILE=",
            "GENOMEAI_AUTH_SIGNING_KEY_FILE=",
            "GENOMEAI_AUTH_REFRESH_HMAC_KEY_FILE=",
            "POSTGRES_PASSWORD_FILE=",
            "REDIS_PASSWORD_FILE=",
            "MINIO_ROOT_PASSWORD_FILE=",
        ]:
            assert key in content


def test_security_artifacts_exist() -> None:
    for rel in [
        "configs/security/production_iam_token_policy_v1.json",
        "configs/security/service_trust_policy_v1.json",
        "configs/security/onprem_security_checklist_v1.json",
        "deploy/adult/security/security_headers.conf",
        "deploy/adult/security/tls_server.conf.example",
        "deploy/adult/secrets/README.md",
        "deploy/adult/k8s/secret.example.yaml",
        "deploy/adult/k8s/networkpolicy.example.yaml",
    ]:
        assert (ROOT / rel).exists(), rel


def test_token_policy_matches_server_defaults() -> None:
    policy = json.loads((ROOT / "configs" / "security" / "production_iam_token_policy_v1.json").read_text(encoding="utf-8"))
    assert policy["access_token_ttl_sec"] == 900
    assert policy["refresh_token_ttl_sec"] == 2592000
    assert policy["refresh_rotation_required"] is True


def test_prod_overlay_applies_container_hardening() -> None:
    data = yaml.safe_load((ADULT / "compose.prod.yaml").read_text(encoding="utf-8"))
    services = data.get("services") or {}
    for name in ["reverse-proxy", "web-frontend", "backend-api", "worker", "scheduler"]:
        svc = services[name]
        assert "no-new-privileges:true" in (svc.get("security_opt") or [])
