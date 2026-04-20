# Полная функциональная проверка через UI — Android field app

Дата: 2026-04-14  
Статус: подробный manual для QA / implementation / customer UAT по `mobile_android/`.

Этот документ описывает **пошаговую проверку Android-приложения** как отдельного field/cowside app. Он не смешивается с web UAT и не делает вид, что мобильный клиент уже эквивалентен офисному web UI.

> Важно: Android-клиент — **отдельное нативное приложение**, не web wrapper и не PWA. Проверка должна учитывать его фактический scope: cowside execution, quick actions и offline/sync baseline.

---

## 1. Что считается объектом проверки

Проверяются:

- login screen
- role-aware mobile navigation
- today worklists
- alerts now
- quick animal card
- quick event entry
- task completion
- shift handover
- offline queue / sync / conflict / audit baseline

Проверяются **только реально реализованные** мобильные сценарии. Нельзя считать fail отсутствие full office functionality на Android — это не цель приложения.

---

## 2. Предварительные условия

### 2.1. Что прогнать до ручной мобильной проверки

```bash
bash scripts/smoke_t32_08_android_field_app.sh
bash scripts/smoke_t32_08a_android_offline_sync_contract.sh
bash scripts/smoke_t32_09_android_offline_sync_model.sh
```

Эти smoke не заменяют ручную UI-проверку, но подтверждают:

- foundation проекта;
- offline/sync contract;
- offline/sync model.

### 2.2. Build/install baseline

Используйте `docs/deployment_full_guide.md` для Android build/distribution baseline.

Практический minimum для UI-проверки:

- Android Studio открывает каталог `mobile_android/`
- приложение собирается как debug build
- APK установлен на device или emulator

### 2.3. Данные и среда

Для UI-проверки Android foundation допускается два режима:

1. **UI-only foundation check** — без реального backend login/sync transport.  
2. **backend-connected check** — если окружение дополнительно wired к backend API.

В текущем baseline честная гарантия есть для режима 1 и для contract/model verification через smoke. Если в customer environment мобильный transport wired end-to-end, фиксируйте это отдельно в UAT отчёте.

---

## 3. Роли и как их проверять

В мобильном приложении поддерживаются роли:

- `HerdManager`
- `Veterinarian`
- `ReproductionSpecialist`
- `Viewer`
- `Admin`

Для целей UAT их соотнесение с бизнес-ролями такое:

| Mobile role | Проверять как |
|---|---|
| `HerdManager` | Operator / Zootech |
| `Veterinarian` | Vet |
| `ReproductionSpecialist` | Reproduction / Zootech-like field role |
| `Viewer` | Viewer / bounded external where allowed |
| `Admin` | Admin |

### 3.1. Как выбирать роль в UI

После T32-14 в `LoginScreen` есть явный блок **`Роль для UI-проверки`**.

Шаги:

1. Откройте приложение.
2. На экране логина заполните `Логин` и `Пароль`.
3. В блоке `Роль для UI-проверки` выберите роль кнопкой.
4. Нажмите `Войти`.

> Честная оговорка: это именно verification-oriented UI choice для проверки role-aware navigation. Она не отменяет server-side auth/session model из T32-03 и не означает, что mobile сам стал источником RBAC-истины.

---

## 4. Карта экранов Android

| Контур | Экран | Что проверять |
|---|---|---|
| Auth | `LoginScreen` | логин-поля + выбор роли |
| Worklists | `TodayWorklistsScreen` | scope chips + field card |
| Alerts | `AlertsNowScreen` | alerts triage card |
| Quick object | `QuickAnimalCardScreen` | animal context card |
| Event entry | `QuickEventEntryScreen` | поля `Animal ID` / `Event type` |
| Task completion | `TaskCompletionScreen` | поля `Task ID` / `Outcome` |
| Handover | `ShiftHandoverScreen` | `Сводка смены` |

---

## 5. Подробные сценарии проверки — Android

### AND-AUTH-001 — Логин и role-aware navigation

**Роли:** все  
**Шаги:**

1. Запустите приложение.
2. Проверьте тексты:
   - `GenomeAI Field`
   - `Отдельное Android-приложение для cowside / field execution`
3. Проверьте наличие полей `Логин`, `Пароль`.
4. Проверьте блок `Роль для UI-проверки`.
5. Выберите `HerdManager`.
6. Нажмите `Войти`.
7. Убедитесь, что после логина открывается cowside shell.
8. Зафиксируйте видимые navigation buttons.
9. Повторите шаги для `Veterinarian`, `ReproductionSpecialist`, `Viewer`, `Admin`.

**Ожидаемый результат:** набор доступных destinations меняется по role-aware policy.

**Pass / Fail:**

- PASS: навигация реально меняется по роли;
- FAIL: все роли видят одинаковый набор экранов.

---

### AND-WL-001 — Today worklists

**Роли:** HerdManager, Veterinarian, ReproductionSpecialist, Viewer, Admin  
**Шаги:**

1. Войдите как `HerdManager`.
2. Откройте `today-worklists`.
3. Убедитесь, что видны scope chips с `farm-demo-1` и `site-a`.
4. Убедитесь, что карточка содержит:
   - `Today worklists`
   - `Полевой контур / backend-first`
   - текст про backend worklists без локальной бизнес-логики.

**Ожидаемый результат:** экран clearly communicates backend-first cowside queue semantics.

---

### AND-ALERT-001 — Alerts now

**Роли:** HerdManager, Veterinarian, ReproductionSpecialist, Viewer, Admin  
**Шаги:**

1. Откройте `alerts-now`.
2. Проверьте scope chips.
3. Проверьте карточку с:
   - `Alerts now`
   - `Только текущие cowside alerts`
   - текст про severity/confidence/reason codes.

**Ожидаемый результат:** mobile alerts surface ограничен текущими cowside alert semantics.

---

### AND-ANIMAL-001 — Quick animal card

**Роли:** HerdManager, Veterinarian, Viewer, Admin  
**Шаги:**

1. Откройте `quick-animal-card`.
2. Убедитесь, что экран содержит:
   - `Quick animal card`
   - `Минимальный объектный контекст`
   - текст про status / parity / recent alerts / active tasks / withdrawal flags.

**Ожидаемый результат:** mobile object card позиционируется как quick context, а не как full office profile.

---

### AND-EVENT-001 — Quick event entry UI

**Роли:** HerdManager, Veterinarian, ReproductionSpecialist, Admin  
**Шаги:**

1. Откройте `quick-event-entry`.
2. Введите в `Animal ID`: `DEMO_COW_1002`.
3. Введите в `Event type`: `health_check`.
4. Нажмите `Поставить в sync queue`.

**Ожидаемый результат:** UI принимает значения и позиционирует действие как queueable offline action.

**Честная оговорка:** в текущем UI foundation этот экран проверяется прежде всего как cowside entry form. Полная end-to-end очередь подтверждается smoke/contract/model из T32-08A/T32-09, а не только кнопкой на экране.

---

### AND-TASK-001 — Task completion UI

**Роли:** HerdManager, Veterinarian, ReproductionSpecialist, Admin  
**Шаги:**

1. Откройте `task-completion`.
2. Введите `Task ID`, например `TASK-DEMO-001`.
3. Введите `Outcome`, например `done`.
4. Нажмите `Закрыть задачу`.

**Ожидаемый результат:** UI позволяет capture task completion как sync-safe action.

---

### AND-HANDOVER-001 — Shift handover UI

**Роли:** HerdManager, Veterinarian, ReproductionSpecialist, Viewer, Admin  
**Шаги:**

1. Откройте `shift-handover`.
2. Убедитесь, что есть поле `Сводка смены`.
3. Введите текст handover summary.
4. Нажмите `Передать смену`.

**Ожидаемый результат:** handover capture доступен как отдельный mobile-specific flow.

---

### AND-OFFLINE-001 — Offline queue / sync / conflict verification через UI + smoke

**Роли:** HerdManager, Veterinarian, ReproductionSpecialist, Admin  
**Предусловия:** smoke T32-08A/T32-09 зелёный.  
**Шаги:**

1. Выполните `AND-EVENT-001`, `AND-TASK-001`, `AND-HANDOVER-001`.
2. Зафиксируйте, что эти действия **по смыслу** относятся к offline-safe set.
3. Затем выполните:

```bash
bash scripts/smoke_t32_08a_android_offline_sync_contract.sh
bash scripts/smoke_t32_09_android_offline_sync_model.sh
```

4. Убедитесь, что smoke подтверждает:
   - success with audit ack
   - retryable failure
   - conflict without silent merge
   - duplicate idempotency rejection

**Ожидаемый результат:** UI-слой и offline/sync contract/model согласованы.

**Pass / Fail:**

- PASS: UI проверен, а underlying sync semantics подтверждены smoke;
- FAIL: UI есть, но contract/model smoke падает.

---

## 6. Role-by-role ожидаемый coverage on Android

| Роль | Должна видеть | Не должна требовать |
|---|---|---|
| Admin | все mobile destinations | full office admin CRUD |
| HerdManager | worklists, alerts, animal card, event entry, task completion, handover | office reports/economics/admin command center |
| Veterinarian | worklists, alerts, animal card, event entry, task completion, handover | office-only vet analytics |
| ReproductionSpecialist | worklists, alerts, animal card, event entry, task completion, handover | office reproduction dashboard |
| Viewer / bounded external | worklists, alerts, animal card, handover | event entry/task completion if role policy не допускает |

---

## 7. Что считать N/A, а не FAIL

Отмечайте `N/A`, а не `FAIL`, если во время Android UAT вы ожидаете то, чего в текущем мобильном scope нет:

- полный office feature set web-приложения;
- full profile/report/governance flows на Android;
- полноценный чат-assistant на мобильном UI;
- локальная бизнес-логика объяснимости;
- silent offline merge (он запрещён by design).

---

## 8. Критерии завершения Android UAT

Android UAT можно считать завершённым, если:

- login screen и role-aware navigation проверены;
- все 6 базовых cowside screens проверены;
- QA зафиксировал scope-ограничения честно, без ложных fail по нецелевым функциям;
- T32-08 / T32-08A / T32-09 smoke зелёные и приложены к UAT artefact.
