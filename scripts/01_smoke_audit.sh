#!/usr/bin/env bash
# 01_smoke_audit.sh
# Smoke test всех ключевых модулей после bootstrap.

set -e

REPO_DIR="${REPO_DIR:-/opt/genomeai/repo}"
cd "$REPO_DIR"

source .venv/bin/activate

if [ -f ".env.ai" ]; then
    set -a; source .env.ai; set +a
fi

echo "=========================================="
echo "GenomeAI Smoke Audit"
echo "Repo: $REPO_DIR"
echo "=========================================="

FAIL_COUNT=0

# 1. Syntax check
echo ""
echo "[1/6] Syntax check всех .py файлов..."
python3 << 'PYEOF'
import py_compile
from pathlib import Path
broken = []
total = 0
for sub in ['src', 'web_cabinet', 'packages', 'tests']:
    base = Path(sub)
    if not base.exists(): continue
    for py in base.rglob('*.py'):
        if '__pycache__' in str(py): continue
        total += 1
        try:
            py_compile.compile(str(py), doraise=True)
        except py_compile.PyCompileError as e:
            broken.append((str(py), str(e).split('\n')[0][:100]))

print(f"  Проверено: {total}, Сломано: {len(broken)}")
if broken:
    print("  ✗ Сломанные файлы:")
    for p, e in broken:
        print(f"    {p}")
        print(f"      {e}")
    exit(1)
else:
    print("  ✓ Все .py файлы синтаксически корректны")
PYEOF
[ $? -eq 0 ] || FAIL_COUNT=$((FAIL_COUNT + 1))

# 2. Import test
echo ""
echo "[2/6] Import test ключевых модулей..."
python3 << 'PYEOF'
import sys
sys.path.insert(0, '.')

modules = [
    "genomeai",
    "genomeai.qc_v2",
    "genomeai.kpi_v2",
    "genomeai.sensor_anomaly_v1",
    "genomeai.alerts_v2",
    "genomeai.economics_v2",
    "genomeai.roi_attribution",
    "genomeai.connectors_v1",
    "core.application.qc_rules_engine",
    "core.application.ml_pipeline",
    "packages.contracts.api_boundary_v1",
    "packages.contracts.analytics_v1",
    "web_cabinet.ai.client",
    "web_cabinet.ai.context",
    "web_cabinet.ai.tools",
    "web_cabinet.ai.background.insight_scanner",
]

ok, fail = 0, []
for m in modules:
    try:
        __import__(m)
        ok += 1
    except Exception as e:
        fail.append((m, f"{type(e).__name__}: {str(e)[:100]}"))

print(f"  OK: {ok}/{len(modules)}")
for m, e in fail:
    print(f"  ✗ {m}")
    print(f"    {e}")
if fail:
    exit(1)
print("  ✓ Все ключевые модули импортируются")
PYEOF
[ $? -eq 0 ] || FAIL_COUNT=$((FAIL_COUNT + 1))

# 3. PostgreSQL
echo ""
echo "[3/6] PostgreSQL connection..."
python3 << 'PYEOF'
import os
try:
    import psycopg2
except ImportError:
    print("  ⚠ psycopg2 не установлен — пропускаем")
    exit(0)

dsn = os.getenv('GENOMEAI_DB_DSN') or os.getenv('GENOMEAI_RUNTIME_POSTGRES_DSN')
if not dsn:
    print("  ⚠ Нет DSN в env — пропускаем")
    exit(0)
try:
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("SELECT version()")
    version = cur.fetchone()[0]
    print(f"  ✓ Подключение работает: {version[:60]}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"  ✗ Ошибка: {e}")
    exit(1)
PYEOF
[ $? -eq 0 ] || FAIL_COUNT=$((FAIL_COUNT + 1))

# 4. Redis
echo ""
echo "[4/6] Redis..."
if redis-cli ping 2>/dev/null | grep -q PONG; then
    echo "  ✓ Redis отвечает"
else
    echo "  ✗ Redis не отвечает"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# 5. Sensor anomaly smoke
echo ""
echo "[5/6] Sensor anomaly detector smoke test..."
python3 << 'PYEOF'
import sys
sys.path.insert(0, '.')
from pathlib import Path

try:
    import pandas as pd
    from genomeai.sensor_anomaly_v1 import detect_sensor_anomalies, DetectorConfig

    sensors_path = Path('data/demo/demo_farm_v1/dm_sensors_daily.csv')
    if not sensors_path.exists():
        print(f"  ⚠ {sensors_path} не существует — пропускаем")
        exit(0)

    df = pd.read_csv(sensors_path)
    result = detect_sensor_anomalies(df, cfg=DetectorConfig())
    print(f"  ✓ Детектор работает: {len(df)} строк → {len(result)} аномалий")
except Exception as e:
    print(f"  ✗ Ошибка: {e}")
    exit(1)
PYEOF
[ $? -eq 0 ] || FAIL_COUNT=$((FAIL_COUNT + 1))

# 6. Pytest
echo ""
echo "[6/6] Pytest на ключевых тестах..."
KEY_TESTS=(
    "tests/test_kpi_v2.py"
    "tests/test_t0_04_qc2_engine.py"
    "tests/test_t3_03_sensor_anomaly.py"
    "tests/test_alerts_v2_catalog.py"
    "tests/test_t11_03_unit_economics.py"
)

for t in "${KEY_TESTS[@]}"; do
    if [ -f "$t" ]; then
        echo "  → $t"
        if pytest "$t" -q --tb=no 2>&1 | tail -3; then
            true
        else
            echo "  ⚠ $t — есть failures"
        fi
    else
        echo "  ⚠ $t не найден — пропускаем"
    fi
done

echo ""
echo "=========================================="
if [ $FAIL_COUNT -eq 0 ]; then
    echo "✅ Smoke audit прошёл (0 критических ошибок)"
else
    echo "⚠️ $FAIL_COUNT критических проверок не прошли"
fi
echo "=========================================="
