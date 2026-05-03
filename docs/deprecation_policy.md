# Deprecation policy для legacy/shim-слоя

## Зачем это нужно

В проекте deliberately сохранены backward-compatible точки входа:
- legacy Python imports (`genomeai.application.*`, `web_cabinet.*`, `genomeai.train`, `genomeai.score`),
- legacy CLI alias `verify-refactor`.

Они должны **оставаться рабочими**, но обязаны явно сигнализировать разработчику,
что canonical путь теперь находится в `core.*` или в новом CLI name.

Одновременно мы не хотим, чтобы в CI незаметно появлялись новые deprecation warnings.
Поэтому для предупреждений введён документированный allowlist + budget.

## Canonical policy

Источник правды:
- `configs/compat/deprecation_warnings_v1.json`

В policy для каждого допустимого warning фиксируются:
- `name` — стабильный идентификатор правила,
- `kind` — тип (`shim_import`, `cli_alias`),
- `trigger` — какой import/alias должен вызвать warning,
- `category` — `DeprecationWarning` или `PendingDeprecationWarning`,
- `message_regex` — точный ожидаемый текст,
- `max_count` — допустимый budget на один прогон gate.

## Что считается допустимым

Допустимы только warnings, которые одновременно:
1. возникают из-за backward-compatible shim/alias surface,
2. документированы в `configs/compat/deprecation_warnings_v1.json`,
3. укладываются в свой `max_count` budget.

## Что считается недопустимым

Недопустимы:
- любые новые `DeprecationWarning`, которых нет в allowlist,
- изменение текста warning без обновления policy,
- повторное срабатывание warning сверх budget,
- deprecation warning в canonical `core.*` paths.

## CI / test gate

Gate реализован тестом:
- `tests/test_t16_07_deprecation_policy.py`

И включён в CI pytest gate через:
- `ci/pytest_gate.txt`

Тест проверяет три вещи:
1. documented shim imports дают только allowlisted warnings,
2. CLI alias `verify-refactor` соответствует allowlist,
3. новый или избыточный deprecation warning приводит к падению gate.

## Как добавить новый shim правильно

1. Создать shim/thin-wrapper и оставить backward-compatible поведение.
2. Явно вызывать `warn_legacy_import(...)` или аналогичный warning в одной точке.
3. Добавить новое правило в `configs/compat/deprecation_warnings_v1.json`.
4. Добавить/обновить targeted тест, который реально вызывает этот shim.
5. Если shim является публичным surface, обновить docs (например `docs/project_map.md` или `docs/public_interfaces.json`, если применимо).

## Как регистрировать ожидаемую deprecation

Для новой deprecation записи держим такие правила:
- сообщение должно быть deterministic и machine-checkable,
- regex должен быть максимально узким,
- `max_count` по умолчанию = `1`,
- budget повышаем только если один и тот же warning действительно должен возникать несколько раз в одном gate и это нельзя безопасно локализовать.

## Примеры

Допустимо:
- `genomeai.application is deprecated; import from core.application instead.`
- `CLI alias 'verify-refactor' is deprecated; use 'verify_refactor' instead.`

Недопустимо:
- `some_module is deprecated` без записи в allowlist,
- новый warning в `core.application.*`,
- два одинаковых warning при budget `max_count=1`.
