# Задача MVP-N08: Mobile PWA polish

**PROMPT:**

## Контекст
- PWA manifest создан в MVP-N01
- Service worker — ещё нет
- Проверяется на реальном iPhone через Safari

## Цель
Сделать GenomeAI Агро полноценным PWA:
- Устанавливается на home screen как приложение
- Работает offline для последних просмотренных страниц
- Touch-friendly (все targets ≥ 44×44px)
- Responsive layouts для всех breakpoints

## Задачи

### 1. Service Worker
Создать `web_app/public/sw.js`:
- Cache strategy: Network-first для API, Cache-first для static assets
- Cache `last-visited-pages` для offline access
- Update notification при новой версии

### 2. PWA manifest (доработка)
- Правильные icons (не SVG placeholder):
  - 192×192, 512×512 PNG
  - maskable icon для Android (с safe area)
- Startup splash screens для iOS
- `apple-touch-icon`, `apple-mobile-web-app-capable`
- `background_color`, `theme_color`

### 3. Layout adaptations

#### Mobile (`< 768px`)
- Sidebar → bottom tab bar (уже в N01)
- Topbar — компактный (убрать breadcrumb, оставить logo + avatar)
- FAB — 48px вместо 56px
- Cards в single column

#### Tablet (`768px — 1024px`)
- Sidebar может collapse в icons-only
- Основной контент в 2 columns где уместно

#### Большой экран (`> 1440px`)
- Max-width контента 1440px
- Центрирование

### 4. Touch UX
- Все buttons / links минимум 44×44px hit area
- Убрать hover-effects на touch-devices
- Swipe gestures на timeline: left/right → previous/next event
- Pull-to-refresh на /dashboard

### 5. Performance
- Lazy load компонентов через `next/dynamic`:
  - Analytics charts
  - Farm Timeline impact panel
  - Copilot briefing preview
- Image optimization (Next.js Image)
- Lighthouse score ≥ 85 Performance, ≥ 95 Accessibility

### 6. iOS-specific
- `-webkit-tap-highlight-color: transparent`
- Disable bounce scroll на fixed elements
- Safe area insets для iPhone (notch) — `env(safe-area-inset-*)`
- Proper viewport meta: `width=device-width, initial-scale=1, viewport-fit=cover`

### 7. Android-specific
- Splash screen через theme
- Notch/cutout support

## Demo check list
- [ ] На iPhone Safari: `https://demo.genomeai.ru` → `Поделиться → На экран "Домой"`
- [ ] Иконка добавляется с правильным названием "GenomeAI Агро"
- [ ] Открытие из иконки: работает как нативное приложение
- [ ] Отключить Wi-Fi → предыдущие просмотренные страницы открываются
- [ ] На Android Chrome: banner "Установить приложение"

## Deliverables
- `web_app/public/sw.js`
- `web_app/public/manifest.json` — доработка
- `web_app/public/icons/*.png` (реальные иконки, не placeholder)
- `web_app/components/pwa/install-prompt.tsx`
- `web_app/components/pwa/update-available.tsx`
- `web_app/lib/service-worker-registration.ts`
- Responsive fixes во всех существующих components
- `docs/iterations/MVP-N08_execution_proof.md`

## Acceptance criteria
1. Lighthouse PWA audit: installable ✓
2. Lighthouse Mobile Performance ≥ 85
3. Lighthouse Accessibility ≥ 95
4. Tested на реальном iPhone Safari: установка + offline работают
5. Все touch targets ≥ 44×44
6. Все CI гейты pass

## Формат ответа
Стандартный T34.
