# Стратегия проекта GenomeAI Агро

**Для чего этот документ:** контекст для AI-разработчика (Claude Code) — зачем мы делаем то, что делаем. Читается при выполнении AI-related MVP задач.

---

## Продукт в одном предложении

**GenomeAI Агро** — AI-помощник для молочной фермы, который превращает разрозненные данные фермы в actionable insights и решения на уровне конкурентных western систем (DeLaval DelPro, AfiFarm, DairyComp 305).

## Референс UX

**Connecterra.ai** — ближайший целевой UX benchmark:
- Overview / Insights / Analytics / Farm Timeline / Copilot — 5 основных разделов
- Светлая тема, бирюзовый accent, чистый минимализм
- Русскоязычный рынок СНГ = blue ocean (Connecterra на английском/немецком)

## Философия AI в нашем продукте

### Принцип: "AI как реальный помощник, не для галочки"

**"Для галочки" (как делают многие):**
- Кнопка "Спросить ИИ", открывающая generic chat-окно
- Preset-вопросы с вшитыми хардкод-ответами
- Weekly brief "всё хорошо, коровы здоровы"
- Insights без recommendations
- AI не знает ферму — отвечает как ChatGPT в браузере

**"Реальный помощник" (как делаем мы):**
- AI **видит** данные фермы через farm_context (KPI, события, инсайты, статусы)
- AI **ссылается** на факты: "У Звёздочки (4821) SCC вырос с 230k до 450k за 9 дней — начало клинического мастита"
- AI **предлагает действия** со сроками: "Провести CMT-тест до 14:00, заблокировать молоко в общий бак"
- AI **проактивен** — insight scanner каждые 6 часов находит новые аномалии
- AI **помнит** контекст разговора в сессии
- AI **честен** про неуверенность — "Данных за 3 дня недостаточно, нужны измерения X"
- AI **показывает evidence** — каждое утверждение кликабельно и ведёт к source event

### 6 мест продукта где AI = реальный помощник

1. **Обзор → утренний брифинг** — cron 06:00 генерирует 1-page narrative
2. **Обзор → виджет "ИИ-помощник"** — interactive Q&A с RAG
3. **Инсайты → drill-down** — AI пишет description + recommendations
4. **Инсайты → proactive scanner** — AI сам находит новые issues каждые 6 часов
5. **Лента событий → impact narrative** — AI описывает влияние каждого события
6. **Помощник → weekly briefing** — развёрнутый отчёт с 5+ рекомендациями

## 3 технических приёма, делающих AI "настоящим"

### 1. Context injection
Перед каждым запросом формируется `farm_context` snapshot (~3000 токенов):
- Today KPI (milk yield, SCC, fresh cows count)
- Period trends (vs previous week)
- Active insights с priority
- Last 50 events compact format
- Attention cows с flags (falling_yield, active_treatment, ...)

Claude видит ферму, не отвечает как generic chat.

### 2. Tool use
AI получает 7 функций, которые **сам** вызывает когда контекста мало:
- `get_cow_history` / `get_group_metrics` / `search_events`
- `get_treatment_records` / `get_reproduction_status`
- `get_milk_quality_trend` / `get_economics_snapshot`

Это **принципиальное** отличие от chat-бота.

### 3. Evidence grounding
System prompt жёстко требует:
> Каждое конкретное утверждение подкрепляй `[evidence: event_xxx]`. Без evidence — не утверждай. Скажи "по имеющимся данным точного ответа нет".

Frontend парсит маркеры → кликабельные chips → source event.

Post-processing: validate_evidence() отфильтровывает claims со ссылками на несуществующие event_ids. Если LLM "выдумал" — chip помечается "⚠ unverified".

## Границы MVP vs Будущие фазы

### В MVP (к показу инвестору за 28 дней)
- **Frontend**: 6 разделов Connecterra-style, русский, PWA, mobile-responsive
- **AI**: 6 use cases выше, через Claude API (Sonnet + Opus для важных задач)
- **Data**: demo farm 350 голов с 6-месячной историей и seeded кейсами
- **Infra**: один dev-сервер, Claude API только что

### После MVP (Фаза 2, 6 месяцев)
- Реальные интеграции: BoviSync, DeLaval, DC305 (ETL коннекторы)
- Native Android для cowside операций
- **Ollama + Qwen 2.5 14B** для self-hosted варианта (privacy для enterprise sales)
- ICAR conformance certification
- Первые пилоты на 2-3 фермах

### После Фазы 2 (Фаза 3, 12-18 месяцев)
- Hardware integrations (milking parlor, activity tags, feed mixers)
- Полный feature-parity с DelPro/DC305/AfiFarm
- Commercial certifications
- Dealer network в СНГ

## Имя AI в продукте

**"ИИ-помощник"** (не "Copilot", не "Ассистент", не "Claude") — выбранное имя для russian market. Везде в UI — только это.

## Язык — только русский

- Весь UI, все labels, все error messages — русский
- Пользовательские тексты AI — русский (**строго** в system prompts)
- Терминология: Insights → Инсайты, Farm Timeline → Лента событий, Copilot → Помощник
- Аббревиатуры оставляем английские где это отраслевой стандарт: SCC, DMI, THI, ECM, DIM, BCS, NPV
- date-fns с русской локалью `ru`

## Demo для инвестора — 15 минут

Акты (по 2-3 минуты каждый):
1. **Обзор** — утренний AI-брифинг
2. **Инсайты** — AI-triage с actionable recommendations
3. **Аналитика** — BI dashboard с 3 табами  
4. **Лента событий + Impact ★** — killer-фича, показывает влияние решений
5. **Помощник** — weekly briefing generation
6. **Мобильный PWA** — работа с телефона + responsive design

Плюс roadmap слайд: что добавится через 6 мес и 18 мес.

## Метрика успеха MVP

Не количество фич, а:
- Инвестор говорит "Я вижу, как это работает"
- Инвестор спрашивает "Когда можно подключить мою пилотную ферму?"
- Инвестор понимает differentiator vs DelPro/DC305/AfiFarm
- Инвестор запрашивает фоллоу-ап через 1-2 недели

Если эти 4 — demo работает. Остальное — техника.
