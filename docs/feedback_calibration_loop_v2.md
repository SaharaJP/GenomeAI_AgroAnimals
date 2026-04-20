# T29-03 — feedback → calibration loop v2

## Что добавлено

В этой итерации feedback loop расширен с уровня "принял/отклонил рекомендацию" до audit-safe operational feedback слоя для:

- operational decisions в daily-use surfaces;
- assistant answers и embedded assistant panels;
- linkage к tasks / outcomes / versions / objects;
- экспорта readiness dataset для recalibration / retraining readiness.

Реальный retrain в рамках T29-03 **не выполняется**.

## Capture extensions

Каждый feedback event теперь может дополнительно нести `capture_v2` metadata:

- `context_kind`
- `feedback_kind` (`assistant_answer` / `operational_decision`)
- `override_applied`
- `override_target`
- `override_comment`
- `outcome_status`
- `outcome_reason_code`
- `linked_action`
- `source_versions`
- `action_observed_at`

Metadata сохраняется append-only внутри `feedback_events_v1.metadata_json`.

## Dataset / metrics v2

Новый v2-layer строится поверх existing feedback/task/outcome flows и добавляет в dataset:

- `feedback_context_kind`
- `feedback_kind`
- `override_applied`
- `override_target`
- `outcome_status`
- `outcome_reason_code`
- `outcome_known`
- `time_to_action_hours`
- `recalibration_ready_flag`
- `recalibration_ready_with_outcome_flag`
- `recalibration_readiness_level`
- `recalibration_readiness_issues`

Дополнительно экспортируется файл:

- `feedback_recalibration_readiness.csv`

## Откуда берётся outcome

Приоритет источников outcome:

1. `completion_outcomes_v1`
2. immediate capture из `capture_v2`
3. fallback из final task status / closed_reason

Так сохраняется linkage с существующими workflow/outcome flows без дублирования бизнес-логики.

## Feedback quality metrics

UI и export теперь показывают:

- assistant vs operational feedback total;
- override rate;
- outcome linked rate;
- median time-to-action;
- recalibration ready rate;
- ready-with-outcome rate;
- by feedback kind;
- by context kind;
- by outcome status;
- quality gaps breakdown.

## Surfaces

Capture extensions подключены к:

- `AI Assistant RAG`
- embedded assistant (`assistant_feedback_ux.py`)
- `Alert Center v2`
- `Animal Profile`
- `Feedback Loop` page

## Ограничения

- Это не retrain pipeline и не auto-calibration engine.
- Outcome capture в feedback form является optional observation layer; authoritative execution outcome по-прежнему живёт в existing task/outcome flow.
- В readiness dataset попадают только explainable rows с достаточным linkage к объектам и версиям.
