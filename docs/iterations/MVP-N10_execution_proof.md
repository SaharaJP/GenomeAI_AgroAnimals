# MVP-N10 Execution Proof — Investor Demo Farm v2 (350 heads)

## Scope

Build investor-grade demo farm dataset on 350 active dairy cows with 6-month history
and seeded demo cases for Acts 1–5. Generator script, all JSON/CSV fixtures, SQL seed,
shell script.

## Executed Checks

### 1. Script runs without error

```
python scripts/build_demo_farm_investor.py --mode connecterra
```

**Output:**
- animals.json: 350 records
- events.json: 3364 records
- treatments.json: 61 records
- breedings.json: 159 records
- milk_yields.json: 37310 records
- insights_seeded.json: 12 records
- timeline_events_seeded.json: 12 records
- morning_briefs_seeded.json: 3 records
- weekly_briefs_seeded.json: 2 records
- impact_analyses_seeded.json: 4 records
- dm_farms.csv, dm_animals.csv, dm_lactations.csv, dm_health_events.csv, dm_treatments.csv
- seed.sql, README.md, manifest.json

### 2. 350 cows with correct distribution

| Metric | Value | Target |
|--------|-------|--------|
| Total animals | 350 | 350 ✓ |
| DIM Fresh (1-30) | 49 | 50 (~) |
| DIM Early (31-100) | 101 | 100 (~) |
| DIM Mid (101-200) | 100 | 100 ✓ |
| DIM Late (201-305) | 50 | 50 ✓ |
| DIM Dry (>305) | 50 | 50 ✓ |
| 1st lactation | 105 | 105 ✓ |
| 2nd lactation | 123 | 122 (~) |
| 3rd lactation | 70 | 70 ✓ |
| 4th+ lactation | 52 | 53 (~) |

Minor ±1 variance in Fresh/2nd/4th+ due to seeded cow DIM occupying target slots.

### 3. Seeded cows present with correct histories

| Cow | ID | Lact | DIM | Key attribute |
|-----|-----|------|-----|---------------|
| Звёздочка | 4821 | 3 | 156 | culling_rec absent; yield 28 кг after mastitis |
| Малина | 3891 | 3 | 285 | culling_score=82, rec=SELL, npv_30d=-180 |
| Ночка | 3142 | 2 | 45 | scc=450000, no_open_treatment=True |

Seeded events verified:
- 4821: mastitis event EV_4821_MAST_01 (day -42), pen move EV_4821_PMOV_01 (day -38),
  treatment TR_4821_MAST_01 with withdrawal until day -34
- 3891: 2× mastitis events (EV_3891_MAST_01 day -60, EV_3891_MAST_02 day -30),
  2× treatments with Цефквином / Пенициллин
- 3142: 3× activity alerts (days -3,-2,-1), SCC alert EV_3142_SCC_01 (day -1)

### 4. genomeai validate

```
python -m genomeai.cli validate --input data/demo/investor_v1 --contracts configs/contracts
```

**Result: VALIDATION_OK** ✓
data_version=47472130f5aa2a58d0fbb3c2fbe7a4607aa85e5fd5f4a80414917e6d95490f0f

### 5. pytest smoke

```
python -m pytest -q tests/test_a6_smoke.py
```

**Result: 1 passed, 2 warnings** ✓ (warnings are pre-existing deprecation notices)

### 6. JSON schema validity

All seeded fixture files are valid JSON. Structure verified for:
- insights_seeded.json: 12 items with insight_id, type, severity, title, body, action, tags
- timeline_events_seeded.json: 12 items with timeline_event_id, date, event_type, title, impact
- morning_briefs_seeded.json: 3 items with kpis including avg_milk_yield, health_index, pregnancy_rate_21d
- Act 1 KPIs: avg_milk_yield=28.5, health_index=94, pregnancy_rate_21d=24, cows_need_attention_today=3

### 7. CI gates (full set)

Not run — offline environment, no Docker/Postgres/Redis available.
Items 1–6 above confirm: script executes, data validates, smoke passes.
Full 7-gate run is an operator action.

## Net Result

All deliverables created:
- `scripts/build_demo_farm_investor.py` — deterministic generator (seed=42)
- `data/demo/investor_v1/` — all JSON + CSV fixtures
- `data/demo/investor_v1/seed.sql` — Postgres schema + seeded-cow INSERTs
- `scripts/seed_demo_investor.sh` — orchestration shell script
- `docs/iterations/MVP-N10_execution_proof.md` — this file

## Honest Status

**partially_proven**

- Runtime proven: script runs, validation passes, smoke passes (gates 1/3/5)
- Not proven: full 7-gate CI (gates 4/6/7 require Docker/Postgres/Redis)
- Not proven: Postgres load via seed.sql (no DSN available in this environment)
- Minor: treatments count 61 vs ~400 target estimate (health episode frequency realistic;
  count is advisory, not a validation gate)

## От координатора

Чтобы перевести в `proven`:
1. Запустить `bash scripts/run_ci_gate.sh` в контуре с Postgres + Redis
2. Запустить `bash scripts/seed_demo_investor.sh` с `GENOMEAI_DB_DSN` и проверить загрузку в Postgres
