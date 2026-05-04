-- Canonical Data Model v2 (Target) - Postgres DDL
-- NOTE: Additive; MVP can continue using file-based artifacts.

CREATE TABLE IF NOT EXISTS dm_farms (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  farm_id   TEXT NOT NULL,
  farm_name TEXT NOT NULL,
  country_code TEXT,
  timezone TEXT,
  currency TEXT DEFAULT 'EUR',
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, farm_id)
);

CREATE TABLE IF NOT EXISTS dm_sites (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  site_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  site_name TEXT NOT NULL,
  address TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, site_id),
  FOREIGN KEY (tenant_id, farm_id) REFERENCES dm_farms(tenant_id, farm_id)
);

CREATE TABLE IF NOT EXISTS dm_pens (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  pen_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  pen_name TEXT NOT NULL,
  pen_type TEXT,
  capacity_head INTEGER,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, pen_id),
  FOREIGN KEY (tenant_id, site_id) REFERENCES dm_sites(tenant_id, site_id)
);

CREATE TABLE IF NOT EXISTS dm_bulls (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  bull_id TEXT NOT NULL,
  bull_name TEXT,
  breed TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, bull_id)
);

CREATE TABLE IF NOT EXISTS dm_animals (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  animal_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  site_id TEXT,
  current_pen_id TEXT,
  master_animal_id TEXT,
  external_id TEXT,
  sex TEXT,
  birth_date DATE,
  breed TEXT,
  status TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, animal_id),
  FOREIGN KEY (tenant_id, farm_id) REFERENCES dm_farms(tenant_id, farm_id),
  FOREIGN KEY (tenant_id, site_id) REFERENCES dm_sites(tenant_id, site_id),
  FOREIGN KEY (tenant_id, current_pen_id) REFERENCES dm_pens(tenant_id, pen_id)
);

CREATE TABLE IF NOT EXISTS dm_lactations (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  lactation_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  lactation_no INTEGER NOT NULL,
  calving_date DATE NOT NULL,
  dryoff_date DATE,
  milk_305d_kg DOUBLE PRECISION,
  calving_outcome TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, lactation_id),
  UNIQUE (tenant_id, animal_id, lactation_no),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id)
);

CREATE TABLE IF NOT EXISTS dm_milkings_daily (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  record_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  lactation_id TEXT,
  date DATE NOT NULL,
  milk_kg DOUBLE PRECISION NOT NULL,
  milking_count INTEGER,
  fat_pct DOUBLE PRECISION,
  protein_pct DOUBLE PRECISION,
  scc_cells_ml INTEGER,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, record_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id),
  FOREIGN KEY (tenant_id, lactation_id) REFERENCES dm_lactations(tenant_id, lactation_id)
);

CREATE TABLE IF NOT EXISTS dm_testday (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  testday_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  lactation_id TEXT,
  test_date DATE NOT NULL,
  dim INTEGER,
  milk_kg DOUBLE PRECISION,
  fat_pct DOUBLE PRECISION,
  protein_pct DOUBLE PRECISION,
  scc_cells_ml INTEGER,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, testday_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id),
  FOREIGN KEY (tenant_id, lactation_id) REFERENCES dm_lactations(tenant_id, lactation_id)
);

CREATE TABLE IF NOT EXISTS dm_sensors_daily (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  record_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  date DATE NOT NULL,
  activity_count INTEGER,
  rumination_min INTEGER,
  lying_min INTEGER,
  temperature_c DOUBLE PRECISION,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, record_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id)
);

CREATE TABLE IF NOT EXISTS dm_health_events (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  event_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  event_date DATE NOT NULL,
  event_type TEXT NOT NULL,
  severity TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, event_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id)
);

CREATE TABLE IF NOT EXISTS dm_treatments (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  treatment_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE,
  treatment_type TEXT NOT NULL,
  reason_event_id TEXT,
  withdrawal_end_date DATE,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, treatment_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id),
  FOREIGN KEY (tenant_id, reason_event_id) REFERENCES dm_health_events(tenant_id, event_id)
);

CREATE TABLE IF NOT EXISTS dm_repro_events (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  repro_event_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  event_date DATE NOT NULL,
  event_type TEXT NOT NULL,
  bull_id TEXT,
  result TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, repro_event_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id),
  FOREIGN KEY (tenant_id, bull_id) REFERENCES dm_bulls(tenant_id, bull_id)
);

CREATE TABLE IF NOT EXISTS dm_pen_moves (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  move_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  from_pen_id TEXT,
  to_pen_id TEXT NOT NULL,
  move_date DATE NOT NULL,
  reason TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, move_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id),
  FOREIGN KEY (tenant_id, from_pen_id) REFERENCES dm_pens(tenant_id, pen_id),
  FOREIGN KEY (tenant_id, to_pen_id) REFERENCES dm_pens(tenant_id, pen_id)
);

CREATE TABLE IF NOT EXISTS animal_events_v1 (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  event_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  farm_id TEXT,
  site_id TEXT,
  lactation_id TEXT,
  event_type TEXT NOT NULL,
  event_ts TIMESTAMPTZ NOT NULL,
  event_date DATE NOT NULL,
  actor_type TEXT NOT NULL,
  actor_user_id INTEGER,
  actor_username TEXT,
  source TEXT NOT NULL,
  source_ref TEXT,
  reason_code TEXT,
  linked_object_type TEXT,
  linked_object_id TEXT,
  linked_decision_id TEXT,
  linked_task_id TEXT,
  request_id TEXT,
  job_id TEXT,
  data_version TEXT,
  qc_run TEXT,
  model_version TEXT,
  scoring_run TEXT,
  report_version TEXT,
  payload_json TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, event_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id)
);

CREATE TABLE IF NOT EXISTS dm_feed_rations (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  ration_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  ration_name TEXT NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE,
  dm_pct DOUBLE PRECISION,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, ration_id),
  FOREIGN KEY (tenant_id, site_id) REFERENCES dm_sites(tenant_id, site_id)
);

CREATE TABLE IF NOT EXISTS dm_feed_deliveries (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  delivery_id TEXT NOT NULL,
  ration_id TEXT NOT NULL,
  pen_id TEXT NOT NULL,
  delivery_date DATE NOT NULL,
  feed_kg_as_fed DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, delivery_id),
  FOREIGN KEY (tenant_id, ration_id) REFERENCES dm_feed_rations(tenant_id, ration_id),
  FOREIGN KEY (tenant_id, pen_id) REFERENCES dm_pens(tenant_id, pen_id)
);

CREATE TABLE IF NOT EXISTS dm_prices (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  price_id TEXT NOT NULL,
  item_type TEXT NOT NULL,
  item_name TEXT NOT NULL,
  currency TEXT NOT NULL,
  unit TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_to DATE,
  value DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, price_id)
);

CREATE TABLE IF NOT EXISTS dm_economics_daily (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  record_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  date DATE NOT NULL,
  milk_price_per_kg DOUBLE PRECISION,
  feed_cost_per_kg_dm DOUBLE PRECISION,
  other_cost_eur DOUBLE PRECISION,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, record_id),
  FOREIGN KEY (tenant_id, farm_id) REFERENCES dm_farms(tenant_id, farm_id)
);

CREATE TABLE IF NOT EXISTS dm_alerts (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  alert_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  alert_date DATE NOT NULL,
  severity TEXT NOT NULL,
  alert_type TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, alert_id),
  FOREIGN KEY (tenant_id, farm_id) REFERENCES dm_farms(tenant_id, farm_id)
);

CREATE TABLE IF NOT EXISTS dm_decisions (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  decision_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  decision_date DATE NOT NULL,
  animal_id TEXT,
  lactation_id TEXT,
  recommendation_type TEXT NOT NULL,
  decision TEXT NOT NULL,
  comment TEXT,
  source_alert_id TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, decision_id),
  FOREIGN KEY (tenant_id, farm_id) REFERENCES dm_farms(tenant_id, farm_id),
  FOREIGN KEY (tenant_id, animal_id) REFERENCES dm_animals(tenant_id, animal_id),
  FOREIGN KEY (tenant_id, lactation_id) REFERENCES dm_lactations(tenant_id, lactation_id),
  FOREIGN KEY (tenant_id, source_alert_id) REFERENCES dm_alerts(tenant_id, alert_id)
);

CREATE TABLE IF NOT EXISTS dm_reports (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  report_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  report_date DATE NOT NULL,
  report_type TEXT NOT NULL,
  data_version TEXT NOT NULL,
  run_id TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, report_id),
  FOREIGN KEY (tenant_id, farm_id) REFERENCES dm_farms(tenant_id, farm_id)
);

CREATE TABLE IF NOT EXISTS dm_users (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  user_id TEXT NOT NULL,
  username TEXT NOT NULL,
  display_name TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, user_id),
  UNIQUE (tenant_id, username)
);

CREATE TABLE IF NOT EXISTS dm_roles (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  role_id TEXT NOT NULL,
  role_name TEXT NOT NULL,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, role_id),
  UNIQUE (tenant_id, role_name)
);

CREATE TABLE IF NOT EXISTS dm_user_roles (
  tenant_id TEXT NOT NULL DEFAULT 'default',
  user_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, user_id, role_id),
  FOREIGN KEY (tenant_id, user_id) REFERENCES dm_users(tenant_id, user_id),
  FOREIGN KEY (tenant_id, role_id) REFERENCES dm_roles(tenant_id, role_id)
);


-- === Identity / Master ID (Target) ===
CREATE TABLE IF NOT EXISTS dm_master_animals (
  tenant_id TEXT NOT NULL,
  master_animal_id TEXT NOT NULL,
  sex TEXT,
  sex_source TEXT,
  birth_date DATE,
  birth_date_source TEXT,
  breed TEXT,
  breed_source TEXT,
  ear_tag_id TEXT,
  ear_tag_id_source TEXT,
  farm_id TEXT,
  farm_id_source TEXT,
  dam_animal_id TEXT,
  dam_animal_id_source TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  status_source TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, master_animal_id)
);

CREATE TABLE IF NOT EXISTS dm_animal_id_map (
  tenant_id TEXT NOT NULL,
  source_system TEXT NOT NULL,
  source_animal_id TEXT NOT NULL,
  master_animal_id TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, source_system, source_animal_id),
  FOREIGN KEY (tenant_id, master_animal_id) REFERENCES dm_master_animals(tenant_id, master_animal_id)
);

CREATE TABLE IF NOT EXISTS dm_identity_events (
  tenant_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_ts TIMESTAMPTZ NOT NULL,
  event_type TEXT NOT NULL, -- RESOLVE|MERGE|SPLIT
  actor TEXT,
  run_id TEXT,
  data_version TEXT,
  payload_json JSONB NOT NULL,
  PRIMARY KEY (tenant_id, event_id)
);

-- Analytics performance indexes (migration 20260504_11)
CREATE INDEX IF NOT EXISTS idx_milkings_tenant_date ON dm_milkings_daily (tenant_id, date);
CREATE INDEX IF NOT EXISTS idx_milkings_animal_date ON dm_milkings_daily (animal_id, date);
CREATE INDEX IF NOT EXISTS idx_health_tenant_date   ON dm_health_events  (tenant_id, event_date);
CREATE INDEX IF NOT EXISTS idx_health_animal_date   ON dm_health_events  (animal_id, event_date);
CREATE INDEX IF NOT EXISTS idx_repro_tenant_date    ON dm_repro_events   (tenant_id, event_date);
CREATE INDEX IF NOT EXISTS idx_sensors_animal_date  ON dm_sensors_daily  (animal_id, date);
