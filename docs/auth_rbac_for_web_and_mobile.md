# Auth / RBAC / session model for web and mobile

Версия: T32-03

## Что фиксируется на этом шаге

На сервере вводится единая модель аутентификации и сессий для двух клиентов:

- `web` — браузерный клиент, который может работать через серверную cookie-session;
- `android` — мобильный клиент, который работает через `Bearer access token + refresh token`.

Обе модели опираются на **один и тот же серверный объект сессии** (`auth_sessions_v1`), один и тот же RBAC и одни и те же tenant/farm/site boundaries.

## Главные правила

1. Backend остаётся единственным источником правды для auth и RBAC.
2. Android auth не строится как частный хак поверх legacy web session.
3. Web и Android не расходятся по ролям и permissions: права вычисляются на сервере через общий `get_current_user` / `require_permissions`.
4. UI-клиенты не обращаются напрямую к внутренним модулям/таблицам; только к backend API boundary.
5. Любое действие клиента опирается на request-bound auth context и сохраняет audit-safe контекст (`request_id`, `tenant_id`, `user_id`, `role`, `auth_session_id` где доступно).

## Серверная модель

### 1. Пользователь

Источник пользователя остаётся прежним:

- `users_v2` — основной источник;
- `users` — legacy fallback.

### 2. Auth session

Вводится таблица `auth_sessions_v1`.

Сессия хранит:

- `session_id`
- `tenant_id`, `user_id`, `username`, `role`, `user_source`
- `client_kind` (`web` / `android` / ...)
- `auth_transport` (`cookie_session` / `bearer` / `hybrid`)
- `status`
- `expires_at`, `refresh_expires_at`
- device metadata
- `active_farm_id`, `active_site_id`
- `allowed_farm_ids_json`, `allowed_site_ids_json`
- last seen / ip / user agent

### 3. Два транспорта поверх одной модели

#### Web

- legacy `/login` теперь создаёт ту же серверную auth session;
- browser хранит signed session cookie, внутри которой есть `auth_session_id`;
- protected endpoints разрешаются через ту же серверную сессию.

#### Android

- `/api/app/v1/auth/login` возвращает `access_token` и `refresh_token`;
- protected endpoints используют `Authorization: Bearer <token>`;
- `/api/app/v1/auth/refresh` ротирует токены той же серверной сессии.

## RBAC и scope boundaries

RBAC остаётся серверным и единым.

`get_current_user` теперь:

- сначала пытается разрешить bearer session;
- затем cookie-backed auth session;
- затем legacy session fallback.

После этого сервер вычисляет:

- `permissions`
- `tenant_id`
- `allowed_farm_ids`
- `allowed_site_ids`
- `active_farm_id`
- `active_site_id`
- `client_kind`
- `auth_transport`

Если клиент запрашивает scope вне разрешённых `farm/site`, сервер отвечает `403`.

## API boundary

Новые auth endpoints:

- `POST /api/app/v1/auth/login`
- `POST /api/app/v1/auth/refresh`
- `GET /api/app/v1/auth/me`
- `POST /api/app/v1/auth/logout`
- `GET /api/app/v1/auth/sessions`
- `POST /api/app/v1/auth/sessions/{session_id}/revoke`

## Почему это важно для web/mobile parity

Web и Android теперь не имеют двух разных auth-механизмов.
Разные только transports, а серверная модель одна:

- одна session сущность;
- один RBAC;
- одна логика tenant/farm/site boundaries;
- один audit-safe request context.

## Что ещё не делается на T32-03

На этом шаге не вводятся:

- полноценный external IdP / SSO;
- device attestation;
- MFA;
- push-based session invalidation;
- полная миграция всех legacy страниц на новый auth UI flow.

Это deliberate increment: усиливаем серверную модель без ломки существующего runnable продукта.
