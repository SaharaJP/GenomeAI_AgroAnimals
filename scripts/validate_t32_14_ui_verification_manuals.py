#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]

WEB_DOC = ROOT / "docs" / "ui_functional_verification_web.md"
ANDROID_DOC = ROOT / "docs" / "ui_functional_verification_android.md"
UAT_DOC = ROOT / "docs" / "full_uat_checklist.md"


def ensure(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"Missing required document: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def main() -> int:
    web = ensure(WEB_DOC)
    android = ensure(ANDROID_DOC)
    uat = ensure(UAT_DOC)

    required_web_tokens = [
        "/daily-summary",
        "/alerts",
        "/worklists",
        "/planner",
        "/profiles/animal/DEMO_COW_1002",
        "/profiles/group/PEN_N1_LACT",
        "/reports",
        "/assistant",
        "/reproduction",
        "/vet",
        "/treatments",
        "/economics",
        "/support",
        "/readiness",
        "/admin",
        "preview parity",
        "admin command center",
        "bash scripts/smoke_t32_05_react_daily_operations.sh",
        "bash scripts/smoke_t32_06_react_profiles_reports_assistant.sh",
        "bash scripts/smoke_t32_07_react_extended_surface.sh",
    ]
    for token in required_web_tokens:
        if token not in web:
            raise SystemExit(f"Web manual missing token: {token}")

    required_android_tokens = [
        "Роль для UI-проверки",
        "Today worklists",
        "Alerts now",
        "Quick animal card",
        "Quick event entry",
        "Task completion",
        "Shift handover",
        "bash scripts/smoke_t32_08_android_field_app.sh",
        "bash scripts/smoke_t32_08a_android_offline_sync_contract.sh",
        "bash scripts/smoke_t32_09_android_offline_sync_model.sh",
        "не web wrapper",
    ]
    for token in required_android_tokens:
        if token not in android:
            raise SystemExit(f"Android manual missing token: {token}")

    required_uat_ids = [
        "WEB-AUTH-001",
        "WEB-OPS-001",
        "WEB-PROFILE-001",
        "WEB-REPORT-002",
        "WEB-REPRO-001",
        "WEB-ECON-001",
        "AND-AUTH-001",
        "AND-EVENT-001",
        "AND-OFFLINE-001",
    ]
    for token in required_uat_ids:
        if token not in uat:
            raise SystemExit(f"UAT checklist missing scenario ID: {token}")

    result = {
        "status": "ok",
        "web_doc": str(WEB_DOC.relative_to(ROOT)),
        "android_doc": str(ANDROID_DOC.relative_to(ROOT)),
        "uat_doc": str(UAT_DOC.relative_to(ROOT)),
        "web_route_count_checked": 15,
        "android_flow_count_checked": 8,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
