# Streamlit removal and cleanup

## Что сделано

- Legacy product UI `streamlit_app/` полностью удалён.
- Streamlit-specific scripts, tests, docs and dependency tails removed from active product/deployment contour.
- Final product architecture is now: `web_app` + `mobile_android` + `backend API` + `workers` + `scheduler`.
- `web_cabinet` remains only as internal admin/support/debug surface.

## Formal cutover basis

Removal was executed only after repo-level cutover evidence reached readiness and an explicit approval artifact was recorded during T32-12. The approval basis is the coordinator-requested final cutover plus green checked-in parity and coexistence/rollback evidence.

## What was removed

- `streamlit_app/`
- Streamlit-only routing/shell/smoke/docs/tests
- Streamlit dependency from `pyproject.toml`
- Streamlit primary-entry assumptions in launcher/deploy/runtime docs

## Post-removal regression-ready state

The repository is considered post-removal regression-ready when all of the following remain true:

- `web_app/` is the only product web UI
- `mobile_android/` is the only mobile field app baseline
- backend/deployment/security baselines remain green
- no runtime code imports `streamlit_app`
- no deployment manifest starts a Streamlit service

## Evidence

See `configs/post_removal/streamlit_removal_regression_report_v1.json`.
