# T29-01 — Embedded operational assistant

## Что сделано

Вместо отдельной chat-оболочки assistant встроен прямо в daily-use surfaces:
- `home_v3`
- `Alert Center v2`
- `Animal Profile`
- `Group Profile`
- `Report View`
- `Daily Worklists By Role`
- `Operational Planner`

Во всех этих точках используется существующий contextual assistant backend и прежние guardrails:
- `fact-pack only`
- source-linked citations
- append-only audit/logging
- `use_llm=False` для contextual operational flows

## Что добавлено в T29-01

### 1) Embedded entry points

В `assistant_feedback_ux.py` расширены contextual prompt families:
- `worklist`
- `planner_item`

Теперь assistant отвечает не только в summary/profile/report contexts, но и прямо в executor/triage workflows.

### 2) Linked actions from assistant answers

После ответа assistant показывает `Linked actions / Следующее действие по ответу`.

Это не “магические” авто-действия, а явные operational links:
- открыть linked object
- перейти в `Daily Worklists`
- перейти в `Operational Planner`
- открыть `Alert Center`
- открыть `Economics Per Action`
- открыть `Operational What-If`
- открыть `Report Builder`
- сохранить append-only `assistant.triage.note` в `Decision Log`

### 3) Linkage preservation

Каждый embedded answer сохраняет явную linkage summary:
- `context_kind`
- `object_type / object_id`
- `related_alert`
- `worklist_id / task_id`
- `data_version`
- `qc_run`
- `model_version`
- `scoring_run`
- `report_version`

Это видно в UI и используется при linked action logging.

### 4) Safe write action

Единственный встроенный write action в этой итерации — append-only `assistant.triage.note`.

Он:
- не ломает task/worklist backend
- не обходит workflow approvals
- пишет `Decision Log` с metadata по assistant answer
- попадает в audit как `assistant.contextual.linked_action`

## Как это работает по страницам

### Daily Worklists

Assistant встроен в detail area выбранного worklist.

Цель:
- объяснить, почему worklist сейчас в очереди;
- предложить next step / handover / execution note;
- сразу перевести пользователя к object/economics/what-if/action surfaces.

### Operational Planner

Assistant встроен в detail area planner item.

Цель:
- объяснить bucket / urgency;
- показать next step по team/shift/executor logic;
- быстро перевести пользователя в worklists/tasks/object profile.

### Alerts / Profiles / Reports / Home

Эти surfaces уже имели contextual assistant panel, но теперь он остаётся частью единой embedded operational модели и использует те же linked actions / linkage patterns.

## Принципы безопасности и explainability

1. Ответ не живёт отдельно от operational page.
2. Ответ не может перейти в hallucination mode: only fact-pack + linked citations.
3. Все linked actions явные и audit-traceable.
4. Assistant не заменяет основную UI-логику страницы, а ускоряет triage/execution.
5. Assistant не создаёт скрытых side effects.

## Ограничения текущей итерации

- Это не conversational agent shell и не agentic automation.
- Embedded assistant не auto-creates tasks/worklists behind the scenes.
- Write path ограничен append-only `assistant.triage.note`.
- Operational actions в основном ведут пользователя в уже существующие action surfaces.

## Acceptance rationale

T29-01 считается закрытым, если:
- assistant встроен в worklists/alerts/profiles/reports/home;
- ответы остаются source-linked и fact-pack only;
- есть прямые linked actions из ответа;
- linkage по версиям и объектам сохраняется;
- продукт не превращается в chat-first shell.
