from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from core.common.time import (
    ensure_utc,
    utc_date,
    utc_date_str,
    utc_isoformat,
    utc_isoformat_z,
    utc_timestamp_compact,
)
from genomeai import versioning


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_t16_01_core_time_helper_preserves_legacy_string_formats() -> None:
    aware = datetime(2026, 3, 19, 12, 34, 56, 987654, tzinfo=timezone.utc)
    legacy_naive = aware.replace(tzinfo=None)

    assert ensure_utc(legacy_naive) == aware
    assert utc_date(aware).isoformat() == legacy_naive.date().isoformat()
    assert utc_date_str(aware) == legacy_naive.strftime("%Y-%m-%d")
    assert utc_timestamp_compact(aware) == legacy_naive.strftime("%Y%m%d_%H%M%S")
    assert utc_isoformat(aware) == legacy_naive.replace(microsecond=0).isoformat() + "+00:00"
    assert utc_isoformat_z(aware) == legacy_naive.replace(microsecond=0).isoformat() + "Z"


def test_t16_01_generate_run_id_keeps_legacy_surface(monkeypatch) -> None:
    monkeypatch.setattr(versioning, "utc_timestamp_compact", lambda: "20260319_123456")
    monkeypatch.setattr(versioning.random, "choices", lambda seq, k: list("abc123"))

    run_id = versioning.generate_run_id(prefix="run")

    assert run_id == "run_20260319_123456_abc123"
    assert re.fullmatch(r"run_\d{8}_\d{6}_[a-z0-9]{6}", run_id)


def test_t16_01_runtime_code_contains_no_datetime_utcnow_calls() -> None:
    runtime_roots = [REPO_ROOT / "src", REPO_ROOT / "web_cabinet", REPO_ROOT / "streamlit_app"]
    offenders: list[str] = []
    for root in runtime_roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "datetime.utcnow(" in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []
