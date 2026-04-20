# Web lifespan migration (T16-02)

## Что изменено

Web startup/shutdown переведен с deprecated `@app.on_event("startup")` на `FastAPI(lifespan=...)`.

## Сохраненное поведение startup

Порядок и смысл операций сохранены:

1. `validate_runtime_config(settings)`
2. `validate_startup_config_bundle(project_root)`
3. `init_db(conn)`
4. `ensure_default_users(...)`
5. `ensure_default_users_v2(...)`
6. `ensure_default_playbooks(...)`
7. `worker.start()` если `GENOMEAI_WEB_DISABLE_WORKER != "1"`

## Shutdown

При завершении lifespan web-worker останавливается через `worker.stop()`.
Это сделано симметрично startup и без изменения публичных route/CLI/import surface.

## Совместимость

- Глобальный `app` сохранен.
- Вспомогательная функция `_startup()` сохранена для существующих тестов и совместимых внутренних вызовов.
- `JobWorker.start()` теперь повторно очищает stop-flag, поэтому worker можно безопасно стартовать снова после `stop()` в lifespan/test-контексте.
