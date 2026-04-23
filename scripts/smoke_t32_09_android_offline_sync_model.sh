#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python -m pytest -q tests/test_t32_09_android_offline_sync_model.py

KOTLIN_SOURCES=(
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncModels.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncQueuePolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncRetryPolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncLifecyclePolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncConflictPolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/OfflineSyncLocalStore.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/InMemoryOfflineSyncLocalStore.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncTransport.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncDiagnostics.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/OfflineSyncService.kt
  mobile_android/contract_smoke/OfflineSyncServiceSmoke.kt
)

mkdir -p _tmp/t32_09_kotlinc
KOTLINC="$(command -v kotlinc)"
if [[ -z "$KOTLINC" ]]; then
  echo "kotlinc not found" >&2
  exit 1
fi
"$KOTLINC" "${KOTLIN_SOURCES[@]}" -include-runtime -d _tmp/t32_09_kotlinc/t32_09_offline_sync_model.jar
java -jar _tmp/t32_09_kotlinc/t32_09_offline_sync_model.jar

echo "mobile_android T32-09 validation OK"
