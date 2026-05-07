#!/usr/bin/env python3
"""One-shot: seed scanner_insights from data/demo/investor_v1/insights_seeded.json.

Idempotent (ON CONFLICT DO NOTHING). Refuses to run on adult/prod profile.
Compatible with psycopg v3 (preferred) or psycopg2.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Driver shim — match web_cabinet/insights_v1.py
try:
    import psycopg  # type: ignore
    _PG_VARIANT = 3
except Exception:
    psycopg = None  # type: ignore
    _PG_VARIANT = 0
    try:
        import psycopg2  # type: ignore
        _PG_VARIANT = 2
    except Exception:
        psycopg2 = None  # type: ignore


def _connect(dsn: str):
    if _PG_VARIANT == 3:
        return psycopg.connect(dsn)
    if _PG_VARIANT == 2:
        return psycopg2.connect(dsn)
    print("REFUSING: no psycopg driver installed", file=sys.stderr)
    sys.exit(2)


PROFILE = os.getenv("GENOMEAI_PROFILE", "dev")
if PROFILE == "prod":
    print("REFUSING: GENOMEAI_PROFILE=prod is forbidden for demo seed", file=sys.stderr)
    sys.exit(2)

DSN = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
if not DSN:
    print("REFUSING: GENOMEAI_DB_DSN not set", file=sys.stderr)
    sys.exit(2)

SEED = Path(__file__).resolve().parents[1] / "data" / "demo" / "investor_v1" / "insights_seeded.json"
FARM_ID = os.getenv("GENOMEAI_DEMO_FARM_ID", "INV_FARM_001")


def main() -> int:
    if not SEED.exists():
        print(f"REFUSING: seed file missing: {SEED}", file=sys.stderr)
        return 2
    records = json.loads(SEED.read_text(encoding="utf-8"))
    inserted = skipped = 0
    with _connect(DSN) as conn:
        with conn.cursor() as cur:
            for rec in records:
                iid = rec["insight_id"]
                cur.execute(
                    """
                    INSERT INTO scanner_insights (
                      insight_id, farm_id, title, category, priority, status,
                      generated_at_utc, generator, payload_json,
                      severity, body, action, animal_ids, recommendations, chart_data
                    )
                    VALUES (%s,%s,%s,%s,%s,%s, NOW()::text,'seed_demo', %s,
                            %s,%s,%s, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (insight_id) DO NOTHING
                    """,
                    (
                        iid,
                        FARM_ID,
                        rec.get("title", ""),
                        rec.get("type") or rec.get("category") or "production",
                        rec.get("severity") or rec.get("priority") or "info",
                        rec.get("status", "to_check"),
                        json.dumps(rec),
                        rec.get("severity") or "info",
                        rec.get("body", ""),
                        rec.get("action", ""),
                        json.dumps(rec.get("animal_ids", [])),
                        json.dumps(rec.get("recommendations", [])),
                        json.dumps(rec.get("chartData") or rec.get("chart_data") or []),
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
        conn.commit()
    print(f"seeded={inserted} skipped_existing={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
