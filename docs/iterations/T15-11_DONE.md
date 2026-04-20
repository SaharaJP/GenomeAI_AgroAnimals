# T15-11 — Стабилизация публичных интерфейсов

## Что сделано
1. Зафиксирован machine-readable snapshot публичных интерфейсов в `docs/public_interfaces.json`.
2. Добавлен human-readable документ `docs/public_interfaces.md`.
3. Добавлен `core.public_interfaces` для сборки/проверки CLI/API/Streamlit/Python contract surface.
4. Введён единый `core.config` loader/validator с понятными ошибками.
5. `permission_matrix`, `audit_retention` и `jobs runner` переведены на общий config loader.
6. FastAPI startup теперь валидирует критичные конфиги до инициализации БД/worker.
7. Добавлен deprecation warning для legacy CLI alias `verify-refactor`.
8. Добавлены контракт-тесты для CLI/API/страниц/сигнатур и тесты config validation/startup wiring.

## Как обновлять интерфейс осознанно
1. Внести изменение в код.
2. Обновить `docs/public_interfaces.json` только вместе с документацией и тестами.
3. Прогнать targeted pytest + smoke + `verify_refactor`.
4. Зафиксировать причину изменения интерфейса в changelog/iteration note.
