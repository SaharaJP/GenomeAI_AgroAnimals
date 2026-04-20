from __future__ import annotations

from pathlib import Path

import yaml


def test_qc_rules_v2_catalog_has_30_plus_rules():
    path = Path("configs/qc_rules_v2.yaml")
    assert path.exists(), "configs/qc_rules_v2.yaml missing"
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))

    rules = obj.get("rules", [])
    assert isinstance(rules, list)
    assert len(rules) >= 30, f"expected >=30 rules, got {len(rules)}"


def test_qc_rules_v2_catalog_fields_and_uniqueness():
    obj = yaml.safe_load(Path("configs/qc_rules_v2.yaml").read_text(encoding="utf-8"))
    rules = obj["rules"]

    ids = [r.get("id") for r in rules]
    assert len(ids) == len(set(ids)), "rule ids must be unique"

    allowed_sev = {"BLOCKER", "MAJOR", "MINOR"}
    for r in rules:
        assert r.get("id"), "rule.id is required"
        assert r.get("domain"), f"rule {r.get('id')} missing domain"
        assert r.get("dataset"), f"rule {r.get('id')} missing dataset"
        assert r.get("type"), f"rule {r.get('id')} missing type"
        assert r.get("severity") in allowed_sev, f"bad severity for {r.get('id')}"
        assert r.get("message"), f"rule {r.get('id')} missing message"
        assert r.get("remediation"), f"rule {r.get('id')} missing remediation"

        # If alert mapping exists, it must be explicit
        alert = r.get("alert")
        if alert:
            assert isinstance(alert, dict)
            assert "create" in alert, f"rule {r.get('id')} alert.create is required"
