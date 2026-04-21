#!/usr/bin/env bash
# Seed investor demo farm v1 into Postgres.
# Usage:  bash scripts/seed_demo_investor.sh [--with-ai-seeds]
# Requires: GENOMEAI_DB_DSN set in environment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$ROOT/data/demo/investor_v1"

echo "=== GenomeAI investor demo seed ==="

# 1. Generate JSON fixtures
echo "[1/3] Generating JSON fixtures..."
python "$ROOT/scripts/build_demo_farm_investor.py" --mode connecterra "$@"

# 2. Apply schema + seeded rows via SQL
if [ -z "${GENOMEAI_DB_DSN:-}" ]; then
  echo "[2/3] GENOMEAI_DB_DSN not set — skipping Postgres seed (JSON fixtures are ready)."
else
  echo "[2/3] Applying schema and seeded rows via psql..."
  psql "$GENOMEAI_DB_DSN" -f "$DATA_DIR/seed.sql"
  echo "      Schema created, seeded cows inserted."
fi

# 3. Summary
echo "[3/3] Done."
echo "      Fixtures: $DATA_DIR"
echo "      Animals:  350 | Events: see events.json | Milk yields: see milk_yields.json"
echo ""
echo "  Seeded cows:"
echo "    Звёздочка  4821  — Акт 2 (ИИ-помощник, мастит, падение удоя)"
echo "    Малина     3891  — Акт 3 (Выбраковка, SELL)"
echo "    Ночка      3142  — Акт 4 (Ветврач, СКК алерт)"
