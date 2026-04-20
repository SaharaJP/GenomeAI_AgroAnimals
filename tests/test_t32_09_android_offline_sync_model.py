import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t32_09_files_exist():
    required = [
        ROOT / "docs" / "android_offline_sync_model.md",
        ROOT / "specs" / "jsonschema" / "android_offline_sync_model_v1.json",
        ROOT / "configs" / "mobile" / "android_sync_retry_policy_v1.json",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "OfflineSyncLocalStore.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "InMemoryOfflineSyncLocalStore.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncTransport.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncDiagnostics.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "OfflineSyncService.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "data" / "local" / "sync" / "SyncQueueEntity.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "data" / "local" / "sync" / "SyncIncidentEntity.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "data" / "local" / "sync" / "MobileSyncDatabase.kt",
        ROOT / "scripts" / "smoke_t32_09_android_offline_sync_model.sh",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    assert not missing, f"Missing T32-09 files: {missing}"


def test_docs_forbid_silent_conflicts_and_second_source_of_truth():
    doc = (ROOT / "docs" / "android_offline_sync_model.md").read_text(encoding="utf-8").lower()
    assert "silent conflict resolution запрещ" in doc or "silent conflict resolution запрещен" in doc or "silent merge" in doc
    assert "единственным источником истины" in doc
    assert "server audit ack" in doc


def test_sync_model_schema_and_policy_align():
    schema = json.loads((ROOT / "specs" / "jsonschema" / "android_offline_sync_model_v1.json").read_text(encoding="utf-8"))
    policy = json.loads((ROOT / "configs" / "mobile" / "android_sync_retry_policy_v1.json").read_text(encoding="utf-8"))

    action_enum = schema["properties"]["queue_item"]["properties"]["action_type"]["enum"]
    assert action_enum == [
        "QuickEventEntry",
        "TaskCompletion",
        "ShiftHandover",
        "FeedbackSubmission",
        "AssistantLinkedAction",
    ]
    assert policy["silent_merges_allowed"] is False
    assert policy["requires_server_audit_ack"] is True
    assert set(policy["retryable_failure_classes"]) == {"RetryableNetwork", "RetryableServer"}


def test_kotlin_model_contains_traceability_and_diagnostics():
    models = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncModels.kt").read_text(encoding="utf-8")
    service = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "OfflineSyncService.kt").read_text(encoding="utf-8")
    diagnostics = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncDiagnostics.kt").read_text(encoding="utf-8")
    room = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "data" / "local" / "sync" / "MobileSyncDatabase.kt").read_text(encoding="utf-8")

    for token in [
        "ObjectVersionLinkage",
        "TaskWorklistOwnershipLinkage",
        "HandoverLinkage",
        "SyncServerAck",
        "SyncIncidentDiagnostic",
    ]:
        assert token in models

    for token in [
        "captureOffline",
        "markReady",
        "replayReady",
        "AwaitingConflictResolution",
        "serverAuditId",
    ]:
        assert token in service

    assert "conflictIncident" in diagnostics and "failureIncident" in diagnostics
    assert "RoomDatabase" in room and "sync_queue" not in room  # entity names live in entity files
