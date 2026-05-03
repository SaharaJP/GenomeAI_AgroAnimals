# Spec: MorningBriefCard — редизайн + редактирование + согласование

**Дата:** 2026-04-26  
**Статус:** approved by user  

---

## 1. Scope

Полная переработка компонента `components/overview/morning-brief-card.tsx`:

1. Перевод с legacy inline-стилей на design system CSS-классы (Connecterra).
2. Удаление блока модели/токенов из footer.
3. Инлайн-редактирование задач брифинга с приоритет-пикером.
4. Добавление задач вручную.
5. Кнопка «Согласовать» → создаёт ворклист-задачи на специалистов через новый API-эндпоинт.
6. PDF-кнопка разблокируется только после согласования.
7. Автодетект ссылок на животных (`№NNN`) и задачи (`#NNN`) в тексте → кликабельные бейджи.

Затрагивает: **один фронт-компонент** + **один новый бэкенд-эндпоинт**.

---

## 2. Компонент: MorningBriefCard

### 2.1 Стиль

- Все `style={{...}}` заменяются на CSS-классы из `globals.css`.
- Используемые классы: `.card`, `.card-title`, `.badge`, `.badge-info`, `.badge-high`, `.badge-med`, `.badge-low`, `.button`, `.button-primary`.
- Нет новых CSS — только существующий design system.
- Footer: только время генерации (`Брифинг сгенерирован сегодня в 06:00`). Поля `generation_model` и `generation_tokens` скрыты.

### 2.2 Шапка карточки

```
[• ИИ-брифинг]          [обновлено 2 ч назад]  [↺ Обновить]
```

- PDF-кнопка в шапке **отсутствует** (появляется только в зоне согласования после approve).

### 2.3 Ссылки на сущности в тексте

Функция `renderWithEntityLinks(text: string): ReactNode`:
- Паттерн `№(\d+)` → `<Link href="/profiles/animal/{id}" className="badge badge-info">🐄 №{id}</Link>`
- Паттерн `#(\d+)` → `<Link href="/worklists" className="badge" style={{background:'#f5f3ff',color:'#7c3aed',border:'1px solid #ddd6fe'}}>⚙ #{id}</Link>`
- Применяется к: `main_takeaway`, `overnight_changes[].text`, `today_actions[].action`.

### 2.4 Редактируемые задачи

Локальное состояние: `editedActions: TodayAction[]`, инициализируется из `brief.today_actions`.

**Строка задачи (просмотр):**
- `[badge приоритет]  [текст с entity-links]  [срок]  [роль]  [✏ edit]  [✕ delete]`
- ✏ и ✕ видны при `hover` через CSS (`:hover .edit-controls { opacity: 1 }`).

**Форма редактирования (инлайн, под строкой):**
- Поле текста (`<input>`)
- Приоритет-пикер: три pill-кнопки `Высокий / Средний / Низкий`, активная — залита цветом
- Выпадающий список роли: Ветврач / Зоотехник / Оператор / Директор
- Поле времени `<input type="time">` (опционально)
- Кнопки: `[Сохранить]  [Отмена]`

**Кнопка «＋ Добавить задачу вручную»** — добавляет пустую строку сразу в режиме редактирования.

### 2.5 Зона согласования

**До согласования (`approved === false`):**
```
Согласование поставит задачи ответственным специалистам
и разблокирует выгрузку в PDF.
                          [ ✓ Согласовать и поставить задачи ]
```

**После согласования (`approved === true`):**
```
✓ Согласовано · задачи поставлены N специалистам     [ ⬇ Скачать PDF ]
```

Состояние `approved` хранится в `useState`, **не персистится** (сбрасывается при перезагрузке — достаточно для MVP).

PDF-кнопка вызывает `morningBriefPdfUrl(brief.brief_id, farmId)` — эндпоинт уже существует.

---

## 3. Новый бэкенд-эндпоинт: POST /api/ai/morning-brief/{brief_id}/approve

**Файл:** `web_cabinet/ai/endpoints/morning_brief.py`

### Request body
```python
class ApproveBriefRequest(BaseModel):
    farm_id: str
    actions: list[TodayAction]   # отредактированный список задач
```

### Логика
1. Для каждого `action` в `actions` — создать запись в системе задач через `create_task()` из `tasks_v1.py` с маппингом:
   - `priority`: high → 1, medium → 2, low → 3
   - `role` → `assignee_role`
   - `due` → `due_date` (если задан)
   - `action` → `title`
2. Вернуть `{ "approved": true, "tasks_created": N }`.

### Response
```python
class ApproveBriefResponse(BaseModel):
    approved: bool
    tasks_created: int
```

Ошибка создания задач — логируется, не блокирует approve (graceful degradation).

---

## 4. Фронт-вызов approve

Новая функция в `lib/api/morning-brief.ts`:
```typescript
export async function approveMorningBrief(
  briefId: string,
  actions: TodayAction[],
  farmId = 'demo-farm-v1'
): Promise<{ approved: boolean; tasks_created: number }> {
  return apiFetch(`/api/ai/morning-brief/${briefId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ farm_id: farmId, actions }),
  });
}
```

---

## 5. Что НЕ входит в scope

- Персистенция состояния approved между сессиями.
- Уведомления специалистам (push/email).
- Редактирование секции «За ночь» (только задачи редактируемы).
- Реальная генерация PDF (эндпоинт уже есть на бэкенде, используем как есть).

---

## 6. Файлы, которые изменятся

| Файл | Изменение |
|------|-----------|
| `web_app/components/overview/morning-brief-card.tsx` | Полная перезапись |
| `web_app/lib/api/morning-brief.ts` | Добавить `approveMorningBrief()` |
| `web_cabinet/ai/endpoints/morning_brief.py` | Добавить `POST /{brief_id}/approve` |

---

## 7. Acceptance criteria

- [ ] Карточка отображается без единого `style={{...}}` (только CSS-классы)
- [ ] Поля `generation_model` и `generation_tokens` нигде не видны
- [ ] PDF-кнопка в шапке отсутствует до согласования
- [ ] `№NNN` в тексте → синий badge-ссылка на `/profiles/animal/NNN`
- [ ] `#NNN` в тексте → фиолетовый badge-ссылка на `/worklists`
- [ ] ✏ и ✕ появляются при hover на задаче
- [ ] Форма редактирования: приоритет-пикер работает, изменения сохраняются в локальном стейте
- [ ] «＋ Добавить задачу» добавляет пустую строку в режиме редактирования
- [ ] После «Согласовать» — зелёная зона + кнопка PDF
- [ ] Кнопка PDF вызывает правильный URL
