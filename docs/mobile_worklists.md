# T25-02 — Mobile worklists

## Что сделано

Исторический шаг T25-02 описывал mobile-first cowside surface до появления отдельного Android-приложения. Актуальный mobile contour теперь находится в `mobile_android/` и использует те же backend/use-case принципы без дублирования workflow logic.

Поддержаны:
- `vet / repro / group rounds`
- fast actions: `open object`, `done`, `+1 day postpone`, `comment`
- compact cards вместо raw-table default UX
- linked facts, due bucket, confidence, object context и last comment

## Принципы

- Актуальный mobile contour — отдельное Android-приложение; этот документ сохранён как историческая заметка.
- Никакого raw query execution и никакого offline queue.
- Все действия идут только через существующие use-cases:
  - `close_worklist_use_case`
  - `postpone_worklist_use_case`
  - `append_worklist_comment_use_case`
- Desktop daily worklists остаётся richer surface для advanced execution.

## Fast mobile rounds

### Vet rounds
Показывают `vet`, `health_follow_up`, `milk_quality` и health-related work items.

### Repro rounds
Показывают `reproduction` и близкие repro due actions.

### Group rounds
Показывают group/pen/site-linked items и movement/group-centric execution.

## Comment trail

Комментарий в mobile worklists не подменяет outcome comment.
Он записывается в comment trail внутри `attachments` worklist-а как bounded comment entry и журналируется через audit action `worklist.comment`.

## Acceptance

Field user может:
- быстро отфильтровать нужный round;
- увидеть why/due/object context без desktop перегруза;
- выполнить `done` / `postpone` / `comment` / `open object` с телефона;
- не потерять linked facts и безопасность текущей session/auth модели.
