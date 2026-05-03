# QC 2.0 (Target): каталог правил + severity + алерты

## Что это

QC v2 — YAML‑driven движок проверок качества данных.

Артефакты создаются в:

`artifacts/<data_version>/qc2/<qc_run>/...`

Выходные файлы:
- `qc_issues.csv` — **единый список** всех найденных проблем (по правилам)
- `alerts_auto.csv` — алерты, созданные автоматически из части QC‑проблем
- `qc_summary.json` — агрегаты по severity/доменам
- `manifest.json` — lineage + checksums

## Severity и политика блокировки

- **BLOCKER** → `qc_status=ERROR` (в downstream пайплайнах запрещён запуск расчётов/дашбордов)
- **MAJOR** → `qc_status=WARN`
- **MINOR** → `qc_status=WARN`
- если проблем нет → `qc_status=PASS`

## Алерты

Правила могут порождать алерты (см. `alert.create: true` в YAML).

Политика по умолчанию:
- алерт создаётся для **BLOCKER** и **MAJOR** (для MINOR — нет)

## Как запустить

```bash
genomeai qc2 --data-version <dv> --artifacts artifacts --rules configs/qc_rules_v2.yaml
```

## Как добавить правило

1) Добавьте запись в `configs/qc_rules_v2.yaml`
2) Укажите `id`, `domain`, `dataset`, `type`, `severity`, `message`, `remediation`
3) Если нужно: `alert.create: true` + `alert_type`

Поддерживаемые `type` см. в `src/genomeai/qc_v2.py`.
