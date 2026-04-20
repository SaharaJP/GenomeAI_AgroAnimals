# Replacement narratives and win themes

T30-05 фиксирует **product-backed narratives для замены legacy herd-management systems** без маркетинговых преувеличений.

## Что входит

- **Win themes**: daily operations parity, explainable AI, QC/governance, economics/explainable action guidance, migration safety.
- **Compare checklists** для `pre-sales`, `UAT`, `implementation`.
- **Feature maps**: parity-map и win-map.
- **Proof points**: каждый тезис привязан к реальным страницам, документации, тестам, smoke scripts, acceptance scenarios и demo scenarios.

## Источник правды

Материалы собираются из:

- `configs/product/replacement_narratives_v1.yaml`
- `configs/product/commercial_packaging_v1.yaml`
- `configs/ops/competitive_acceptance_set_v1.yaml`
- `configs/ui/demo_farm_scenarios_v1.yaml`
- `configs/ui/ia_v3.yaml`

Это означает, что narrative не живёт отдельно от продукта: если страница, smoke, acceptance scenario или demo scenario исчезают, proof point должен упасть на валидации.

## Главные темы

### 1. Daily operations parity

Подтверждается реальными governed surfaces:

- daily worklists
- operational planner
- animal/group profile
- mobile worklists
- cowside entry

Это не claim про полную ERP или HR/scheduling replacement.

### 2. Explainable AI under governance

Подтверждается через:

- embedded assistant в workflow
- explainability by object
- governed daily brief

Это не freeform AI shell и не hidden auto-decision mode.

### 3. QC и governance

Подтверждается через:

- operational rollout gates
- bounded external collaboration
- competitive acceptance set

Это не ad hoc permissions и не неподтверждённые quality claims.

### 4. Economics и explainable action guidance

Подтверждается через:

- economics per action
- feedback → recalibration readiness

Это не optimizer, который решает за пользователя.

### 5. Migration safety

Подтверждается через:

- migration verification toolkit
- parallel run mode
- migration playbook
- competitive acceptance evidence
- runnable demo farm/benchmark demos

Это не big-bang cutover promise без verification evidence.

## In-product surface

Добавлена страница:

- `pages/73_Replacement_Narratives_And_Win_Themes.py`

Она показывает:

- win themes
- compare checklists
- feature maps
- proof points
- source-linked page jumps
- JSON / Markdown export

## Проверка

```bash
PYTHONPATH=src:. pytest -q tests/test_t30_05_replacement_narratives_and_win_themes.py
```

## Для чего это полезно

Эта итерация даёт команде формальный язык для replacement conversations:

- что уже заменяется по parity,
- где продукт выигрывает,
- что **не** заявляется,
- на какие реальные product surfaces и regression evidence можно ссылаться.
