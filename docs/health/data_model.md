# Health data model (T4-01)

## dm_health_events

Факты событий здоровья. Это **не** диагнозы от ИИ, а учёт того, что произошло (осмотр/симптом/внешний факт).

Ключи:
- PK: (tenant_id, event_id)

Поля (минимум v1):
- tenant_id (string, required)
- event_id (string, required)
- animal_id (string, required)
- event_date (date, required)
- event_type (string, required) — код из справочника `configs/health/dictionaries/health_event_types.csv`
- severity (string, optional): low/medium/high/critical
- notes (string, optional)

## dm_treatments

Факты лечений/назначений. 1 строка = 1 курс.

Ключи:
- PK: (tenant_id, treatment_id)

Поля (минимум v1):
- tenant_id (string, required)
- treatment_id (string, required)
- animal_id (string, required)
- start_date (date, required)
- end_date (date, optional; если пусто, считается равным start_date)
- treatment_type (string, required) — код из справочника `configs/health/dictionaries/treatment_types.csv`
- reason_event_id (string, optional) — ссылка на dm_health_events.event_id
- withdrawal_end_date (date, optional) — явное значение из источника (если есть)

## Withdrawal

Source of truth: `configs/health/withdrawal_rules.yaml` + алгоритм из `docs/health/withdrawal_rules.md`.

Важно: окно считается **включительно** по дате окончания.

## QC правила (v2)

Файл: `configs/qc_rules_v2.yaml`, секция `HEALTH (T4)`.

Минимум:
- обязательные колонки
- уникальность PK
- FK к животным и событиям
- валидность дат (не из будущего)
- start_date <= end_date
- пересечения интервалов лечений в пределах (tenant_id, animal_id)
- allowed values для event_type/treatment_type
