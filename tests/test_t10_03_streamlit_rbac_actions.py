from __future__ import annotations

from pathlib import Path


def test_rbac_gates_present_for_confirm_recommendation():
    """T10-03: confirm recommendation must be gated by perms (incl. Director)."""

    repo_root = Path(__file__).resolve().parents[1]

    animal = (repo_root / "streamlit_app" / "pages" / "15_Animal_Profile.py").read_text(encoding="utf-8")
    alerts = (repo_root / "streamlit_app" / "pages" / "5_Alert_Center_v2.py").read_text(encoding="utf-8")

    for s in ("PERM_RECS_CONFIRM", "PERM_DECISIONS_WRITE", "PERM_DECISIONLOG_WRITE"):
        assert s in animal
        assert s in alerts
