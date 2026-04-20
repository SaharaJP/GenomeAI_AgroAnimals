# T34-07 — Production profile lockdown

Статус шага: **partially_proven**.

## Что сделано

Этот шаг не объявляет полный live production proof, но вводит жёсткий production-lockdown контракт для `adult/stage/prod` профилей.

### 1. Production diagnostics
Добавлен production-lockdown snapshot с явной публикацией:

- active runtime storage backend
- active runtime state backend
- active queue backend
- auth mode
- internal web login mode
- compatibility flags
- forbidden legacy tails status
- startup gate status

Доступно через:

- `GET /api/production-profile`
- `GET /admin/production-profile`
- `GET /api/observability`
- `GET /readyz` headers

### 2. Fail-fast production lockdown
Для `adult/stage/prod` введён дополнительный gate поверх storage/queue/auth в `validate_runtime_config()`.

Lockdown проверяет, что:

- legacy storage fallback не активен
- queue fallback не активен
- legacy cookie/session bypass не активен
- embedded worker path не активен в web/backend process при Redis queue
- internal web login не включён молча

### 3. Internal web login policy
Введена явная политика `GENOMEAI_INTERNAL_WEB_LOGIN_MODE`:

- `enabled` — compat/dev mode
- `disabled` — production default
- `support_only` — только при явном `GENOMEAI_INTERNAL_WEB_LOGIN_JUSTIFICATION`

В текущем шаге `adult/stage/prod` требуют, чтобы internal web login был production-disabled.

Маршруты `/login` теперь уважают этот режим и возвращают `404 auth.internal_web_login_disabled`, если interactive web login запрещён.

### 4. No implicit dev secret in adult middleware
`SessionMiddleware` больше не использует dev fallback secret в adult profiles.

### 5. CI / regression gate
Добавлены lockdown-focused tests и включены в `ci/pytest_gate.txt`:

- `tests/test_t34_07_production_lockdown.py`
- `tests/web/test_t34_07_production_profile_diagnostics.py`
- `tests/test_t34_07_ci_lockdown_gate.py`

## Что это доказывает

### proven

- production diagnostics page/report реально существуют
- startup получает явный production-lockdown gate
- internal web login больше не является молчаливым production path
- readiness/observability публикуют lockdown state
- CI gate на forbidden production regressions добавлен

### not proven

- live adult contour всё ещё не доказан end-to-end
- в репозитории остаются legacy-compatible paths для dev/test
- часть old code paths всё ещё присутствует, но вынесена в compat/blocked posture, а не полностью удалена

## Ограничение шага

Шаг сознательно делает `adult` профиль более жёстким и fail-fast. Это означает, что при незавершённом реальном cutover часть adult startup сценариев продолжит падать раньше, чем приложение начнёт обслуживать трафик. Это ожидаемое поведение для production lockdown.
