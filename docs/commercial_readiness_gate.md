# Commercial readiness gate

T31-05 adds an **evidence-backed final readiness gate** for `product-ready`, `pilot-ready` and `commercially-ready`.

This surface is intentionally conservative:
- it does **not** substitute missing field evidence,
- it shows `partial` / `not_ready` when only starter or synthetic pilot evidence exists,
- it turns existing reports and configs into one explainable market-launch checklist.

## What the gate combines

- competitive acceptance / product parity evidence
- pilot framework and deployment tracking
- pilot adoption / ROI evidence
- support / SLA / incident readiness
- commercial packaging and edition model
- migration / upgrade discipline
- launch-supporting materials and evidence-pack structure

## Honest status model

- `product_ready` = product parity + packaging + migration + support readiness
- `pilot_ready` = enough governed tooling to **run** pilots without claiming completed field evidence
- `commercially_ready` = requires explicit reference deployment evidence and must stay blocked without it

## Market-launch checklist

The gate builds a reproducible checklist where every item has:
- status (`ready` / `partial` / `not_ready`)
- reason
- evidence path

## Evidence pack

The report also builds an evidence-pack manifest that points to real artifacts/configs/docs already present in the system.

## In-product surfaces

- `pages/78_Commercial_Readiness_Gate.py`
- `pages/37_Admin_Observability_Release.py`

## Smoke / regression

- `scripts/smoke_t31_05_commercial_readiness_gate.py`
- `scripts/run_commercial_readiness_gate_v1.sh`
- `tests/test_t31_05_commercial_readiness_gate.py`
