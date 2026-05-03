# T34-06 — Android real auth integration + runtime sync/session proof

Статус этого шага: `partially_proven`.

## Что сделано

На этом шаге Android-клиент переводится с уровня UI/contract shell на уровень реального runtime path к серверной auth/session/RBAC model.

Ключевые изменения:

- Android login использует серверный `POST /api/app/v1/auth/login` с `client_kind=android`.
- Refresh использует серверный `POST /api/app/v1/auth/refresh`.
- Logout использует серверный `POST /api/app/v1/auth/logout`.
- Защищённые запросы используют bearer token и умеют делать refresh/re-login path.
- Локальное состояние auth хранится в `PreferencesSessionStore` (DataStore), а не в local role picker.
- Добавлен server-side evidence hook `GET /api/app/v1/auth/mobile/runtime-proof`.
- В Android shell добавлен отдельный `AuthDiagnostics` экран: current session state, last refresh result, auth failure, protected request failure, offline queue diagnostics.
- Добавлен runnable smoke script `scripts/smoke_t34_06_android_auth_runtime.sh`.

## Что принципиально запрещено

- **Нет local role picker как источника истины.** Роль приходит только из серверной auth/session model.
- **Нет WebView wrapper.** Это отдельное Android-приложение.
- **Нет mock auth storage для production path.** Для auth-state используется `PreferencesSessionStore`.
- **Нет ослабления серверных guard'ов** ради mobile convenience.

## Android runtime path

1. Пользователь вводит логин/пароль.
2. Клиент вызывает `/api/app/v1/auth/login`.
3. Сервер возвращает `user`, `session`, `scope`, `tokens`.
4. Клиент сохраняет `access_token`, `refresh_token`, `session_id`, scope и роль в `PreferencesSessionStore`.
5. Защищённые запросы используют bearer token.
6. При `401` клиент делает `refresh`; если refresh неудачен — требует re-login.
7. Для доказательства runtime path клиент и smoke/UAT используют `/api/app/v1/auth/mobile/runtime-proof`.

## Mobile diagnostics

Android diagnostics должны показывать:

- current session id
- current username / role / tenant
- allowed farm/site scope
- last refresh result
- last refresh timestamp
- last auth failure reason
- last protected request failure
- re-login required flag
- offline queue pending / ready / retryable / conflict / terminal counts
- latest sync/auth reason

## Server-side evidence hook

`GET /api/app/v1/auth/mobile/runtime-proof` возвращает:

- `schema`
- `storage_backend`
- `auth_backend`
- `request_auth_transport`
- `refresh_lineage_count`
- `revoke_status`
- `session`
- `scope`

Это нужно для smoke/UAT/proof pack, чтобы Android runtime path был проверяемым на стороне сервера.

## Smoke/UAT baseline

Минимальный runnable порядок:

1. Login как `client_kind=android`.
2. `GET /api/app/v1/auth/me` с bearer token.
3. `GET /api/app/v1/auth/mobile/runtime-proof`.
4. `POST /api/app/v1/auth/refresh`.
5. Повторный protected request уже с новым токеном.
6. `POST /api/app/v1/auth/logout`.
7. Проверка, что старый access token больше не работает.

## Что ещё не доказано

- Сборка и UAT на реальном Android-устройстве / эмуляторе.
- Реальная offline sync replay цепочка на живом mobile runtime.
- End-to-end mobile → server → workflow execution proof на production-like контуре.
