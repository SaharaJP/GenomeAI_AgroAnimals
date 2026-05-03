# T4-02 — ML-спека: Риск мастита (MVP+ / Target)

## 1) Постановка
**Задача:** оценка *риска мастита* на горизонте **N дней** для каждой коровы на уровне `cow_day`  
Единица наблюдения: `(farm_id, animal_id, date)`.

**Выход модели:** `risk_proba` (0..1) + флаг `risk_flag` по бизнес‑порогу.  
**Политика:** никаких диагнозов — только риск и рекомендованные действия (осмотр/проба/перепроверка).

## 2) Целевая переменная
### 2.1 Основной источник
`dm_health_events`:
- `event_date` (дата события)
- `condition_code` (код состояния)

**y(date)=1**, если для той же коровы мастит‑событие случилось в окне:
`(date, date + N]` (строго после текущего дня).

Список мастит‑кодов задаётся в `configs/mastitis_risk.yaml` (`mastitis_codes`), матчинг:
- без учёта регистра
- точное совпадение **или** substring‑match (для разных вендоров/кодов)

### 2.2 Fallback при отсутствии кодов/таблицы
Если `dm_health_events` отсутствует или по кодам не найдено ни одного мастит‑события, включается proxy‑fallback:
**y(date)=1**, если в окне `(date, date+N]` есть будущий всплеск `scc_cells_ml >= fallback_scc_high`.

Порог `fallback_scc_high` задаётся в `configs/mastitis_risk.yaml`.

## 3) Признаки
Источники:
- `cow_day` mart (из `marts_timeseries`): `milk_kg`, `scc_cells_ml`, `activity_steps`, `rumination_min`, `body_temp_c`, + флаги наблюдения.
- `dm_lactations`: `lactation_no` / parity (best-effort join).

Фичи v1 (MVP+):
- rolling‑агрегаты по окнам `{3,7,14,21}` дней для:
  - `milk_kg_ffill3`, `scc_cells_ml_ffill3`, `activity_steps_ffill3`, `rumination_min_ffill3`, `body_temp_c_ffill3`
  - mean/std/min/max
- статические: `lactation_no`, `dim`, `is_observed_milkings`, `is_observed_sensors`

## 4) Валидация и анти‑утечки
Split: **time-based** (holdout по времени), с гарантиями:
- `max(train_date) + N < min(test_date)` (сдвиг границы до выполнения)
- признаки строятся только по прошлому/текущему дню (rolling windows)

Переносимость по фермам:
- в `train_summary.json` сохраняются базовые статистики (n_train/n_test)  
- **Target-следующий шаг**: добавить отдельный farm-holdout сплит (когда появится достаточно ферм).

## 5) Метрики
- **PR-AUC** (основная)
- `Precision@K`, `Recall@K` (K=50,100 в MVP+)

Бизнес‑порог:
- `risk_threshold` из `configs/mastitis_risk.yaml`
- параметры стоимости ошибок: `cost_false_alert`, `cost_missed_case` (пока narrative placeholders)

## 6) Explainability
MVP+:
- глобальная важность (feature_importance.csv) из модели (best-effort)
- локальные «почему» как **факты** (`why_facts` в scoring):
  - `SCC_high`, `milk_low`, `rumination_low`, `temp_high`
  - это не объяснение модели и не диагноз; это подсветка сигналов.

## 7) Интеграция: риск → Alert → действие → Decision Log
1) `score-mastitis` пишет `mastitis_risk_scores.csv` и `scoring_summary.json`.
2) `alerts_v2.generate_mastitis_risk_alerts()` поднимает alert‑кандидаты типа `ML.MASTITIS_RISK` для `risk_flag=1`.
3) UI показывает алерт и действия (из `configs/alerts_v2/catalog.yaml`), пользователь подтверждает/закрывает.
4) UI пишет решение через `decision_log.add_decision` (сквозные версии сохраняются).

## Артефакты
- Train: `artifacts/<data_version>/mastitis/models/<model_version>/...`
- Score: `artifacts/<data_version>/mastitis/scoring/<scoring_run>/...`
