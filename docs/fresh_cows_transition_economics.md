# Fresh cows / transition economics

T27-04 вводит явный operational-economic слой по fresh cows / transition, не как отдельную вертикаль, а как связанный слой между vet / repro / milk quality workflows.

## Что делает слой
- выделяет cows в fresh/transition окне `0 <= DIM <= fresh_days`
- считает прозрачный `risk_score`
- показывает `workflow_lane` (`vet`, `repro`, `quality`, `monitor`)
- считает `expected_loss_rub`, `expected_gain_rub`, `cost_of_delay_per_day_rub`
- строит weekly monitoring по fresh weeks
- даёт action lists по животным и группам
- создаёт linked follow-up worklists через existing use-cases

## Прозрачность
Формулы и thresholds находятся в `configs/economics/fresh_cows_transition_economics_v1.yaml`.
Версия inputs хранится в `economics_inputs_version`.

## Что не делает
- не дублирует alerts/worklists engine
- не является отдельной LIMS/transition ERP
- не скрывает отсутствие данных по milk/SCC
- не делает auto-treatment / auto-cull actions
