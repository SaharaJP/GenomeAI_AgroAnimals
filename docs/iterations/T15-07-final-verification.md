# T15-07 final verification

Единая точка приемки для ML-refactor:

```bash
bash scripts/verify_t15_07_ml_refactor.sh
```

С отдельной директорией под web smoke:

```bash
bash scripts/verify_t15_07_ml_refactor.sh /tmp/t15_07_web_smoke
```

Что проверяется:

- core train/score pipeline
- registry/model_card/scoring_summary resolvers
- downstream consumers: report, pack, regular_reports
- parity CLI vs mini-web job-runner vs Streamlit
- web train/score pages и advanced run forms
- `verify_refactor`
- `smoke_offline`
- `smoke_web`

Ожидаемый результат:

- pytest зелёный
- `VERIFY_REFACTOR_OK`
- `SMOKE_OK`
- `WEB_SMOKE_OK`
