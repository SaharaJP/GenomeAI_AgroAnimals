# Spec: Animal Profile Page — редизайн + расширение бэкенда

**Дата:** 2026-04-26  
**Статус:** approved by user

---

## 1. Scope

Полная переработка страницы `/profiles/animal/{id}`:

1. Перевод на русский язык, удаление developer-текста и технических панелей (FactPackGuardrailNote, SourceLinkagePanel).
2. Шапка животного с ключевыми атрибутами и статусными бейджами.
3. Таб-навигация: **Здоровье / Продуктивность / Задачи / История**.
4. Расширение бэкенда: `ProfileResponse` дополняется блоком `animal_attributes` с атрибутами животного и `health_metrics` с показателями здоровья/продуктивности.
5. Страница доступна всем ролям: ветврач, зоотехник, оператор, директор.

Затрагивает: **один фронт-компонент** (`profile-surface.tsx`) + **один бэкенд-эндпоинт** (`profiles`) + **новые Pydantic-модели**.

---

## 2. Бэкенд: расширение ProfileResponse

### 2.1 Новые Pydantic-модели

Файл: `web_cabinet/profiles/models.py` (или рядом с существующим профильным кодом)

```python
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel

class AnimalAttributes(BaseModel):
    name: Optional[str] = None          # кличка
    breed: Optional[str] = None         # порода
    birth_date: Optional[str] = None    # YYYY-MM-DD
    lactation_number: Optional[int] = None   # номер лактации
    days_in_milk: Optional[int] = None       # ДИМ
    last_calving_date: Optional[str] = None  # YYYY-MM-DD
    total_calvings: Optional[int] = None     # всего отёлов
    reproduction_status: Optional[str] = None  # "Ожидает", "Осеменена", "Стельная", "—"
    next_calving_expected: Optional[str] = None  # YYYY-MM-DD или None
    group_label: Optional[str] = None    # название группы/секции
    farm_label: Optional[str] = None     # название фермы

class HealthMetrics(BaseModel):
    activity_score: Optional[float] = None   # индекс активности (норма >60)
    activity_norm: Optional[float] = 60.0
    scc: Optional[int] = None                # соматические клетки, тыс/мл
    scc_trend: Optional[str] = None          # "↑", "↓", "→"
    body_condition_score: Optional[float] = None  # БКТ (норма 2.5–3.5)
    daily_milk_yield_kg: Optional[float] = None   # суточный надой, кг
```

### 2.2 Расширение ProfileResponse

В существующую модель `ProfileResponse` добавляется опциональное поле:

```python
class ProfileResponse(BaseModel):
    # ... существующие поля ...
    animal_attributes: Optional[AnimalAttributes] = None
    health_metrics: Optional[HealthMetrics] = None
```

`animal_attributes` и `health_metrics` заполняются только когда `entity.object_type == "animal"`. Для других типов объектов — `None`.

### 2.3 Demo-данные (seeded)

При `GENOMEAI_AI_DEMO_MODE=true` и `object_type == "animal"` эндпоинт возвращает фиксированные атрибуты, зависящие от `object_id`. Маппинг для известных demo-животных:

| object_id | name | breed | birth_date | lactation | dim | last_calving | calvings | repro_status | group_label | farm_label |
|-----------|------|-------|------------|-----------|-----|--------------|----------|--------------|-------------|------------|
| 3142 | Ночка | Голштинская | 2022-03-15 | 3 | 45 | 2026-03-12 | 3 | Ожидает | Группа 2 | Ферма Восток |
| 4821 | Звёздочка | Айрширская | 2021-11-20 | 4 | 120 | 2026-01-05 | 4 | Стельная | Группа 1 | Ферма Восток |
| 3887 | Роза | Голштинская | 2023-01-10 | 2 | 10 | 2026-04-16 | 2 | Осеменена | Группа 3 | Ферма Запад |
| 4012 | Ива | Джерсейская | 2022-07-04 | 2 | 10 | 2026-04-16 | 2 | Осеменена | Группа 3 | Ферма Запад |

Для неизвестных `object_id` — поля `None`, страница корректно отображает прочерки.

Health metrics для demo — из seeded alert/worklist данных (activity_score из `why` поля алертов, если есть) или `None`.

---

## 3. Фронтенд: ProfileSurface — полная перезапись

### 3.1 Файлы

| Файл | Изменение |
|------|-----------|
| `web_app/components/profiles/profile-surface.tsx` | Полная перезапись |
| `web_app/lib/api/contracts.ts` | Добавить `AnimalAttributes`, `HealthMetrics` в `ProfileResponse` |
| `web_app/app/globals.css` | Добавить `.profile-*` CSS-классы |

### 3.2 Шапка животного

Компонент `AnimalHero` (внутри profile-surface.tsx):

```
┌─────────────────────────────────────────────────────────────────┐
│  🐄   Ночка №3142                          [⚠ Алерт: мастит]   │
│       Голштинская · 4 года · Лактация 3,   [СКК 450k]          │
│       45 ДИМ · Группа 2 · Ферма Восток     [Надой 18.2 кг]     │
└─────────────────────────────────────────────────────────────────┘
```

- Фон: градиент `var(--teal)` → `var(--teal-dark)`, белый текст
- Бейджи справа: формируются динамически из `health_metrics` и `summary`:
  - `summary.alerts_open > 0` → красный бейдж `⚠ {N} алерт(а)`
  - `health_metrics.scc` → оранжевый бейдж если `scc > 200k`
  - `health_metrics.daily_milk_yield_kg` → зелёный бейдж всегда если есть данные
- Подзаголовок: порода · возраст (вычислен из `birth_date`) · лактация + ДИМ · группа · ферма
- При отсутствии `animal_attributes` — только `objectType: objectId` в заголовке

### 3.3 Таб-навигация

Локальный `useState<'health'|'productivity'|'tasks'|'history'>` — активная вкладка.

```tsx
const TABS = [
  { key: 'health',       label: 'Здоровье' },
  { key: 'productivity', label: 'Продуктивность' },
  { key: 'tasks',        label: 'Задачи' },
  { key: 'history',      label: 'История' },
];
```

Таб-бар рендерится только после загрузки данных.

### 3.4 Вкладка «Здоровье»

**Метрики (3 карточки в ряд):**
- Активность: значение + норма `>60` + тренд (`↓ N дней`)
- СКК: значение + тренд
- БКТ: значение + норма `2.5–3.5`
- При `null` — показывать `—`

**Активные алерты:**
- Карточка с красной левой полосой для каждого алерта
- Поля: заголовок, серьёзность, срок, ответственная роль
- Если алертов нет — сообщение «Активных алертов нет»

### 3.5 Вкладка «Продуктивность»

**Метрики (3 карточки в ряд):**
- Надой сегодня (кг)
- Лактация (номер + ДИМ)
- Последний отёл (дата)

**Блок воспроизводства:**
- Строки ключ–значение: статус осеменения / всего отёлов / прогноз следующего отёла
- При `null` значениях — прочерк `—`

### 3.6 Вкладка «Задачи»

- Список открытых `worklists` с полями: заголовок, приоритет (бейдж), ответственный, срок
- Приоритет 1 → красный бейдж «Высокий», 2 → оранжевый «Средний», 3 → зелёный «Низкий»
- Просроченные (`is_overdue`) — красная пометка
- Если задач нет — «Открытых задач нет»

### 3.7 Вкладка «История»

- Последние `decisions` (до 10): дата, действие, имя пользователя, комментарий
- Закрытые алерты (`status == 'resolved'`): заголовок, дата закрытия
- Если истории нет — «История пуста»

### 3.8 Состояния страницы

- **Загрузка:** спиннер-карточка «Загрузка профиля…»
- **Ошибка:** карточка с текстом ошибки на русском
- **Нет данных атрибутов:** шапка показывает только ID, табы работают

---

## 4. CSS-классы (добавить в globals.css)

```css
/* Animal Profile */
.profile-hero            { /* teal gradient header */ }
.profile-hero-avatar     { /* circle with emoji/icon */ }
.profile-hero-name       { /* large bold name */ }
.profile-hero-sub        { /* breed · age · group line */ }
.profile-hero-badges     { /* right side badges row */ }
.profile-tab-bar         { /* tab navigation strip */ }
.profile-tab             { /* single tab button */ }
.profile-tab--active     { /* active tab with teal underline */ }
.profile-metric-row      { /* 3-col metric grid */ }
.profile-alert-card      { /* alert card with red left border */ }
.profile-kv-row          { /* key-value row in reproduction block */ }
.profile-empty           { /* empty state text */ }
```

---

## 5. Что НЕ входит в scope

- Редактирование атрибутов животного прямо со страницы
- Графики динамики надоя / СКК / активности (история в виде чисел, без графиков)
- Кнопка «Спросить ИИ» (AssistantEntryPoints — убирается в этой версии)
- DecisionIntelligenceWidgets (глобальная статистика — не нужна на странице животного)
- FactPackGuardrailNote, SourceLinkagePanel — убираются

---

## 6. Acceptance criteria

- [ ] Страница открывается на русском языке, нет English-текстов
- [ ] Шапка показывает имя, №, породу, возраст, лактацию + ДИМ, группу, ферму
- [ ] Бейджи в шапке отражают реальные данные из API
- [ ] Таб-навигация работает: клик переключает содержимое без перезагрузки
- [ ] Вкладка «Здоровье»: 3 метрики + список алертов
- [ ] Вкладка «Продуктивность»: 3 метрики + блок воспроизводства
- [ ] Вкладка «Задачи»: список worklists с приоритетами и сроками
- [ ] Вкладка «История»: последние решения
- [ ] При `null`-значениях — прочерки `—`, не падает
- [ ] Нет `style={{...}}` (только CSS-классы)
- [ ] Нет FactPackGuardrailNote, SourceLinkagePanel, DecisionIntelligenceWidgets
