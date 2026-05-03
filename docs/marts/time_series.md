# T3-02 — Time-series витрины: cow_day и group_day (v1)

Цель: единые «витрины по дням» для графиков в кабинете и базовых ML-признаков.

## 1) cow_day

**Ключ:** `farm_id + animal_id + date` (день, UTC, floor to day).

### Источники
- `dm_milkings_daily` — операционные надои (daily).
- `dm_sensors_daily` — daily агрегаты датчиков.

### Поля (v1, только минимально нужные)
- Идентификаторы: `farm_id, animal_id, date, lactation_id, dim`.
- Надои/состав: `milk_kg, fat_pct, protein_pct, scc_cells_ml`.
- Сенсоры: `activity_steps, rumination_min, body_temp_c`.

### Правила обработки пропусков (v1)
1) **Dense grid:** для каждого животного строится ежедневная сетка дат между `min(date)` и `max(date)` по объединению источников (milkings OR sensors). Это делает ряды пригодными для графиков.
2) Флаги наблюдаемости:
   - `is_observed_milkings` — факт присутствия записи/значений надоев.
   - `is_observed_sensors` — факт присутствия записи сенсоров.
3) **Короткая имputation для первых графиков/признаков:** для `milk_kg/activity_steps/rumination_min/body_temp_c` создаются колонки `*_ffill3` (forward-fill с лимитом 3 дня). Флаг `*_imputed_ffill3` отмечает, что значение получено имputation.

> Важно: эти правила не «улучшают» факты, а обеспечивают стабильность визуализаций и простых фичей на коротких разрывах.

## 2) group_day

**Ключ:** `farm_id + pen_id + date`.

### Привязка животного к группе
Источник: `dm_pen_moves`.

Правило (v1): для каждой строки cow_day берём последнее перемещение `move_date <= date` (as-of join) и ставим `pen_id = to_pen_id`.

### Агрегации (v1)
- `headcount` = `nunique(animal_id)`.
- `sum_milk_kg` = `sum(milk_kg)`.
- `avg_milk_kg` = `mean(milk_kg)`.
- `avg_activity_steps`, `avg_rumination_min`, `avg_body_temp_c` = `mean(...)`.
- `pct_missing_milkings` = `1 - mean(is_observed_milkings)`.
- `pct_missing_sensors` = `1 - mean(is_observed_sensors)`.

## 3) Lineage / воспроизводимость

При сборке витрин пишется `lineage_manifest.json`, где фиксируется:
- какие исходные таблицы использовались;
- ключи и правила join/aggregation;
- правила пропусков/имputation.

Артефакты лежат в: `artifacts/<data_version>/marts/<marts_run>/`.
