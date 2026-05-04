#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python -m pytest -q tests/test_t32_08a_android_offline_sync_contract.py

KOTLIN_SOURCES=(
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncModels.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncQueuePolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncRetryPolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncLifecyclePolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncConflictPolicy.kt
  mobile_android/contract_smoke/SyncContractSmoke.kt
)

mkdir -p _tmp/t32_08a_kotlinc
KOTLINC="$(command -v kotlinc || true)"
if [[ -z "$KOTLINC" ]]; then
  echo "kotlinc not available — skipping compilation (source-presence verified by pytest)" >&2
else
  "$KOTLINC" "${KOTLIN_SOURCES[@]}" -include-runtime -d _tmp/t32_08a_kotlinc/t32_08a_sync_contract.jar
  java -jar _tmp/t32_08a_kotlinc/t32_08a_sync_contract.jar
fi

echo "mobile_android T32-08A validation OK"
