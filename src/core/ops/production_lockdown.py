from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from core.infra.queue_runtime import build_queue_runtime_summary_payload
from core.infra.runtime_auth_storage import auth_storage_diagnostics
from core.infra.runtime_state_storage import runtime_state_storage_diagnostics
from core.infra.runtime_storage import resolve_runtime_storage_settings, runtime_storage_diagnostics

ADULT_PROFILES = {"adult", "prod", "stage"}
INTERNAL_WEB_LOGIN_MODES = {"enabled", "disabled", "support_only"}


class ProductionLockdownError(RuntimeError):
    """Raised when production lockdown invariants are violated."""


@dataclass(frozen=True)
class ProductionProfileLockdownReport:
    profile: str
    adult_mode: bool
    lockdown_active: bool
    runtime_storage_backend: str
    runtime_state_backend: str
    queue_backend: str
    auth_backend: str
    auth_mode: str
    internal_web_login_mode: str
    internal_web_login_allowed: bool
    internal_web_login_justification_present: bool
    compatibility_flags: dict[str, Any]
    forbidden_tails_status: dict[str, Any]
    startup_gates: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def current_profile() -> str:
    return str(os.environ.get("GENOMEAI_DEPLOY_PROFILE") or "dev").strip().lower() or "dev"


def is_adult_profile(profile: str | None = None) -> bool:
    return str(profile or current_profile()).strip().lower() in ADULT_PROFILES


def internal_web_login_mode() -> str:
    profile = current_profile()
    default = "disabled" if is_adult_profile(profile) else "enabled"
    mode = str(os.environ.get("GENOMEAI_INTERNAL_WEB_LOGIN_MODE") or default).strip().lower() or default
    if mode not in INTERNAL_WEB_LOGIN_MODES:
        raise ProductionLockdownError(
            f"GENOMEAI_INTERNAL_WEB_LOGIN_MODE должен быть одним из {sorted(INTERNAL_WEB_LOGIN_MODES)}, получено: {mode!r}"
        )
    return mode


def internal_web_login_justification() -> str:
    return str(os.environ.get("GENOMEAI_INTERNAL_WEB_LOGIN_JUSTIFICATION") or "").strip()


def internal_web_login_allowed() -> bool:
    mode = internal_web_login_mode()
    if mode == "disabled":
        return False
    if mode == "enabled":
        return True
    return bool(internal_web_login_justification())


def _build_report(*, settings: Any) -> ProductionProfileLockdownReport:
    runtime = resolve_runtime_storage_settings(
        project_root=settings.project_root,
        storage_dir=settings.storage_dir,
        sqlite_db_path=getattr(settings, "db_path", settings.storage_dir / "web.db"),
    )
    storage = runtime_storage_diagnostics(runtime).as_dict()
    state = runtime_state_storage_diagnostics().as_dict()
    queue = build_queue_runtime_summary_payload(queue_names=["default"])
    auth = auth_storage_diagnostics(settings=settings).as_dict()
    profile = str(storage.get("profile") or current_profile())
    adult_mode = bool(storage.get("adult_mode"))
    login_mode = internal_web_login_mode()
    login_allowed = internal_web_login_allowed()
    justification_present = bool(internal_web_login_justification())

    compatibility_flags = {
        "runtime_storage_compat_mode": bool(storage.get("compat_mode")),
        "runtime_state_compat_mode": bool(state.get("compat_mode")),
        "queue_compat_mode": bool(queue.get("compat_mode")),
        "legacy_cookie_fallback_allowed": bool(auth.get("legacy_cookie_fallback_allowed")),
        "internal_web_login_mode": login_mode,
        "internal_web_login_allowed": login_allowed,
        "web_disable_worker": str(os.environ.get("GENOMEAI_WEB_DISABLE_WORKER") or ""),
    }

    forbidden_tails_status = {
        "legacy_storage_fallback_disabled": (not adult_mode) or str(storage.get("backend") or "sqlite") == "postgres",
        "queue_fallback_disabled": (not adult_mode) or str(queue.get("backend") or "sqlite") == "redis",
        "legacy_cookie_session_bypass_disabled": (not adult_mode) or (not bool(auth.get("legacy_cookie_fallback_allowed"))),
        "internal_web_login_disabled": (not adult_mode) or (not login_allowed),
        "hidden_fallback_detected": bool(storage.get("forbidden_fallback_detected")) or bool(auth.get("forbidden_fallback_detected")),
        "embedded_worker_active_in_web": str(os.environ.get("GENOMEAI_WEB_DISABLE_WORKER") or "") != "1" if adult_mode and str(queue.get("backend") or "sqlite") == "redis" else False,
    }
    lockdown_active = all(
        [
            bool(forbidden_tails_status["legacy_storage_fallback_disabled"]),
            bool(forbidden_tails_status["queue_fallback_disabled"]),
            bool(forbidden_tails_status["legacy_cookie_session_bypass_disabled"]),
            bool(forbidden_tails_status["internal_web_login_disabled"]),
            not bool(forbidden_tails_status["hidden_fallback_detected"]),
            not bool(forbidden_tails_status["embedded_worker_active_in_web"]),
        ]
    ) if adult_mode else True

    startup_gates = {
        "runtime_storage_migration_status": str(storage.get("migration_status") or "unknown"),
        "queue_broker_status": str(queue.get("broker_status") or "unknown"),
        "auth_backend": str(auth.get("backend") or "unknown"),
        "lockdown_ready": lockdown_active,
    }

    return ProductionProfileLockdownReport(
        profile=profile,
        adult_mode=adult_mode,
        lockdown_active=lockdown_active,
        runtime_storage_backend=str(storage.get("backend") or "unknown"),
        runtime_state_backend=str(state.get("backend") or state.get("primary_runtime_state_backend") or "unknown"),
        queue_backend=str(queue.get("backend") or "unknown"),
        auth_backend=str(auth.get("backend") or "unknown"),
        auth_mode="server_session_rbac_only" if not bool(auth.get("legacy_cookie_fallback_allowed")) else "compat_legacy_cookie_allowed",
        internal_web_login_mode=login_mode,
        internal_web_login_allowed=login_allowed,
        internal_web_login_justification_present=justification_present,
        compatibility_flags=compatibility_flags,
        forbidden_tails_status=forbidden_tails_status,
        startup_gates=startup_gates,
    )


def production_lockdown_report(*, settings: Any | None = None) -> ProductionProfileLockdownReport:
    if settings is None:
        from core.infra.web_db import get_settings
        settings = get_settings()
    return _build_report(settings=settings)


def validate_production_lockdown(*, settings: Any | None = None) -> ProductionProfileLockdownReport:
    report = production_lockdown_report(settings=settings)
    if not report.adult_mode:
        return report
    if report.internal_web_login_mode == "support_only" and not report.internal_web_login_justification_present:
        raise ProductionLockdownError(
            "GENOMEAI_INTERNAL_WEB_LOGIN_MODE=support_only требует GENOMEAI_INTERNAL_WEB_LOGIN_JUSTIFICATION"
        )
    if report.internal_web_login_allowed:
        raise ProductionLockdownError(
            "adult/prod/stage profile запрещает internal web login; используйте GENOMEAI_INTERNAL_WEB_LOGIN_MODE=disabled"
        )
    if not report.lockdown_active:
        raise ProductionLockdownError(
            f"production lockdown нарушен: {report.forbidden_tails_status}"
        )
    return report


__all__ = [
    "ProductionLockdownError",
    "ProductionProfileLockdownReport",
    "current_profile",
    "internal_web_login_allowed",
    "internal_web_login_justification",
    "internal_web_login_mode",
    "is_adult_profile",
    "production_lockdown_report",
    "validate_production_lockdown",
]
