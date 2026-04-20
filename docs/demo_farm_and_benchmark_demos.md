# T30-03 — Demo farm и benchmark demos

Что добавлено:
- Synthetic but realistic dataset `data/demo/demo_farm_v1` с явной маркировкой `synthetic=true` и manifest/README.
- Role-based demo scenarios для `Operator`, `Zootech`, `Vet`, `Director`, `Admin`.
- Covered demo flows: daily operator, reproduction, vet triage, reports + daily brief, economics delta, admin rollout/training, mobile/cowside, enterprise benchmark compare.
- Reproducible scripts:
  - `scripts/build_demo_farm_v1.py`
  - `scripts/smoke_t30_03_demo_farm.py`
  - `scripts/run_demo_farm_v1.sh`
- In-product reference page: `pages/71_Demo_Farm_And_Benchmark_Demos.py`.

Принципы:
- dataset synthetic but realistic и clearly marked;
- demo-only layer не меняет production logic;
- сценарии идут по реальным governed pages, а не по рисованным screen mocks;
- benchmark demos опираются на multi-farm / multi-site synthetic data.

Быстрый запуск:

```bash
PYTHONPATH=src:. python scripts/build_demo_farm_v1.py --output-dir data/demo/demo_farm_v1
PYTHONPATH=src:. python scripts/smoke_t30_03_demo_farm.py --dataset-dir data/demo/demo_farm_v1 --report-root artifacts/_ci/demo_farm_v1
```

Ожидаемые артефакты:
- `data/demo/demo_farm_v1/demo_farm_manifest.json`
- `artifacts/_ci/demo_farm_v1/demo_farm_report.json`
- `artifacts/_ci/demo_farm_v1/demo_farm_report.md`
- role markdown exports `artifacts/_ci/demo_farm_v1/demo_<role>.md`

Что показывать на демо:
- Operator: `Home -> Daily Worklists -> Mobile Worklists -> Animal Profile -> Cowside Event Entry`
- Zootech: `Reproduction Worklists -> Reproduction Cockpit -> Mating Plan -> Enterprise Benchmark Views`
- Vet: `Alert Center -> Animal Profile -> Mobile Worklists`
- Director: `Home / Daily Brief -> Report View -> Economics per action -> Enterprise Benchmark Views`
- Admin: `Admin Observability -> Training by role -> Admin Console`

Диагностика:
- если сценарий не открывается — проверить роль и `configs/ui/ia_v3.yaml`;
- если benchmark пустой — проверить `data/demo/demo_farm_v1/dm_alerts.csv`, `dm_sites.csv`, `dm_animals.csv`;
- если smoke падает — сначала проверить `demo_farm_manifest.json` и relation validation через `validate_target_v2_relations`.
