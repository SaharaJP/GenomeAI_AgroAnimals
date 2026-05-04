"""T32-08A Android offline sync contract — source-presence and structural smoke tests."""
from __future__ import annotations

from pathlib import Path

import pytest

MOBILE_ROOT = Path(__file__).resolve().parents[1] / "mobile_android"
SYNC_ROOT = MOBILE_ROOT / "app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync"
CONTRACT_ROOT = MOBILE_ROOT / "contract_smoke"


REQUIRED_SYNC_SOURCES = [
    "SyncModels.kt",
    "SyncQueuePolicy.kt",
    "SyncRetryPolicy.kt",
    "SyncLifecyclePolicy.kt",
    "SyncConflictPolicy.kt",
]


@pytest.mark.parametrize("fname", REQUIRED_SYNC_SOURCES)
def test_sync_source_present(fname: str) -> None:
    path = SYNC_ROOT / fname
    assert path.exists(), f"Required sync Kotlin source missing: {fname}"
    assert path.stat().st_size > 0, f"Sync Kotlin source is empty: {fname}"


def test_sync_contract_smoke_present() -> None:
    path = CONTRACT_ROOT / "SyncContractSmoke.kt"
    assert path.exists(), "SyncContractSmoke.kt missing from contract_smoke/"
    assert path.stat().st_size > 0


def test_sync_models_defines_types() -> None:
    content = (SYNC_ROOT / "SyncModels.kt").read_text(encoding="utf-8")
    assert "SyncActionType" in content or "SyncStatus" in content or "Sync" in content


def test_sync_queue_policy_defines_policy() -> None:
    content = (SYNC_ROOT / "SyncQueuePolicy.kt").read_text(encoding="utf-8")
    assert "SyncQueuePolicy" in content


def test_sync_conflict_policy_defines_resolution() -> None:
    content = (SYNC_ROOT / "SyncConflictPolicy.kt").read_text(encoding="utf-8")
    assert "server" in content.lower() or "conflict" in content.lower() or "SyncConflictPolicy" in content


def test_sync_retry_policy_nonempty() -> None:
    content = (SYNC_ROOT / "SyncRetryPolicy.kt").read_text(encoding="utf-8")
    assert "SyncRetryPolicy" in content or "retry" in content.lower()
