# Commercial packaging and editions

T30-04 фиксирует **edition/feature model** и связывает packaging с **config gates**, а не только с текстом для продаж.

## Что добавлено

- единая конфигурация editions/modules/features: `configs/product/commercial_packaging_v1.yaml`
- runtime resolution через `GENOMEAI_COMMERCIAL_PROFILE`, `GENOMEAI_EDITION`, `GENOMEAI_ENABLED_MODULES`
- shell/nav filtering по `features/modules`, а не только по role/RBAC
- admin/director page: `pages/72_Commercial_Packaging_And_Editions.py`
- JSON/Markdown export packaging summary

## Edition model

### Foundation
- базовая поставка для governed daily operations
- включает core operational surfaces, reports/governance и onboarding
- optional modules: reproduction, vet, economics, embedded AI, mobile, demo/training

### Professional
- Foundation + operational intelligence
- включает reproduction, vet, economics, embedded assistant, explainability, decision intelligence
- optional modules: mobile, demo/training, genomics

### Enterprise
- Professional + enterprise capabilities
- включает multi-site enterprise ops, migration replacement, external collaboration, rollout diagnostics, competitive acceptance
- optional modules: mobile, demo/training, genomics

## Почему это не только текст для продаж

Packaging привязан к реальным technical flags/configs:

- modules → feature sets
- features/modules → shell/nav visibility
- runtime profiles → deploy configuration
- page access для gated surfaces блокируется централизованно через active edition/module configuration

## Что считается implementation scope

Базовая единица лицензирования: `site`.
Базовая единица внедрения: `site_wave`.

Это позволяет отделить:
- базовую поставку
- optional modules
- enterprise capabilities
- implementation scope

## Где смотреть в продукте

- `pages/72_Commercial_Packaging_And_Editions.py`
- sidebar/runtime shell показывает активную `edition` и `profile`

## Как проверить

```bash
PYTHONPATH=src:. pytest -q tests/test_t30_04_commercial_packaging_and_editions.py tests/test_t10_01_streamlit_pages_compile.py
```

## Ограничения

- В этой итерации packaging model не пишет лицензии в БД и не делает billing.
- Цель шага — зафиксировать понятный edition/module contract и config gates для лицензирования и внедрения.
