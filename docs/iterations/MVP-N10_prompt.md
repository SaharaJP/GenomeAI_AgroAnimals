# Задача MVP-N10: Demo farm v2 (350 голов)

**PROMPT:**

## Контекст
- Существующий скрипт: `scripts/build_demo_farm_v1.py`
- `design_decisions.md` — там зафиксированы имена коров и название фермы

## Цель
Investor-grade demo farm dataset на 350 голов с 6-месячной историей и seeded демо-кейсами под каждый Акт.

## Параметры
- **Название фермы**: "Демо-ферма" (она же "Агрохолдинг Заря", адрес "с. Васильково")
- **Размер**: 350 активных дойных коров
- **Период**: 6 месяцев истории → сегодня
- **Имя директора**: Андрей Жиров (для hero приветствия)

## Распределение
- Лактации: 30% 1-я / 35% 2-я / 20% 3-я / 15% 4+
- DIM: 50 Fresh (1-30), 100 Early (31-100), 100 Mid (101-200), 50 Late (201-305), 50 Dry (>305)
- Продуктивность: 32-40 кг/день пик

## Русские имена коров
Сгенерируй детерминированно из списка:
Бурёнка, Зорька, Ночка, Ласточка, Звёздочка, Милка, Умница, Красавица, Белянка, Пеструха, Роза, Майка, Весна, Малина, Чернушка, Снежинка, Рябинка, Калинка, Любава, Забава, Марта, Мальвина, Сирень, Василёк, Берёзка, Ивушка, Ромашка, Лютик, Незабудка, Голубка, Зая, Кнопка, Линда, Лада, Макара, Нежность, Облачко, Полина, Радуга, Салфетка, Туча, Удача, Фиалка, Хатыль, Цветочек, Шалунья, Щеголиха, Эличка, Юла, Яна...

ID: 4-значные (3000-4999). Детерминированно: `f"{3000 + cow_index:04d}"`.

## Seeded демо-кейсы

### Для Акта 1 (Утренний обзор)
- Сегодняшние KPI на dashboard:
  - avg_milk_yield: 28.5 кг/голова/день
  - health_index: 94%
  - pregnancy_rate_21d: 24%
  - cows_need_attention_today: 3

### Для Акта 2 (ИИ-помощник) — Звёздочка (ID 4821)
- 3-я лактация, 156 DIM
- История за последние 60 дней:
  - День -60: норма ~36 кг/день
  - День -42: мастит обнаружен (SCC 230k → 450k, conductivity abnormal)
  - День -42 до -38: лечение Cefquinome, withdrawal до -34
  - День -38: перевод из группы 2 в группу 3 (социальный стресс)
  - День -38 до -28: intake падение на 14%
  - День -28 до сегодня: удой 28 кг/день (падение ~22%)

Все события записаны как отдельные events с timestamps, reporters, evidence_ids.

### Для Акта 3 (Выбраковка) — Малина (ID 3891)
- 3-я лактация, 285 DIM
- 2 эпизода мастита за последние 60 дней
- Open 145 дней
- NPV последние 30 дней отрицательный (-$180)
- Recommendation: SELL

Плюс ещё 14 коров с разными culling scores (5 sell, 5 watch, 5 keep).

### Для Акта 4 (Ветврач) — Ночка (ID 3142)
- Текущий профиль (на сегодня):
  - Activity score упал за 3 дня
  - SCC вырос до 450k
  - Conductivity abnormal
  - НЕТ открытого treatment — готова для демо записи

Плюс 5 других коров с активными withdrawals.

### Для Акта 5 (Мобильный оператор)
8 задач в сегодняшнем worklist оператора:
- 3 × проверка стельности
- 2 × осеменение (heat detected)
- 2 × наблюдение здоровья
- 1 × ввод intake

## События для каждой коровы
- Calving events с датами, полом телят, complications
- Breeding events с dates, bulls (русские клички быков: Атаман, Буран, Вихрь, Гром, Дунай, Ермак, Жигули, Зевс, ...)
- Pregnancy checks с outcomes
- Health episodes с частотами реалистичными (15% mastitis, 8% lameness, 5% ketosis, ...)
- Treatments с препаратами из `configs/drugs/`
- Milk yields daily
- Group moves
- BCS measurements периодически
- Milk quality readings еженедельно

## Технические детали
- Всё seed-deterministic (`random.seed(42)`)
- Timestamps в UTC
- Формат совместимый с существующим `data/demo/`
- Путь: `data/demo/investor_v1/`
- Fixtures:
  - `animals.json` — 350 коров
  - `events.json` — ~2000 events
  - `treatments.json` — ~400 treatments
  - `breedings.json`
  - `milk_yields.json` — 350 × 180 дней ≈ 63000 записей
  - `insights_seeded.json` — 12 insights
  - `timeline_events_seeded.json` — 10-12 events с impact
  - `morning_briefs_seeded.json` — 3 briefing (сегодня/вчера/позавчера)
  - `weekly_briefs_seeded.json` — 2 briefings
  - `impact_analyses_seeded.json` — impact для каждого timeline event
  - `README.md` — описание всех seeded cases

- Новый скрипт: `scripts/build_demo_farm_investor.py`
- Режим запуска: `python scripts/build_demo_farm_investor.py --mode connecterra [--with-ai-seeds]`

## Deliverables
- `scripts/build_demo_farm_investor.py`
- Все JSON fixtures в `data/demo/investor_v1/`
- SQL seed скрипт `data/demo/investor_v1/seed.sql` (для загрузки в Postgres)
- Shell скрипт `scripts/seed_demo_investor.sh` (вызывает python + psql)
- `docs/iterations/MVP-N10_execution_proof.md`

## Acceptance criteria
1. `python scripts/build_demo_farm_investor.py --mode connecterra` работает
2. 350 активных коров с правильным распределением
3. Звёздочка (4821), Малина (3891), Ночка (3142) присутствуют с правильными историями
4. `genomeai validate --input data/demo/investor_v1` → pass
5. `pytest -q tests/test_a6_smoke.py` на новых данных → pass
6. Все seeded events/insights/briefs валидны по JSON schema
7. Все CI гейты pass

## Формат ответа
Стандартный T34.
