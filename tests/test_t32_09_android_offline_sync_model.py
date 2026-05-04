"""T32-09 Android offline sync model — source-presence and structural smoke tests."""
from __future__ import annotations

from pathlib import Path

import pytest

MOBILE_ROOT = Path(__file__).resolve().parents[1] / "mobile_android"
SYNC_ROOT = MOBILE_ROOT / "app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync"
CONTRACT_ROOT = MOBILE_ROOT / "contract_smoke"


REQUIRED_MODEL_SOURCES = [
    "SyncModels.kt",
    "SyncQueuePolicy.kt",
    "SyncRetryPolicy.kt",
    "SyncLifecyclePolicy.kt",
    "SyncConflictPolicy.kt",
    "OfflineSyncLocalStore.kt",
    "InMemoryOfflineSyncLocalStore.kt",
    "SyncTransport.kt",
    "SyncDiagnostics.kt",
    "OfflineSyncService.kt",
]


@pytest.mark.parametrize("fname", REQUIRED_MODEL_SOURCES)
def test_sync_model_source_present(fname: str) -> None:
    path = SYNC_ROOT / fname
    assert path.exists(), f"Required sync model Kotlin source missing: {fname}"
    assert path.stat().st_size > 0, f"Sync model Kotlin source is empty: {fname}"


def test_offline_sync_service_smoke_present() -> None:
    path = CONTRACT_ROOT / "OfflineSyncServiceSmoke.kt"
    assert path.exists(), "OfflineSyncServiceSmoke.kt missing from contract_smoke/"
    assert path.stat().st_size > 0


def test_offline_sync_local_store_defines_interface() -> None:
    content = (SYNC_ROOT / "OfflineSyncLocalStore.kt").read_text(encoding="utf-8")
    assert "OfflineSyncLocalStore" in content


def test_in_memory_store_implements_interface() -> None:
    content = (SYNC_ROOT / "InMemoryOfflineSyncLocalStore.kt").read_text(encoding="utf-8")
    assert "InMemoryOfflineSyncLocalStore" in content


def test_offline_sync_service_nonempty() -> None:
    content = (SYNC_ROOT / "OfflineSyncService.kt").read_text(encoding="utf-8")
    assert "OfflineSyncService" in content


def test_sync_diagnostics_nonempty() -> None:
    content = (SYNC_ROOT / "SyncDiagnostics.kt").read_text(encoding="utf-8")
    assert "SyncDiagnostics" in content or "diagnostic" in content.lower()


def test_sync_transport_nonempty() -> None:
    content = (SYNC_ROOT / "SyncTransport.kt").read_text(encoding="utf-8")
    assert "SyncTransport" in content
