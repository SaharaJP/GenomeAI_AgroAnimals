"""T32-08 Android field app foundation — source-presence and structural smoke tests."""
from __future__ import annotations

from pathlib import Path

import pytest

MOBILE_ROOT = Path(__file__).resolve().parents[1] / "mobile_android"
DOMAIN_ROOT = MOBILE_ROOT / "app/src/main/java/com/genomeai/agroanimals/mobile"


REQUIRED_KOTLIN_SOURCES = [
    "domain/Role.kt",
    "domain/MobileDestinations.kt",
    "domain/MobileNavigationPolicy.kt",
    "domain/sync/SyncModels.kt",
    "domain/sync/SyncQueuePolicy.kt",
    "auth/AuthModels.kt",
    "api/MobileContracts.kt",
]


@pytest.mark.parametrize("rel", REQUIRED_KOTLIN_SOURCES)
def test_kotlin_source_present(rel: str) -> None:
    path = DOMAIN_ROOT / rel
    assert path.exists(), f"Required Kotlin source missing: {rel}"
    assert path.stat().st_size > 0, f"Kotlin source is empty: {rel}"


def test_role_kt_defines_roles() -> None:
    content = (DOMAIN_ROOT / "domain/Role.kt").read_text(encoding="utf-8")
    for role in ("Admin", "Viewer", "Veterinarian", "HerdManager"):
        assert role in content, f"Role.kt missing role enum entry: {role}"


def test_mobile_destinations_kt_defines_screens() -> None:
    content = (DOMAIN_ROOT / "domain/MobileDestinations.kt").read_text(encoding="utf-8")
    for screen in ("TodayWorklists", "AlertsNow"):
        assert screen in content, f"MobileDestinations.kt missing screen: {screen}"


def test_navigation_policy_kt_nonempty() -> None:
    content = (DOMAIN_ROOT / "domain/MobileNavigationPolicy.kt").read_text(encoding="utf-8")
    assert len(content.strip()) > 0, "MobileNavigationPolicy.kt is empty"


def test_sync_queue_policy_kt_nonempty() -> None:
    content = (DOMAIN_ROOT / "domain/sync/SyncQueuePolicy.kt").read_text(encoding="utf-8")
    assert "SyncQueuePolicy" in content


def test_auth_models_kt_defines_session() -> None:
    content = (DOMAIN_ROOT / "auth/AuthModels.kt").read_text(encoding="utf-8")
    assert "token" in content.lower() or "session" in content.lower() or "Auth" in content


def test_mobile_contracts_kt_nonempty() -> None:
    content = (DOMAIN_ROOT / "api/MobileContracts.kt").read_text(encoding="utf-8")
    assert "Dto" in content or "Request" in content or "Response" in content or len(content.strip()) > 100
