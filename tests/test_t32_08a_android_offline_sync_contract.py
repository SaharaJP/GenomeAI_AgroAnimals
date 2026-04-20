import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_offline_sync_docs_and_specs_exist():
    required = [
        ROOT / "docs" / "android_offline_sync_contract.md",
        ROOT / "specs" / "jsonschema" / "android_offline_sync_contract_v1.json",
        ROOT / "configs" / "mobile" / "android_sync_conflict_policy_v1.json",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncModels.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncQueuePolicy.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncRetryPolicy.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncLifecyclePolicy.kt",
        ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncConflictPolicy.kt",
        ROOT / "scripts" / "smoke_t32_08a_android_offline_sync_contract.sh",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    assert not missing, f"Missing Android offline/sync contract files: {missing}"


def test_offline_contract_forbids_silent_merge_and_covers_required_actions():
    doc = (ROOT / "docs" / "android_offline_sync_contract.md").read_text(encoding="utf-8").lower()
    assert "silent merge запрещён" in doc or "silent merge запрещен" in doc
    for token in [
        "quickevententry",
        "taskcompletion",
        "shifthandover",
        "feedbacksubmission",
        "assistantlinkedaction",
    ]:
        assert token in doc



def test_conflict_policy_and_schema_are_consistent():
    schema = json.loads((ROOT / "specs" / "jsonschema" / "android_offline_sync_contract_v1.json").read_text(encoding="utf-8"))
    policy = json.loads((ROOT / "configs" / "mobile" / "android_sync_conflict_policy_v1.json").read_text(encoding="utf-8"))

    action_enum = schema["properties"]["queue_item"]["properties"]["action_type"]["enum"]
    assert set(action_enum) == set(policy["conflict_modes"].keys())
    assert policy["silent_merges_allowed"] is False



def test_sync_models_capture_audit_idempotency_and_conflict_semantics():
    models = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncModels.kt").read_text(encoding="utf-8")
    queue_policy = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncQueuePolicy.kt").read_text(encoding="utf-8")
    retry_policy = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncRetryPolicy.kt").read_text(encoding="utf-8")
    lifecycle_policy = (ROOT / "mobile_android" / "app" / "src" / "main" / "java" / "com" / "genomeai" / "agroanimals" / "mobile" / "domain" / "sync" / "SyncLifecyclePolicy.kt").read_text(encoding="utf-8")

    for token in [
        "SyncAuditSemantics",
        "SyncIdempotency",
        "SyncConflictRecord",
        "AwaitingConflictResolution",
        "FeedbackSubmission",
        "AssistantLinkedAction",
    ]:
        assert token in models

    assert "permitsSilentMerge(actionType: SyncActionType): Boolean = false" in queue_policy
    assert "MAX_RETRY_ATTEMPTS" in retry_policy
    assert "nextRetryDelaySeconds" in retry_policy
    assert "canTransition" in lifecycle_policy
    assert "nextStatusAfterFailure" in lifecycle_policy
