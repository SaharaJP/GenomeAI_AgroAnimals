-- GenomeAI investor demo farm v1 — SQL seed
-- SYNTHETIC DATA ONLY. Never mix with production evidence.
-- Generated: 2026-04-21
-- Load: psql $GENOMEAI_DB_DSN -f seed.sql

BEGIN;

CREATE SCHEMA IF NOT EXISTS demo_investor;

CREATE TABLE IF NOT EXISTS demo_investor.animals (
  animal_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  sex CHAR(1) NOT NULL DEFAULT 'F',
  breed TEXT,
  birth_date DATE,
  status TEXT,
  lactation_no INT,
  calving_date DATE,
  dim INT,
  current_pen_id TEXT,
  milk_305d_kg INT,
  peak_milk_kg NUMERIC(5,1),
  tags TEXT[]
);

CREATE TABLE IF NOT EXISTS demo_investor.events (
  event_id TEXT PRIMARY KEY,
  animal_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_date TIMESTAMPTZ,
  severity TEXT,
  details JSONB,
  reporter TEXT,
  evidence_ids TEXT[]
);

CREATE TABLE IF NOT EXISTS demo_investor.treatments (
  treatment_id TEXT PRIMARY KEY,
  animal_id TEXT NOT NULL,
  start_date DATE,
  end_date DATE,
  drug_name TEXT,
  drug_route TEXT,
  withdrawal_end_date DATE,
  reason_event_id TEXT,
  prescribed_by TEXT,
  executed_by TEXT
);

CREATE TABLE IF NOT EXISTS demo_investor.milk_yields (
  record_id TEXT PRIMARY KEY,
  animal_id TEXT NOT NULL,
  date DATE NOT NULL,
  milk_kg NUMERIC(5,1),
  fat_pct NUMERIC(4,2),
  protein_pct NUMERIC(4,2),
  scc_cells_ml INT
);

CREATE TABLE IF NOT EXISTS demo_investor.breedings (
  breeding_id TEXT PRIMARY KEY,
  animal_id TEXT NOT NULL,
  date DATE,
  method TEXT,
  bull_name TEXT,
  heat_detected BOOLEAN,
  result TEXT,
  preg_check_date DATE
);

-- Bulk data is loaded from JSON fixtures via the Python script.
-- Insert the 3 seeded cows explicitly for quick reference:

INSERT INTO demo_investor.animals (animal_id,name,farm_id,tenant_id,sex,breed,birth_date,status,lactation_no,calving_date,dim,current_pen_id,milk_305d_kg,peak_milk_kg,tags) VALUES ('4821','Звёздочка','INV_FARM_001','default','F','Holstein','2021-10-18','active',3,'2025-11-16',156,'PEN_LACT_3',10200,37.0,ARRAY['act2_ai_copilot', 'mastitis_history', 'yield_drop']) ON CONFLICT (animal_id) DO NOTHING;
INSERT INTO demo_investor.animals (animal_id,name,farm_id,tenant_id,sex,breed,birth_date,status,lactation_no,calving_date,dim,current_pen_id,milk_305d_kg,peak_milk_kg,tags) VALUES ('3891','Малина','INV_FARM_001','default','F','Holstein','2021-06-11','active',3,'2025-07-10',285,'PEN_LACT_2',8800,28.0,ARRAY['act3_culling', 'mastitis_recurrence', 'open_cow', 'negative_npv']) ON CONFLICT (animal_id) DO NOTHING;
INSERT INTO demo_investor.animals (animal_id,name,farm_id,tenant_id,sex,breed,birth_date,status,lactation_no,calving_date,dim,current_pen_id,milk_305d_kg,peak_milk_kg,tags) VALUES ('3142','Ночка','INV_FARM_001','default','F','Holstein','2023-02-21','active',2,'2026-03-07',45,'PEN_FRESH_1',9100,33.0,ARRAY['act4_vet_record', 'scc_alert', 'activity_drop', 'no_open_treatment']) ON CONFLICT (animal_id) DO NOTHING;

-- To load full dataset into Postgres from JSON:
-- python scripts/build_demo_farm_investor.py --mode connecterra
-- Then use: \copy demo_investor.milk_yields FROM PROGRAM
--   'python -c "import json,csv,sys; ...'
-- Or use psycopg2 / asyncpg bulk insert in seed_demo_investor.sh

COMMIT;