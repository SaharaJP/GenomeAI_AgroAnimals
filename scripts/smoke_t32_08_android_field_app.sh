#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python -m pytest -q tests/test_t32_08_android_field_app_foundation.py

KOTLIN_SOURCES=(
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/Role.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/MobileDestinations.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/MobileNavigationPolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncModels.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/domain/sync/SyncQueuePolicy.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/auth/AuthModels.kt
  mobile_android/app/src/main/java/com/genomeai/agroanimals/mobile/api/MobileContracts.kt
)

mkdir -p _tmp/t32_08_kotlinc
KOTLINC="$(command -v kotlinc)"
if [[ -z "$KOTLINC" ]]; then
  echo "kotlinc not found" >&2
  exit 1
fi
"$KOTLINC" "${KOTLIN_SOURCES[@]}" -d _tmp/t32_08_kotlinc/t32_08_foundation.jar

echo "mobile_android T32-08 validation OK"
