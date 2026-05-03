# GenomeAI AgroAnimals — Data Contracts Catalog

- Generated at (UTC): 2026-03-08T07:06:20+00:00
- Dataset count: 6
- Required for MVP: 3
- Mapping templates: 15

## Summary

| Dataset | Version | Domain | Status | Required | Required fields | Mapping templates | QC coverage |
|---|---|---|---|---:|---:|---:|---|
| dm_animals | 1.0.0 | master_data | active | yes | 2 | 4 | covered:5 |
| dm_farms | 1.0.0 | reference | active | yes | 2 | 4 | covered:3, n/a:2 |
| dm_health_events | 1.0.0 | health | active | no | 5 | 1 | covered:3, planned:2 |
| dm_lactations | 1.0.0 | production | active | yes | 2 | 4 | covered:4, n/a:1 |
| dm_testday | 1.0.0 | production | active | no | 2 | 1 | covered:2, n/a:1, planned:2 |
| dm_treatments | 1.0.0 | health | active | no | 5 | 1 | covered:2, n/a:1, planned:2 |

## dm_animals

- Contract version: 1.0.0
- Domain/status: master_data / active
- Required for MVP: yes
- Source systems: СЕЛЭКС, excel, 1c, selex
- Required fields: animal_id, farm_id
- Description: Справочник животных (P0). 1 строка = 1 животное.
- Notes: FK на dm_farms не проверяется в A0 (будет в QC).

### Fields

| Field | Type | Required | Allowed values | Description |
|---|---|---|---|---|
| animal_id | string | yes | — | Уникальный идентификатор животного |
| farm_id | string | yes | — | Ссылка на dm_farms |
| ear_tag | string | no | — | Бирка/номер |
| breed | string | no | — | Порода |
| sex | string | no | F, M | Пол (F/M) |
| birth_date | date | no | — | Дата рождения |
| is_alive | bool | no | — | Животное живо |
| status | string | no | — | Статус |

### Mapping templates

| Source | Path | Columns | Dayfirst |
|---|---|---:|---|
| example | configs/mappings/animals_example.yaml | 8 | no |
| 1c | configs/mappings/templates/1c/animals.yaml | 8 | yes |
| excel | configs/mappings/templates/excel/animals.yaml | 8 | no |
| selex | configs/mappings/templates/selex/animals.yaml | 8 | yes |

### Example files

- data/examples/dm_animals.csv
- data/fixtures/target_v2/dm_animals.csv

## dm_farms

- Contract version: 1.0.0
- Domain/status: reference / active
- Required for MVP: yes
- Source systems: excel, 1c, manual, selex
- Required fields: farm_id, farm_name
- Description: Справочник ферм/площадок (P0). 1 строка = 1 ферма.
- Notes: farm_id — ключ для ссылок из других датасетов.

### Fields

| Field | Type | Required | Allowed values | Description |
|---|---|---|---|---|
| farm_id | string | yes | — | Уникальный идентификатор фермы |
| farm_name | string | yes | — | Название фермы |
| region | string | no | — | Регион/область |
| country | string | no | — | Страна |
| lat | float | no | — | Широта |
| lon | float | no | — | Долгота |
| created_at | date | no | — | Дата (YYYY-MM-DD) |
| is_active | bool | no | — | Активна ли ферма |

### Mapping templates

| Source | Path | Columns | Dayfirst |
|---|---|---:|---|
| example | configs/mappings/farms_example.yaml | 8 | no |
| 1c | configs/mappings/templates/1c/farms.yaml | 8 | yes |
| excel | configs/mappings/templates/excel/farms.yaml | 8 | no |
| selex | configs/mappings/templates/selex/farms.yaml | 8 | no |

### Example files

- data/examples/dm_farms.csv
- data/fixtures/target_v2/dm_farms.csv

## dm_health_events

- Contract version: 1.0.0
- Domain/status: health / active
- Required for MVP: no
- Source systems: 1c, excel, manual
- Required fields: tenant_id, event_id, animal_id, event_date, event_type
- Description: Фактические события здоровья (учёт). 1 строка = 1 событие (осмотр/симптом/факт).
- Notes: Это учёт фактов. Никаких диагнозов от ИИ.

### Fields

| Field | Type | Required | Allowed values | Description |
|---|---|---|---|---|
| tenant_id | string | yes | — | Идентификатор тенанта/фермы (логический) |
| event_id | string | yes | — | Уникальный идентификатор события |
| animal_id | string | yes | — | Идентификатор животного |
| event_date | date | yes | — | Дата события |
| event_type | string | yes | — | Код типа события (из справочника) |
| severity | string | no | low, medium, high, critical | Опциональная тяжесть (не диагноз) |
| notes | string | no | — | Комментарий оператора/ветврача |

### Mapping templates

| Source | Path | Columns | Dayfirst |
|---|---|---:|---|
| example | configs/mappings/health_events_example.yaml | 6 | no |

### Example files

- data/fixtures/target_v2/dm_health_events.csv

## dm_lactations

- Contract version: 1.0.0
- Domain/status: production / active
- Required for MVP: yes
- Source systems: СЕЛЭКС, excel, 1c, selex
- Required fields: animal_id, lactation_no
- Description: Лактации животных (P0). 1 строка = 1 лактация у животного.
- Notes: Бизнес-правила и проверки дат — позже (QC).

### Fields

| Field | Type | Required | Allowed values | Description |
|---|---|---|---|---|
| animal_id | string | yes | — | Ссылка на животное |
| lactation_no | int | yes | — | Номер лактации |
| calving_date | date | no | — | Дата отёла |
| dryoff_date | date | no | — | Дата запуска |
| days_in_milk | int | no | — | DIM |
| milk_305d_kg | float | no | — | 305-дневный удой (кг) |
| fat_pct | float | no | — | Жир, % |
| protein_pct | float | no | — | Белок, % |

### Mapping templates

| Source | Path | Columns | Dayfirst |
|---|---|---:|---|
| example | configs/mappings/lactations_example.yaml | 8 | no |
| 1c | configs/mappings/templates/1c/lactations.yaml | 8 | yes |
| excel | configs/mappings/templates/excel/lactations.yaml | 8 | no |
| selex | configs/mappings/templates/selex/lactations.yaml | 8 | yes |

### Example files

- data/examples/dm_lactations.csv
- data/fixtures/target_v2/dm_lactations.csv

## dm_testday

- Contract version: 1.0.0
- Domain/status: production / active
- Required for MVP: no
- Source systems: СЕЛЭКС, excel
- Required fields: animal_id, test_date
- Description: Контрольные дойки (опционально). 1 строка = измерение в дату.
- Notes: Файл может отсутствовать — validate не падает.

### Fields

| Field | Type | Required | Allowed values | Description |
|---|---|---|---|---|
| animal_id | string | yes | — | Ссылка на животное |
| test_date | date | yes | — | Дата измерения |
| milk_kg | float | no | — | Удой за день, кг |
| fat_pct | float | no | — | Жир, % |
| protein_pct | float | no | — | Белок, % |
| somatic_cells | int | no | — | Соматические клетки |

### Mapping templates

| Source | Path | Columns | Dayfirst |
|---|---|---:|---|
| example | configs/mappings/testday_example.yaml | 6 | no |

### Example files

- data/examples/dm_testday.csv
- data/fixtures/target_v2/dm_testday.csv

## dm_treatments

- Contract version: 1.0.0
- Domain/status: health / active
- Required for MVP: no
- Source systems: 1c, excel, manual
- Required fields: tenant_id, treatment_id, animal_id, start_date, treatment_type
- Description: Учёт назначений/лечений. 1 строка = 1 курс/назначение.
- Notes: withdrawal рассчитывается детерминированно по configs/health/withdrawal_rules.yaml (см. docs/health/withdrawal_rules.md).; Никаких диагнозов от ИИ: tests/веб используют только факты + правила.

### Fields

| Field | Type | Required | Allowed values | Description |
|---|---|---|---|---|
| tenant_id | string | yes | — | Идентификатор тенанта/фермы (логический) |
| treatment_id | string | yes | — | Уникальный идентификатор лечения |
| animal_id | string | yes | — | Идентификатор животного |
| start_date | date | yes | — | Дата начала лечения |
| end_date | date | no | — | Дата окончания лечения (если пусто, считаем start_date) |
| treatment_type | string | yes | — | Категория лечения (из справочника) |
| reason_event_id | string | no | — | Ссылка на событие здоровья (dm_health_events.event_id) |
| withdrawal_end_date | date | no | — | Опциональная явная дата окончания withdrawal из источника |

### Mapping templates

| Source | Path | Columns | Dayfirst |
|---|---|---:|---|
| example | configs/mappings/treatments_example.yaml | 7 | no |

### Example files

- data/fixtures/target_v2/dm_treatments.csv
