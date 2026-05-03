# T34-06 execution proof

Status: `partially_proven`

## Scope

Android real auth integration + runtime sync/session proof foundation.

## What was executed

### Static and shell checks

```bash
bash -n scripts/smoke_t34_06_android_auth_runtime.sh
python -m py_compile web_cabinet/auth_boundary_v1.py src/web_cabinet/auth_boundary_v1.py
```

Result: OK.

### Targeted T34-06 tests

```bash
pytest -q \
  tests/test_t34_06_android_auth_runtime_integration.py \
  tests/web/test_t34_06_mobile_runtime_proof_hook.py
```

Result: 4 passed.

### Auth regression

```bash
pytest -q \
  tests/web/test_t32_03_auth_boundary.py \
  tests/test_t34_02_auth_storage_foundation.py \
  tests/web/test_t34_02_auth_admin_diagnostics.py
```

Result: 6 passed.

## Proven now

- Android auth runtime files exist in repository.
- Login screen no longer contains local role picker.
- Android shell is wired to `AuthSessionManager` / `ServerAuthRepository` / `PreferencesSessionStore`.
- Server-side protected evidence hook `/api/app/v1/auth/mobile/runtime-proof` works for Android bearer session.
- Existing auth boundary regression remains green.

## Not yet proven

- Real Android build and emulator/device UAT.
- End-to-end protected mobile requests against full production workflow surface.
- Live offline sync replay proof from Android client on production-like contour.
