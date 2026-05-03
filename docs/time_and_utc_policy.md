# Time / UTC policy (T16-01)

## Что считается canonical
- Runtime-код больше не должен вызывать `datetime.utcnow()`.
- Canonical helper lives in `src/core/common/time.py`.
- Источник текущего времени — только timezone-aware UTC (`datetime.now(timezone.utc)`).

## Почему это сделано
`datetime.utcnow()` возвращает naive datetime и в новых версиях Python даёт предупреждения/неоднозначную семантику. Для проекта важно убрать warning, но не менять внешний surface артефактов.

## Правила совместимости
Чтобы не менять поведение уже существующего MVP+/golden:
- `run_id`, file stamps, export names сохраняют формат `YYYYmmdd_HHMMSS`.
- Даты для `asof_date`/UI defaults сохраняют формат `YYYY-MM-DD`.
- Поля вида `created_at`/`updated_at`, которые исторически использовали `...isoformat() + "Z"`, продолжают сериализоваться в том же виде.
- Поля, которые раньше использовали aware ISO с `+00:00`, продолжают использовать `+00:00`.
- Naive datetime внутри helper трактуется как уже UTC — это deliberate backward-compatibility rule для legacy кода, выросшего из `datetime.utcnow()`.

## Рекомендуемые helper-функции
- `utc_now()` — aware UTC datetime
- `utc_date()` / `utc_date_str()` — дата UTC
- `utc_timestamp_compact()` — `YYYYmmdd_HHMMSS`
- `utc_isoformat()` — ISO with `+00:00`
- `utc_isoformat_z()` — ISO with trailing `Z`
- `ensure_utc(dt)` — нормализация datetime в UTC без смены legacy semantics для naive values

## Практическое правило для новых изменений
- Новый runtime-код использует только `core.common.time`.
- UI/CLI/reporting/dashboard не дублируют собственные `utcnow`/`strftime` helper-ы без необходимости.
- Если нужен новый формат времени, он сначала добавляется в `core.common.time`, а затем переиспользуется адаптерами.
