# T10-03 — Step 6: RBAC для подтверждения рекомендаций + тестируемый таймлайн + audit smoke

## Что сделано
1) **Confirm recommendation** (Alert Center v2 + Animal Profile) теперь разрешён для ролей, у которых есть хотя бы одно из:
   - `recommendations.confirm`
   - `decisions.write`
   - `decisionlog.write`
   Это важно, т.к. Director в Target может подтверждать рекомендации, но не всегда имеет полный `decisionlog.write`.

2) Компонент `timeline_v1` дополнен функцией `build_timeline_df(...)` (Streamlit-free), чтобы:
   - гарантировать, что таймлайн = **только нормализация фактов + overlay задач/решений**
   - иметь **unit-тесты** (без запуска Streamlit)

3) Добавлены тесты:
   - запись действий через `streamlit_app.common.audit_action()` в `audit_log`
   - корректность сборки таймлайна (fact + task + decision)
   - smoke-проверка, что RBAC-условия присутствуют в UI (статический тест)

## Как проверять
```bash
pytest -q tests/test_t10_03_streamlit_audit_action.py \
  tests/test_t10_03_timeline_build_df.py \
  tests/test_t10_03_streamlit_rbac_actions.py
```

## Примечания
- Таймлайн не рассчитывает KPI/ML и не изменяет артефакты — только отображение.
- Audit в Streamlit остаётся **best-effort**: UI не падает, если запись в audit log не удалась.
