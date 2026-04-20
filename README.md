# GenomeAI AgroAnimals

Текущая продуктовая архитектура после T32-12:

- `src/core/` — canonical domain/application/infra/use-cases
- `src/genomeai/` — backward-compatible CLI/legacy facade/shim surface
- `web_cabinet/` — internal admin/support/debug surface поверх backend API
- `apps/api/` — production API ownership surface
- `apps/web/` — ownership placeholder для web product contour
- `web_app/` — React/Next.js target web frontend
- `apps/android/` — ownership placeholder для Android contour
- `mobile_android/` — отдельное Android-приложение для field/cowside сценариев
- `packages/contracts/` — shared contracts между backend/web/mobile

Публичные интерфейсы (CLI/API/страницы/ключевые функции) зафиксированы в `docs/public_interfaces.{md,json}`.
PR-гейты и локальное воспроизведение CI описаны в `docs/ci_gates.md`.

## Quickstart

```bash
pip install -e .
python -m genomeai.app_launcher --open-browser
```

Для быстрой проверки offline-core по-прежнему доступны:

```bash
genomeai validate --input data/examples
genomeai init-run
pytest -q tests/test_a6_smoke.py
```

## Проектная карта

- Актуальная карта проекта и shim-слоёв: `docs/project_map.md`
- Новая целевая архитектура: `docs/target_architecture_web_android_backend.md` (дополнительно: `docs/architecture/target_architecture_v2.md`)
- Repo ownership map: `docs/repo_ownership_map.md`
- Server runtime target: `docs/architecture/server_runtime_target.md`
- Production security / IAM / secrets / network baseline: `docs/production_security_and_iam_baseline.md`
- Server deployment baseline: `docs/server_deployment_baseline.md`
- Android field app foundation: `docs/android_field_app_foundation.md`
- Android offline/sync model: `docs/android_offline_sync_model.md`
- Legacy cleanup verification gate: `docs/streamlit_legacy_cleanup_gate.md`
- Post-removal cleanup / regression report: `docs/streamlit_removal_and_cleanup.md`
- Public interfaces: `docs/public_interfaces.md`
- CI gates and local verification: `docs/ci_gates.md`
- Golden verification / refactor safety: `golden/README.md`

## Single-entry запуск (рекомендуется)

```bash
python -m genomeai.app_launcher --open-browser
bash scripts/run_single_entry_local.sh
```

Что поднимется:
- React web frontend (`http://127.0.0.1:3000` по умолчанию, либо `GENOMEAI_WEB_PUBLIC_URL`) — основной пользовательский вход
- FastAPI backend (`http://127.0.0.1:8000`) — backend/fallback internal admin-debug surface

Демо-учётки: `admin/admin`, `operator/operator`, `viewer/viewer`, `director/director`, `zootech/zootech`, `vet/vet`.

## Базовые команды

```bash
# Offline-core smoke
genomeai smoke

# Synthetic demo farm / benchmark demos
bash scripts/run_demo_farm_v1.sh

# Legacy web fallback smoke (оставлен рядом для parity/compat)
python -m web_cabinet.smoke --workdir _tmp/local_web_smoke --clean

# Golden verification
genomeai verify_refactor
```

## Fallback / internal backend surface

```bash
# Backend fallback only (support/debug/admin surface)
uvicorn web_cabinet.app:app --host 0.0.0.0 --port 8000
```

## CI / PR gates

Pull request не должен проходить без пяти проверок:

1. `bash scripts/run_ci_gate.sh`
2. `python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean --timing-json artifacts/_ci/web_smoke.json | tee artifacts/_ci/web_smoke.log`
3. `python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root artifacts/_ci/verify_refactor | tee artifacts/_ci/verify_refactor.log`
4. `bash scripts/run_warning_governance_gate.sh`
5. `bash scripts/run_perf_gates.sh`

При падении CI сохраняет pytest/junit, smoke-логи, warning governance report, perf diagnostics и Golden diff-артефакты.


## Deployment / operations docs

- `docs/deployment_full_guide.md` — подробная production-oriented инструкция по развёртыванию всей системы.
- `docs/ui_functional_verification_web.md` — подробный web UI verification manual по ролям и сценариям.
- `docs/ui_functional_verification_android.md` — подробный Android UI verification manual для field/cowside flows.
- `docs/full_uat_checklist.md` — сводный UAT checklist для web + Android.
- `docs/operations_runbook.md` — install / upgrade / rollback / incident / support runbook.
