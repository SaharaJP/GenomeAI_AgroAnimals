# Canonical Data Model v2 (Target System: Farm Command Center)

> Scope: **specification only** (no code). This document extends MVP canonical datasets (`dm_farms`, `dm_animals`, `dm_lactations`, optional `dm_testday`) to a Target-ready model while keeping **backward compatibility**.


## 0) Implementation artifacts (code + DDL)

- Pydantic schemas: `src/genomeai/target/model_v2.py`
- Relation validators: `src/genomeai/target/validators_v2.py`
- DDL (SQLite): `db/ddl/target_v2/sqlite.sql`
- DDL (Postgres): `db/ddl/target_v2/postgres.sql`
- Fixtures (CSV): `data/fixtures/target_v2/dm_*.csv`
- Unit tests: `tests/target/test_data_model_v2.py`

> Note: This implementation is **additive** and does not change MVP pipelines; it is a foundation for Target ingestion/QC extensions.


## 1) Design goals

- **Backwards compatible**: MVP ingest/QC/ML/score/report must continue to work unchanged on P0 datasets.
- **Target-ready**: add entities needed for operations (health, repro, sensors, feed, economics, alerts, decisions, reports, RBAC).
- **Strong lineage**: every dataset/run must be traceable: `data_version`, `qc_run`, `model_version`, `scoring_run`, `report_version`.
- **On-prem & sensitive data**: RBAC and auditability are first-class.

## 2) Naming conventions (canonical)

### 2.1 Identifiers
- Primary keys: `*_id` (string), stable across versions.
- Composite business keys are allowed, but **prefer a single PK**; keep business key fields as unique constraints.
- Deterministic IDs are acceptable for MVP compatibility (e.g., `lactation_id = "{animal_id}__{lactation_no}"`).

### 2.2 Field names & types
- `snake_case` for columns and tables.
- Dates: `*_date` (`YYYY-MM-DD`, type `date`)
- Timestamps: `*_ts` (ISO 8601, UTC recommended), type `datetime`
- Booleans: `is_*`
- Numbers: `*_kg`, `*_l`, `*_pct`, `*_count`, `*_min`, `*_c` etc.

### 2.3 Units of measurement (defaults)
- Milk yield: `kg` (preferred), alternatively `l` explicitly named.
- Body weight: `kg`
- Feed: `kg` as-fed unless stated; nutrients in `%` (DM basis) or `kg/day` if explicit.
- Temperature: `°C` (`*_c`)
- Activity: steps `count`, rumination `minutes`, lying `minutes`.
- Prices: monetary values as `currency` + `value` (float). Currency default: `EUR` unless configured.

### 2.4 Nullability
- Required fields: **NOT NULL**
- Optional: NULL allowed
- Use empty string only for textual notes; not for IDs.

## 3) Common metadata (recommended)

These fields are **recommended** across Target tables (not mandatory for MVP P0 tables):

- `record_source` (string): source system name (e.g., "dairycomp", "uniform-agri", "manual")
- `ingest_run_id` (string): the ingestion run identifier
- `data_version` (string): folder/version that produced canonical data
- `created_ts` (datetime), `updated_ts` (datetime)
- `is_deleted` (bool): soft delete

> Note: P0 MVP tables may remain minimal; metadata can be managed at dataset/run level in `artifacts/*/metadata`.

## 4) Entities (Target v2)

Legend:
- **PK** = primary key
- **FK** = foreign key
- **REQ** = required
- Types: `string`, `int`, `float`, `bool`, `date`, `datetime`, `enum`

---

## 4.1 Farm (`dm_farms`) — P0
**Purpose:** legal/business farm entity.

**PK:** `farm_id` (string)  
**Required:** `farm_id`, `farm_name`  
**Optional:** `country_code`, `timezone`, `integration_key`

**Suggested fields**
| field | type | req | notes |
|---|---:|:---:|---|
| farm_id | string | ✅ | stable id (e.g., FARM_001) |
| farm_name | string | ✅ | display name |
| country_code | string |  | ISO-3166-1 alpha-2 |
| timezone | string |  | e.g., "Europe/Berlin" |
| integration_key | string |  | external system farm key |

**Integrity rules**
- `farm_id` unique, not null
- `timezone` should be a valid IANA TZ if provided

**Example**
| farm_id | farm_name | country_code | timezone |
|---|---|---|---|
| FARM_001 | Hof Sonnenfeld | DE | Europe/Berlin |

---

## 4.2 Site (`dm_sites`) — Target
**Purpose:** physical site/location within a farm (optional if farm has one site).

**PK:** `site_id` (string)  
**FK:** `farm_id -> dm_farms.farm_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| site_id | string | ✅ | e.g., SITE_001 |
| farm_id | string | ✅ | FK |
| site_name | string | ✅ | |
| address_text | string |  | free form |
| is_active | bool | ✅ | default true |

**Integrity rules**
- `(farm_id, site_id)` unique; `site_id` globally unique preferred
- `farm_id` must exist in `dm_farms`

**Example**
| site_id | farm_id | site_name | is_active |
|---|---|---|---|
| SITE_001 | FARM_001 | Main Barn | true |

---

## 4.3 Animal (`dm_animals`) — P0
**Purpose:** animal master record.

**PK:** `animal_id` (string)  
**FK:** `farm_id -> dm_farms.farm_id`, optional `site_id -> dm_sites.site_id`

**Required (P0):** `animal_id`, `farm_id`  
**Target adds (optional):** `birth_date`, `sex`, `breed_code`, `status`, `current_pen_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| animal_id | string | ✅ | stable |
| farm_id | string | ✅ | FK |
| site_id | string |  | FK (optional) |
| animal_tag | string |  | ear tag / visible id |
| sex | enum |  | {F, M} |
| birth_date | date |  | |
| breed_code | string |  | e.g., HOL |
| status | enum |  | {active, sold, dead} |
| dam_id | string |  | FK to animals.animal_id (same farm) |
| sire_id | string |  | FK to bulls.bull_id (preferred) or animals.animal_id |
| current_pen_id | string |  | FK to pens.pen_id |

**Integrity rules**
- `animal_id` unique
- `farm_id` exists
- If `dam_id` provided: must exist in same `farm_id`
- If `birth_date` exists and there is any calving date: `birth_date < calving_date`

**Example**
| animal_id | farm_id | site_id | sex | birth_date | breed_code | status |
|---|---|---|---|---|---|---|
| A1001 | FARM_001 | SITE_001 | F | 2021-04-15 | HOL | active |

---

## 4.4 Lactation (`dm_lactations`) — P0
**Purpose:** lactation facts per animal per lactation number.

**PK (Target):** `lactation_id` (string)  
**Business key (P0):** `(animal_id, lactation_no)` unique  
**FK:** `animal_id -> dm_animals.animal_id`

**Required (P0):** `animal_id`, `lactation_no`  
**Target adds:** `calving_date` (highly recommended), `dry_off_date`, `milk_305d_kg`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| lactation_id | string | ✅ | recommended deterministic: `{animal_id}__{lactation_no}` |
| animal_id | string | ✅ | FK |
| lactation_no | int | ✅ | parity (1,2,3,...) |
| calving_date | date |  | required for many Target KPIs |
| dry_off_date | date |  | |
| milk_305d_kg | float |  | target variable for baseline ML |
| calving_easy_score | int |  | 1..5 if available |

**Integrity rules**
- `(animal_id, lactation_no)` unique
- `animal_id` exists
- If `calving_date` provided: must be `<= today`
- If `birth_date` exists on animal: `birth_date < calving_date`

**Example**
| lactation_id | animal_id | lactation_no | calving_date | milk_305d_kg |
|---|---|---:|---|---:|
| A1001__1 | A1001 | 1 | 2024-03-10 | 9450.0 |

---

## 4.5 MilkingsDaily (`dm_milkings_daily`) — Target
**Purpose:** daily aggregated milking yields per animal (and optionally per milking).

**PK:** `milking_day_id` (string)  
**Business key:** `(animal_id, milking_date)` unique (if daily aggregation only)  
**FK:** `animal_id`, optional `lactation_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| milking_day_id | string | ✅ | e.g., `{animal_id}__{milking_date}` |
| animal_id | string | ✅ | FK |
| lactation_id | string |  | FK |
| milking_date | date | ✅ | |
| milk_yield_kg | float | ✅ | daily total |
| milking_count | int |  | e.g., 2/3 |
| fat_pct | float |  | 0..20 |
| protein_pct | float |  | 0..20 |
| scc_cells_ml | int |  | somatic cell count |

**Integrity rules**
- `milking_date <= today`
- `milk_yield_kg >= 0`
- If `lactation_id` present, must exist and belong to same `animal_id`

**Example**
| milking_day_id | animal_id | lactation_id | milking_date | milk_yield_kg | milking_count |
|---|---|---|---|---:|---:|
| A1001__2024-03-11 | A1001 | A1001__1 | 2024-03-11 | 32.5 | 2 |

---

## 4.6 TestDay (`dm_testday`) — optional P0 / Target
**Purpose:** periodic official test-day measurements.

**PK:** `testday_id` (string)  
**Business key:** `(animal_id, test_date)` unique  
**FK:** `animal_id`, optional `lactation_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| testday_id | string | ✅ | `{animal_id}__{test_date}` |
| animal_id | string | ✅ | |
| lactation_id | string |  | |
| test_date | date | ✅ | |
| milk_yield_kg | float | ✅ | daily yield at test |
| fat_pct | float |  | |
| protein_pct | float |  | |
| scc_cells_ml | int |  | |

**Integrity rules**
- `test_date <= today`

**Example**
| testday_id | animal_id | lactation_id | test_date | milk_yield_kg | fat_pct | protein_pct |
|---|---|---|---|---:|---:|---:|
| A1001__2024-04-10 | A1001 | A1001__1 | 2024-04-10 | 34.1 | 4.1 | 3.3 |

---

## 4.7 SensorsDaily (`dm_sensors_daily`) — Target
**Purpose:** daily sensor aggregates per animal.

**PK:** `sensor_day_id` (string)  
**Business key:** `(animal_id, sensor_date)` unique (aggregated across sensors)  
**FK:** `animal_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| sensor_day_id | string | ✅ | `{animal_id}__{sensor_date}` |
| animal_id | string | ✅ | |
| sensor_date | date | ✅ | |
| activity_steps_count | int |  | >=0 |
| rumination_min | int |  | >=0 |
| lying_min | int |  | 0..1440 |
| body_temp_c | float |  | e.g., 35..42 |
| conductivity_ms_cm | float |  | optional |

**Integrity rules**
- `sensor_date <= today`

**Example**
| sensor_day_id | animal_id | sensor_date | activity_steps_count | rumination_min | body_temp_c |
|---|---|---|---:|---:|---:|
| A1001__2024-04-10 | A1001 | 2024-04-10 | 6120 | 480 | 38.6 |

---

## 4.8 HealthEvents (`dm_health_events`) — Target
**Purpose:** health incidents (mastitis, lameness, fever, etc.).

**PK:** `health_event_id` (string)  
**FK:** `animal_id`, optional `lactation_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| health_event_id | string | ✅ | e.g., HE_0001 |
| animal_id | string | ✅ | |
| lactation_id | string |  | |
| event_type | enum | ✅ | e.g., {mastitis, lameness, metritis, fever, other} |
| start_date | date | ✅ | |
| end_date | date |  | |
| severity | enum |  | {mild, moderate, severe} |
| diagnosis_text | string |  | |
| recorded_by_user_id | string |  | FK to users |

**Integrity rules**
- `start_date <= today`
- if `end_date` present: `end_date >= start_date`

**Example**
| health_event_id | animal_id | lactation_id | event_type | start_date | severity |
|---|---|---|---|---|---|
| HE_0001 | A1001 | A1001__1 | mastitis | 2024-04-12 | moderate |

---

## 4.9 Treatments (`dm_treatments`) — Target
**Purpose:** treatments/medications linked to health events or standalone.

**PK:** `treatment_id` (string)  
**FK:** `animal_id`, optional `health_event_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| treatment_id | string | ✅ | TR_0001 |
| animal_id | string | ✅ | |
| health_event_id | string |  | |
| drug_name | string | ✅ | |
| dose_value | float |  | |
| dose_unit | string |  | e.g., ml, mg |
| start_date | date | ✅ | |
| end_date | date |  | |
| withdrawal_milk_until | date |  | compliance |
| recorded_by_user_id | string |  | |

**Integrity rules**
- `start_date <= today`
- if `end_date` present: `end_date >= start_date`

**Example**
| treatment_id | animal_id | health_event_id | drug_name | start_date | end_date | withdrawal_milk_until |
|---|---|---|---|---|---|---|
| TR_0001 | A1001 | HE_0001 | Antibiotic_X | 2024-04-12 | 2024-04-14 | 2024-04-20 |

---

## 4.10 ReproEvents (`dm_repro_events`) — Target
**Purpose:** reproductive events: heat, insemination, pregnancy check, abortion, calving.

**PK:** `repro_event_id` (string)  
**FK:** `animal_id`, optional `bull_id`, optional `lactation_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| repro_event_id | string | ✅ | RE_0001 |
| animal_id | string | ✅ | |
| event_type | enum | ✅ | {heat, insemination, preg_check, abortion, calving, dry_off, other} |
| event_date | date | ✅ | |
| bull_id | string |  | for insemination |
| result | enum |  | e.g., {positive, negative} |
| notes | string |  | |

**Integrity rules**
- `event_date <= today`
- if `event_type == insemination` and `bull_id` present: bull must exist

**Example**
| repro_event_id | animal_id | event_type | event_date | bull_id | result |
|---|---|---|---|---|---|
| RE_0001 | A1001 | insemination | 2024-06-01 | B9001 |  |

---

## 4.11 Bulls (`dm_bulls`) — Target
**Purpose:** bull registry for breeding lineage.

**PK:** `bull_id` (string)

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| bull_id | string | ✅ | e.g., B9001 |
| bull_name | string | ✅ | |
| breed_code | string |  | |
| genetic_index_total | float |  | optional |
| status | enum |  | {active, retired} |

**Example**
| bull_id | bull_name | breed_code | status |
|---|---|---|---|
| B9001 | Atlas | HOL | active |

---

## 4.12 Pens (`dm_pens`) — Target
**Purpose:** pen/group structure.

**PK:** `pen_id` (string)  
**FK:** `site_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| pen_id | string | ✅ | PEN_01 |
| site_id | string | ✅ | |
| pen_name | string | ✅ | |
| pen_type | enum |  | {fresh, high, low, dry, heifers, calves, other} |
| capacity_head | int |  | |

**Example**
| pen_id | site_id | pen_name | pen_type | capacity_head |
|---|---|---|---|---:|
| PEN_01 | SITE_001 | Fresh Cows | fresh | 60 |

---

## 4.13 PenMoves (`dm_pen_moves`) — Target
**Purpose:** movement history.

**PK:** `pen_move_id` (string)  
**FK:** `animal_id`, `from_pen_id`, `to_pen_id`

**Fields**
| field | type | req |
|---|---:|:---:|
| pen_move_id | string | ✅ |
| animal_id | string | ✅ |
| move_date | date | ✅ |
| from_pen_id | string |  |
| to_pen_id | string | ✅ |
| reason | string |  |

**Integrity rules**
- `move_date <= today`
- if `from_pen_id` present: must exist

**Example**
| pen_move_id | animal_id | move_date | from_pen_id | to_pen_id | reason |
|---|---|---|---|---|---|
| PM_0001 | A1001 | 2024-03-10 |  | PEN_01 | post-calving |

---

## 4.14 FeedRations (`dm_feed_rations`) — Target
**Purpose:** ration definition.

**PK:** `ration_id` (string)  
**FK:** `site_id`, optional `pen_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| ration_id | string | ✅ | R_01 |
| site_id | string | ✅ | |
| pen_id | string |  | ration can be per-pen |
| ration_name | string | ✅ | |
| effective_from | date | ✅ | |
| effective_to | date |  | |
| dm_pct | float |  | 0..100 |
| nel_mcal_kg_dm | float |  | optional |
| cp_pct_dm | float |  | crude protein % DM |

**Integrity rules**
- `effective_from <= today` (usually)
- if `effective_to` present: `effective_to >= effective_from`

**Example**
| ration_id | site_id | pen_id | ration_name | effective_from | dm_pct | cp_pct_dm |
|---|---|---|---|---|---:|---:|
| R_01 | SITE_001 | PEN_01 | Fresh TMR | 2024-03-01 | 45.0 | 16.5 |

---

## 4.15 FeedDeliveries (`dm_feed_deliveries`) — Target
**Purpose:** daily feed delivered (by ration / ingredient).

**PK:** `delivery_id` (string)  
**FK:** `site_id`, optional `pen_id`, optional `ration_id`

**Fields**
| field | type | req |
|---|---:|:---:|
| delivery_id | string | ✅ |
| site_id | string | ✅ |
| pen_id | string |  |
| ration_id | string |  |
| delivery_date | date | ✅ |
| feed_as_fed_kg | float | ✅ |
| cost_value | float |  |
| cost_currency | string |  |

**Integrity rules**
- `delivery_date <= today`
- `feed_as_fed_kg >= 0`

**Example**
| delivery_id | site_id | pen_id | ration_id | delivery_date | feed_as_fed_kg | cost_value | cost_currency |
|---|---|---|---|---|---:|---:|---|
| FD_0001 | SITE_001 | PEN_01 | R_01 | 2024-04-10 | 1800.0 | 310.0 | EUR |

---

## 4.16 Prices/Economics (`dm_prices`) — Target
**Purpose:** time series of economic parameters.

**PK:** `price_id` (string)  
**FK:** optional `farm_id`, `site_id`

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| price_id | string | ✅ | PR_0001 |
| scope_type | enum | ✅ | {global, farm, site} |
| farm_id | string |  | if scope=farm |
| site_id | string |  | if scope=site |
| item_type | enum | ✅ | {milk_price, feed_price, vet_cost, other} |
| item_name | string | ✅ | e.g., "milk_raw" |
| effective_from | date | ✅ | |
| effective_to | date |  | |
| value | float | ✅ | |
| currency | string | ✅ | e.g., EUR |
| unit | string | ✅ | e.g., "EUR/kg", "EUR/t" |

**Example**
| price_id | scope_type | farm_id | item_type | item_name | effective_from | value | currency | unit |
|---|---|---|---|---|---|---:|---|---|
| PR_0001 | farm | FARM_001 | milk_price | milk_raw | 2024-01-01 | 0.45 | EUR | EUR/kg |

---

## 4.17 Alerts (`dm_alerts`) — Target
**Purpose:** system-generated alerts (health, yield drops, sensor anomalies, compliance).

**PK:** `alert_id` (string)  
**FK:** optional `animal_id`, `site_id`, `pen_id`

**Fields**
| field | type | req |
|---|---:|:---:|
| alert_id | string | ✅ |
| created_ts | datetime | ✅ |
| alert_type | enum | ✅ | {health, production, repro, compliance, other} |
| severity | enum | ✅ | {info, warn, error} |
| status | enum | ✅ | {open, acknowledged, closed} |
| farm_id | string | ✅ |
| site_id | string |  |
| pen_id | string |  |
| animal_id | string |  |
| message | string | ✅ |
| evidence_ref | string |  | points to fact pack / tables |

**Integrity rules**
- If `animal_id` set: must exist and belong to `farm_id`

**Example**
| alert_id | created_ts | alert_type | severity | status | farm_id | animal_id | message |
|---|---|---|---|---|---|---|---|
| AL_0001 | 2024-04-12T09:20:00Z | health | warn | open | FARM_001 | A1001 | Possible mastitis: SCC high |

---

## 4.18 Decisions (`dm_decisions`) — Target (extends MVP decision_log idea)
**Purpose:** user decisions about recommendations/alerts.

**PK:** `decision_id` (string)  
**FK:** `user_id -> dm_users.user_id` (Target), optional `alert_id`

**Business key (recommended):** `(object_type, object_id, recommendation_type, decided_ts)` unique-ish.

**Fields**
| field | type | req | notes |
|---|---:|:---:|---|
| decision_id | string | ✅ | |
| decided_ts | datetime | ✅ | |
| user_id | string | ✅ | |
| farm_id | string | ✅ | |
| object_type | enum | ✅ | {animal_lactation, animal, pen, farm, report} |
| object_id | string | ✅ | for animal_lactation: `{animal_id}__{lactation_no}` |
| recommendation_type | enum | ✅ | {priority, observe, cull_candidate, other} |
| decision | enum | ✅ | {accept, reject, defer} |
| comment | string |  | |
| alert_id | string |  | link to originating alert |
| scoring_run | string |  | lineage |
| report_version | string |  | lineage |

**Integrity rules**
- `user_id` exists and has permission for `farm_id`
- If `alert_id` present: must exist

**Example**
| decision_id | decided_ts | user_id | farm_id | object_type | object_id | recommendation_type | decision | comment |
|---|---|---|---|---|---|---|---|---|
| D_0001 | 2024-12-30T10:15:00Z | U_OP_01 | FARM_001 | animal_lactation | A1001__1 | priority | accept | Monitor and treat per protocol |

---

## 4.19 Reports (`dm_reports`) — Target
**Purpose:** generated reports with versioning.

**PK:** `report_version` (string)  
**FK:** `farm_id`

**Fields**
| field | type | req |
|---|---:|:---:|
| report_version | string | ✅ |
| created_ts | datetime | ✅ |
| farm_id | string | ✅ |
| data_version | string | ✅ |
| qc_run | string | ✅ |
| model_version | string | ✅ |
| scoring_run | string | ✅ |
| report_type | enum | ✅ | {daily_ops, weekly_ops, genetics, custom} |
| mode | enum | ✅ | {llm, fallback} |
| exports_dir | string | ✅ | filesystem pointer |

**Example**
| report_version | created_ts | farm_id | data_version | qc_run | model_version | scoring_run | report_type | mode |
|---|---|---|---|---|---|---|---|---|
| rep_20241230_101800_ab12cd | 2024-12-30T10:18:00Z | FARM_001 | dv_demo_001 | qc_... | model_... | score_... | daily_ops | fallback |

---

## 4.20 Users & Roles (`dm_users`, `dm_roles`, `dm_user_roles`) — Target
**Purpose:** RBAC minimum for on-prem.

### `dm_users`
**PK:** `user_id` (string)  
**Fields**
| field | type | req |
|---|---:|:---:|
| user_id | string | ✅ |
| username | string | ✅ |
| display_name | string |  |
| is_active | bool | ✅ |
| created_ts | datetime | ✅ |

### `dm_roles`
**PK:** `role_name` (string)  
Predefined roles: `Admin`, `Operator`, `Viewer`

### `dm_user_roles`
**PK:** `(user_id, role_name, farm_id)`  
**Fields**
| field | type | req |
|---|---:|:---:|
| user_id | string | ✅ |
| role_name | string | ✅ |
| farm_id | string | ✅ |

**Integrity rules**
- User must have at least one role assignment
- Viewer: read-only (download allowed), Operator/Admin: can run jobs and write decisions

**Example (users)**
| user_id | username | is_active | created_ts |
|---|---|---|---|
| U_ADM_01 | admin | true | 2024-12-30T08:00:00Z |
| U_OP_01 | operator | true | 2024-12-30T08:00:00Z |
| U_VW_01 | viewer | true | 2024-12-30T08:00:00Z |

**Example (user roles)**
| user_id | role_name | farm_id |
|---|---|---|
| U_ADM_01 | Admin | FARM_001 |
| U_OP_01 | Operator | FARM_001 |
| U_VW_01 | Viewer | FARM_001 |

---

## 5) Key relationships (summary)

- `dm_farms (1) -> dm_sites (N)`
- `dm_farms (1) -> dm_animals (N)`
- `dm_animals (1) -> dm_lactations (N)`
- `dm_animals (1) -> dm_milkings_daily (N)`
- `dm_animals (1) -> dm_testday (N)`
- `dm_animals (1) -> dm_sensors_daily (N)`
- `dm_animals (1) -> dm_health_events (N) -> dm_treatments (N)`
- `dm_animals (1) -> dm_repro_events (N)` with optional `dm_bulls (1)`
- `dm_sites (1) -> dm_pens (N)` and `dm_animals (1) -> dm_pen_moves (N)`
- `dm_farms (1) -> dm_alerts (N) -> dm_decisions (N)`
- `dm_reports` ties together `{data_version, qc_run, model_version, scoring_run, report_version}`

## 6) Minimal integrity rule set (Target baseline)

These are the **minimum** cross-table rules expected for Target:

1. **FK existence**
   - Every `animal_id` referenced must exist in `dm_animals`.
   - Every `farm_id` referenced must exist in `dm_farms`.
2. **Date sanity**
   - Any `*_date` must be `<= today` unless explicitly configured otherwise.
   - `birth_date < calving_date` when both exist.
3. **Uniqueness**
   - `dm_animals.animal_id` unique
   - `dm_lactations` unique on `(animal_id, lactation_no)` and `lactation_id`
4. **Value ranges (starter)**
   - `milk_yield_kg >= 0`
   - `fat_pct/protein_pct` in 0..20
   - `scc_cells_ml >= 0`

## 7) Cross-table examples (consistent set)

IDs used across examples:
- `farm_id = FARM_001`
- `site_id = SITE_001`
- `pen_id = PEN_01`
- `animal_id = A1001`
- `lactation_id = A1001__1`
- `bull_id = B9001`

This consistency allows using examples as a minimal synthetic fixture.

---

## Appendix A: Mapping from MVP P0 datasets

- `dm_farms` stays P0 as-is; Target adds optional fields (`country_code`, `timezone`).
- `dm_animals` stays P0 as-is; Target adds optional fields (`birth_date`, `sex`, etc.).
- `dm_lactations` stays P0 as-is; Target introduces `lactation_id` but keeps `(animal_id, lactation_no)` as business key.
- `dm_testday` remains optional in MVP; becomes recommended in Target.

