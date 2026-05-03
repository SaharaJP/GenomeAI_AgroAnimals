# T15-06 — Final verification helper

This iteration keeps behavior unchanged and adds a single helper entrypoint for replaying
all key T15-06 QC refactor checks from one command.

## Command

```bash
bash scripts/verify_t15_06_qc_refactor.sh
```

Optional web smoke output directory:

```bash
bash scripts/verify_t15_06_qc_refactor.sh /tmp/t15_06_web_check
```

## What it runs

1. Targeted pytest for legacy QC, QC2 engine, shared QC report/layout, QC2 path resolution,
   QC2 registration, pack determinism, Vet dashboard, Alerts/Tasks integration.
2. `python -m genomeai verify_refactor --project-root . --golden golden`
3. `bash scripts/smoke_offline.sh`
4. `bash scripts/smoke_web.sh <dir>`

## Purpose

Use this as the repeatable acceptance check for T15-06 before starting the next refactor task.
It is intentionally narrow and does not replace the broader full repository regression suite.
