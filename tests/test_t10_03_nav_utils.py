from __future__ import annotations

from datetime import date

from streamlit_app.nav_utils import infer_asof_date_iso, infer_report_version


def test_infer_asof_date_prefers_why_asof_date():
    obj = {"why": {"asof_date": "2025-01-31"}, "created_at": "2025-02-01T10:00:00Z"}
    assert infer_asof_date_iso(obj, default=date(2024, 1, 1)) == "2025-01-31"


def test_infer_asof_date_from_attachments():
    obj = {"attachments": [{"asof_date": "2025-01-15"}]}
    assert infer_asof_date_iso(obj, default=date(2024, 1, 1)) == "2025-01-15"


def test_infer_asof_date_from_created_at():
    obj = {"created_at": "2025-01-05T12:30:00+00:00"}
    assert infer_asof_date_iso(obj, default=date(2024, 1, 1)) == "2025-01-05"


def test_infer_asof_date_fallback_default():
    obj = {"title": "x"}
    assert infer_asof_date_iso(obj, default=date(2024, 1, 1)) == "2024-01-01"


def test_infer_report_version():
    assert infer_report_version({"report_version": "run_001"}) == "run_001"
    assert infer_report_version({"run_id": "r2"}) == "r2"
    assert infer_report_version({}) is None
