#!/usr/bin/env python3
"""Extend dm_milkings_daily for every animal up to today.

Idempotent — record_id is deterministic (MY_{animal_id}_{YYYYMMDD}) and
the INSERT uses ON CONFLICT DO NOTHING. Each new row is generated as a
small Mulberry-style walk anchored on the animal's last observed values
so charts continue smoothly into the past 3-week gap.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import sys
from pathlib import Path

if os.getenv("GENOMEAI_PROFILE", "dev") == "prod":
    print("REFUSING: GENOMEAI_PROFILE=prod", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from web_cabinet.insights_v1 import _conn


def _seeded_walk(animal_id: str, n: int) -> list[float]:
    """Return n samples in [-1, 1] driven by a deterministic seed."""
    seed = int(hashlib.sha1(animal_id.encode()).hexdigest()[:8], 16)
    out: list[float] = []
    s = seed & 0xFFFFFFFF
    for _ in range(n):
        s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
        out.append((s / 0xFFFFFFFF) * 2.0 - 1.0)
    return out


def main() -> int:
    today = _dt.date.today()
    inserted = 0
    skipped = 0
    with _conn() as conn:
        with conn.cursor() as cur:
            # Get the latest row per animal as baseline.
            cur.execute(
                """
                SELECT DISTINCT ON (animal_id)
                       tenant_id, animal_id, lactation_id, date,
                       milk_kg, fat_pct, protein_pct, scc_cells_ml
                FROM dm_milkings_daily
                ORDER BY animal_id, date DESC
                """
            )
            baselines = list(cur.fetchall())

        for tenant_id, animal_id, lactation_id, last_date, milk, fat, prot, scc in baselines:
            if last_date >= today:
                continue
            days = (today - last_date).days
            walk = _seeded_walk(animal_id, days)
            with conn.cursor() as cur:
                for i in range(1, days + 1):
                    d = last_date + _dt.timedelta(days=i)
                    w = walk[i - 1]
                    new_milk = max(4.0, round(float(milk) + w * 1.4, 1))
                    new_fat = round(min(5.5, max(2.5, float(fat or 3.7) + w * 0.05)), 2) if fat is not None else None
                    new_prot = round(min(4.5, max(2.5, float(prot or 3.2) + w * 0.04)), 2) if prot is not None else None
                    new_scc = max(20_000, int((scc or 150_000) + w * 25_000)) if scc is not None else None
                    rid = f"MY_{animal_id}_{d.strftime('%Y%m%d')}"
                    cur.execute(
                        """
                        INSERT INTO dm_milkings_daily
                          (tenant_id, record_id, animal_id, lactation_id, date,
                           milk_kg, milking_count, fat_pct, protein_pct, scc_cells_ml,
                           created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (tenant_id, record_id) DO NOTHING
                        """,
                        (tenant_id, rid, animal_id, lactation_id, d,
                         new_milk, new_fat, new_prot, new_scc),
                    )
                    if cur.rowcount > 0:
                        inserted += 1
                    else:
                        skipped += 1
        conn.commit()

    print(f"animals={len(baselines)} inserted={inserted} skipped={skipped} today={today}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
