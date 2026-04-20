# T32-04 — React/Next.js foundation + design system shell

## Что сделано

В репозитории добавлен новый каталог `web_app/` как **целевой взрослый web frontend** для GenomeAI AgroAnimals.

На этом шаге реализованы:

- отдельный Next.js App Router frontend;
- auth-aware protected shell;
- role-aware navigation sections;
- reusable design-system primitives;
- thin API client + BFF/proxy layer к canonical backend API `/api/app/v1/*`;
- foundation pages для дальнейшей миграции экранов из legacy surfaces.

## Принципы

- frontend **не содержит бизнес-логики**;
- frontend не импортирует внутренние Python-модули;
- все данные идут только через backend boundary;
- standalone web frontend является единственным продуктовым web UI после T32-12.

## Структура

- `web_app/app/` — маршруты и layouts
- `web_app/components/` — shell/auth/ui primitives
- `web_app/lib/api/` — contract-facing TS слой
- `web_app/lib/server/` — backend proxy helpers и auth-cookie handling
- `web_app/tests/` — type-level / utility smoke tests

## Запуск локально

```bash
cd web_app
npm install
npm run smoke
npm run dev
```

По умолчанию web shell ожидает backend по адресу:

```bash
GENOMEAI_WEB_BACKEND_URL=http://127.0.0.1:8000
```

## Что готово для следующей итерации

- перенос read-heavy страниц на новый shell;
- добавление write-actions через canonical mutation boundary;
- server-side authenticated data fetching для production pages;
- e2e smoke поверх login + protected routes.
