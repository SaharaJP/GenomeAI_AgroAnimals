# Withdrawal: правила расчёта (Vet dashboard v2)

## Источники данных

1) Канонический датасет `dm_treatments`:
- `start_date` — дата начала лечения
- `end_date` — дата окончания лечения (если пусто, считаем датой последнего введения `start_date`)
- `treatment_type` — тип лечения (категория)
- `withdrawal_end_date` — (опционально) явная дата окончания withdrawal, если пришла из исходной системы.

2) Конфиг правил: `configs/health/withdrawal_rules.yaml`
- `treatment_types.<treatment_type>.withdrawal_days` — число календарных дней withdrawal
- `default_withdrawal_days` — fallback, если treatment_type неизвестен

## Правило расчёта

Для каждой записи лечения:

`last_admin_date = end_date если заполнено, иначе start_date`

`withdrawal_end_date_calc = last_admin_date + withdrawal_days`

Где `withdrawal_days` берётся из `configs/health/withdrawal_rules.yaml`.

### Про "включительно"

В системе окно withdrawal считается **включительно по дате окончания**:

- ограничение активно на дату `last_admin_date`;
- ограничение продолжается до `withdrawal_end_date_effective` включительно;
- на дату `asof_date` запись считается активной, если `asof_date <= withdrawal_end_date_effective`.

## Приоритеты и прозрачность

- Если `dm_treatments.withdrawal_end_date` заполнено, это трактуется как **явное значение из источника**.
- Дашборд всё равно считает `withdrawal_end_date_calc` по правилам и показывает флаг `withdrawal_mismatch` при расхождении.

## Что НЕ делаем

- Не ставим диагнозы и не выводим «болезнь от ИИ».
- Withdrawal — это календарный расчёт по фактам лечения и заданным правилам.
