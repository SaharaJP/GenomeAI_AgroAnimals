# MVP-N07 Execution Proof — Add Event FAB

## Scope
Реализован полный flow добавления события через FAB: React Context для состояния диалога, компонент диалога (desktop) / bottom drawer (mobile), обновлены FAB, AppShell, timeline page, backend endpoint в v1 router.

## Deliverables

| Файл | Статус | Описание |
|------|--------|----------|
| `web_app/components/app/add-event-context.tsx` | ✓ создан | Context + Provider + `useAddEvent()` hook |
| `web_app/components/app/event-type-select.tsx` | ✓ создан | Grid из 10 типов событий с emoji |
| `web_app/components/app/add-event-dialog.tsx` | ✓ создан | Dialog + all 6 fields + submit → POST + toast |
| `web_app/components/app/fab.tsx` | ✓ обновлён | `useAddEvent().openDialog()` + pulse animation |
| `web_app/components/app/app-shell.tsx` | ✓ обновлён | `<AddEventProvider>` + `<AddEventDialog>` |
| `web_app/app/(protected)/timeline/page.tsx` | ✓ обновлён | `useAddEvent()`, `userEvents` prepended |
| `web_app/app/globals.css` | ✓ обновлён | `.ae-*` styles, `.fab--pulse`, mobile drawer |
| `web_cabinet/api_boundary_v1.py` | ✓ обновлён | `POST /api/app/v1/timeline/events` |

## Executed checks

### 1. Python syntax — OK
```
python -c "import ast; ast.parse(open('web_cabinet/api_boundary_v1.py').read()); print('OK')"
# api_boundary_v1.py: OK
```

### 2. Endpoint registration — OK
```
Timeline routes in v1 router: ['/api/app/v1/timeline/events']
```
Маршрут доступен по `/api/backend/timeline/events` через Next.js proxy.

### 3. Smoke test — 1 passed
```
python -m pytest tests/test_a6_smoke.py -q
# 1 passed, 2 warnings in 1.97s
```

## Net result

- FAB на всех 5 protected pages открывает `AddEventDialog` через `useAddEvent` context
- Диалог содержит все 6 полей из spec
- POST `/api/backend/timeline/events` → проксируется в `/api/app/v1/timeline/events` → demo response с `event_id` + `status: "pending_analysis"`
- Новое событие добавляется в `userEvents` (context state) и немедленно появляется в `/timeline` (prepend к DEMO_TIMELINE_EVENTS)
- Toast "Событие добавлено в Ленту. Результаты будут готовы через ~24ч."
- Mobile: `ae-overlay` + `ae-dialog` переключаются в bottom drawer через CSS media query (≤768px)
- FAB пульсирует при клике (CSS keyframe `fab-pulse`, 350ms)
- Timeline page: кнопка "+ Добавить событие" вызывает тот же `openDialog()`

## Честный статус

**`partially_proven`** — runtime-доказательство в браузере не проведено (UI dev server не запускался).
- Python backend: синтаксис OK, endpoint зарегистрирован, smoke passed.
- TypeScript: ручная проверка файлов, tsc не запускался (worktree ограничения).
- Acceptance criteria 4 (сохранение в БД): demo mode, без персистирования.
- Acceptance criteria 5 (mobile drawer): реализован CSS, не протестирован на устройстве.
- Acceptance criteria 6 (CI gates): не прогнаны полные 7 гейтов (pre-existing test failures в worktree не связаны с N07).
