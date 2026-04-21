# Задача MVP-N01: App shell + Sidebar refresh (Connecterra-style)

**PROMPT:**

## Контекст (обязательно прочитай)
- `CLAUDE.md` — протокол работы ИИ-разработчика
- `design_decisions.md` — дизайн-решения v2 (Connecterra-style, русский, светлая тема, бирюзовый)
- `docs/design_reference/*.png` — 11 скриншотов Connecterra. Открой их и изучи визуально.

## Цель
Переписать app shell, sidebar и topbar под Connecterra-style. Светлая тема по умолчанию. Весь UI на русском.

## Что сделать
1) **Светлая тема default:**
   - Фон: `#ffffff` / `#f7f9fa`
   - Обновить `web_app/lib/design-tokens.ts` с палитрой из design_decisions.md
   - Переписать `web_app/app/globals.css` — новые CSS variables, старые классы сохранить

2) **Sidebar (220px):**
   - Бирюзовая плашка `#2dd4bf` с логотипом
   - Wordmark "genomeai агро" lowercase рядом
   - Пункты: **Обзор** / **Инсайты** / **Аналитика** / **Лента событий** / **Помощник**
   - Активный пункт: фон `#e6fff9`, текст `#0d9488`
   - Разделитель, далее: **Свернуть** / **Мои подключения** / **Настройки** / **Справка** / **Чат поддержки** / **Выход**
   - Иконки Lucide React (outline-style)

3) **Topbar (56px, тёмно-серый `#2a3440`):**
   - Breadcrumb: "Демо-ферма ▸ Обзор" (активная крошка бирюзовым)
   - Справа: кнопка "Выйти из демо-режима" (outline-teal)
   - Справа: аватар с инициалами

4) **FAB "+":**
   - Круглая 56px, бирюзовая `#2dd4bf`, fixed bottom-right 24px
   - Onclick → toast "Форма в разработке" (заполним в MVP-N07)

5) **PWA manifest:**
   - `web_app/public/manifest.json` — name "GenomeAI Агро", theme color `#2dd4bf`, display standalone
   - Icons 192x192, 512x512 (SVG placeholder или сгенерировать простые)

6) **Responsive:**
   - `< 768px`: sidebar → bottom tab bar (5 tabs: Обзор/Инсайты/Аналитика/Лента/☰)
   - `< 640px`: topbar компактный

## Ограничения
- Все существующие страницы должны продолжать работать
- Не трогать `deploy/adult/secrets/`, `env/runtime.env`
- Русский копирайтинг — строго
- shadcn/ui для новых компонентов

## Deliverables
- `web_app/app/globals.css` — обновлён
- `web_app/lib/design-tokens.ts` — новая палитра
- `web_app/components/app/app-shell.tsx` — redesign
- `web_app/components/app/topbar.tsx` — новый
- `web_app/components/app/sidebar.tsx` — новый
- `web_app/components/app/fab.tsx` — новый
- `web_app/components/app/mobile-tab-bar.tsx` — новый
- `web_app/public/manifest.json`
- `web_app/public/icons/icon-192.svg`, `icon-512.svg`
- `web_app/app/layout.tsx` — lang="ru", manifest
- `docs/iterations/MVP-N01_execution_proof.md`

## Acceptance criteria
1. Visual match со скриншотом `docs/design_reference/Снимок экрана 2026-04-21 в 09.57.49.png` — sidebar и topbar идентичны
2. `npm run typecheck` + `npm run build` — pass
3. `bash scripts/run_ci_gate.sh` — pass
4. Chrome DevTools iPhone 14 Pro view → bottom tab bar работает
5. Активная крошка в topbar бирюзовая
6. Клик на FAB показывает toast
7. Все тексты — на русском

## Обязательные проверки
Все 7 CI гейтов + ручной визуальный review всех существующих страниц.

## Формат ответа
Scope → План → Deliverables → Acceptance → Проверки → Риски → От координатора.
Статус: proven / partially_proven / not_proven / blocked.
