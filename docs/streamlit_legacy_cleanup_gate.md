# Streamlit legacy cleanup gate

T32-12A добавляет **formal no-tail gate** после удаления Streamlit.

Цель gate: доказуемо подтвердить, что Streamlit-контур выведен из активного продукта и deployment,
а оставшиеся упоминания живут только в **исторических / evidence** артефактах.

## Что проверяет gate

1. **Absence paths**
   - `streamlit_app/`
   - `.streamlit/`
   - `scripts/run_streamlit.sh`

2. **Dependency / deployment files**
   - нет `streamlit` в `pyproject.toml`
   - нет streamlit reference в активных deploy/Docker files

3. **Runtime imports**
   - нет `import streamlit`
   - нет `from streamlit`
   - нет активных runtime references на `streamlit_app`

4. **Operational tails**
   - README / deploy / configs / scripts / active product surfaces не должны содержать Streamlit tails
   - исторические упоминания разрешены только через explicit allowlist из manifest

## Почему это не просто grep

Gate проверяет несколько классов сигналов одновременно:

- отсутствие legacy paths
- отсутствие dependency tails
- отсутствие runtime imports
- отсутствие disallowed operational references
- explicit allowlist для исторических/evidence paths

То есть само наличие слова `Streamlit` где-то в историческом документе не валит gate,
но любой скрытый operational hook в активном контуре валит.

## Источник истины

- Manifest: `configs/post_removal/streamlit_legacy_cleanup_manifest_v1.json`
- Report: `configs/post_removal/streamlit_legacy_cleanup_report_v1.json`
- Validator: `scripts/validate_t32_12a_streamlit_legacy_cleanup.py`

## Локальный запуск

```bash
python scripts/validate_t32_12a_streamlit_legacy_cleanup.py
bash scripts/smoke_t32_12a_streamlit_legacy_cleanup.sh
```

## Ожидаемый статус

`streamlit_contour_fully_removed = true`

Это означает:

- Streamlit больше не является частью активного продукта
- deployment contour не зависит от Streamlit
- active config/docs/scripts/routes/pages не содержат скрытых tails
- historical references контролируются allowlist'ом и не считаются активными operational hooks
