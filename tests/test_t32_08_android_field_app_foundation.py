from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_foundation_files_exist():
    required = [
        ROOT / "mobile_android" / "settings.gradle.kts",
        ROOT / "mobile_android" / "build.gradle.kts",
        ROOT / "mobile_android" / "app" / "build.gradle.kts",
        ROOT / "mobile_android" / "app" / "src" / "main" / "AndroidManifest.xml",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "MainActivity.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "ui" / "shell" / "AppShell.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "ui" / "screens" / "TodayWorklistsScreen.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "ui" / "screens" / "AlertsNowScreen.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "ui" / "screens" / "QuickAnimalCardScreen.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "ui" / "screens" / "QuickEventEntryScreen.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "ui" / "screens" / "TaskCompletionScreen.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "ui" / "screens" / "ShiftHandoverScreen.kt",
        ROOT / "docs" / "android_field_app_foundation.md",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    assert not missing, f"Missing Android foundation files: {missing}"


def test_android_is_not_web_wrapper():
    doc = (ROOT / "docs" / "android_field_app_foundation.md").read_text(encoding="utf-8")
    assert "отдельное приложение" in doc.lower()
    assert "не web wrapper" in doc.lower() or "не является web wrapper" in doc.lower()


def test_role_aware_navigation_and_sync_policy_present():
    nav = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "MobileNavigationPolicy.kt").read_text(encoding="utf-8")
    sync = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncQueuePolicy.kt").read_text(encoding="utf-8")
    assert "TodayWorklists" in nav and "AlertsNow" in nav and "ShiftHandover" in nav
    assert "QuickEventEntry" in sync and "TaskCompletion" in sync and "ShiftHandover" in sync
